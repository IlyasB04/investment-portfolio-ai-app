"""
Management command: ingest_approved_sources

Rebuilds the FAISS vector index from two source pools:
  1. Built-in knowledge base  (core/services/knowledge_base.py — always included)
  2. Local .txt files          (data/approved_sources/*.txt   — optional enrichment)

The command automatically matches local files to registry entries via
ApprovedSource.local_path so citation metadata is preserved.

Usage
-----
    python manage.py ingest_approved_sources
    python manage.py ingest_approved_sources --local-only   # skip built-in chunks
    python manage.py ingest_approved_sources --stats        # show per-source breakdown
    python manage.py ingest_approved_sources --list         # list registry entries only
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Rebuild the FAISS index from the approved source registry and local .txt files."

    # ── Project root detection ─────────────────────────────────────────────────
    # manage.py lives in backend/; data/ is at backend/data/
    _BASE_DIR = Path(__file__).resolve().parents[4]   # portfolio_ai_app/
    _LOCAL_SOURCES_DIR = _BASE_DIR / "data" / "approved_sources"
    _INDEX_DIR         = _BASE_DIR / "data" / "faiss_index"

    def add_arguments(self, parser):
        parser.add_argument(
            "--stats",
            action  = "store_true",
            default = False,
            help    = "Print per-source chunk statistics after ingestion.",
        )
        parser.add_argument(
            "--list",
            action  = "store_true",
            default = False,
            help    = "List all registry entries without rebuilding the index.",
        )
        parser.add_argument(
            "--local-only",
            action  = "store_true",
            default = False,
            dest    = "local_only",
            help    = "Only ingest local .txt files; skip built-in knowledge base.",
        )

    def handle(self, *args, **options):
        # ── Dependency check ──────────────────────────────────────────────────
        try:
            import faiss  # noqa: F401
            from sentence_transformers import SentenceTransformer  # noqa: F401
            import numpy  # noqa: F401
        except ImportError as exc:
            raise CommandError(
                f"Missing dependency: {exc}\n"
                "Install with: pip install faiss-cpu sentence-transformers numpy"
            ) from exc

        from core.services.source_registry import all_sources, get_source
        from core.services.knowledge_base  import get_all_chunks, _chunk_text
        from core.services.vector_store    import get_vector_store

        registry = all_sources()

        # ── --list mode ───────────────────────────────────────────────────────
        if options["list"]:
            self.stdout.write(self.style.SUCCESS(
                f"\n{'SOURCE KEY':<35} {'CITATION':<25} {'TIER':<6} {'LOCAL FILE'}"
            ))
            self.stdout.write("─" * 100)
            for src in registry:
                local_exists = (self._LOCAL_SOURCES_DIR / src.local_path).exists() \
                               if src.local_path else False
                indicator = "✓" if local_exists else ("—" if not src.local_path else "✗ missing")
                self.stdout.write(
                    f"{src.source_key:<35} {src.citation_label:<25} {src.trust_tier:<6} "
                    f"{src.local_path or '(none)'} [{indicator}]"
                )
            return

        # ── Collect chunks ─────────────────────────────────────────────────────
        all_chunks: list[dict] = []

        # 1. Built-in knowledge base
        if not options["local_only"]:
            builtin_chunks = get_all_chunks()
            all_chunks.extend(builtin_chunks)
            self.stdout.write(
                f"  Built-in knowledge base: {len(builtin_chunks)} chunks"
            )

        # 2. Local .txt files
        local_chunk_count = 0
        if self._LOCAL_SOURCES_DIR.exists():
            txt_files = sorted(self._LOCAL_SOURCES_DIR.glob("*.txt"))
            if txt_files:
                self.stdout.write(
                    f"  Local sources dir: {self._LOCAL_SOURCES_DIR}"
                )
                for txt_path in txt_files:
                    # Try to match to a registry entry by local_path
                    matched_src = next(
                        (s for s in registry if s.local_path == txt_path.name), None
                    )
                    source_label = matched_src.source_key if matched_src else txt_path.stem

                    try:
                        text = txt_path.read_text(encoding="utf-8").strip()
                    except Exception as exc:
                        self.stderr.write(f"  [SKIP] {txt_path.name}: {exc}")
                        continue

                    if not text:
                        self.stderr.write(f"  [SKIP] {txt_path.name}: empty file")
                        continue

                    new_chunks = _chunk_text(text, chunk_words=250, overlap_words=50)
                    for i, chunk_text in enumerate(new_chunks):
                        chunk_id = f"{source_label}_local_{i}"
                        # Avoid duplicating a chunk that already came from knowledge_base.py
                        existing_ids = {c.get("chunk_id", "") for c in all_chunks}
                        if chunk_id not in existing_ids:
                            all_chunks.append({
                                "chunk_id":   chunk_id,
                                "source":     source_label,
                                "text":       chunk_text,
                                "word_count": len(chunk_text.split()),
                            })
                            local_chunk_count += 1

                    self.stdout.write(
                        f"    {txt_path.name:<40} → {len(new_chunks)} chunks"
                        f"  ({matched_src.citation_label if matched_src else 'unregistered'})"
                    )
            else:
                self.stdout.write(
                    f"  No local .txt files found in {self._LOCAL_SOURCES_DIR}"
                )
        else:
            self.stdout.write(
                f"  Local sources dir not found ({self._LOCAL_SOURCES_DIR}) — skipping."
            )

        if not all_chunks:
            raise CommandError("No chunks collected — nothing to ingest.")

        self.stdout.write(
            f"\n  Total chunks to ingest: {len(all_chunks)} "
            f"(built-in + {local_chunk_count} local)"
        )

        # ── Build FAISS index ─────────────────────────────────────────────────
        self.stdout.write("\nBuilding FAISS index…")
        t0 = time.time()

        vs = get_vector_store()
        vs.build_index(all_chunks)

        elapsed = time.time() - t0
        self.stdout.write(
            self.style.SUCCESS(
                f"  Index built in {elapsed:.1f}s — {len(all_chunks)} chunks indexed."
            )
        )

        # ── Save index + chunks to disk ───────────────────────────────────────
        try:
            self._INDEX_DIR.mkdir(parents=True, exist_ok=True)
            import faiss
            import numpy as np

            faiss.write_index(vs._index, str(self._INDEX_DIR / "index.faiss"))
            with open(self._INDEX_DIR / "chunks.json", "w", encoding="utf-8") as fh:
                json.dump(vs._chunks, fh, ensure_ascii=False, indent=2)

            self.stdout.write(
                self.style.SUCCESS(
                    f"  Saved to {self._INDEX_DIR}"
                )
            )
        except Exception as exc:
            self.stderr.write(f"  [WARNING] Could not persist index to disk: {exc}")

        # ── Stats ─────────────────────────────────────────────────────────────
        if options["stats"]:
            from collections import Counter
            source_counts = Counter(c["source"] for c in all_chunks)

            self.stdout.write(f"\n{'SOURCE':<40} {'CHUNKS':>6}")
            self.stdout.write("─" * 50)
            for src_key, count in sorted(source_counts.items()):
                src = get_source(src_key)
                label = src.citation_label if src else src_key
                self.stdout.write(f"  {label:<38} {count:>6}")

            avg_words = sum(c.get("word_count", 0) for c in all_chunks) / len(all_chunks)
            self.stdout.write(f"\n  Average chunk size: {avg_words:.0f} words")
            self.stdout.write(f"  Index ready: {vs.is_ready()}")
