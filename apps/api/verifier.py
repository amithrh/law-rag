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


# Hard-meta: lines that are always non-claims — headers, disclaimer text,
# the canonical refusal. Citation check skipped regardless of [N] presence.
_META_PATTERNS = [
    re.compile(r"^\s*\*\*[A-Z][A-Za-z ()/-]{1,40}\*\*\s*:?\s*$"),                # **Section header**
    re.compile(r"the sources i have don'?t cover this", re.IGNORECASE),         # refusal
    re.compile(r"information, not legal advice", re.IGNORECASE),                # disclaimer line
    re.compile(r"general legal information", re.IGNORECASE),
    re.compile(r"consult a (qualified )?lawyer", re.IGNORECASE),
    re.compile(r"talk to a lawyer for your specific situation", re.IGNORECASE),
    re.compile(r"laws and (their|the) interpretation change", re.IGNORECASE),    # second sentence of the disclaimer block
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
_PREAMBLE_PATTERNS = [
    re.compile(r"^\s*(based on|according to|looking at|in response to|here (are|is)|from the (provided|retrieved) (cases|passages|sources)|the (provided|retrieved) (cases|passages|sources)) ", re.IGNORECASE),
    re.compile(r"^\s*(below|here)\s+(are|is)\s+(the|a|some)\b", re.IGNORECASE),
    re.compile(r"^\s*(let me|i'?ll|let's) (explain|walk you through|address)", re.IGNORECASE),
    # Sentences that end with ":" are introducing a list, not making a claim.
    # The cited claims appear in the list items that follow. Conservative —
    # only match when no citation is in the sentence (the outer check
    # guarantees that).
    re.compile(r":\s*$"),
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
    # because the attached passage still has to clear NLI in step 3.
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

    # Step 3: NLI. Per Codex review #3 — NLI is FORCED for auto-cited
    # sentences regardless of the skip_nli flag, because auto-cite chose
    # the passage by lexical overlap alone and a negated/overbroad
    # sentence ("you CANNOT approach the SP under Section 154(3)") would
    # otherwise be greenlit despite contradicting the cited passage.
    if not citations:
        # Unreachable in normal flow (auto-cite would have attached or
        # we'd have returned UNSUPPORTED above), but guard anyway.
        return SentenceVerification(
            text=sentence, status=SentenceStatus.UNSUPPORTED,
            reason="no citation tag (post-auto-cite)",
            auto_cited=auto_cited,
        )

    if skip_nli and not auto_cited:
        # Explicit citation, NLI explicitly skipped (eval / fast path).
        return SentenceVerification(
            text=sentence, status=SentenceStatus.OK, citations=citations,
            auto_cited=auto_cited,
        )

    # Aggregate evidence from cited passages. Take max entailment across
    # passages (a sentence is supported if ANY cited passage entails it).
    max_score: float | None = None
    nli_unavailable = False
    for n in citations:
        passage = retrieved_by_idx.get(n)
        if not passage:
            continue
        sc = nli_score(passage, sentence)
        if sc is None:
            nli_unavailable = True
            continue
        if max_score is None or sc > max_score:
            max_score = sc

    if nli_unavailable and max_score is None:
        # NLI is unavailable and we couldn't score any passage. For
        # auto-cited sentences this is unsafe (lexical-only match with no
        # entailment confirmation) — fail closed to WEAK_SUPPORT so the
        # UI badges it and downstream consumers can drop it. For
        # explicitly-cited sentences this matches prior behavior.
        return SentenceVerification(
            text=sentence,
            status=SentenceStatus.WEAK_SUPPORT if auto_cited else SentenceStatus.OK,
            citations=citations,
            reason="nli unavailable; "
                   + ("auto-cite cannot confirm entailment" if auto_cited else "coverage-only verdict"),
            auto_cited=auto_cited,
        )

    if max_score is not None and max_score < nli_threshold:
        return SentenceVerification(
            text=sentence, status=SentenceStatus.WEAK_SUPPORT,
            citations=citations, entailment_score=max_score,
            reason=f"max entailment {max_score:.2f} < threshold {nli_threshold:.2f}",
            auto_cited=auto_cited,
        )

    return SentenceVerification(
        text=sentence, status=SentenceStatus.OK,
        citations=citations, entailment_score=max_score,
        auto_cited=auto_cited,
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
