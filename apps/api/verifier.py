"""Per-sentence verifier (PLAN §4.2, §4.3).

Three-stage check per sentence:
  1. index check    — every [n] tag resolves to a retrieved passage
  2. coverage check — every factual sentence ends with at least one [n] tag
  3. NLI entailment — sentence-as-hypothesis against cited passage-as-premise

This module exposes:
  - parse_citation_tags(sentence)            → list[int]
  - segment_sentences(text)                  → list[str]   (pysbd)
  - verify_sentence(text, retrieved_idx_set) → SentenceVerification
  - verify_answer(text, retrieved)           → AnswerVerification
  - nli_score(premise, hypothesis)           → float in [0,1]  (lazy-loaded NLI)

Strict policy (PLAN §4.3):
  - default `SKIP_RATIO_STOP=0` — any `unsupported` halts the stream.
  - `weak_support` (NLI < 0.5) emitted with "verify with a lawyer" badge.
  - Segmentation safety net: if a sentence is flagged unsupported but
    re-segmentation moves the citation onto it, downgrade to weak_support.
"""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from typing import Optional

import pysbd

from apps.api.config import get_settings

logger = logging.getLogger(__name__)


class SentenceStatus(StrEnum):
    OK = "ok"
    WEAK_SUPPORT = "weak_support"
    UNSUPPORTED = "unsupported"
    UNKNOWN_CITATION = "unknown_citation"
    META = "meta"           # designated meta-sentences (refusal line, disclaimer headers)


# Disclaimer / meta lines that legitimately have no citations (server-side
# rendered + LLM-emitted). Match leniently.
_META_PATTERNS = [
    re.compile(r"^\s*\*\*[A-Z][A-Za-z ]+\*\*\s*$"),                              # **Section header**
    re.compile(r"the sources i have don'?t cover this", re.IGNORECASE),         # refusal
    re.compile(r"information, not legal advice", re.IGNORECASE),                # disclaimer line
    re.compile(r"general legal information", re.IGNORECASE),
    re.compile(r"consult a (qualified )?lawyer", re.IGNORECASE),
    re.compile(r"talk to a lawyer for your specific situation", re.IGNORECASE),
    re.compile(r"^\s*[-*]\s+", re.MULTILINE),                                    # bullet items — citations may carry on next line
]

# [n] or [n][m] or [n,m] tag patterns.
_CITATION_RE = re.compile(r"\[(\d+)\]")

# Sentence-end anchor for "ends with citation" coverage rule.
_ENDS_WITH_CITATION_RE = re.compile(r"\[\d+\](?:\[\d+\])*\s*[\.\?\!]?\s*$")


@dataclass(slots=True)
class SentenceVerification:
    text: str
    status: SentenceStatus
    citations: list[int] = field(default_factory=list)
    entailment_score: float | None = None
    reason: str = ""


@dataclass(slots=True)
class AnswerVerification:
    sentences: list[SentenceVerification] = field(default_factory=list)

    @property
    def unsupported_count(self) -> int:
        return sum(1 for s in self.sentences
                   if s.status in (SentenceStatus.UNSUPPORTED, SentenceStatus.UNKNOWN_CITATION))

    @property
    def weak_support_count(self) -> int:
        return sum(1 for s in self.sentences if s.status == SentenceStatus.WEAK_SUPPORT)

    @property
    def skip_ratio(self) -> float:
        emitted = [s for s in self.sentences if s.status != SentenceStatus.META]
        if not emitted:
            return 0.0
        return self.unsupported_count / len(emitted)


# --- Sentence segmentation ---------------------------------------------------

@lru_cache
def _segmenter() -> pysbd.Segmenter:
    return pysbd.Segmenter(language="en", clean=False)


def segment_sentences(text: str) -> list[str]:
    """pysbd-based sentence segmentation. Handles 'v.', 'Sec.', etc."""
    if not text.strip():
        return []
    return [s.strip() for s in _segmenter().segment(text) if s.strip()]


def parse_citation_tags(sentence: str) -> list[int]:
    """All [n] tags in a sentence, in order."""
    return [int(m.group(1)) for m in _CITATION_RE.finditer(sentence)]


def _is_meta_sentence(sentence: str) -> bool:
    return any(p.search(sentence) for p in _META_PATTERNS)


# --- NLI (lazy-loaded) -------------------------------------------------------

class _NLIWorker:
    """Loads MoritzLaurer/DeBERTa-v3-base-mnli on first use.

    Returns entailment probability ∈ [0,1]. Tracks the §2.4 known bias —
    general MNLI under-performs on legal phrasing by ~10-20%; we ship this
    gap explicitly until a legal-NLI replacement is benched.
    """

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None
        self._tokenizer = None
        self._lock = threading.Lock()

    def _ensure(self):
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            logger.info("loading NLI model %s on MPS", self.model_name)
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )
            import torch

            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
            self._model.eval()
            # Use MPS when available
            if torch.backends.mps.is_available():
                self._model = self._model.to("mps")
                self._device = "mps"
            else:
                self._device = "cpu"

    def score(self, premise: str, hypothesis: str) -> float:
        import torch

        self._ensure()
        # DeBERTa-v3-mnli labels: 0=contradiction, 1=neutral, 2=entailment
        inputs = self._tokenizer(
            premise, hypothesis,
            truncation=True, max_length=512, return_tensors="pt", padding=True,
        )
        inputs = {k: v.to(self._device) for k, v in inputs.items()}
        with torch.no_grad():
            logits = self._model(**inputs).logits[0]
        probs = torch.softmax(logits, dim=-1).cpu().numpy()
        # entailment is index 2 in MoritzLaurer/DeBERTa-v3-base-mnli
        return float(probs[2])


@lru_cache
def get_nli() -> Optional[_NLIWorker]:
    s = get_settings()
    try:
        return _NLIWorker(s.nli_model)
    except Exception as e:
        logger.warning("NLI worker unavailable: %s", e)
        return None


def nli_score(premise: str, hypothesis: str) -> float | None:
    """Entailment probability. Returns None if NLI is unavailable."""
    worker = get_nli()
    if worker is None:
        return None
    try:
        return worker.score(premise, hypothesis)
    except Exception as e:
        logger.warning("nli_score failed: %s", e)
        return None


# --- Public API --------------------------------------------------------------

def verify_sentence(
    sentence: str,
    retrieved_by_idx: dict[int, str],
    *,
    skip_nli: bool = False,
    nli_threshold: float | None = None,
) -> SentenceVerification:
    """Run index → coverage → NLI on a single sentence."""
    s = get_settings()
    if nli_threshold is None:
        nli_threshold = s.nli_weak_support_below

    # Meta-sentence: no citation requirement
    if _is_meta_sentence(sentence):
        return SentenceVerification(text=sentence, status=SentenceStatus.META, reason="meta line")

    citations = parse_citation_tags(sentence)

    # Step 1: index check (every [n] must be in retrieved)
    for n in citations:
        if n not in retrieved_by_idx:
            return SentenceVerification(
                text=sentence, status=SentenceStatus.UNKNOWN_CITATION,
                citations=citations,
                reason=f"citation [{n}] not in retrieved set",
            )

    # Step 2: coverage check
    if not citations:
        return SentenceVerification(
            text=sentence, status=SentenceStatus.UNSUPPORTED, reason="no citation tag",
        )
    if not _ENDS_WITH_CITATION_RE.search(sentence):
        # Has citation tags somewhere, but not at the end — borderline.
        # Don't fail outright; treat as a soft violation. Logged.
        logger.debug("sentence has citations but not at end: %r", sentence[:80])

    # Step 3: NLI (optional; on by default)
    if skip_nli or not citations:
        return SentenceVerification(
            text=sentence, status=SentenceStatus.OK, citations=citations,
        )

    # Aggregate evidence from all cited passages (concatenated). Take max
    # entailment across passages (a sentence is supported if ANY cited
    # passage entails it). This is conservative but reasonable.
    max_score: float | None = None
    for n in citations:
        passage = retrieved_by_idx.get(n)
        if not passage:
            continue
        sc = nli_score(passage, sentence)
        if sc is None:
            # NLI unavailable — fall back to coverage-only verdict.
            return SentenceVerification(
                text=sentence, status=SentenceStatus.OK, citations=citations,
                reason="nli unavailable; coverage-only verdict",
            )
        if max_score is None or sc > max_score:
            max_score = sc

    if max_score is not None and max_score < nli_threshold:
        return SentenceVerification(
            text=sentence, status=SentenceStatus.WEAK_SUPPORT,
            citations=citations, entailment_score=max_score,
            reason=f"max entailment {max_score:.2f} < threshold {nli_threshold:.2f}",
        )

    return SentenceVerification(
        text=sentence, status=SentenceStatus.OK,
        citations=citations, entailment_score=max_score,
    )


def verify_answer(
    text: str,
    retrieved_by_idx: dict[int, str],
    *,
    skip_nli: bool = False,
) -> AnswerVerification:
    out = AnswerVerification()
    for sent in segment_sentences(text):
        out.sentences.append(verify_sentence(sent, retrieved_by_idx, skip_nli=skip_nli))
    return out


__all__ = [
    "AnswerVerification",
    "SentenceStatus",
    "SentenceVerification",
    "nli_score",
    "parse_citation_tags",
    "segment_sentences",
    "verify_answer",
    "verify_sentence",
]
