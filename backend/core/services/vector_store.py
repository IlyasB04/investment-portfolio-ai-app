"""
FAISS-based financial knowledge vector store.

Architecture
------------
  FinancialVectorStore manages:
    • Embedding generation via sentence-transformers (all-MiniLM-L6-v2, 384-dim)
    • FAISS IndexFlatIP over L2-normalised vectors (= cosine similarity search)
    • Chunk metadata persisted alongside the index as JSON
    • Lazy loading — the index is only read from disk on first retrieval

On-disk layout
--------------
  {INDEX_DIR}/index.faiss     FAISS binary index
  {INDEX_DIR}/chunks.json     [{id, text, source, word_count}, ...]

Retrieval returns
-----------------
  [{"text": ..., "source": ..., "score": 0.0–1.0, "chunk_id": n}, ...]

Confidence threshold
--------------------
  Chunks with cosine score < CONFIDENCE_THRESHOLD (0.25) are filtered out.
  If no chunks pass the threshold the caller receives an empty list — the
  RAG orchestrator then falls back to portfolio analytics only.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

_BASE_DIR = Path(__file__).resolve().parents[3]   # → backend/
INDEX_DIR = _BASE_DIR / "data" / "faiss_index"
INDEX_PATH = INDEX_DIR / "index.faiss"
CHUNKS_PATH = INDEX_DIR / "chunks.json"

EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # 384-dim, ~22 MB, runs on CPU
TOP_K_DEFAULT = 5
CONFIDENCE_THRESHOLD = 0.25            # min cosine similarity to include a chunk


# ── Lazy dependency imports ────────────────────────────────────────────────────

def _require_faiss():
    try:
        import faiss
        return faiss
    except ImportError:
        raise ImportError(
            "faiss-cpu is not installed. Run: pip install faiss-cpu"
        )


def _require_st():
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer
    except ImportError:
        raise ImportError(
            "sentence-transformers is not installed. "
            "Run: pip install sentence-transformers"
        )


# ── Singleton vector store ─────────────────────────────────────────────────────

class FinancialVectorStore:
    """
    Thread-safe FAISS vector store for financial knowledge retrieval.

    Usage
    -----
      store = get_vector_store()          # singleton accessor
      results = store.retrieve("What is diversification?", top_k=4)
    """

    def __init__(self, index_dir: Path = INDEX_DIR):
        self._index_dir = index_dir
        self._index = None          # faiss.Index — loaded lazily
        self._chunks: list[dict] = []
        self._model = None          # SentenceTransformer — loaded lazily
        self._lock = threading.RLock()
        self._loaded = False

    # ── Model ──────────────────────────────────────────────────────────────────

    def _get_model(self):
        if self._model is None:
            SentenceTransformer = _require_st()
            logger.info("[vector_store] Loading embedding model '%s'…", EMBEDDING_MODEL)
            self._model = SentenceTransformer(EMBEDDING_MODEL)
            logger.info("[vector_store] Embedding model loaded.")
        return self._model

    def _embed(self, texts: list[str]) -> np.ndarray:
        """Return L2-normalised float32 embedding matrix, shape (n, dim)."""
        model = self._get_model()
        vecs = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        vecs = vecs.astype(np.float32)
        # L2 normalise so inner-product search == cosine similarity
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)  # avoid div-by-zero
        return vecs / norms

    # ── Build ──────────────────────────────────────────────────────────────────

    def build_index(self, chunks: list[dict]) -> None:
        """
        Embed `chunks` and persist a new FAISS index.

        Each chunk must be a dict with at least {"text": str, "source": str}.
        chunk_id is assigned sequentially during ingestion.

        Saves:
          {INDEX_DIR}/index.faiss
          {INDEX_DIR}/chunks.json
        """
        faiss = _require_faiss()

        if not chunks:
            raise ValueError("chunks list is empty — nothing to index")

        self._index_dir.mkdir(parents=True, exist_ok=True)

        texts = [c["text"] for c in chunks]
        logger.info("[vector_store] Embedding %d chunks…", len(texts))
        embeddings = self._embed(texts)

        dim = embeddings.shape[1]
        logger.info("[vector_store] Building IndexFlatIP (dim=%d)…", dim)
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings)

        # Persist
        faiss.write_index(index, str(INDEX_PATH))
        annotated = [
            {**c, "chunk_id": i, "word_count": len(c["text"].split())}
            for i, c in enumerate(chunks)
        ]
        CHUNKS_PATH.write_text(json.dumps(annotated, indent=2), encoding="utf-8")

        # Update in-memory state
        with self._lock:
            self._index = index
            self._chunks = annotated
            self._loaded = True

        logger.info(
            "[vector_store] Index built: %d vectors, dim=%d  →  %s",
            index.ntotal, dim, INDEX_PATH,
        )

    # ── Load ───────────────────────────────────────────────────────────────────

    def _load(self) -> bool:
        """Load index + chunks from disk. Returns True on success."""
        faiss = _require_faiss()

        if not INDEX_PATH.exists() or not CHUNKS_PATH.exists():
            logger.warning(
                "[vector_store] Index not found at %s. "
                "Run: python manage.py ingest_knowledge",
                INDEX_DIR,
            )
            return False

        try:
            index = faiss.read_index(str(INDEX_PATH))
            chunks = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
            with self._lock:
                self._index = index
                self._chunks = chunks
                self._loaded = True
            logger.info(
                "[vector_store] Loaded index: %d vectors  (%d chunks)",
                index.ntotal, len(chunks),
            )
            return True
        except Exception as exc:
            logger.error("[vector_store] Failed to load index: %s", exc)
            return False

    def is_ready(self) -> bool:
        """Return True if the index is loaded and non-empty."""
        with self._lock:
            return self._loaded and self._index is not None and len(self._chunks) > 0

    # ── Retrieve ───────────────────────────────────────────────────────────────

    def retrieve(self, question: str, top_k: int = TOP_K_DEFAULT) -> list[dict]:
        """
        Return top-k relevant chunks for `question`.

        Each result is a dict:
          {"chunk_id": int, "text": str, "source": str, "score": float [0-1]}

        Returns [] if the index is not ready or no chunks pass the
        CONFIDENCE_THRESHOLD.

        Logs:
          - query string
          - number of results
          - top score per chunk
        """
        # Lazy load on first call
        with self._lock:
            if not self._loaded:
                loaded = self._load()
                if not loaded:
                    return []

        if not self.is_ready():
            return []

        try:
            q_vec = self._embed([question])    # (1, dim)
            k = min(top_k, len(self._chunks))

            with self._lock:
                scores, indices = self._index.search(q_vec, k)

            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0:    # FAISS returns -1 for padding
                    continue
                score_f = float(score)
                if score_f < CONFIDENCE_THRESHOLD:
                    continue
                chunk = self._chunks[idx]
                results.append({
                    "chunk_id": chunk["chunk_id"],
                    "text":     chunk["text"],
                    "source":   chunk["source"],
                    "score":    round(score_f, 4),
                })

            logger.info(
                "[vector_store] Query: '%s…'  top_k=%d  results=%d  "
                "scores=%s  threshold=%.2f",
                question[:60], top_k, len(results),
                [r["score"] for r in results],
                CONFIDENCE_THRESHOLD,
            )
            return results

        except Exception as exc:
            logger.error("[vector_store] Retrieval error: %s", exc)
            return []


# ── Module-level singleton ─────────────────────────────────────────────────────

_store_instance: Optional[FinancialVectorStore] = None
_store_lock = threading.Lock()


def get_vector_store() -> FinancialVectorStore:
    """Return the process-wide FinancialVectorStore singleton."""
    global _store_instance
    if _store_instance is None:
        with _store_lock:
            if _store_instance is None:
                _store_instance = FinancialVectorStore()
    return _store_instance
