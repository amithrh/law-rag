"""FastAPI app: /search, /answer (SSE stream with per-sentence verification gate).

Run with:
    cd <repo>
    PYTHONPATH=. .venv/bin/uvicorn apps.api.main:app --reload --port 8000
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from apps.api import config as cfg
from apps.api import metrics
from apps.api.db import close_pool, get_pool
from apps.api.llm import build_messages, load_answer_prompt, stream_chat
from apps.api.relevance import compute_relevance
from apps.api.retrieval import RetrievedChunk, hybrid_retrieve, multi_query_hybrid_retrieve
from apps.api.verifier import (
    AnswerVerification,
    SentenceStatus,
    SentenceVerification,
    segment_sentences,
    verify_sentence,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    yield
    await close_pool()


app = FastAPI(title="law-rag", lifespan=lifespan)

# CORS — added 2026-05-21 after frontend SSE proxy timed out at Next.js's
# 30s default. Bypassing the proxy means the browser calls :8000 directly,
# which avoids the timeout entirely. Dev-only allowlist; prod should restrict.
from fastapi.middleware.cors import CORSMiddleware as _CORSMiddleware

app.add_middleware(
    _CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.1.5:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# Standard disclaimer rendered server-side on every answer (PLAN §4.4)
DISCLAIMER_FOOTER = (
    "**Disclaimer**\n"
    "This is general legal information, not legal advice for your specific "
    "situation. Laws and their interpretation change. For decisions that "
    "affect your rights, consult a qualified lawyer or the relevant court / forum."
)


# ----- /search ---------------------------------------------------------------

class SearchResponseItem(BaseModel):
    chunk_id: int
    anchor: str
    text: str
    title: str
    source_type: str
    subject_area: str | None
    dense_score: float
    bm25_score: float
    sparse_score: float = 0.0
    combined_score: float
    rrf_score: float | None = None
    rerank_score: float | None
    as_at: str | None
    citation: str | None
    court: str | None


@app.get("/search")
async def search(
    q: str = Query(..., min_length=2),
    sources: str | None = Query(None, description="comma-separated subset of {sc_judgment,hc_judgment,bare_act,circular}"),
    subjects: str | None = Query(None, description="comma-separated subset of slice subject areas"),
    top_k: int = Query(20, ge=1, le=100),
):
    pool = await get_pool()
    src_types = [s.strip() for s in sources.split(",")] if sources else None
    subj = [s.strip() for s in subjects.split(",")] if subjects else None

    t0 = time.perf_counter()
    hits = await hybrid_retrieve(
        pool, q, source_types=src_types, subject_areas=subj, top_k=top_k,
    )
    elapsed = time.perf_counter() - t0
    metrics.retrieval_latency.observe(elapsed)
    elapsed_ms = elapsed * 1000

    return JSONResponse({
        "query": q,
        "took_ms": round(elapsed_ms, 1),
        "hits": [
            SearchResponseItem(
                chunk_id=h.chunk_id, anchor=h.anchor, text=h.text, title=h.title,
                source_type=h.source_type, subject_area=h.subject_area,
                dense_score=h.dense_score, bm25_score=h.bm25_score,
                sparse_score=h.sparse_score,
                combined_score=h.combined_score,
                rrf_score=h.rrf_score,
                rerank_score=h.rerank_score,
                as_at=h.as_at.isoformat() if h.as_at else None,
                citation=h.citation, court=h.court,
            ).model_dump()
            for h in hits
        ],
    })


# ----- /answer (SSE stream) --------------------------------------------------

class AnswerRequest(BaseModel):
    q: str
    sources: list[str] | None = None
    subjects: list[str] | None = None
    top_k: int = 8           # passages handed to the LLM
    # `skip_nli` is a CLIENT HINT, not a directive. Per round-3 review
    # (security #4): exposing it as a free toggle let a caller `curl ...
    # -d '{"skip_nli":true}'` and bypass NLI for every cited sentence,
    # shipping fabricated content with valid [N] indices. The server
    # honours this flag ONLY when settings.answer_fast_enabled=True
    # (an env-gated /answer-fast mode). In production
    # (answer_fast_enabled=False), the client hint is ignored and NLI
    # always runs.
    skip_nli: bool = False


def _make_passages(retrieved: list[RetrievedChunk], n: int) -> tuple[list[dict], dict[int, str]]:
    """Return (passages-for-prompt, idx-to-passage-text-map)."""
    passages: list[dict] = []
    idx_map: dict[int, str] = {}
    for i, h in enumerate(retrieved[:n], start=1):
        passages.append({
            "index": i,
            "text": h.text,
            "anchor": h.anchor,
            "title": h.title,
            "as_at": h.as_at.isoformat() if h.as_at else None,
            "court": h.court,
            "citation": h.citation,
            "statute_short": h.statute_short,
        })
        idx_map[i] = h.text
    return passages, idx_map


@app.post("/answer")
async def answer(req: AnswerRequest):
    """Stream-with-verification per PLAN §4.3 strict topology.

    Implementation strategy:
      - Retrieve passages.
      - Stream the LLM into an internal buffer.
      - Each time the buffer closes a sentence (pysbd), verify it.
      - Emit verified sentences as SSE events.
      - Public-product default: any `unsupported`/`unknown_citation`
        stops the stream and emits the structured fallback.

    NOTE: the current implementation buffers a small lookahead before
    verifying, so the very last (un-terminated) fragment is verified at
    stream-end. The parallel-with-generation optimization (PLAN §4.3 v1.5)
    requires moving LLM generation onto its own task; this v1 keeps it
    simple and sequential.
    """
    settings = cfg.get_settings()
    pool = await get_pool()
    src_filter_label = ",".join(sorted(req.sources)) if req.sources else "all"
    metrics.query_total.labels(source_filter=src_filter_label).inc()

    # NLI policy: the client hint is honoured ONLY when fast-mode is
    # enabled server-side. In production (answer_fast_enabled=False)
    # NLI always runs, regardless of what the request asks for. See
    # AnswerRequest comment + round-3 review #4.
    skip_nli = req.skip_nli and settings.answer_fast_enabled

    # Retrieve. Task #13: if query_expansion_enabled (default True), use
    # the multi-query path that asks the LLM to translate the lay query
    # into 2-3 legal-vocabulary variants and reranks the union. On the
    # 15 worst-failing queries from the 102-query e2e eval (2026-05-19,
    # scripts/eval_query_expand.py), this lifted the bare-act top-5
    # surface rate from 13% → 53% with 0 WORSE outcomes. Falls back to
    # plain hybrid_retrieve automatically on any expander error.
    src_types = req.sources
    subj = req.subjects
    t_retr = time.perf_counter()
    retrieved, expansion_variants = await multi_query_hybrid_retrieve(
        pool, req.q, source_types=src_types, subject_areas=subj,
        top_k=max(req.top_k, settings.rerank_top_k),
    )
    metrics.retrieval_latency.observe(time.perf_counter() - t_retr)
    if not retrieved:
        metrics.refused_total.inc()
        async def empty():
            yield {"event": "refused", "data": json.dumps({
                "message": "The sources I have don't cover this clearly. I won't guess. "
                           "You should talk to a lawyer for your specific situation.",
                "disclaimer": DISCLAIMER_FOOTER,
            })}
        return EventSourceResponse(empty())

    # Coverage gate: when the reranker can't find anything close to the
    # query, the LLM will either hallucinate or produce verbose "I don't
    # know" prose grounded in tangential passages. Refuse honestly instead.
    # Threshold derived empirically: in-slice queries score 0.6-0.9 at top;
    # out-of-slice (tenant, IP, "swallow") score < 0.15.
    #
    # Per Codex review (round 2) #3: the gate must fail CLOSED when rerank
    # scores are absent — the original implementation skipped the gate when
    # `top_rerank is None`, which is precisely the degraded state (reranker
    # disabled/unavailable/predict failure) where out-of-slice queries
    # would slip through. If reranking is enabled in config but scores are
    # missing, treat it as service degraded and refuse.
    rerank_scores = [h.rerank_score for h in retrieved if h.rerank_score is not None]
    top_rerank = max(rerank_scores, default=None)
    if settings.rerank_enabled and top_rerank is None:
        # Reranker is supposed to be running but produced no scores.
        # Fail closed.
        metrics.refused_total.inc()
        logger.warning(
            "coverage-gate refusal: reranker enabled but no rerank scores "
            "produced (degraded service) for query %r",
            req.q[:120],
        )
        async def degraded():
            yield {"event": "refused", "data": json.dumps({
                "message": "The retrieval service is in a degraded state right "
                           "now (the reranker did not return scores). I won't "
                           "answer without that quality signal. Please try again "
                           "shortly, or talk to a lawyer for your specific "
                           "situation.",
                "reason": "rerank_unavailable",
                "disclaimer": DISCLAIMER_FOOTER,
            })}
        return EventSourceResponse(degraded())
    if top_rerank is not None and top_rerank < settings.refuse_below_rerank:
        metrics.refused_total.inc()
        logger.info("coverage-gate refusal: top_rerank=%.3f < %.3f for query %r",
                    top_rerank, settings.refuse_below_rerank, req.q[:120])
        async def low_coverage():
            yield {"event": "refused", "data": json.dumps({
                "message": "I couldn't find sources in this index that clearly "
                           "cover your question. I won't make something up from "
                           "tangentially related judgments. Try asking the same "
                           "question more concretely — for example "
                           "'my landlord won't return my deposit' instead of "
                           "'tenant rights' — or talk to a lawyer or legal-aid "
                           "service for your specific situation.",
                "reason": "low_coverage",
                "disclaimer": DISCLAIMER_FOOTER,
            })}
        return EventSourceResponse(low_coverage())

    # Per round-3 review (security #5): when reranker is disabled in
    # config (operator chose ablation), the rerank-based gate above
    # can't fire — fall back to a calibrated combined-score gate on the
    # BM25+dense fusion so out-of-slice queries can't leak through the
    # disabled-rerank state.
    if not settings.rerank_enabled:
        top_combined = max((h.combined_score for h in retrieved), default=0.0)
        if top_combined < settings.refuse_below_combined:
            metrics.refused_total.inc()
            logger.info(
                "coverage-gate (no-rerank) refusal: top_combined=%.3f < %.3f for query %r",
                top_combined, settings.refuse_below_combined, req.q[:120],
            )
            async def low_dense():
                yield {"event": "refused", "data": json.dumps({
                    "message": "I couldn't find sources that clearly cover your "
                               "question. Try asking more concretely, or talk to "
                               "a lawyer or legal-aid service for your specific "
                               "situation.",
                    "reason": "low_coverage_dense_fallback",
                    "disclaimer": DISCLAIMER_FOOTER,
                })}
            return EventSourceResponse(low_dense())

    passages, idx_map = _make_passages(retrieved, req.top_k)

    # Build prompt
    system = load_answer_prompt()
    messages = build_messages(system=system, user_question=req.q, passages=passages)

    # Coverage chip — sent up front so the UI can render bounds immediately
    seen_sources = set()
    seen_subjects = set()
    for h in retrieved[:req.top_k]:
        seen_sources.add(h.source_type)
        if h.subject_area:
            seen_subjects.add(h.subject_area)

    async def event_stream() -> AsyncIterator[dict]:
        # Send the coverage chip first
        yield {"event": "coverage", "data": json.dumps({
            "sources_searched": sorted(seen_sources),
            "subjects_in_results": sorted(seen_subjects),
            "passages_used": len(passages),
        })}
        # Send the passages so the UI can render citation popovers eagerly
        yield {"event": "passages", "data": json.dumps([
            {"index": p["index"], "anchor": p["anchor"], "title": p["title"],
             "as_at": p["as_at"], "court": p["court"], "citation": p["citation"]}
            for p in passages
        ])}

        # Mutable state — closured into _check_and_emit so the strict-stop
        # check runs identically in the streaming-loop and final-flush paths.
        state = {
            "emitted": 0,
            "unsupported": 0,
            "skip_threshold": settings.skip_ratio_stop,
            "min_unsupported": settings.min_unsupported_before_stop,
            # Per Codex review (round 2) #4: the model can't be trusted to
            # author the Sources section — a fabricated "[1] SC — INVENTED
            # CASE v. SOMEONE, 2007, para 99." passes the [N] index check
            # while the case name is fiction. We strip everything between
            # the "**Sources**" header and the next major section header
            # (or end-of-stream) and emit our own authoritative sources
            # event from the retrieved metadata after the answer.
            "in_sources_section": False,
            # Strip the model's "**Disclaimer**" block the same way —
            # the server emits the canonical disclaimer event at end of
            # stream, so the model's version is just a duplicate (real
            # user reports showed "**Disclaimer** ..." rendered twice).
            "in_disclaimer_section": False,
            # Dedupe normalized sentence text — small Q4 models routinely
            # loop, emitting the same bullet 4-5 times in a row. The
            # verifier passes each one individually but the UX is broken.
            # Drop verbatim repeats.
            "seen_sentences": set(),
            # Task #10: accumulator for the user-visible answer body —
            # OK + WEAK_SUPPORT sentence texts only. After the stream
            # closes, this concatenation is embedded and compared with
            # the query to compute the relevance verdict.
            # META lines (headers, refusal text, disclaimers) and
            # SUPPRESSED sentences (unsupported, unconfirmed auto-cite)
            # are EXCLUDED — the relevance signal must reflect what the
            # user actually reads.
            "answer_body_sentences": [],
        }

        def _stop_event() -> dict:
            return {"event": "stop", "data": json.dumps({
                "reason": "insufficient_support",
                "message": ("The sources I have don't cover your question clearly "
                            "enough for me to give a useful answer. Try rephrasing "
                            "it more narrowly, or talk to a lawyer for your "
                            "specific situation."),
                "unsupported_count": state["unsupported"],
                "emitted_count": state["emitted"],
            })}

        def _suppressed_marker() -> dict:
            """Per round-3 UX review: a lightweight signal the UI renders as
            "…" so users can see when a sentence was dropped. Without this,
            the suppress path is invisible: the model wrote "X. Y (uncited).
            Z." and the user sees "X. Z." as if Y never existed."""
            return {"event": "suppressed", "data": json.dumps({})}

        def _emit_and_check(v: SentenceVerification) -> tuple[dict | None, bool]:
            """Return (sentence-event-or-None, should_stop_now).

            Per Codex adversarial review #1: we do NOT ship unsupported or
            unknown-citation sentences to the user — they get SUPPRESSED
            (event=None) while still counting against the stop budget. This
            preserves the citation guarantee (no uncited legal claim ever
            reaches the user) while letting harmless trailing fluff drop
            silently instead of killing the whole answer.

            Stop still fires when BOTH:
              (a) ratio of unsupported/emitted exceeds skip_threshold, AND
              (b) we've seen at least min_unsupported absolute count.
            With suppression, stop firing means most of the answer was
            uncited — a genuinely bad response — so the explicit banner
            is the right UX."""
            # Detect Sources-section boundary. Per round-3 review (security
            # finding #1) the model can write the header in many shapes
            # — "**Sources**", "## Sources", "Sources:", "SOURCES",
            # "References:", "** Sources **" — and any of those followed by
            # "[N] FAKE CASE v MADE UP, 2099" would ship as OK (valid [N]).
            # Match TOLERANTLY: any line that, after stripping markdown
            # markup, is just the word "sources" or "references".
            if _SOURCES_HEADER_RE.match(v.text.strip()):
                state["in_sources_section"] = True
                return None, False  # drop the header itself
            # Same treatment for the model's Disclaimer block — the server
            # emits the canonical disclaimer at end-of-stream, so anything
            # the model writes under "**Disclaimer**" is a duplicate.
            if _DISCLAIMER_HEADER_RE.match(v.text.strip()):
                state["in_disclaimer_section"] = True
                return None, False
            if state["in_sources_section"] or state["in_disclaimer_section"]:
                # End suppression on ANY major section header so an
                # answer that omits the closing header doesn't suppress
                # the rest of the stream. Both Sources and Disclaimer
                # are last-ish sections; any other major header means
                # the model moved on (defensive).
                if _MAJOR_HEADER_RE.match(v.text.strip()):
                    state["in_sources_section"] = False
                    state["in_disclaimer_section"] = False
                else:
                    return None, False  # inside Sources/Disclaimer, drop

            # Sentence dedupe — small models loop. Normalize and check.
            normalized = _normalize_for_dedupe(v.text)
            if normalized and normalized in state["seen_sentences"]:
                logger.debug("dedupe: dropping repeated sentence %r", v.text[:80])
                return None, False
            if normalized:
                state["seen_sentences"].add(normalized)

            is_bad = v.status in (
                SentenceStatus.UNSUPPORTED, SentenceStatus.UNKNOWN_CITATION,
            )
            # Per Codex review (round 2) #2: auto-cited sentences are
            # citation-by-lexical-overlap, NOT by entailment. If NLI cleared
            # them (status=OK) they're safe to emit. If NLI flagged them as
            # WEAK or was unavailable, they MUST be suppressed — a lexical
            # match without entailment confirmation is not citation evidence
            # and shipping it as cited prose breaks the citation guarantee.
            is_unconfirmed_auto_cite = (
                v.status == SentenceStatus.WEAK_SUPPORT and v.auto_cited
            )
            suppress = is_bad or is_unconfirmed_auto_cite
            if is_bad or is_unconfirmed_auto_cite:
                state["unsupported"] += 1
                # Use the closest existing status label for the metric so
                # the suppression rate is observable.
                metrics.unsupported_total.labels(
                    status=v.status.value if is_bad else "weak_auto_cite",
                ).inc()
            elif v.status == SentenceStatus.WEAK_SUPPORT:
                metrics.weak_support_total.inc()
            if v.status != SentenceStatus.META:
                state["emitted"] += 1
            triggered = (
                state["unsupported"] >= state["min_unsupported"]
                and state["emitted"]
                and state["unsupported"] / max(1, state["emitted"]) > state["skip_threshold"]
            )
            if suppress:
                # Lightweight marker so the UI can render "…" — see
                # _suppressed_marker docstring. We return it as the event
                # so the caller can yield it; counters still tick above.
                return _suppressed_marker(), triggered
            # Task #10: accumulate user-visible cited prose (OK or
            # WEAK_SUPPORT, never META) for the relevance check. We
            # store the sentence text WITHOUT the [N] citation tags so
            # the cosine reflects the claim itself, not the citation
            # numerals.
            if v.status in (SentenceStatus.OK, SentenceStatus.WEAK_SUPPORT):
                state["answer_body_sentences"].append(
                    _CITATION_TAG_RE.sub("", v.text).strip()
                )
            return _sentence_event(v), triggered

        buf = ""
        llm_t0 = time.perf_counter()
        first_token_seen = False
        try:
            async for delta in stream_chat(messages):
                if not first_token_seen and delta.strip():
                    metrics.llm_ttft.observe(time.perf_counter() - llm_t0)
                    first_token_seen = True
                buf += delta
                sentences = segment_sentences(buf)
                # Keep the LAST TWO segments in the buffer (1-sentence lookahead).
                # pysbd has no lookahead — a buffer ending in "Cr.P." will be
                # split there even though "C. [1]" is about to arrive in the
                # next token. Holding the tail sentence lets a later delta
                # re-merge the false split.
                #
                # CRITICAL: slice the ORIGINAL buf rather than joining the
                # segmented sentences back together. pysbd strips/normalizes
                # whitespace between segments, and re-joining with " "
                # injects spaces where the original had none ("Cr.P.\n"+"C."
                # → "Cr.P. C." → pysbd splits this forever). Sliced original
                # buf preserves the LLM's exact byte stream.
                if len(sentences) < 3:
                    continue
                ready = sentences[:-2]
                # Find where the last two sentences begin in buf by searching
                # for their text. pysbd stripped them so use lstrip-aware
                # search.
                tail_start = _find_tail_start(buf, sentences[-2])
                buf = buf[tail_start:] if tail_start >= 0 else " ".join(sentences[-2:])

                for sent in ready:
                    v = verify_sentence(sent, idx_map, skip_nli=skip_nli)
                    sentence_ev, should_stop = _emit_and_check(v)
                    if sentence_ev is not None:
                        yield sentence_ev
                    if should_stop:
                        metrics.stopped_total.inc()
                        yield _stop_event()
                        yield {"event": "disclaimer", "data": json.dumps({"text": DISCLAIMER_FOOTER})}
                        _record_final_metrics(state, llm_t0)
                        return

            # Flush the tail. Stream is done so there's no lookahead value
            # left — emit every remaining sentence. Strict-stop check applies
            # here too — a wrong final sentence is just as much a citation-
            # correctness defect.
            if buf.strip():
                for sent in segment_sentences(buf):
                    v = verify_sentence(sent, idx_map, skip_nli=skip_nli)
                    sentence_ev, should_stop = _emit_and_check(v)
                    if sentence_ev is not None:
                        yield sentence_ev
                    if should_stop:
                        metrics.stopped_total.inc()
                        yield _stop_event()
                        yield {"event": "disclaimer", "data": json.dumps({"text": DISCLAIMER_FOOTER})}
                        _record_final_metrics(state, llm_t0)
                        return

            # Server-authored authoritative Sources event. Per Codex review
            # (round 2) #4, the LLM is no longer allowed to author the
            # Sources section because it can fabricate case names while
            # using a real [N] index. The UI renders this `sources` event
            # exactly as-is from the retrieval result.
            yield {"event": "sources", "data": json.dumps([
                {
                    "index": p["index"],
                    "title": p["title"],
                    "court": p["court"],
                    "citation": p["citation"],
                    "anchor": p["anchor"],
                    "as_at": p["as_at"],
                }
                for p in passages
            ])}

            # Task #10: answer-vs-query relevance check. Embed the
            # original query and the concatenated answer body, compare
            # by cosine, classify by calibrated threshold. ADDITIVE — the
            # event is informational; the UI may render a notice but the
            # answer itself is not affected.
            #
            # Emit ONLY on the normal end path (after `sources`, before
            # `disclaimer`). NOT emitted on refused / stopped / empty-
            # body paths because there's nothing meaningful to score.
            if settings.answer_relevance_enabled and state["answer_body_sentences"]:
                body = " ".join(state["answer_body_sentences"]).strip()
                rel = compute_relevance(
                    req.q, body,
                    threshold=settings.answer_relevance_threshold,
                    band=settings.answer_relevance_band,
                )
                if rel is not None:
                    yield {"event": "relevance", "data": json.dumps({
                        "score": round(rel.score, 4),
                        "verdict": rel.verdict.value,
                        "threshold": round(rel.threshold, 4),
                        "band": round(rel.band, 4),
                    })}

            # Final disclaimer event — always
            yield {"event": "disclaimer", "data": json.dumps({"text": DISCLAIMER_FOOTER})}
            _record_final_metrics(state, llm_t0)
        except Exception as e:
            logger.exception("answer stream error: %s", e)
            yield {"event": "error", "data": json.dumps({"message": str(e)})}

    return EventSourceResponse(event_stream())


# Section-header detectors used by the Sources/Disclaimer stripping path.
# Match tolerantly so the model can't slip fabricated content through by
# varying header style. See main.py:_emit_and_check.
_SOURCES_HEADER_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*\s*)?(sources?|references?|bibliography)(?:\s*\*\*)?\s*:?\s*$",
    re.IGNORECASE,
)
_DISCLAIMER_HEADER_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*\s*)?disclaimer(?:\s*\*\*)?\s*:?\s*$",
    re.IGNORECASE,
)
_MAJOR_HEADER_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?\*\*\s*[A-Za-z][^*]+?\*\*\s*:?\s*$"
)

# Strip [N] / [1,2] / [1][2] citation tags from a sentence before
# embedding it for the relevance check (Task #10). bge-m3 doesn't know
# what "[1]" means — leaving the tag in just adds noise to the cosine.
_CITATION_TAG_RE = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")


def _normalize_for_dedupe(text: str) -> str:
    """Normalize a sentence for verbatim-repeat detection. Strip leading
    bullet markers, citation tags, surrounding whitespace, and casefold.
    A sentence like "- You may apply ... [1][2]." and "  You may apply ...
    [1] [2]" should compare equal."""
    s = text.strip()
    s = re.sub(r"^\s*[-*]\s*", "", s)
    s = re.sub(r"\[\d+\]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.lower().strip(" .;:")


def _find_tail_start(buf: str, second_to_last: str) -> int:
    """Locate where the second-to-last segmented sentence starts inside the
    original buffer text. pysbd strips outer whitespace and may normalize
    internal whitespace; we look for the first ~16-char prefix that survives
    intact, then return that index. Falls back to -1 if not found."""
    needle = second_to_last.strip()[:16]
    if not needle:
        return -1
    return buf.find(needle)


def _sentence_event(v: SentenceVerification) -> dict:
    return {
        "event": "sentence",
        "data": json.dumps({
            "text": v.text,
            "status": v.status.value,
            "citations": v.citations,
            "entailment_score": v.entailment_score,
            "reason": v.reason,
            "auto_cited": v.auto_cited,
        }),
    }


def _record_final_metrics(state: dict, llm_t0: float) -> None:
    """End-of-stream metrics (skip_ratio + total LLM time)."""
    metrics.llm_total.observe(time.perf_counter() - llm_t0)
    if state["emitted"]:
        metrics.skip_ratio.observe(state["unsupported"] / state["emitted"])


# ----- health ---------------------------------------------------------------

@app.get("/healthz")
async def healthz():
    pool = await get_pool()
    async with pool.acquire() as conn:
        chunk_count = await conn.fetchval("SELECT COUNT(*) FROM chunks WHERE NOT quarantined")
        doc_count = await conn.fetchval("SELECT COUNT(*) FROM documents")
    return {
        "status": "ok",
        "chunks": chunk_count,
        "documents": doc_count,
    }


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus scrape endpoint (PLAN §6.4)."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
