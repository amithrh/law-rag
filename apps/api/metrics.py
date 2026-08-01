"""Prometheus metrics (PLAN §6.4).

Exposed at `/metrics` by main.py. Each per-request /search or /answer call
records timing into the histograms below, plus monotonic counters for
events the dashboard cares about.

Histogram bucket choices:
- Retrieval/rerank/LLM histograms use bucket boundaries that span the
  realistic latency range on Mac dev (M4 Max, MPS): 50ms - 10s.
- For Linux/CUDA prod, the same buckets work because faster end is just
  bucket-0 saturation; we'll widen if needed once we have real traffic.
"""
from __future__ import annotations

from prometheus_client import Counter, Histogram

# --- Retrieval -------------------------------------------------------------

retrieval_latency = Histogram(
    "rag_retrieval_latency_seconds",
    "Hybrid retrieval (BM25 + dense + union) latency, before rerank.",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

rerank_latency = Histogram(
    "rag_rerank_latency_seconds",
    "Cross-encoder rerank latency over the candidate set.",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0),
)

# --- LLM -------------------------------------------------------------------

llm_ttft = Histogram(
    "rag_llm_ttft_seconds",
    "Time-to-first-token from the LLM stream.",
    buckets=(0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 20.0),
)

llm_total = Histogram(
    "rag_llm_total_seconds",
    "Total LLM stream duration (start of generation → final disclaimer).",
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0),
)

answer_stage_latency = Histogram(
    "rag_answer_stage_latency_seconds",
    "Per-stage /answer latency, labelled by stage.",
    labelnames=("stage",),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 60.0),
)

# --- Verifier --------------------------------------------------------------

unsupported_total = Counter(
    "rag_unsupported_claims_total",
    "Sentences classified as UNSUPPORTED or UNKNOWN_CITATION.",
    labelnames=("status",),
)

weak_support_total = Counter(
    "rag_weak_support_total",
    "Sentences flagged as WEAK_SUPPORT by NLI (entailment < threshold).",
)

skip_ratio = Histogram(
    "rag_skip_ratio",
    "Per-answer fraction of sentences skipped (UNSUPPORTED + UNKNOWN_CITATION).",
    buckets=(0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0),
)

# --- Query metadata --------------------------------------------------------

query_total = Counter(
    "rag_query_total",
    "Number of /answer requests served.",
    labelnames=("source_filter",),  # 'all' | 'bare_act' | 'sc_judgment' | …
)

refused_total = Counter(
    "rag_refused_total",
    "Number of /answer requests that emitted a `refused` event after a service or composition failure.",
)

source_gap_handoff_total = Counter(
    "rag_source_gap_handoff_total",
    "Number of /answer requests that stopped at a verified-source gap and emitted a safe handoff.",
)

stopped_total = Counter(
    "rag_stopped_total",
    "Number of /answer requests that emitted a `stop` event due to "
    "skip_ratio exceeding threshold mid-stream.",
)


__all__ = [
    "answer_stage_latency",
    "llm_total",
    "llm_ttft",
    "query_total",
    "refused_total",
    "source_gap_handoff_total",
    "rerank_latency",
    "retrieval_latency",
    "skip_ratio",
    "stopped_total",
    "unsupported_total",
    "weak_support_total",
]
