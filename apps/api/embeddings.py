"""Host-side embedding worker — BGE-M3 dense + learned-sparse from one pass.

Per Q3 bench (OPEN_QUESTIONS), local-host inference is materially faster than
Ollama-in-Docker on Mac (12 emb/s vs 0.4 emb/s). On Linux prod, swap
`embedding_backend=tei` and point at the TEI service on CUDA.

Why two backends:

  - **sentence-transformers** (legacy default in this repo): gives us the
    dense head only. Suitable for the rerank model (which is also a
    sentence-transformers CrossEncoder) and for callers that don't need
    the sparse vector. Kept for backward-compatibility with the existing
    ingest scripts.

  - **FlagEmbedding (`BGEM3FlagModel`)**: emits dense, sparse (lexical
    weights), and ColBERT from a single forward pass. Same underlying
    BGE-M3 weights — we just use more of the model's output. Required
    for multi-head retrieval (Task #3 in architecture-research roadmap).

The runtime API:

  - `encode_one(text) -> np.ndarray` — dense only, unchanged.
  - `encode_with_sparse(texts) -> tuple[np.ndarray, list[dict[str, float]]]`
    — dense and sparse together. Caller is responsible for serializing
    the sparse dicts to JSONB at insert time.
  - `encode_sparse_one(text) -> dict[str, float]` — query-time helper.

Singleton — load the model once per process. Switch via the
`embedding_runtime` setting (defaults to `flag` so we get sparse for free).
"""
from __future__ import annotations

import json
import logging
import threading
from functools import lru_cache

import numpy as np

from apps.api.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dense-only worker (legacy path; kept so existing tests / ingest scripts
# that import sentence-transformers directly continue to work).
# ---------------------------------------------------------------------------


class DenseOnlyWorker:
    """sentence-transformers backend. Dense head only.

    Suitable for callers that don't need the sparse output (e.g. the rerank
    pipeline, or a dense-only retrieval ablation).
    """

    def __init__(self, model_name: str, max_seq_len: int, device: str = "mps") -> None:
        self.model_name = model_name
        self.max_seq_len = max_seq_len
        self.device = device
        self._model = None
        self._lock = threading.Lock()

    def _ensure(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    logger.info(
                        "loading sentence-transformers %s on %s",
                        self.model_name, self.device,
                    )
                    m = SentenceTransformer(self.model_name, device=self.device)
                    m.max_seq_length = self.max_seq_len
                    self._model = m
                    logger.info("ST model loaded (max_seq_length=%d)", m.max_seq_length)
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
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

    # Sparse not supported on this backend — caller should use FlagWorker.
    def encode_with_sparse(self, texts: list[str]):
        raise NotImplementedError(
            "DenseOnlyWorker cannot emit sparse vectors. Use FlagEmbeddingWorker "
            "(set embedding_runtime='flag')."
        )

    def encode_sparse_one(self, text: str) -> dict[str, float]:
        raise NotImplementedError(
            "DenseOnlyWorker cannot emit sparse vectors. Use FlagEmbeddingWorker."
        )


# ---------------------------------------------------------------------------
# Multi-head worker — BGE-M3 dense + sparse from one forward pass.
# ---------------------------------------------------------------------------


class FlagEmbeddingWorker:
    """FlagEmbedding backend. Dense + learned-sparse from one forward pass.

    Sparse output shape per call: list[dict[str, float]], one dict per input
    text. Keys are stringified BERT token ids; values are the learned-sparse
    weights from the BGE-M3 lexical head.

    The model is exactly BGE-M3 (BAAI/bge-m3) — same weights as the
    sentence-transformers path. Different Python wrapper to access the
    sparse head.
    """

    def __init__(self, model_name: str, max_seq_len: int, device: str = "mps") -> None:
        self.model_name = model_name
        self.max_seq_len = max_seq_len
        self.device = device
        self._model = None
        self._lock = threading.Lock()

    def _ensure(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from FlagEmbedding import BGEM3FlagModel

                    logger.info(
                        "loading FlagEmbedding %s on %s (multi-head)",
                        self.model_name, self.device,
                    )
                    # use_fp16=False on MPS — fp16 on MPS is flaky for some
                    # ops; the dense head is what we still cast to halfvec
                    # on the storage side. For CUDA we can flip to True.
                    self._model = BGEM3FlagModel(
                        self.model_name, use_fp16=False, device=self.device,
                    )
                    logger.info("FlagEmbedding model loaded")
        return self._model

    # --- dense API (mirrors DenseOnlyWorker) ----------------------------

    def encode(self, texts: list[str]) -> np.ndarray:
        m = self._ensure()
        out = m.encode(
            texts,
            batch_size=16,
            max_length=self.max_seq_len,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        # The 'dense_vecs' result is L2-normalized by BGEM3FlagModel by
        # default (the BGE-M3 paper uses L2-normalized dense for cosine).
        return np.asarray(out["dense_vecs"], dtype=np.float32)

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]

    # --- multi-head API -------------------------------------------------

    def encode_with_sparse(self, texts: list[str]):
        """Return (dense, sparse) where sparse is a list[dict[str, float]]."""
        m = self._ensure()
        out = m.encode(
            texts,
            batch_size=16,
            max_length=self.max_seq_len,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        dense = np.asarray(out["dense_vecs"], dtype=np.float32)
        # `lexical_weights` is list[defaultdict[str, np.float32]]. Convert
        # the values to plain Python floats so json.dumps doesn't choke,
        # and drop zero-weight tokens.
        sparse: list[dict[str, float]] = []
        for raw in out["lexical_weights"]:
            sparse.append(_normalize_sparse(raw))
        return dense, sparse

    def encode_sparse_one(self, text: str) -> dict[str, float]:
        _, sparse = self.encode_with_sparse([text])
        return sparse[0]


def _normalize_sparse(raw) -> dict[str, float]:
    """Convert FlagEmbedding's raw sparse dict (defaultdict with np.float32
    values, sometimes integer keys) into a JSON-serializable plain dict
    with string keys and float values. Drop zero-weighted tokens which
    BGE-M3 sometimes emits at the boundary.
    """
    out: dict[str, float] = {}
    for k, v in raw.items():
        # Token ids might come back as str or int depending on the
        # FlagEmbedding version — coerce to str so the JSONB shape is
        # consistent across versions.
        key = str(k)
        val = float(v)
        if val > 0.0:
            out[key] = val
    return out


# ---------------------------------------------------------------------------
# Factory + utilities
# ---------------------------------------------------------------------------


@lru_cache
def get_embedder():
    """Return the embedding worker for the current process.

    Backend selection:
      * embedding_backend == 'tei' — not yet implemented (Linux+CUDA).
      * embedding_runtime == 'flag' (default) — multi-head BGEM3FlagModel.
      * embedding_runtime == 'st' — legacy sentence-transformers, dense only.

    The `FlagEmbeddingWorker` and `DenseOnlyWorker` share the same dense
    API surface (`encode`, `encode_one`, dimensions, L2 normalization) so
    callers that don't need sparse are unaffected.
    """
    s = get_settings()
    if s.embedding_backend == "tei":
        raise NotImplementedError("TEI backend lands with the Linux prod migration (§7)")
    runtime = getattr(s, "embedding_runtime", "flag")
    if runtime == "st":
        return DenseOnlyWorker(s.embedding_model, s.embedding_max_seq_len, device="mps")
    return FlagEmbeddingWorker(s.embedding_model, s.embedding_max_seq_len, device="mps")


def embedding_to_halfvec_literal(vec: np.ndarray) -> str:
    """Format a numpy vector as a pgvector halfvec literal: '[v0,v1,...]'."""
    return "[" + ",".join(f"{x:.7f}" for x in vec) + "]"


def sparse_to_jsonb(sparse: dict[str, float]) -> str:
    """Serialize a sparse vector dict to a JSON string suitable for
    Postgres JSONB insertion.

    `json.dumps` enforces string keys and finite floats. Empty dicts
    serialize to `{}`, which is a valid JSONB value (search for these
    rows via `embedding_sparse = '{}'::jsonb` if we ever need to).
    """
    return json.dumps(sparse, separators=(",", ":"))
