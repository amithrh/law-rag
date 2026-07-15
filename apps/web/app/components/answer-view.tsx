"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { readSse } from "../lib/sse";
import type {
  CoverageEvent,
  DisclaimerEvent,
  ErrorEvent as ApiErrorEvent,
  MatterRouteEvent,
  PassageEvent,
  RefusedEvent,
  RelevanceEvent,
  SentenceEvent,
  SourceGapEvent,
  SourcesEvent,
  StopEvent,
  TimingEvent,
} from "../lib/types";
import { CoverageChip } from "./coverage-chip";
import { IndexStatus } from "./index-status";
import { SentenceLine } from "./sentence-line";

// A timeline entry: either a real cited sentence or a gap marker
// produced when the server suppressed an uncited sentence. The UI
// renders gap markers as "…" so the reader can see that content was
// dropped (rather than silently disappearing from the answer).
type TimelineEntry =
  | { kind: "sentence"; sentence: SentenceEvent }
  | { kind: "gap" };

interface AnswerState {
  pending: boolean;
  matterRoute: MatterRouteEvent | null;
  coverage: CoverageEvent | null;
  sourceGap: SourceGapEvent | null;
  passages: PassageEvent[];
  // Server-authored authoritative source list (round-3). The UI prefers
  // this over `passages` when present — it's emitted at end-of-stream
  // and may diverge from the early retrieval snapshot once we add
  // post-filtering / redaction.
  sources: SourcesEvent | null;
  timeline: TimelineEntry[];
  // Convenience: sentences-only view for components that don't care
  // about gaps. Derived from `timeline` on read.
  sentences: SentenceEvent[];
  stop: StopEvent | null;
  refused: RefusedEvent | null;
  // Task #10: answer-vs-query relevance verdict. null until the server
  // emits the `relevance` event (only on the normal end path with a
  // non-empty answer body). When `verdict !== "ok"`, the UI renders a
  // notice — see the "off_topic" / "partial" Notice block below.
  relevance: RelevanceEvent | null;
  timing: TimingEvent | null;
  disclaimer: string | null;
  error: string | null;
  startedAt: number | null;
  finishedAt: number | null;
}

const INITIAL: AnswerState = {
  pending: false,
  matterRoute: null,
  coverage: null,
  sourceGap: null,
  passages: [],
  sources: null,
  timeline: [],
  sentences: [],
  stop: null,
  refused: null,
  relevance: null,
  timing: null,
  disclaimer: null,
  error: null,
  startedAt: null,
  finishedAt: null,
};

const EXAMPLES = [
  "Police did not file my FIR. What can I do?",
  "My employer has not paid my salary for two months. How do I recover it?",
  "Can I file for divorce on grounds of cruelty?",
  "My online order arrived broken. Can I get a refund?",
];

export function AnswerView() {
  const [q, setQ] = useState("");
  const [state, setState] = useState<AnswerState>(INITIAL);
  const abortRef = useRef<AbortController | null>(null);

  const passagesByIndex = useMemo(() => {
    const m = new Map<number, PassageEvent>();
    for (const p of state.passages) m.set(p.index, p);
    return m;
  }, [state.passages]);

  const submit = useCallback(
    async (query: string) => {
      const text = query.trim();
      if (!text) return;
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;
      setState({ ...INITIAL, pending: true, startedAt: performance.now() });

      try {
        // 2026-05-21: Next.js dev proxy times out at 30s but /answer needs
        // ~40-50s. Hit the API directly. The FastAPI side has CORS
        // configured for http://localhost:3000.
        const apiBase =
          process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
        const res = await fetch(`${apiBase}/answer`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          },
          body: JSON.stringify({ q: text, top_k: 8 }),
          signal: ac.signal,
        });
        if (!res.ok) {
          const body = await res.text().catch(() => "");
          throw new Error(`HTTP ${res.status}${body ? `: ${body.slice(0, 200)}` : ""}`);
        }

        for await (const packet of readSse(res, ac.signal)) {
          let data: unknown;
          try {
            data = JSON.parse(packet.data);
          } catch {
            continue;
          }
          setState((s) => applyEvent(s, packet.event, data));
        }
      } catch (e) {
        if (ac.signal.aborted) return;
        setState((s) => ({
          ...s,
          pending: false,
          error: e instanceof Error ? e.message : String(e),
          finishedAt: performance.now(),
        }));
        return;
      }
      setState((s) => ({ ...s, pending: false, finishedAt: performance.now() }));
    },
    [],
  );

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void submit(q);
  };

  const elapsed =
    state.startedAt && state.finishedAt
      ? Math.round(state.finishedAt - state.startedAt)
      : null;
  const answerMs = state.timing?.total_ms ?? elapsed;

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-10">
      <header className="mb-8">
        <div className="flex items-start justify-between gap-4">
          <h1 className="text-2xl font-semibold tracking-tight text-stone-900">
            Indian Law — Plain-language answers with citations
          </h1>
          <IndexStatus />
        </div>
        <p className="mt-2 text-sm text-stone-600">
          Ask in your own words. Answers cite the section or judgment they came
          from. Not legal advice — consult a lawyer for your specific situation.
        </p>
      </header>

      <form onSubmit={onSubmit} className="mb-2">
        <div className="flex gap-2">
          <input
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="e.g. Police did not file my FIR. What can I do?"
            className="flex-1 rounded-md border border-stone-300 bg-white px-4 py-3 text-base shadow-sm outline-none focus:border-stone-500 focus:ring-1 focus:ring-stone-400"
            disabled={state.pending}
            autoFocus
          />
          <button
            type="submit"
            disabled={state.pending || !q.trim()}
            className="rounded-md bg-stone-900 px-5 py-3 text-sm font-medium text-white shadow-sm hover:bg-stone-800 disabled:cursor-not-allowed disabled:bg-stone-400"
          >
            {state.pending ? "Working…" : "Ask"}
          </button>
        </div>
      </form>

      {!state.pending && !state.sentences.length && !state.refused && !state.error && (
        <div className="mt-3 mb-8 flex flex-wrap gap-2 text-xs">
          <span className="text-stone-500">Try:</span>
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => {
                setQ(ex);
                void submit(ex);
              }}
              className="rounded-full border border-stone-300 bg-white px-3 py-1 text-stone-700 hover:bg-stone-100"
            >
              {ex}
            </button>
          ))}
        </div>
      )}

      <section className="mt-6">
        {state.refused && (
          <Notice
            tone={state.refused.reason === "rerank_unavailable" ? "red" : "amber"}
            title={
              state.refused.reason === "rerank_unavailable"
                ? "Search service is having trouble"
                : "Not enough sources for this question"
            }
          >
            {state.refused.message}
          </Notice>
        )}

        {state.matterRoute && state.matterRoute.category !== "off_topic" && (
          <ActionPlan route={state.matterRoute} />
        )}

        {state.coverage && <CoverageChip coverage={state.coverage} />}

        {state.sourceGap && state.sourceGap.has_gap && (
          <Notice tone="amber" title="Controlling source not fully available">
            <span>{state.sourceGap.message}</span>
            {state.sourceGap.missing_required_sources.length > 0 && (
              <span className="mt-2 block text-xs">
                Missing:{" "}
                {state.sourceGap.missing_required_sources
                  .slice(0, 3)
                  .map((item) => item.required_source)
                  .join("; ")}
              </span>
            )}
          </Notice>
        )}

        {/* Task #10: relevance verdict notice. The answer text itself
            is still grounded by citations (NLI / bge gates verified each
            sentence). This notice is ADDITIVE — it warns when the
            cosine between query and answer-body falls below the
            calibrated threshold (the deposit-question failure mode). */}
        {state.relevance && state.relevance.verdict !== "ok" && (
          <Notice
            tone={state.relevance.verdict === "off_topic" ? "red" : "amber"}
            title={
              state.relevance.verdict === "off_topic"
                ? "This answer may not match your question"
                : "This answer may only partly match your question"
            }
          >
            {state.relevance.verdict === "off_topic"
              ? "This answer cites real law correctly, but the cited passages may not match your specific situation. If your question is different from what the answer addresses, please consult a lawyer or rephrase your question more specifically."
              : "Parts of this answer may not directly address your question. Read it carefully and, if anything seems off, consult a lawyer or rephrase your question more specifically."}
          </Notice>
        )}

        {(() => {
          // Round-4 UX: a 1-2 sentence stub after suppression is worse
          // than a clean refusal. Count non-meta sentences; if the
          // answer is thin AND stop fired, collapse to a refusal-style
          // notice and hide the orphan content.
          const nonMeta = state.sentences.filter((s) => s.status !== "meta");
          const isStub = state.stop !== null && nonMeta.length < 3;
          if (isStub) return null;
          return (
            <div className="rounded-lg bg-white p-5 shadow-sm ring-1 ring-stone-200">
              {state.sentences.length === 0 && state.pending && (
                <p className="text-sm text-stone-500">Retrieving and reading sources…</p>
              )}
              {state.sentences.length === 0 && !state.pending && !state.refused && !state.error && (
                <p className="text-sm text-stone-500">
                  Ask a question above. Answers stream in sentence by sentence and
                  cite the source of each claim.
                </p>
              )}
              {state.timeline.map((entry, i) =>
                entry.kind === "sentence" ? (
                  <SentenceLine
                    key={`s-${i}`}
                    sentence={entry.sentence}
                    passagesByIndex={passagesByIndex}
                  />
                ) : (
                  <p
                    key={`g-${i}`}
                    className="my-2 select-none text-stone-300"
                    title="A sentence was removed here because it didn't cite a passage in the index."
                  >
                    ⋯
                  </p>
                ),
              )}
            </div>
          );
        })()}

        {state.stop && (() => {
          const nonMeta = state.sentences.filter((s) => s.status !== "meta");
          const isStub = nonMeta.length < 3;
          return (
            <Notice
              tone="amber"
              title={isStub ? "I couldn't give you a confident answer" : "Stopped — not enough support"}
            >
              {isStub
                ? "The model wrote a few sentences but most of them couldn't be tied back to a source I have. I dropped them rather than show you uncited legal claims. Try rephrasing more concretely, or talk to a lawyer for your specific situation."
                : state.stop.message}
            </Notice>
          );
        })()}

        {state.error && (
          <Notice tone="red" title="Something went wrong">
            {state.error}
          </Notice>
        )}

        {(() => {
          // Prefer the server-authored authoritative source list. Fall
          // back to the early retrieval `passages` snapshot if the
          // sources event hasn't arrived yet (mid-stream or stream cut
          // short).
          const list: PassageEvent[] | null = state.sources ?? (
            state.passages.length > 0 ? state.passages : null
          );
          if (!list) return null;
          // Limit to indices the answer actually referenced — otherwise
          // we'd dump all retrieved passages even though only some were
          // cited.
          const cited = new Set<number>();
          for (const s of state.sentences) {
            for (const c of s.citations ?? []) cited.add(c);
          }
          const display = cited.size > 0
            ? list.filter((p) => cited.has(p.index))
            : list;
          if (display.length === 0) return null;
          return (
            <details
              className="mt-6 rounded-lg bg-white p-4 text-sm shadow-sm ring-1 ring-stone-200"
              open={display.length <= 4}
            >
              <summary className="cursor-pointer font-medium text-stone-800">
                Sources cited in this answer ({display.length})
              </summary>
              <ol className="mt-3 space-y-3">
                {display.map((p) => (
                  <li key={p.index} className="border-l-2 border-stone-300 pl-3">
                    <span className="block">
                      <span className="font-medium text-stone-900">
                        [{p.index}] {p.title}
                      </span>
                    </span>
                    <span className="block text-xs text-stone-500">
                      {p.court ? `${p.court} · ` : ""}
                      {p.citation ?? p.anchor}
                      {p.as_at ? ` · as-at ${p.as_at}` : ""}
                    </span>
                  </li>
                ))}
              </ol>
            </details>
          );
        })()}

        {(state.disclaimer || state.refused?.disclaimer) && (
          <p className="mt-6 border-t border-stone-200 pt-4 text-xs text-stone-500">
            {state.disclaimer ?? state.refused?.disclaimer}
          </p>
        )}

        {answerMs !== null && (
          <p className="mt-2 text-right text-[11px] text-stone-400">
            answered in {(answerMs / 1000).toFixed(1)}s
          </p>
        )}
        {state.timing && (
          <details className="mt-1 text-right text-[11px] text-stone-400">
            <summary className="cursor-pointer">stage timings</summary>
            <div className="mt-1 space-x-2">
              <span>preflight {fmtMs(state.timing.llm_preflight_ms)}</span>
              <span>retrieval {fmtMs(state.timing.retrieval_ms)}</span>
              <span>prompt {fmtMs(state.timing.prompt_build_ms)}</span>
              <span>llm {fmtMs(state.timing.llm_stream_ms)}</span>
              <span>verify {fmtMs(state.timing.verification_ms)}</span>
              {state.timing.relevance_ms !== undefined && (
                <span>relevance {fmtMs(state.timing.relevance_ms)}</span>
              )}
            </div>
            <div className="mt-1">
              {state.timing.llm_model} · {state.timing.retrieved_count} retrieved ·{" "}
              {state.timing.sentence_count ?? 0} checked
            </div>
          </details>
        )}
      </section>
    </div>
  );
}

function ActionPlan({ route }: { route: MatterRouteEvent }) {
  const pack = route.action_pack;
  const urgencyCls =
    route.urgency === "emergency" || route.urgency === "high"
      ? "bg-red-50 text-red-800 ring-red-200"
      : route.urgency === "medium"
        ? "bg-amber-50 text-amber-800 ring-amber-200"
        : "bg-emerald-50 text-emerald-800 ring-emerald-200";

  return (
    <section className="mb-4 rounded-lg bg-white p-4 text-sm shadow-sm ring-1 ring-stone-200">
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-medium text-stone-900">{route.label}</p>
        <span className={`rounded-full px-2 py-0.5 text-[11px] ring-1 ${urgencyCls}`}>
          {route.urgency}
        </span>
        {route.legal_regime && (
          <span className="rounded-full bg-stone-100 px-2 py-0.5 text-[11px] text-stone-600 ring-1 ring-stone-200">
            {route.legal_regime.replaceAll("_", " ")}
          </span>
        )}
      </div>

      {route.red_flags.length > 0 && (
        <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-red-900">
          <p className="font-medium">Urgent flags</p>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {route.red_flags.map((flag) => (
              <li key={flag}>{flag}</li>
            ))}
          </ul>
        </div>
      )}

      {pack && (
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          <div>
            <p className="font-medium text-stone-800">{pack.title}</p>
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-stone-700">
              {pack.next_steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          </div>
          <div>
            <p className="font-medium text-stone-800">Keep ready</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-stone-700">
              {pack.documents.slice(0, 5).map((doc) => (
                <li key={doc}>{doc}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {route.required_sources.length > 0 && (
        <div className="mt-3 rounded-md border border-stone-200 bg-stone-50 px-3 py-2 text-xs text-stone-700">
          <span className="font-medium text-stone-800">Sources to verify: </span>
          {route.required_sources.slice(0, 4).join(", ")}
        </div>
      )}

      <div className="mt-3 grid gap-3 text-xs text-stone-600 md:grid-cols-2">
        {route.forums.length > 0 && (
          <p>
            <span className="font-medium text-stone-700">Forum: </span>
            {route.forums.slice(0, 3).join(", ")}
          </p>
        )}
        {route.missing_facts.length > 0 && (
          <p>
            <span className="font-medium text-stone-700">Need: </span>
            {route.missing_facts.slice(0, 4).join(", ")}
          </p>
        )}
        {pack?.portals && pack.portals.length > 0 && (
          <p>
            <span className="font-medium text-stone-700">Portal: </span>
            {pack.portals.slice(0, 3).join(", ")}
          </p>
        )}
        {pack?.escalation && pack.escalation.length > 0 && (
          <p>
            <span className="font-medium text-stone-700">Escalate to: </span>
            {pack.escalation.slice(0, 3).join(", ")}
          </p>
        )}
      </div>

      {pack?.cautions && pack.cautions.length > 0 && (
        <p className="mt-3 text-xs text-stone-500">
          {pack.cautions[0]}
        </p>
      )}
    </section>
  );
}

function Notice({
  tone,
  title,
  children,
}: {
  tone: "amber" | "red";
  title: string;
  children: React.ReactNode;
}) {
  const cls =
    tone === "amber"
      ? "border-amber-300 bg-amber-50 text-amber-900"
      : "border-red-300 bg-red-50 text-red-900";
  return (
    <div className={`mb-4 rounded-md border ${cls} px-4 py-3 text-sm`}>
      <p className="font-medium">{title}</p>
      <p className="mt-1">{children}</p>
    </div>
  );
}

function applyEvent(s: AnswerState, event: string, data: unknown): AnswerState {
  switch (event) {
    case "coverage":
      return { ...s, coverage: data as CoverageEvent };
    case "source_gap":
      return { ...s, sourceGap: data as SourceGapEvent };
    case "matter_route":
      return { ...s, matterRoute: data as MatterRouteEvent };
    case "passages":
      return { ...s, passages: data as PassageEvent[] };
    case "sentence": {
      const sentence = data as SentenceEvent;
      return {
        ...s,
        timeline: [...s.timeline, { kind: "sentence", sentence }],
        sentences: [...s.sentences, sentence],
      };
    }
    case "suppressed":
      // Coalesce consecutive gaps so 4 dropped sentences in a row still
      // render as a single "…".
      if (s.timeline.length > 0 && s.timeline[s.timeline.length - 1].kind === "gap") {
        return s;
      }
      return { ...s, timeline: [...s.timeline, { kind: "gap" }] };
    case "stop":
      return { ...s, stop: data as StopEvent };
    case "refused":
      return { ...s, refused: data as RefusedEvent };
    case "sources":
      // Server-authored authoritative source list — overrides the
      // earlier `passages` snapshot for the final Sources block.
      return { ...s, sources: data as SourcesEvent };
    case "relevance":
      // Task #10: answer-vs-query relevance verdict. The UI renders a
      // notice for "partial" / "off_topic" (see the Notice block in
      // the JSX). Stored as-is so the verdict, score, and threshold
      // are all available for the notice text.
      return { ...s, relevance: data as RelevanceEvent };
    case "timing":
      return { ...s, timing: data as TimingEvent };
    case "disclaimer":
      return { ...s, disclaimer: (data as DisclaimerEvent).text };
    case "error":
      return { ...s, error: (data as ApiErrorEvent).message };
    default:
      return s;
  }
}

function fmtMs(value: number | undefined): string {
  if (value === undefined) return "-";
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`;
  return `${Math.round(value)}ms`;
}
