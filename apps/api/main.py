"""FastAPI app: /search, /answer (SSE stream with per-sentence verification gate).

Run with:
    cd <repo>
    PYTHONPATH=. .venv/bin/uvicorn apps.api.main:app --reload --port 8000
"""
from __future__ import annotations

import json
import logging
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
from apps.api.retrieval import RetrievedChunk, hybrid_retrieve
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
    combined_score: float
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
                combined_score=h.combined_score,
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
    skip_nli: bool = False   # /answer-fast variant; NLI on by default since Q1 bench (p95 72ms) makes it viable


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

    # Retrieve
    src_types = req.sources
    subj = req.subjects
    t_retr = time.perf_counter()
    retrieved = await hybrid_retrieve(
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
    top_rerank = max(
        (h.rerank_score for h in retrieved if h.rerank_score is not None),
        default=None,
    )
    if (
        top_rerank is not None
        and top_rerank < settings.refuse_below_rerank
    ):
        metrics.refused_total.inc()
        logger.info("coverage-gate refusal: top_rerank=%.3f < %.3f for query %r",
                    top_rerank, settings.refuse_below_rerank, req.q[:120])
        async def low_coverage():
            yield {"event": "refused", "data": json.dumps({
                "message": "I don't have sources in this index that clearly cover "
                           "your question. I won't guess from tangentially related "
                           "judgments. You should talk to a lawyer for your specific "
                           "situation, or rephrase the question to focus on the "
                           "specific law or section you're asking about.",
                "top_rerank_score": round(top_rerank, 3),
                "disclaimer": DISCLAIMER_FOOTER,
            })}
        return EventSourceResponse(low_coverage())

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
            is_bad = v.status in (
                SentenceStatus.UNSUPPORTED, SentenceStatus.UNKNOWN_CITATION,
            )
            if is_bad:
                state["unsupported"] += 1
                metrics.unsupported_total.labels(status=v.status.value).inc()
            elif v.status == SentenceStatus.WEAK_SUPPORT:
                metrics.weak_support_total.inc()
            if v.status != SentenceStatus.META:
                state["emitted"] += 1
            triggered = (
                state["unsupported"] >= state["min_unsupported"]
                and state["emitted"]
                and state["unsupported"] / max(1, state["emitted"]) > state["skip_threshold"]
            )
            # Suppress: don't yield bad sentences. The counters still tick;
            # if the answer is broadly uncited, `triggered` fires.
            ev = None if is_bad else _sentence_event(v)
            return ev, triggered

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
                    v = verify_sentence(sent, idx_map, skip_nli=req.skip_nli)
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
                    v = verify_sentence(sent, idx_map, skip_nli=req.skip_nli)
                    sentence_ev, should_stop = _emit_and_check(v)
                    if sentence_ev is not None:
                        yield sentence_ev
                    if should_stop:
                        metrics.stopped_total.inc()
                        yield _stop_event()
                        yield {"event": "disclaimer", "data": json.dumps({"text": DISCLAIMER_FOOTER})}
                        _record_final_metrics(state, llm_t0)
                        return

            # Final disclaimer event — always
            yield {"event": "disclaimer", "data": json.dumps({"text": DISCLAIMER_FOOTER})}
            _record_final_metrics(state, llm_t0)
        except Exception as e:
            logger.exception("answer stream error: %s", e)
            yield {"event": "error", "data": json.dumps({"message": str(e)})}

    return EventSourceResponse(event_stream())


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
