"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { parseSseData, readSse } from "../lib/sse";
import { isCurrentRequest } from "../lib/request-guard";
import {
  applyAnswerEvent,
  INITIAL_ANSWER_STATE,
  type AnswerState,
  canRevealPlannedAnswer,
  isSafeSourceGapHandoff,
  parseTimingEvent,
  PlannedSentenceGate,
} from "../lib/matter-plan";
import type {
  CoverageEvent,
  DisclaimerEvent,
  ErrorEvent as ApiErrorEvent,
  IntakeEvent,
  MatterPlanEvent,
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

const MAX_QUERY_LENGTH = 2000;
const REFINEMENT_PREFIX = "\n\nAdditional facts:\n";

const EXAMPLES = [
  "Police did not file my FIR. What can I do?",
  "My employer has not paid my salary for two months. How do I recover it?",
  "Can I file for divorce on grounds of cruelty?",
  "My online order arrived broken. Can I get a refund?",
];

export function AnswerView() {
  const [q, setQ] = useState("");
  const [intakeDraft, setIntakeDraft] = useState("");
  const [intakeChoices, setIntakeChoices] = useState<Record<string, string>>({});
  const [inputError, setInputError] = useState<string | null>(null);
  const [state, setState] = useState<AnswerState>(INITIAL_ANSWER_STATE);
  const abortRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);

  const passagesByIndex = useMemo(() => {
    const m = new Map<number, PassageEvent>();
    for (const p of state.passages) m.set(p.index, p);
    return m;
  }, [state.passages]);

  const submit = useCallback(
    async (query: string) => {
      const text = query.trim();
      if (!text) return;
      if (text.length > MAX_QUERY_LENGTH) {
        setInputError(`Please keep the question and added facts within ${MAX_QUERY_LENGTH} characters.`);
        return;
      }
      setInputError(null);
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;
      const requestId = requestIdRef.current + 1;
      requestIdRef.current = requestId;
      const isActive = () =>
        abortRef.current === ac && isCurrentRequest(requestId, requestIdRef.current, ac.signal);
      setIntakeDraft("");
      setIntakeChoices({});
      setState({ ...INITIAL_ANSWER_STATE, pending: true, startedAt: performance.now() });

      try {
        // Use the same-origin server proxy by default. It injects the API key
        // server-side in production; a public API base remains an explicit
        // development override for local debugging only.
        const apiBase = process.env.NEXT_PUBLIC_API_BASE;
        const endpoint = apiBase ? `${apiBase}/answer` : "/api/answer";
        const res = await fetch(endpoint, {
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
        const contentType = res.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase();
        if (contentType !== "text/event-stream") {
          throw new Error("answer endpoint returned a non-stream response");
        }

        let sawValidTerminalEvent = false;
        for await (const packet of readSse(res, ac.signal)) {
          if (!isActive()) return;
          let data: unknown = parseSseData(packet.data);
          if (packet.event === "timing") {
            const timing = parseTimingEvent(data);
            if (!timing) throw new Error("answer stream ended with invalid timing");
            sawValidTerminalEvent = true;
            data = timing;
          }
          setState((s) => (isActive() ? applyAnswerEvent(s, packet.event, data) : s));
        }
        if (!sawValidTerminalEvent) {
          throw new Error("answer stream ended without a terminal timing event");
        }
      } catch {
        if (!isActive()) return;
        setState((s) => {
          // A source-gap handoff is already a safe, actionable terminal
          // outcome. Preserve it when the transport closes before timing so
          // users do not lose the missing-authority explanation.
          if (s.sourceGapHandoffLatched && s.sourceGap?.outcome === "source_gap_handoff") {
            return {
              ...s,
              pending: false,
              error: null,
              finishedAt: performance.now(),
            };
          }
          return {
            ...INITIAL_ANSWER_STATE,
            pending: false,
            error: "The answer could not be completed safely. Please retry or contact DLSA/legal aid.",
            startedAt: s.startedAt,
            finishedAt: performance.now(),
          };
        });
        return;
      }
      if (!isActive()) return;
      setState((s) => ({
        ...s,
        pending: false,
        finishedAt: performance.now(),
        planContractError:
          s.sourceGapProtocolError ?? s.planContractError ?? (
            !s.sourceGapHandoffLatched && !s.matterPlan && s.sentences.length > 0
              ? "The answer stream did not include a valid MatterPlan v2 contract."
              : null
          ),
      }));
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
  const selectedFacts = Object.entries(intakeChoices)
    .filter(([, value]) => value.trim())
    .map(([id, value]) => `${id}: ${value}`)
    .join("\n");
  const maxDraftLength = Math.max(
    0,
    MAX_QUERY_LENGTH - q.trim().length - REFINEMENT_PREFIX.length -
      selectedFacts.length - (selectedFacts ? 1 : 0),
  );

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
            maxLength={MAX_QUERY_LENGTH}
            onChange={(e) => {
              setQ(e.target.value);
              setInputError(null);
            }}
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

      {inputError && (
        <p className="mb-3 text-sm text-red-700" role="alert">{inputError}</p>
      )}

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
                : state.refused.reason === "off_topic"
                  ? "Outside legal-help scope"
                : "Not enough sources for this question"
            }
          >
            {state.refused.message}
          </Notice>
        )}

        {state.planContractError && (
          <Notice tone="red" title="Answer plan unavailable">
            {state.planContractError} The legal answer has been hidden because its
            controlling-source plan cannot be verified. Please retry.
          </Notice>
        )}

        {state.matterPlan &&
          state.matterPlan.primary_issue !== "off_topic" &&
          !state.sourceGapHandoffLatched &&
          !isSafeSourceGapHandoff(state.sourceGap) && (
          <ActionPlan plan={state.matterPlan} />
        )}

        {state.sourceGap?.outcome === "source_gap_handoff" &&
          isSafeSourceGapHandoff(state.sourceGap) && (
            <SafeHandoffPanel route={state.matterRoute} />
          )}

        {state.intake && state.intake.questions.length > 0 && (
          <GuidedIntake
            intake={state.intake}
            draft={intakeDraft}
            choices={intakeChoices}
            onDraftChange={setIntakeDraft}
            onChoiceChange={(id, value) => {
              setIntakeChoices((current) => ({ ...current, [id]: value }));
            }}
            onRefine={() => {
              const additional = [selectedFacts, intakeDraft.trim()].filter(Boolean).join("\n");
              const refined = `${q.trim()}${REFINEMENT_PREFIX}${additional}`.trim();
              setQ(refined);
              void submit(refined);
            }}
            maxDraftLength={maxDraftLength}
            hasAnswers={Boolean(
              intakeDraft.trim() || Object.values(intakeChoices).some((value) => value.trim()),
            )}
          />
        )}

        {!state.sourceGapHandoffLatched && state.coverage && <CoverageChip coverage={state.coverage} />}

        {state.sourceGap && state.sourceGap.has_gap && (
          <Notice tone="amber" title="Controlling source not fully available">
            The controlling authority could not be verified for this question, so
            the legal answer is withheld. Use the preparation panel below to
            organize your records and ask DLSA/legal aid or a qualified lawyer to
            verify the source before acting.
          </Notice>
        )}

        {/* Task #10: relevance verdict notice. The answer text itself
            is still grounded by citations (NLI / bge gates verified each
            sentence). This notice is ADDITIVE — it warns when the
            cosine between query and answer-body falls below the
            calibrated threshold (the deposit-question failure mode). */}
        {canRevealPlannedAnswer(state.matterPlan, state.planContractError, state.sourceGapHandoffLatched) && state.relevance && state.relevance.verdict !== "ok" && (
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
          // A source-gap handoff deliberately contains one uncited guidance
          // sentence. It is the safe fallback, not an incomplete model stub,
          // so it must remain visible even when the answer has no citations.
          if (state.sourceGapHandoffLatched) return null;
          // Round-4 UX: a 1-2 sentence stub after suppression is worse
          // than a clean refusal. Count non-meta sentences; if the
          // answer is thin AND stop fired, collapse to a refusal-style
          // notice and hide the orphan content.
          const nonMeta = state.sentences.filter((s) => s.status !== "meta");
          const isStub = state.stop !== null && nonMeta.length < 3;
          if (isStub) return null;
          if (state.sentences.length > 0) {
            return (
              <PlannedSentenceGate
                plan={state.matterPlan}
                planContractError={state.planContractError}
                sourceGapHandoffLatched={state.sourceGapHandoffLatched}
                pending={state.pending}
              >
                <div className="rounded-lg bg-white p-5 shadow-sm ring-1 ring-stone-200">
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
              </PlannedSentenceGate>
            );
          }
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
            </div>
          );
        })()}

        {state.stop && canRevealPlannedAnswer(state.matterPlan, state.planContractError, state.sourceGapHandoffLatched) && (() => {
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
          if (!canRevealPlannedAnswer(state.matterPlan, state.planContractError, state.sourceGapHandoffLatched)) return null;
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

function SafeHandoffPanel({ route }: { route: MatterRouteEvent | null }) {
  if (!route || !route.intake_only) {
    return (
      <div className="mb-4 rounded-lg bg-white p-5 shadow-sm ring-1 ring-amber-200">
        <p className="font-medium text-stone-900">Safe intake handoff</p>
        <p className="mt-2 text-sm text-stone-700">
          Keep the key records and papers listed for this matter, then contact
          DLSA/legal aid or a qualified lawyer to verify the controlling authority
          before acting.
        </p>
      </div>
    );
  }
  return (
    <section className="mb-4 rounded-lg bg-white p-5 shadow-sm ring-1 ring-amber-200">
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-medium text-stone-900">Safe intake handoff</p>
        <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] text-amber-800 ring-1 ring-amber-200">
          source verification pending
        </span>
      </div>
      <p className="mt-2 text-sm text-stone-700">
        This is a preparation path, not a legal conclusion. Keep the records
        below and verify the controlling authority with DLSA/legal aid or a
        qualified lawyer before acting. The issue label is only a triage signal.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2">
        <p className="text-sm font-medium text-stone-900">{route.label}</p>
        <span className="rounded-full bg-white px-2 py-0.5 text-[11px] text-amber-800 ring-1 ring-amber-200">
          {route.urgency} urgency
        </span>
      </div>
      <div className="mt-4">
        <p className="font-medium text-stone-800">Prepare for verification</p>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-stone-700">
          <li>Write a short timeline with dates, people or offices involved, and the result you want.</li>
          <li>Keep copies of notices, applications, receipts, messages, photos, and other records; do not share passwords, OTPs, or full account numbers.</li>
          <li>Take this packet to DLSA/legal aid or a qualified lawyer and ask for the controlling source, forum, and deadline to be verified before acting.</li>
        </ol>
        <p className="mt-4 font-medium text-stone-800">Records to keep available</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-stone-700">
          <li>Notices, applications, receipts, messages, photos, and relevant identity or address proof.</li>
          <li>Any complaint, reference, acknowledgement, or order number.</li>
        </ul>
      </div>
      <p className="mt-4 text-xs text-stone-600">
        If there is immediate danger, arrest, self-harm risk, or medical danger,
        contact local emergency help, a hospital, or a trusted person first.
      </p>
    </section>
  );
}

function ActionPlan({ plan }: { plan: MatterPlanEvent }) {
  const requiredSources = plan.authority_ledger
    .filter((entry) => entry.must_cite)
    .map((entry) => entry.source);
  const urgencyCls =
    plan.urgency === "emergency" || plan.urgency === "high"
      ? "bg-red-50 text-red-800 ring-red-200"
      : plan.urgency === "medium"
        ? "bg-amber-50 text-amber-800 ring-amber-200"
        : "bg-emerald-50 text-emerald-800 ring-emerald-200";

  return (
    <section className="mb-4 rounded-lg bg-white p-4 text-sm shadow-sm ring-1 ring-stone-200">
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-medium text-stone-900">{plan.primary_label}</p>
        <span className={`rounded-full px-2 py-0.5 text-[11px] ring-1 ${urgencyCls}`}>
          {plan.urgency}
        </span>
        {plan.legal_regime && (
          <span className="rounded-full bg-stone-100 px-2 py-0.5 text-[11px] text-stone-600 ring-1 ring-stone-200">
            {plan.legal_regime.replaceAll("_", " ")}
          </span>
        )}
      </div>

      {plan.safety_flags.length > 0 && (
        <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-red-900">
          <p className="font-medium">Urgent flags</p>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {plan.safety_flags.map((flag) => (
              <li key={flag}>{flag}</li>
            ))}
          </ul>
        </div>
      )}

      {plan.action_pack_id && (
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          <div>
            <p className="font-medium text-stone-800">{plan.action_pack_title}</p>
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-stone-700">
              {plan.next_steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          </div>
          <div>
            <p className="font-medium text-stone-800">Keep ready</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-stone-700">
              {plan.documents.slice(0, 5).map((doc) => (
                <li key={doc}>{doc}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {requiredSources.length > 0 && (
        <div className="mt-3 rounded-md border border-stone-200 bg-stone-50 px-3 py-2 text-xs text-stone-700">
          <span className="font-medium text-stone-800">Sources to verify: </span>
          {requiredSources.slice(0, 4).join(", ")}
        </div>
      )}

      <div className="mt-3 grid gap-3 text-xs text-stone-600 md:grid-cols-2">
        {plan.forums.length > 0 && (
          <p>
            <span className="font-medium text-stone-700">Forum: </span>
            {plan.forums.slice(0, 3).join(", ")}
          </p>
        )}
        {plan.required_facts.length > 0 && (
          <p>
            <span className="font-medium text-stone-700">Need: </span>
            {plan.required_facts.slice(0, 4).join(", ")}
          </p>
        )}
        {plan.portals.length > 0 && (
          <p>
            <span className="font-medium text-stone-700">Portal: </span>
            {plan.portals.slice(0, 3).join(", ")}
          </p>
        )}
        {plan.escalation.length > 0 && (
          <p>
            <span className="font-medium text-stone-700">Escalate to: </span>
            {plan.escalation.slice(0, 3).join(", ")}
          </p>
        )}
      </div>

      {plan.cautions.length > 0 && (
        <p className="mt-3 text-xs text-stone-500">
          {plan.cautions[0]}
        </p>
      )}
    </section>
  );
}

function GuidedIntake({
  intake,
  draft,
  choices,
  onDraftChange,
  onChoiceChange,
  onRefine,
  maxDraftLength,
  hasAnswers,
}: {
  intake: IntakeEvent;
  draft: string;
  choices: Record<string, string>;
  onDraftChange: (value: string) => void;
  onChoiceChange: (id: string, value: string) => void;
  onRefine: () => void;
  maxDraftLength: number;
  hasAnswers: boolean;
}) {
  const hasSafetyQuestion = intake.questions.some((question) => question.id === "current_safety");
  const sourceGapCopy = intake.intake_kind === "source_gap_facts";
  const sourceGapQuestionCopy: Record<string, { prompt: string; reason: string; input_type: "text" | "date" }> = {
    jurisdiction: {
      prompt: "Which state, city, or district is this in?",
      reason: "Local procedure can differ by jurisdiction.",
      input_type: "text",
    },
    incident_date: {
      prompt: "What date did the incident, notice, or decision happen?",
      reason: "The applicable source may depend on the date.",
      input_type: "date",
    },
    document_status: {
      prompt: "What notice, document, complaint, or order do you have?",
      reason: "The document helps a lawyer or help desk verify the route.",
      input_type: "text",
    },
    desired_outcome: {
      prompt: "What result are you trying to obtain?",
      reason: "The desired result helps identify the correct authority to check.",
      input_type: "text",
    },
  };
  return (
    <section className="mb-4 rounded-lg bg-stone-50 p-4 text-sm ring-1 ring-stone-200">
      <p className="font-medium text-stone-900">To make this more specific</p>
      {hasSafetyQuestion && (
        <p className="mt-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-900">
          If you are in immediate danger, contact local emergency services or a trusted person now. This form is not emergency support.
        </p>
      )}
      <ol className="mt-2 list-decimal space-y-2 pl-5 text-stone-700">
        {intake.questions.map((question) => {
          const copy = sourceGapCopy ? sourceGapQuestionCopy[question.id] : question;
          if (!copy) return null;
          return (
            <li key={question.id}>
              <span>{copy.prompt}</span>
              <span className="mt-0.5 block text-xs text-stone-500">{copy.reason}</span>
              {!sourceGapCopy && question.input_type === "choice" && question.options.length > 0 && (
                <select
                  className="mt-2 w-full rounded-md border border-stone-300 bg-white px-2 py-2 text-sm text-stone-900"
                  value={choices[question.id] ?? ""}
                  onChange={(event) => onChoiceChange(question.id, event.target.value)}
                  aria-label={copy.prompt}
                >
                  <option value="">Select one</option>
                  {question.options.map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              )}
              {sourceGapCopy && copy.input_type === "date" && (
                <input
                  type="date"
                  className="mt-2 w-full rounded-md border border-stone-300 bg-white px-2 py-2 text-sm text-stone-900"
                  value={draft}
                  onChange={(event) => onDraftChange(event.target.value)}
                  aria-label={copy.prompt}
                />
              )}
            </li>
          );
        })}
      </ol>
      <textarea
        className="mt-3 min-h-20 w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm text-stone-900 outline-none focus:border-stone-500 focus:ring-2 focus:ring-stone-200"
        value={draft}
        maxLength={maxDraftLength}
        onChange={(event) => onDraftChange(event.target.value)}
        placeholder="Answer any of these in your own words"
        aria-label="Additional facts for a more specific answer"
      />
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-stone-500">
          {sourceGapCopy ? "Do not share passwords, OTPs, or full account numbers." : intake.privacy_note}
        </p>
        <button
          type="button"
          className="rounded-md bg-stone-900 px-3 py-2 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          onClick={onRefine}
          disabled={!hasAnswers}
        >
          Ask with these facts
        </button>
      </div>
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

function fmtMs(value: number | undefined): string {
  if (value === undefined) return "-";
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`;
  return `${Math.round(value)}ms`;
}
