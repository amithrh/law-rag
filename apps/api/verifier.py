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
    GUIDANCE = "guidance"
    WEAK_SUPPORT = "weak_support"
    UNSUPPORTED = "unsupported"
    UNKNOWN_CITATION = "unknown_citation"
    META = "meta"           # designated meta-sentences (refusal line, disclaimer headers)


# Hard-meta: lines that are always non-claims — headers, disclaimer text,
# the canonical refusal. Citation check skipped regardless of [N] presence.
_META_PATTERNS = [
    re.compile(r"^\s*\*\*[A-Z][A-Za-z ()/-]{1,40}\*\*\s*:?\s*$"),                # **Section header**
    re.compile(r"^\s*the sources i have don'?t cover this clearly\.?\s*$", re.IGNORECASE),
    re.compile(r"^\s*the sources i have don'?t cover this clearly\.\s*i won'?t guess\.?\s*$", re.IGNORECASE),
    re.compile(r"^\s*i won'?t guess\.?\s*$", re.IGNORECASE),
    re.compile(r"^\s*the provided passages do not state how this applies to your exact facts\.\s*$", re.IGNORECASE),
    re.compile(r"^\s*the provided passages do not state a concrete next step\.\s*$", re.IGNORECASE),
    re.compile(r"^\s*the provided passages do not state enough to apply the rule to your exact facts\.\s*$", re.IGNORECASE),
    re.compile(r"^\s*the provided passages do not state a concrete punishment for the prohibition offence\.\s*$", re.IGNORECASE),
    re.compile(r"^\s*this is general legal information, not legal advice for your specific situation\.?\s*$", re.IGNORECASE),
    re.compile(r"^\s*you should talk to a lawyer for your specific situation\.?\s*$", re.IGNORECASE),
    re.compile(r"^\s*talk to a lawyer for your specific situation\.?\s*$", re.IGNORECASE),
    re.compile(r"^\s*laws and (their|the) interpretation change\.?\s*$", re.IGNORECASE),
    re.compile(r"^\s*for decisions that affect your rights, consult a qualified lawyer or the relevant court / forum\.?\s*$", re.IGNORECASE),
    re.compile(r"^\s*the incident date decides whether bns/bnss/bsa or ipc/crpc/evidence act applies\.?\s*$", re.IGNORECASE),
    # NOTE: bullet-line exemption removed per Codex review #4. Bullets in
    # "What you can do next" make procedural claims ("file within 30 days",
    # "appeal to magistrate") that need citations too. With the suppress
    # architecture, bullets without [N] are dropped, not shown to the user —
    # so the user only sees cited procedural steps.
    #
    # NOTE: case-reference META pattern removed per Codex review #2. It was
    # over-matching real holdings like "In Lalita Kumari v. UP, 2013, police
    # must register an FIR." Source-catalog lines are still recognized by
    # their leading "[N]" — the citation gate still runs, but the rest of
    # the line doesn't get NLI-checked because [N] is present and the
    # passage exists.
]

# Soft-preamble: phrases that frame the answer without making a legal claim.
# Treated as META ONLY when the sentence has no citation [N] — so a real
# cited claim that happens to start with "Based on…" still gets verified.
# Without this whitelist, small Q4 models trip strict-stop on their opening
# transition sentence even when the rest of the answer cites correctly.
# Per Codex review (round 2) #1: the preamble whitelist must ONLY match
# phrases that explicitly frame the response as drawn from the retrieved
# sources. Generic "according to" / "based on" / sentences ending in ":"
# would let real legal claims like "According to Section 154(3), you can
# complain to the Superintendent of Police." slip through as META. Match
# only the narrow set of source-framing openings; nothing else.
_PREAMBLE_PATTERNS = [
    re.compile(
        r"^\s*("
        r"based on (the )?(provided|retrieved) (passages|cases|sources),?\s+here (are|is) (the )?(key |main )?(points|highlights)"
        r"|here (are|is) (the )?(key |main )?(points|highlights) (from|in) (the )?(passages|cases|sources)"
        r")\.?\s*$",
        re.IGNORECASE,
    ),
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
    auto_cited: bool = False


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
    """pysbd-based sentence segmentation, then a post-merge pass to undo
    false splits inside Indian legal abbreviations (Cr.P.C., U.P., ORS.,
    Hon'ble, v., etc.). pysbd is good at "Sec." and "v." but consistently
    splits on "ORS." (all-caps ≤4 letters then dot) and on multi-dotted
    abbreviations when streamed token-by-token. Without the merge, citation
    tags get stranded on the wrong segment ("Cr.P." emitted with no [N],
    "C. [1]" emitted as next sentence) and strict-stop fires."""
    if not text.strip():
        return []
    segs = [s.strip() for s in _segmenter().segment(text) if s.strip()]
    return _merge_abbreviation_splits(segs)


# Matches when a sentence ends in something that LOOKS like a short legal
# abbreviation that pysbd may have mis-split. We don't merge on this alone
# (many real sentences end with all-caps words like FIR/IPC/CrPC). We also
# require the NEXT segment to continue mid-clause — see _looks_like_split.
_ABBREV_TAIL_RE = re.compile(
    r"(?:"
    r"[A-Z]+\."                                  # ORS. UP. SC. AIR. FIR. (all caps)
    r"|[A-Z][a-z]?\.([A-Z][a-z]?\.)+"            # U.P. Cr.P.C. a.k.a.
    r"|\b(v|vs|Vs|Sec|Art|Hon|Ors|Smt|Sri|Shri|Pvt|Ltd|No|Ch|Cl|cf|cl|sec|ed|fn|pp|para|p|i\.e|e\.g|viz|etc|et al|Mr|Mrs|Ms|Dr|Prof|Govt|Rs)\."
    r")\s*$"
)

# A "continuation" first token in the NEXT segment — these only ever appear
# mid-sentence (commas, lowercase starts, conjunctions in all-caps lists,
# closing brackets, etc.). If segment i+1 starts with one of these, segment
# i's trailing "." was almost certainly an abbreviation, not a real period.
_CONTINUATION_START_RE = re.compile(
    r"^\s*(?:"
    r"[,;:\)\]\}]"                               # punctuation continuation
    r"|[a-z]"                                    # lowercase letter
    r"|(?:AND|OR|VS|VERSUS|ETC|AT|IN|OF|FOR)\b"  # all-caps list connectors
    r"|C\b"                                      # bare "C" — completes "Cr.P. C." → "Cr.P.C."
    r"|\d"                                       # digit — ", 2007, para 26" with leading comma stripped
    # Honorific-abbrev → party-name pattern: "Smt." / "Shri." / "Hon." /
    # "M/s." routinely precede ALL-CAPS party names in case headers
    # ("SMT. MAYADEVI versus JAGDISH PRASAD"). pysbd splits at the dot;
    # the next segment then begins with an all-caps word that on its own
    # isn't a continuation marker, but in this context clearly is.
    r"|[A-Z]{2,}\b"                              # ALL-CAPS word (party name continuation)
    r")"
)


def _merge_abbreviation_splits(segs: list[str]) -> list[str]:
    """Walk pysbd's segments; merge segment i into i+1 only when BOTH (a)
    segment i ends with an abbreviation-shaped token, AND (b) segment i+1
    starts with a continuation marker (comma, lowercase, connector). Either
    signal alone has too many false positives — "Police must file the FIR.
    The Magistrate..." would over-merge on (a); "Cr.P." followed by "C." in
    abbrev context would over-merge on (b)."""
    if len(segs) < 2:
        return segs
    out: list[str] = []
    i = 0
    while i < len(segs):
        cur = segs[i]
        while (
            i + 1 < len(segs)
            and _ABBREV_TAIL_RE.search(cur)
            and _CONTINUATION_START_RE.match(segs[i + 1])
        ):
            cur = cur + " " + segs[i + 1]
            i += 1
        out.append(cur)
        i += 1
    return out


def parse_citation_tags(sentence: str) -> list[int]:
    """All [n] tags in a sentence, in order."""
    return [int(m.group(1)) for m in _CITATION_RE.finditer(sentence)]


def _is_meta_sentence(sentence: str) -> bool:
    return any(p.search(sentence) for p in _META_PATTERNS)


def _is_preamble_sentence(sentence: str) -> bool:
    """Soft preamble — only counts as META when sentence has no [N] tag."""
    return any(p.search(sentence) for p in _PREAMBLE_PATTERNS)


# Word-level for auto-cite lexical match. Stopwords stripped so overlap
# is meaningful — without this, any sentence matches any passage on
# "the/a/and/of/to" alone.
_AUTO_CITE_STOPWORDS = frozenset({
    "a", "an", "and", "any", "are", "as", "at", "be", "because", "been",
    "but", "by", "can", "could", "did", "do", "does", "doing", "done",
    "for", "from", "had", "has", "have", "her", "him", "his", "how", "i",
    "if", "in", "into", "is", "it", "its", "may", "me", "might", "mine",
    "must", "my", "no", "not", "now", "of", "on", "or", "our", "out", "own",
    "she", "should", "so", "some", "such", "than", "that", "the", "their",
    "them", "they", "this", "those", "to", "too", "under", "very", "was",
    "we", "were", "what", "when", "where", "which", "who", "whom", "why",
    "will", "with", "would", "you", "your",
})

# Tokens for auto-cite. Legal text is full of "Section 154(3)", "Cr.P.C.",
# "Section 36" — they're the *content* citations the model is paraphrasing,
# and any tokenizer that drops them loses the signal we need to match.
_AUTO_CITE_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9.()/-]*[A-Za-z0-9)]|\d+(?:\([0-9a-z]+\))?")


def _content_words(text: str) -> list[str]:
    out: list[str] = []
    for m in _AUTO_CITE_WORD_RE.finditer(text):
        w = m.group(0).rstrip(".").lower()
        if not w or w in _AUTO_CITE_STOPWORDS:
            continue
        # Keep short alphabetic tokens only if they're statute abbreviations
        # or section references (3+ chars or contain a digit).
        if len(w) <= 2 and not any(c.isdigit() for c in w):
            continue
        out.append(w)
    return out


def _ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def _auto_cite(
    sentence: str,
    retrieved_by_idx: dict[int, str],
    min_recall: float,
) -> list[int]:
    """Return [N] for the highest-overlap passage if it clears `min_recall`.

    Score = |sentence content-words ∩ passage content-words| / |sentence
    content-words| (unigram recall). We tried 3- and 4-grams first but
    legal text consistently paraphrases ("Cr.P.C." ↔ "Code of Criminal
    Procedure", "Superintendent of Police" ↔ "higher-ranking police
    officer") and n-gram overlap collapsed to zero even when the topic was
    plainly the same. Unigram recall stays meaningful through paraphrase.

    To prevent noise (a stray "police" matching every passage in a
    criminal-law retrieval set), we also require at least
    `_AUTO_CITE_MIN_SHARED` distinct content words to be shared with the
    chosen passage.
    """
    sent_tokens = _content_words(sentence)
    if len(sent_tokens) < 4:
        return []
    sent_set = set(sent_tokens)
    if not sent_set:
        return []

    best_idx = -1
    best_recall = 0.0
    best_hits = 0
    for n, passage_text in retrieved_by_idx.items():
        p_set = set(_content_words(passage_text))
        if not p_set:
            continue
        hits = sent_set & p_set
        recall = len(hits) / len(sent_set)
        if recall > best_recall:
            best_recall = recall
            best_hits = len(hits)
            best_idx = n

    if (
        best_idx > 0
        and best_recall >= min_recall
        and best_hits >= _AUTO_CITE_MIN_SHARED
    ):
        logger.debug(
            "auto-cite attached [%d] (recall=%.2f, hits=%d) to %r",
            best_idx, best_recall, best_hits, sentence[:80],
        )
        return [best_idx]
    return []


_AUTO_CITE_MIN_SHARED = 4


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
        self._entailment_label_idx: int = 0   # resolved at load time
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
            # Resolve entailment label index from the model's own config.
            # Different MNLI fine-tunes use different label orderings.
            id2label = {int(k): str(v).lower() for k, v in self._model.config.id2label.items()}
            for idx, name in id2label.items():
                if name == "entailment":
                    self._entailment_label_idx = idx
                    break
            else:
                logger.warning(
                    "NLI model %s has no 'entailment' label in config.id2label=%s; "
                    "defaulting to index 0",
                    self.model_name, id2label,
                )
            logger.info("entailment label idx=%d", self._entailment_label_idx)

            # Use MPS when available
            if torch.backends.mps.is_available():
                self._model = self._model.to("mps")
                self._device = "mps"
            else:
                self._device = "cpu"

    def score(self, premise: str, hypothesis: str) -> float:
        import torch

        self._ensure()
        # Label mapping resolved from the model's own config — DON'T assume.
        # MoritzLaurer/DeBERTa-v3-base-mnli: 0=entailment, 1=neutral, 2=contradiction
        # (verified via model.config.id2label).
        ent_idx = self._entailment_label_idx
        inputs = self._tokenizer(
            premise, hypothesis,
            truncation=True, max_length=512, return_tensors="pt", padding=True,
        )
        inputs = {k: v.to(self._device) for k, v in inputs.items()}
        with torch.no_grad():
            logits = self._model(**inputs).logits[0]
        probs = torch.softmax(logits, dim=-1).cpu().numpy()
        return float(probs[ent_idx])


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


# --- bge (reranker as verifier) ----------------------------------------------
#
# Architecture-research task #2: reuse the existing bge-reranker-v2-m3
# cross-encoder for per-sentence verification. The score is "how relevant is
# this passage to this query" — when the query is the sentence and the
# passage is the cited evidence, that correlates with answer-support.
#
# Two safety properties we lean on:
#   1. The model is ALREADY loaded for retrieval-stage reranking. Calling
#      it again for verification adds zero load cost — just inference cost.
#   2. If NLI is retired (verifier_backend=bge), we free ~1.5 GB of NLI
#      model RAM.
#
# Two caveats vs categorical entailment (see docs/VERIFIER_SWAP.md):
#   - bge does not encode negation/contradiction directly. A sentence that
#     contradicts the passage may still score moderately positive because
#     the topic overlaps. NLI handles contradiction natively.
#   - bge scores are in roughly [-10, +10], NOT a probability. Threshold
#     calibration is essential — a hard-coded 0.5 doesn't transfer.

def bge_score(premise: str, hypothesis: str) -> float | None:
    """Cross-encoder relevance score for (passage, sentence). Higher = more
    supportive. Returns None if the reranker is unavailable.

    Signature mirrors `nli_score(premise, hypothesis)` so the two backends
    can be swapped at the call site. Premise = cited passage text;
    hypothesis = sentence being verified.

    Shares the singleton reranker with the retrieval rerank step
    (apps.api.rerank.get_reranker()) — DON'T load a second copy of the
    1-2 GB model.
    """
    # Lazy import to avoid circular import (rerank.py imports config which
    # imports verifier indirectly via main.py at app startup).
    from apps.api.rerank import get_reranker

    worker = get_reranker()
    if not worker.is_available():
        return None
    try:
        scores = worker.score_pairs(hypothesis, [premise])
    except Exception as e:  # defensive; worker.score_pairs already logs+falls back
        logger.warning("bge_score failed: %s", e)
        return None
    if scores is None:
        return None
    return scores[0]


# --- Backend dispatch --------------------------------------------------------
#
# Two backends, identical contract:
#   _score(premise, hypothesis) -> float | None
# The verify_sentence() core calls _score() per (cited passage, sentence)
# and applies backend-specific thresholds.

_STATUS_RANK: dict[SentenceStatus, int] = {
    SentenceStatus.META: 0,                # best — exempt from claims gate
    SentenceStatus.GUIDANCE: 0,            # reviewed non-claim operational step
    SentenceStatus.OK: 1,
    SentenceStatus.WEAK_SUPPORT: 2,
    SentenceStatus.UNSUPPORTED: 3,
    SentenceStatus.UNKNOWN_CITATION: 4,    # worst — index check failed
}


def _worse(a: SentenceStatus, b: SentenceStatus) -> SentenceStatus:
    """Return the pessimistic (worse) of two sentence statuses. Used by the
    ensemble backend to AND the two safety nets together — a sentence only
    survives ensemble when BOTH backends agree it's safe."""
    return a if _STATUS_RANK[a] >= _STATUS_RANK[b] else b


# --- Public API --------------------------------------------------------------

@dataclass(slots=True)
class _BackendVerdict:
    """Per-backend output of the entailment step. Wraps the backend-specific
    score with the resulting status. Used internally by verify_sentence()
    so the ensemble path can compare two verdicts side-by-side."""
    status: SentenceStatus
    score: float | None
    reason: str
    # If True, the backend ran but the model was unavailable / failed and
    # we fell back to a fail-closed verdict (WEAK_SUPPORT). Used by the
    # ensemble path to decide whether to "trust this verdict" or skip the
    # backend entirely.
    unavailable: bool = False


def _entailment_verdict(
    backend: str,
    sentence: str,
    citations: list[int],
    retrieved_by_idx: dict[int, str],
    *,
    auto_cited: bool,
    nli_threshold: float,
    bge_threshold: float,
) -> _BackendVerdict:
    """Run one backend (nli or bge) against the cited passages and return
    a verdict. Same hard-floor / fail-closed semantics as the original NLI
    code path — only the scorer + thresholds differ.

    Aggregation: take max score across cited passages (a sentence is
    supported if ANY cited passage supports it).
    """
    s = get_settings()
    if backend == "nli":
        scorer = nli_score
        threshold = nli_threshold
        hard_floor = s.nli_hard_floor
        name = "nli"
    elif backend == "bge":
        scorer = bge_score
        threshold = bge_threshold
        hard_floor = s.bge_verifier_hard_floor
        name = "bge"
    else:
        raise ValueError(f"unknown backend {backend!r}")

    max_score: float | None = None
    unavailable = False
    for n in citations:
        passage = retrieved_by_idx.get(n)
        if not passage:
            continue
        sc = scorer(passage, sentence)
        if sc is None:
            unavailable = True
            continue
        if max_score is None or sc > max_score:
            max_score = sc

    if unavailable and max_score is None:
        # Backend unavailable, no passages scored. Per round-3 review
        # (security #3): fail CLOSED for explicit-cite too — degraded
        # entailment service must not silently downgrade to coverage-only.
        return _BackendVerdict(
            status=SentenceStatus.WEAK_SUPPORT,
            score=None,
            reason=f"{name} unavailable; "
                   + ("auto-cite cannot confirm entailment"
                      if auto_cited else "explicit-cite entailment unconfirmed"),
            unavailable=True,
        )

    if max_score is not None and max_score < hard_floor:
        return _BackendVerdict(
            status=SentenceStatus.UNSUPPORTED,
            score=max_score,
            reason=f"max {name} {max_score:.2f} < hard floor {hard_floor:.2f}",
        )

    if max_score is not None and max_score < threshold:
        return _BackendVerdict(
            status=SentenceStatus.WEAK_SUPPORT,
            score=max_score,
            reason=f"max {name} {max_score:.2f} < threshold {threshold:.2f}",
        )

    return _BackendVerdict(
        status=SentenceStatus.OK,
        score=max_score,
        reason="",
    )


def verify_sentence(
    sentence: str,
    retrieved_by_idx: dict[int, str],
    *,
    skip_nli: bool = False,
    nli_threshold: float | None = None,
    backend: str | None = None,
) -> SentenceVerification:
    """Run index → coverage → entailment on a single sentence.

    `backend` selects the entailment scorer:
      - "nli"      : DeBERTa MNLI (legacy behaviour).
      - "bge"      : bge-reranker-v2-m3 cross-encoder relevance score.
      - "ensemble" : run both, take the pessimistic (worse) verdict.
    None falls back to settings.verifier_backend.

    `skip_nli=True` is the legacy /answer-fast path — explicit-cite sentences
    skip entailment entirely. It applies symmetrically: for any backend,
    skip_nli=True + explicit-cite means OK without scoring. Auto-cited
    sentences ALWAYS run entailment (per Codex review #3) regardless of
    skip_nli or backend.
    """
    s = get_settings()
    if backend is None:
        backend = s.verifier_backend
    if nli_threshold is None:
        nli_threshold = s.nli_weak_support_below

    # Hard-meta: always exempt from citation requirement.
    if _is_meta_sentence(sentence):
        return SentenceVerification(text=sentence, status=SentenceStatus.META, reason="meta line")

    citations = parse_citation_tags(sentence)

    # Soft-preamble: only exempt if it truly has no citation tag. A sentence
    # that happens to begin with "Based on Section 154(3) [1]…" is a real
    # claim and must be verified normally.
    if not citations and _is_preamble_sentence(sentence):
        return SentenceVerification(text=sentence, status=SentenceStatus.META, reason="preamble")

    # Auto-cite: small Q4 models routinely produce accurate sentences that
    # forget the inline [N]. Recover by lexical 4-gram overlap against each
    # retrieved passage. If a passage's content covers the sentence ≥
    # auto_cite_min_recall, attach it as the citation. This preserves the
    # strict-stop guarantee (we never let an unsupported sentence through),
    # because the attached passage still has to clear entailment in step 3.
    auto_cited = False
    if not citations and s.auto_cite_enabled:
        auto = _auto_cite(sentence, retrieved_by_idx, s.auto_cite_min_recall)
        if auto:
            citations = auto
            auto_cited = True

    # Step 1: index check (every [n] must be in retrieved)
    for n in citations:
        if n not in retrieved_by_idx:
            return SentenceVerification(
                text=sentence, status=SentenceStatus.UNKNOWN_CITATION,
                citations=citations,
                reason=f"citation [{n}] not in retrieved set",
                auto_cited=auto_cited,
            )

    # Step 2: coverage check
    if not citations:
        return SentenceVerification(
            text=sentence, status=SentenceStatus.UNSUPPORTED, reason="no citation tag",
        )
    if not auto_cited and not _ENDS_WITH_CITATION_RE.search(sentence):
        # Has citation tags somewhere, but not at the end — borderline.
        # Don't fail outright; treat as a soft violation. Logged.
        # (auto-cited sentences are appended by us, not the LLM, so the
        # end-anchor check doesn't apply.)
        logger.debug("sentence has citations but not at end: %r", sentence[:80])

    # Step 3: entailment. Per Codex review #3 — entailment is FORCED for
    # auto-cited sentences regardless of the skip_nli flag, because
    # auto-cite chose the passage by lexical overlap alone and a
    # negated/overbroad sentence ("you CANNOT approach the SP under
    # Section 154(3)") would otherwise be greenlit despite contradicting
    # the cited passage.
    if skip_nli and not auto_cited:
        # Explicit citation, entailment explicitly skipped (eval / fast path).
        return SentenceVerification(
            text=sentence, status=SentenceStatus.OK, citations=citations,
            auto_cited=auto_cited,
        )

    if backend == "nli":
        v = _entailment_verdict(
            "nli", sentence, citations, retrieved_by_idx,
            auto_cited=auto_cited,
            nli_threshold=nli_threshold,
            bge_threshold=s.bge_verifier_threshold,
        )
        return SentenceVerification(
            text=sentence, status=v.status, citations=citations,
            entailment_score=v.score, reason=v.reason, auto_cited=auto_cited,
        )

    if backend == "bge":
        v = _entailment_verdict(
            "bge", sentence, citations, retrieved_by_idx,
            auto_cited=auto_cited,
            nli_threshold=nli_threshold,
            bge_threshold=s.bge_verifier_threshold,
        )
        return SentenceVerification(
            text=sentence, status=v.status, citations=citations,
            entailment_score=v.score, reason=v.reason, auto_cited=auto_cited,
        )

    if backend == "ensemble":
        nli_v = _entailment_verdict(
            "nli", sentence, citations, retrieved_by_idx,
            auto_cited=auto_cited,
            nli_threshold=nli_threshold,
            bge_threshold=s.bge_verifier_threshold,
        )
        bge_v = _entailment_verdict(
            "bge", sentence, citations, retrieved_by_idx,
            auto_cited=auto_cited,
            nli_threshold=nli_threshold,
            bge_threshold=s.bge_verifier_threshold,
        )
        # Fail-closed graceful degradation: if exactly ONE backend is
        # unavailable, fall back to the OTHER (don't double-penalize the
        # sentence). If BOTH are unavailable, the surviving WEAK_SUPPORT
        # verdict propagates (which is the fail-closed contract).
        if nli_v.unavailable and not bge_v.unavailable:
            note = f"ensemble→bge (nli unavailable); {bge_v.reason}".rstrip("; ")
            v = _BackendVerdict(status=bge_v.status, score=bge_v.score, reason=note)
        elif bge_v.unavailable and not nli_v.unavailable:
            note = f"ensemble→nli (bge unavailable); {nli_v.reason}".rstrip("; ")
            v = _BackendVerdict(status=nli_v.status, score=nli_v.score, reason=note)
        else:
            # Pessimistic AND: take the worse of the two verdicts.
            worse_status = _worse(nli_v.status, bge_v.status)
            reason_bits = []
            if nli_v.score is not None:
                reason_bits.append(f"nli={nli_v.score:.2f}")
            if bge_v.score is not None:
                reason_bits.append(f"bge={bge_v.score:.2f}")
            reason = (
                f"ensemble {worse_status.value}: " + ", ".join(reason_bits)
                if reason_bits else f"ensemble {worse_status.value}"
            )
            # Report NLI score in entailment_score for backward-compat
            # with existing UI / metrics consumers. NLI is the primary
            # signal; bge is the safety net. If NLI is missing, fall
            # through to bge so the field is never None when one
            # backend produced a score.
            v = _BackendVerdict(
                status=worse_status,
                score=nli_v.score if nli_v.score is not None else bge_v.score,
                reason=reason,
            )
        return SentenceVerification(
            text=sentence, status=v.status, citations=citations,
            entailment_score=v.score, reason=v.reason, auto_cited=auto_cited,
        )

    raise ValueError(f"unknown verifier_backend {backend!r}")


def verify_answer(
    text: str,
    retrieved_by_idx: dict[int, str],
    *,
    skip_nli: bool = False,
    backend: str | None = None,
) -> AnswerVerification:
    out = AnswerVerification()
    for sent in segment_sentences(text):
        out.sentences.append(
            verify_sentence(sent, retrieved_by_idx, skip_nli=skip_nli, backend=backend),
        )
    return out


__all__ = [
    "AnswerVerification",
    "SentenceStatus",
    "SentenceVerification",
    "bge_score",
    "nli_score",
    "parse_citation_tags",
    "segment_sentences",
    "verify_answer",
    "verify_sentence",
]
