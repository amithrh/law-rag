"""Cross-encoder rerank pass (PLAN §2.3, stage 2).

Takes the BM25 ∪ dense candidate set and reorders it using
`BAAI/bge-reranker-v2-m3`, a cross-encoder that scores (query, passage)
pairs more accurately than the bi-encoder used for dense retrieval.

Singleton loaded lazily on first call. On Mac, runs on MPS.
On Linux/CUDA, swap device via env.

Performance notes (PLAN §5.3 — to be benched as Q4):
  - bge-reranker-v2-m3 has ~568M params (same as bge-m3 embedder)
  - On MPS, expect ~50-150ms per pair at 512-token seq length
  - Batched: rerank top-100 typically 1-3 seconds on M-series MPS
  - On CUDA L4/A100, ~10x faster

Failure mode: if the reranker is unavailable (model not pulled, MPS error),
log and fall back to combined_score order — never block retrieval.
"""
from __future__ import annotations

import logging
import threading
import time
from functools import lru_cache

from apps.api.config import get_settings
from apps.api.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)


# Models that have proven reliable as cross-encoder rerankers.
# bge-reranker-v2-m3 is multilingual + recommended by BAAI alongside bge-m3.
DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


class _RerankerWorker:
    """Lazy-loaded cross-encoder. Keeps the model on the chosen device."""

    def __init__(self, model_name: str, device: str = "mps") -> None:
        self.model_name = model_name
        self.device = device
        self._model = None
        self._lock = threading.Lock()
        self._unavailable = False  # if first load fails, mark and stop retrying

    def _load_model(self, device: str):
        from sentence_transformers import CrossEncoder

        logger.info(
            "loading reranker %s on %s (first call; ~1-2 GB)",
            self.model_name,
            device,
        )
        t0 = time.perf_counter()
        model = CrossEncoder(self.model_name, device=device, max_length=512)
        logger.info("reranker loaded on %s in %.1fs", device, time.perf_counter() - t0)
        return model

    def _ensure(self):
        if self._model is not None or self._unavailable:
            return
        with self._lock:
            if self._model is not None or self._unavailable:
                return
            try:
                self._model = self._load_model(self.device)
            except Exception as e:
                if self.device != "cpu":
                    logger.warning(
                        "reranker unavailable on %s (%s); retrying on CPU",
                        self.device,
                        e,
                    )
                    try:
                        self.device = "cpu"
                        self._model = self._load_model(self.device)
                    except Exception as cpu_error:
                        logger.warning(
                            "reranker unavailable, falling back to combined_score order: %s",
                            cpu_error,
                        )
                        self._unavailable = True
                else:
                    logger.warning(
                        "reranker unavailable, falling back to combined_score order: %s", e,
                    )
                    self._unavailable = True

    def is_available(self) -> bool:
        self._ensure()
        return not self._unavailable

    def score_pairs(self, query: str, passages: list[str]) -> list[float] | None:
        """Score each (query, passage) pair; higher = more relevant. Returns
        None if the reranker is unavailable so callers can fall back gracefully.
        """
        self._ensure()
        if self._unavailable or self._model is None:
            return None
        try:
            scores = self._model.predict(
                [(query, p) for p in passages],
                batch_size=32,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            return [float(s) for s in scores]
        except Exception as e:
            if self.device != "cpu":
                logger.warning(
                    "reranker.predict failed on %s (%s); retrying on CPU",
                    self.device,
                    e,
                )
                try:
                    with self._lock:
                        self.device = "cpu"
                        self._model = self._load_model(self.device)
                    scores = self._model.predict(
                        [(query, p) for p in passages],
                        batch_size=32,
                        show_progress_bar=False,
                        convert_to_numpy=True,
                    )
                    return [float(s) for s in scores]
                except Exception as cpu_error:
                    logger.warning("reranker CPU retry failed: %s; falling back", cpu_error)
            else:
                logger.warning("reranker.predict failed: %s; falling back", e)
            self._unavailable = True
            return None


@lru_cache
def get_reranker() -> _RerankerWorker:
    """Lazy singleton. Resolves model from settings in this order:

    1. settings.rerank_model_path — a LOCAL directory (e.g. a fine-tuned
       Stage-3 checkpoint at models/bge-reranker-v2-m3-finetuned/). When
       set and non-empty, this wins — letting us A/B between the
       upstream BAAI model and our fine-tune via env-only change
       (LAWRAG__RERANK_MODEL_PATH=…) without touching code.
    2. settings.rerank_model — an HF model name like
       "BAAI/bge-reranker-v2-m3" (default).
    3. DEFAULT_RERANKER_MODEL — the hardcoded last resort.

    The CrossEncoder constructor accepts either an HF name or a local
    directory transparently (it dispatches via `from_pretrained`), so
    the same code path serves both.
    """
    settings = get_settings()
    local = (getattr(settings, "rerank_model_path", None) or "").strip()
    name = local or settings.rerank_model or DEFAULT_RERANKER_MODEL
    logger.info("reranker resolved to %r (local=%s)", name, bool(local))
    return _RerankerWorker(model_name=name, device="mps")


def rerank(
    query: str,
    chunks: list[RetrievedChunk],
    *,
    keep: int | None = None,
) -> list[RetrievedChunk]:
    """Score chunks against `query` using the cross-encoder, sort by rerank
    score, and return the top `keep` chunks. Each chunk is mutated to carry
    its `rerank_score`.

    If the reranker is unavailable, the input list is returned unchanged
    (already sorted by combined_score by hybrid_retrieve).
    """
    if not chunks:
        return chunks
    worker = get_reranker()
    if not worker.is_available():
        return chunks[:keep] if keep else chunks

    scores = worker.score_pairs(query, [c.text for c in chunks])
    if scores is None:
        return chunks[:keep] if keep else chunks

    for c, s in zip(chunks, scores, strict=True):
        c.rerank_score = s

    chunks.sort(key=lambda c: c.rerank_score or -1e9, reverse=True)
    return chunks[:keep] if keep else chunks


__all__ = ["DEFAULT_RERANKER_MODEL", "get_reranker", "rerank"]
