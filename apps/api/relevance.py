"""Answer-vs-query relevance check (Task #10).

Why this exists — the failure case:

  User: "My landlord is not returning my deposit money."
  System (pre-task-10): cited correct SC judgments about *Section 30 of UP
                        Rent Act — how to deposit your monthly rent in court
                        when the landlord refuses to accept it*. Citations
                        and NLI verified perfectly. But the answer was about
                        the OPPOSITE money flow.

Citation-correctness (NLI/bge gates) measures "do the cited passages
support the claim". It does NOT measure "does the answer address the
question the user asked". This module adds that missing dimension.

Approach:

  After the answer stream finishes:
    1. Embed the original user query (bge-m3 dense head, same model as
       retrieval — already in memory).
    2. Embed the concatenation of all OK + WEAK_SUPPORT sentence texts
       (the "user-visible answer body", not META headers or refusal
       lines).
    3. Compute cosine similarity between the two L2-normalized vectors.
    4. Compare to calibrated threshold T (from
       `data/processed/answer_relevance_calibration.json`):
         - ok        : score >= T          (high confidence on-topic)
         - partial   : score in T - band   (mid-band; UI shows a notice)
         - off_topic : score < T - band    (UI shows a strong warning)

This is ADDITIVE — it warns the user, it does NOT refuse on its own.
The citation gates still ground the actual answer text.

Honest caveats (called out in the task brief):

  - Embedding-cosine alone is a weak hallucination signal. The deep
    research agent flagged exactly this gap. On the answer-relevance
    eval set (Part B) we report TPR/FPR; if AUC < 0.75 we recommend
    swapping in an LLM-judge for the partial/off_topic determination.
  - This check fires AFTER generation. It cannot prevent the off-topic
    answer from being shown — only flag it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

logger = logging.getLogger(__name__)


class RelevanceVerdict(StrEnum):
    OK = "ok"
    PARTIAL = "partial"
    OFF_TOPIC = "off_topic"


@dataclass(slots=True)
class RelevanceResult:
    score: float
    verdict: RelevanceVerdict
    threshold: float
    band: float


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity for two 1-D vectors. The bge-m3 dense head returns
    L2-normalized embeddings by default, so this is just a dot product —
    but we re-normalize defensively in case the worker contract changes.
    """
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def compute_relevance(
    query: str,
    answer_body: str,
    *,
    threshold: float,
    band: float = 0.05,
) -> RelevanceResult | None:
    """Embed (query, answer_body) and classify the cosine into a verdict.

    Returns None when:
      - `answer_body` is empty/whitespace (nothing the user would see).
      - The embedder is unavailable (don't ship a confused signal during
        a degraded state).
    Caller must treat None as "no relevance event" — DON'T emit the SSE
    event with a placeholder score. The task brief is specific: refused /
    empty answers should NOT emit relevance.

    Band semantics:
      - score >= threshold + band/2          → OK
      - threshold - band/2 < score < ...     → PARTIAL
      - score <= threshold - band/2          → OFF_TOPIC
    Default band=0.05 (so partial = threshold ± 0.025) — tuned to the
    on-topic/off-topic gap observed on the calibration set. The brief
    suggested ~0.1 but the data argues tighter; see docs/ANSWER_RELEVANCE.md.
    """
    body = (answer_body or "").strip()
    if not body:
        return None

    # Lazy import — relevance.py is imported by main.py at app startup,
    # but get_embedder() loads the BGE-M3 model on first call (multi-GB).
    # In the unit-test path where retrieval is mocked, embeddings.get_embedder
    # is not exercised until we hit this path; importing it lazily lets
    # tests that don't exercise relevance skip the model entirely.
    try:
        from apps.api.embeddings import get_embedder
        embedder = get_embedder()
    except Exception as e:
        logger.warning("relevance: embedder unavailable: %s", e)
        return None

    try:
        q_vec = embedder.encode_one(query)
        a_vec = embedder.encode_one(body)
    except Exception as e:
        logger.warning("relevance: encoding failed: %s", e)
        return None

    score = _cosine(np.asarray(q_vec), np.asarray(a_vec))

    half = band / 2.0
    if score >= threshold + half:
        verdict = RelevanceVerdict.OK
    elif score <= threshold - half:
        verdict = RelevanceVerdict.OFF_TOPIC
    else:
        verdict = RelevanceVerdict.PARTIAL

    return RelevanceResult(
        score=score, verdict=verdict, threshold=threshold, band=band,
    )


__all__ = [
    "RelevanceResult",
    "RelevanceVerdict",
    "compute_relevance",
]
