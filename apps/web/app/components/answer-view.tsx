"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { readSse } from "../lib/sse";
import type {
  CoverageEvent,
  DisclaimerEvent,
  ErrorEvent as ApiErrorEvent,
  PassageEvent,
  RefusedEvent,
  SentenceEvent,
  StopEvent,
} from "../lib/types";
import { CoverageChip } from "./coverage-chip";
import { IndexStatus } from "./index-status";
import { SentenceLine } from "./sentence-line";

interface AnswerState {
  pending: boolean;
  coverage: CoverageEvent | null;
  passages: PassageEvent[];
  sentences: SentenceEvent[];
  stop: StopEvent | null;
  refused: RefusedEvent | null;
  disclaimer: string | null;
  error: string | null;
  startedAt: number | null;
  finishedAt: number | null;
}

const INITIAL: AnswerState = {
  pending: false,
  coverage: null,
  passages: [],
  sentences: [],
  stop: null,
  refused: null,
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
        const res = await fetch("/api/answer", {
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
          <Notice tone="amber" title="Not enough sources for this question">
            {state.refused.message}
          </Notice>
        )}

        {state.coverage && <CoverageChip coverage={state.coverage} />}

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
          {state.sentences.map((s, i) => (
            <SentenceLine
              key={`s-${i}`}
              sentence={s}
              passagesByIndex={passagesByIndex}
            />
          ))}
        </div>

        {state.stop && (
          <Notice tone="amber" title="Stopped — not enough support">
            {state.stop.message}
            <span className="mt-1 block text-xs text-stone-500">
              {state.stop.unsupported_count} of {state.stop.emitted_count}{" "}
              sentence{state.stop.emitted_count === 1 ? "" : "s"} could not be
              verified against the sources.
            </span>
          </Notice>
        )}

        {state.error && (
          <Notice tone="red" title="Something went wrong">
            {state.error}
          </Notice>
        )}

        {state.passages.length > 0 && (
          <details className="mt-6 rounded-lg bg-white p-4 text-sm shadow-sm ring-1 ring-stone-200">
            <summary className="cursor-pointer font-medium text-stone-800">
              Sources ({state.passages.length})
            </summary>
            <ol className="mt-3 space-y-3">
              {state.passages.map((p) => (
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
        )}

        {(state.disclaimer || state.refused?.disclaimer) && (
          <p className="mt-6 border-t border-stone-200 pt-4 text-xs text-stone-500">
            {state.disclaimer ?? state.refused?.disclaimer}
          </p>
        )}

        {elapsed !== null && (
          <p className="mt-2 text-right text-[11px] text-stone-400">
            answered in {(elapsed / 1000).toFixed(1)}s
          </p>
        )}
      </section>
    </div>
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
    case "passages":
      return { ...s, passages: data as PassageEvent[] };
    case "sentence":
      return { ...s, sentences: [...s.sentences, data as SentenceEvent] };
    case "stop":
      return { ...s, stop: data as StopEvent };
    case "refused":
      return { ...s, refused: data as RefusedEvent };
    case "disclaimer":
      return { ...s, disclaimer: (data as DisclaimerEvent).text };
    case "error":
      return { ...s, error: (data as ApiErrorEvent).message };
    default:
      return s;
  }
}
