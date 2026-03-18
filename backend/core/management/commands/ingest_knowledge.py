"""
Management command: ingest_knowledge

Builds (or rebuilds) the FAISS vector index from the financial knowledge base
and saves it to data/faiss_index/.

Usage
-----
  python manage.py ingest_knowledge              # build index
  python manage.py ingest_knowledge --stats      # show chunk stats only, no write
  python manage.py ingest_knowledge --rebuild    # force rebuild even if index exists

Output
------
  Prints a progress table showing each document, the number of chunks produced,
  and the average/min/max word counts.  On success, prints the index path and
  total vector count.

Requirements
------------
  pip install faiss-cpu sentence-transformers numpy
"""

import time

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Build the FAISS vector index from the financial knowledge base."

    def add_arguments(self, parser):
        parser.add_argument(
            "--stats",
            action="store_true",
            help="Print chunk statistics only — do not write the index.",
        )
        parser.add_argument(
            "--rebuild",
            action="store_true",
            help="Force rebuild even if an index already exists.",
        )

    def handle(self, *args, **options):
        stats_only = options["stats"]
        force_rebuild = options["rebuild"]

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Financial Knowledge Ingestion ===\n"))

        # ── Import and validate dependencies ──────────────────────────────────
        self.stdout.write("Checking dependencies…")
        try:
            import faiss  # noqa: F401
            self.stdout.write(f"  ✓ faiss-cpu (version: {faiss.__version__})")
        except ImportError:
            raise CommandError(
                "faiss-cpu is not installed.\n"
                "Run: pip install faiss-cpu"
            )

        try:
            from sentence_transformers import SentenceTransformer  # noqa: F401
            self.stdout.write("  ✓ sentence-transformers")
        except ImportError:
            raise CommandError(
                "sentence-transformers is not installed.\n"
                "Run: pip install sentence-transformers"
            )

        try:
            import numpy  # noqa: F401
            self.stdout.write(f"  ✓ numpy (version: {numpy.__version__})")
        except ImportError:
            raise CommandError("numpy is not installed.\nRun: pip install numpy")

        # ── Load knowledge base and chunk ─────────────────────────────────────
        self.stdout.write("")
        self.stdout.write("Loading knowledge base…")

        from core.services.knowledge_base import get_all_chunks, list_sources
        from core.services.vector_store import INDEX_PATH, get_vector_store

        sources = list_sources()
        self.stdout.write(f"  Documents: {len(sources)}")
        for s in sources:
            self.stdout.write(f"    • {s}")

        self.stdout.write("")
        self.stdout.write("Chunking documents…")
        all_chunks = get_all_chunks()

        # ── Per-source stats ──────────────────────────────────────────────────
        source_stats: dict[str, list[int]] = {}
        for chunk in all_chunks:
            source_stats.setdefault(chunk["source"], []).append(chunk["word_count"])

        self.stdout.write("")
        self.stdout.write(
            f"{'Source':<42} {'Chunks':>6}  {'Avg wds':>7}  {'Min':>5}  {'Max':>5}"
        )
        self.stdout.write("─" * 70)
        for source, wcs in source_stats.items():
            self.stdout.write(
                f"  {source:<40} {len(wcs):>6}  "
                f"{sum(wcs)/len(wcs):>7.0f}  "
                f"{min(wcs):>5}  {max(wcs):>5}"
            )
        self.stdout.write("─" * 70)
        self.stdout.write(
            f"  {'TOTAL':<40} {len(all_chunks):>6}  "
            f"{sum(c['word_count'] for c in all_chunks)/len(all_chunks):>7.0f}"
        )
        self.stdout.write("")

        if stats_only:
            self.stdout.write(self.style.SUCCESS("Stats-only mode — index not written."))
            return

        # ── Check existing index ──────────────────────────────────────────────
        if INDEX_PATH.exists() and not force_rebuild:
            self.stdout.write(
                self.style.WARNING(
                    f"Index already exists at {INDEX_PATH}\n"
                    "Use --rebuild to overwrite it."
                )
            )
            return

        # ── Build index ───────────────────────────────────────────────────────
        self.stdout.write("Building FAISS index (this may take 30–120 s on first run)…")
        self.stdout.write("  Loading embedding model 'all-MiniLM-L6-v2'…")
        self.stdout.write(
            "  (First run downloads ~90 MB. Subsequent runs use the cached model.)"
        )
        self.stdout.write("")

        store = get_vector_store()
        t0 = time.monotonic()

        try:
            store.build_index(all_chunks)
        except Exception as exc:
            raise CommandError(f"Index build failed: {exc}") from exc

        elapsed = time.monotonic() - t0

        # ── Summary ───────────────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("✓ Index built successfully"))
        self.stdout.write(f"  Vectors stored : {len(all_chunks)}")
        self.stdout.write(f"  Index path     : {INDEX_PATH}")
        self.stdout.write(f"  Chunks path    : {INDEX_PATH.parent / 'chunks.json'}")
        self.stdout.write(f"  Build time     : {elapsed:.1f}s")
        self.stdout.write("")
        self.stdout.write(
            "The RAG assistant will now use this index for knowledge retrieval.\n"
            "To verify: GET /api/ai/health/ should return {\"rag_index_ready\": true}"
        )
