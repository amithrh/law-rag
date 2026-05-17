"""Host-side embedding worker (sentence-transformers + MPS on Mac).

Per Q3 bench (OPEN_QUESTIONS), this is materially faster than Ollama-in-Docker
on Mac (12 emb/s vs 0.4 emb/s). On Linux prod, swap `embedding_backend=tei`
and point at the TEI service on CUDA.

Singleton — load the model once per process.
"""
from __future__ import annotations

import logging
import threading
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from apps.api.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingWorker:
    """Loads the embedding model on first use and serves encode() calls."""

    def __init__(self, model_name: str, max_seq_len: int, device: str = "mps") -> None:
        self.model_name = model_name
        self.max_seq_len = max_seq_len
        self.device = device
        self._model: SentenceTransformer | None = None
        self._lock = threading.Lock()

    def _ensure(self) -> SentenceTransformer:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    logger.info("loading embedding model %s on %s", self.model_name, self.device)
                    m = SentenceTransformer(self.model_name, device=self.device)
                    m.max_seq_length = self.max_seq_len
                    self._model = m
                    logger.info("embedding model loaded (max_seq_length=%d)", m.max_seq_length)
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        """Return float32 array of shape (len(texts), dim) with L2-normalized vectors."""
        m = self._ensure()
        return m.encode(
            texts,
            batch_size=16,
            show_progress_bar=False,
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype(np.float32)

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]


@lru_cache
def get_embedder() -> EmbeddingWorker:
    s = get_settings()
    # On Mac dev, sentence-transformers on MPS is the right backend.
    # On Linux prod, EMBEDDING_BACKEND=tei swaps this for an HTTP client.
    if s.embedding_backend == "tei":
        # Placeholder — implement TEI HTTP client when deploying to Linux+CUDA
        raise NotImplementedError("TEI backend lands with the Linux prod migration (§7)")
    return EmbeddingWorker(s.embedding_model, s.embedding_max_seq_len, device="mps")


def embedding_to_halfvec_literal(vec: np.ndarray) -> str:
    """Format a numpy vector as a pgvector halfvec literal: '[v0,v1,...]'."""
    return "[" + ",".join(f"{x:.7f}" for x in vec) + "]"
