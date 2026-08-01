import { createElement, Fragment, type ReactNode } from "react";

import type {
  AuthorityLedgerEntry,
  CoverageEvent,
  DisclaimerEvent,
  IntakeEvent,
  IntakeQuestion,
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
} from "./types";

const SOURCE_GAP_INTAKE_QUESTION_IDS = new Set([
  "jurisdiction",
  "incident_date",
  "document_status",
  "desired_outcome",
]);

export function parseIntakeEvent(data: unknown): IntakeEvent | null {
  if (!isRecord(data) || data.schema_version !== 1) return null;
  if (
    typeof data.privacy_note !== "string" ||
    !Array.isArray(data.questions) ||
    data.questions.length === 0 ||
    data.questions.length > 3 ||
    !data.questions.every(isIntakeQuestion)
  ) {
    return null;
  }
  if (
    data.intake_kind !== undefined &&
    data.intake_kind !== "matter_plan_facts" &&
    data.intake_kind !== "source_gap_facts"
  ) {
    return null;
  }
  if (data.route_category !== undefined && !isNonEmptyString(data.route_category)) {
    return null;
  }
  if (
    data.intake_kind === "source_gap_facts" &&
    (!isNonEmptyString(data.route_category) ||
      !data.questions.every((question) => SOURCE_GAP_INTAKE_QUESTION_IDS.has(question.id)))
  ) {
    return null;
  }
  return data as unknown as IntakeEvent;
}

export function parseMatterRouteEvent(data: unknown): MatterRouteEvent | null {
  if (!isRecord(data)) return null;
  if (
    !isNonEmptyString(data.category) ||
    !isNonEmptyString(data.label) ||
    typeof data.confidence !== "number" ||
    !isUrgency(data.urgency) ||
    !isStringArray(data.required_sources) ||
    !isStringArray(data.forums) ||
    !isStringArray(data.missing_facts) ||
    !isStringArray(data.red_flags) ||
    (data.legal_regime !== null && typeof data.legal_regime !== "string") ||
    (data.intake_only !== undefined && typeof data.intake_only !== "boolean")
  ) {
    return null;
  }
  if (data.action_pack !== null) {
    if (!isRecord(data.action_pack)) return null;
    if (
      !isNonEmptyString(data.action_pack.id) ||
      !isNonEmptyString(data.action_pack.title) ||
      !isStringArray(data.action_pack.next_steps) ||
      !isStringArray(data.action_pack.documents) ||
      !isStringArray(data.action_pack.portals) ||
      !isStringArray(data.action_pack.escalation) ||
      !isStringArray(data.action_pack.cautions)
    ) {
      return null;
    }
    if (
      data.intake_only === true &&
      (
        data.action_pack.next_steps.length > 0 ||
        data.action_pack.documents.length > 0 ||
        data.action_pack.portals.length > 0 ||
        data.action_pack.escalation.length > 0 ||
        data.action_pack.cautions.length > 0
      )
    ) {
      return null;
    }
  }
  if (
    data.intake_only === true &&
    (
      data.required_sources.length > 0 ||
      data.forums.length > 0 ||
      data.legal_regime !== null
    )
  ) {
    return null;
  }
  return data as unknown as MatterRouteEvent;
}

export function parseSentenceEvent(data: unknown): SentenceEvent | null {
  if (!isRecord(data)) return null;
  if (
    !isNonEmptyString(data.text) ||
    !isSentenceStatus(data.status) ||
    !Array.isArray(data.citations) ||
    !data.citations.every((citation) => Number.isInteger(citation) && citation >= 0) ||
    (data.entailment_score !== null && typeof data.entailment_score !== "number") ||
    (data.reason !== null && typeof data.reason !== "string") ||
    (data.auto_cited !== undefined && typeof data.auto_cited !== "boolean")
  ) {
    return null;
  }
  return data as unknown as SentenceEvent;
}

export function parseMatterPlan(data: unknown): MatterPlanEvent | null {
  if (!isRecord(data) || data.schema_version !== 2) return null;
  if (
    typeof data.plan_id !== "string" ||
    !data.plan_id.startsWith("matter_plan_v2_") ||
    !isNonEmptyString(data.primary_issue) ||
    !isNonEmptyString(data.primary_label) ||
    typeof data.confidence !== "number" ||
    !isNonEmptyString(data.user_role) ||
    !isNonEmptyString(data.incident_date_status) ||
    !isNonEmptyString(data.case_stage) ||
    !isNonEmptyString(data.desired_outcome) ||
    !isUrgency(data.urgency) ||
    (data.legal_regime !== null && typeof data.legal_regime !== "string") ||
    (data.action_pack_id !== null && typeof data.action_pack_id !== "string") ||
    (data.action_pack_title !== null && typeof data.action_pack_title !== "string")
  ) {
    return null;
  }
  const stringArrayFields = [
    "required_facts",
    "secondary_issues",
    "forums",
    "remedies",
    "deadlines",
    "documents",
    "next_steps",
    "portals",
    "escalation",
    "cautions",
    "safety_flags",
  ] as const;
  if (stringArrayFields.some((field) => !isStringArray(data[field]))) return null;
  if (
    !isRecord(data.jurisdiction) ||
    (data.jurisdiction.state !== null && typeof data.jurisdiction.state !== "string") ||
    (data.jurisdiction.city !== null && typeof data.jurisdiction.city !== "string") ||
    (data.jurisdiction.forum_mentioned !== null && typeof data.jurisdiction.forum_mentioned !== "string") ||
    typeof data.jurisdiction.needs_state !== "boolean" ||
    !isRecord(data.answer_policy) ||
    !isNonEmptyString(data.answer_policy.required_primary_owner) ||
    !isNonEmptyString(data.answer_policy.fallback_owner) ||
    typeof data.answer_policy.allow_freeform_llm !== "boolean" ||
    typeof data.answer_policy.requires_reviewed_contract !== "boolean" ||
    !Array.isArray(data.authority_ledger) ||
    data.authority_ledger.length === 0 ||
    !data.authority_ledger.every(isAuthorityLedgerEntry) ||
    !data.authority_ledger.some(isEnforceableAuthorityObligation) ||
    !Array.isArray(data.retrieval_sources) ||
    data.retrieval_sources.length === 0 ||
    !data.retrieval_sources.every(isRetrievalSource)
  ) {
    return null;
  }
  return data as unknown as MatterPlanEvent;
}

export function parseSourceGapEvent(data: unknown): SourceGapEvent | null {
  if (!isRecord(data)) return null;
  if (
    typeof data.has_gap !== "boolean" ||
    !isNonEmptyString(data.route_category) ||
    !isStringArray(data.gap_kinds) ||
    !Array.isArray(data.missing_required_sources) ||
    !isNonEmptyString(data.message) ||
    !isNonEmptyString(data.handoff) ||
    (data.policy !== "do_not_substitute_neighboring_authority" &&
      data.policy !== "separate_conflicting_answer_owners")
  ) {
    return null;
  }
  if (!data.missing_required_sources.every(isSourceGapItem)) return null;
  // A source_gap event is an assertion that the answer must be withheld. A
  // contradictory no-gap packet must be treated as invalid, not as a benign
  // status update that could reopen the answer stream.
  if (data.has_gap !== true) return null;
  if (data.has_gap && data.outcome !== "source_gap_handoff") return null;
  if (data.outcome !== undefined && data.outcome !== "source_gap_handoff") return null;
  if (data.reason !== undefined && !isNonEmptyString(data.reason)) return null;
  if (data.safe_handoff_only !== undefined && typeof data.safe_handoff_only !== "boolean") return null;
  if (
    data.outcome === "source_gap_handoff" &&
    (data.has_gap !== true || data.safe_handoff_only !== true)
  ) return null;
  if (data.safe_handoff_only === true && data.outcome !== "source_gap_handoff") return null;
  return data as unknown as SourceGapEvent;
}

export function parseCoverageEvent(data: unknown): CoverageEvent | null {
  if (!isRecord(data)) return null;
  return (
    isStringArray(data.sources_searched) &&
    isStringArray(data.subjects_in_results) &&
    isNonNegativeFiniteNumber(data.passages_used)
  ) ? data as unknown as CoverageEvent : null;
}

export function parsePassagesEvent(data: unknown): PassageEvent[] | null {
  if (!Array.isArray(data) || !data.every(isPassageEvent)) return null;
  return data as PassageEvent[];
}

export function parseStopEvent(data: unknown): StopEvent | null {
  if (!isRecord(data)) return null;
  return (
    isNonEmptyString(data.reason) &&
    isNonEmptyString(data.message) &&
    isNonNegativeFiniteNumber(data.unsupported_count) &&
    isNonNegativeFiniteNumber(data.emitted_count)
  ) ? data as unknown as StopEvent : null;
}

export function parseRefusedEvent(data: unknown): RefusedEvent | null {
  if (!isRecord(data)) return null;
  const validReason = data.reason === undefined ||
    data.reason === "rerank_unavailable" ||
    data.reason === "low_coverage" ||
    data.reason === "low_coverage_dense_fallback" ||
    data.reason === "critical_route_needs_reviewed_contract" ||
    data.reason === "off_topic";
  const validScore = (value: unknown) =>
    value === undefined || isNonNegativeFiniteNumber(value);
  return (
    isNonEmptyString(data.message) &&
    isNonEmptyString(data.disclaimer) &&
    validReason &&
    validScore(data.top_rerank_score) &&
    validScore(data.top_combined_score)
  ) ? data as unknown as RefusedEvent : null;
}

export function parseRelevanceEvent(data: unknown): RelevanceEvent | null {
  if (!isRecord(data)) return null;
  return (
    isNonNegativeFiniteNumber(data.score) &&
    (data.verdict === "ok" || data.verdict === "partial" || data.verdict === "off_topic") &&
    isNonNegativeFiniteNumber(data.threshold) &&
    isNonNegativeFiniteNumber(data.band)
  ) ? data as unknown as RelevanceEvent : null;
}

export function parseDisclaimerEvent(data: unknown): DisclaimerEvent | null {
  if (!isRecord(data) || !isNonEmptyString(data.text)) return null;
  return data as unknown as DisclaimerEvent;
}

export function parseTimingEvent(data: unknown): TimingEvent | null {
  if (!isRecord(data)) return null;
  const isNonNegativeFinite = (value: unknown): value is number =>
    typeof value === "number" && Number.isFinite(value) && value >= 0;
  const requiredNumeric = [
    "total_ms",
    "retrieved_count",
    "passages_used",
    "expansion_variant_count",
  ];
  if (
    !requiredNumeric.every((field) => isNonNegativeFinite(data[field])) ||
    typeof data.llm_model !== "string" ||
    data.llm_model.length === 0 ||
    typeof data.llm_model_available !== "boolean"
  ) {
    return null;
  }
  const optionalNumeric = [
    "llm_preflight_ms",
    "retrieval_ms",
    "prompt_build_ms",
    "llm_stream_ms",
    "verification_ms",
    "relevance_ms",
    "sentence_count",
    "unsupported_count",
  ];
  if (
    optionalNumeric.some(
      (field) => data[field] !== undefined && !isNonNegativeFinite(data[field]),
    )
  ) {
    return null;
  }
  return data as unknown as TimingEvent;
}

export function isSafeSourceGapHandoff(sourceGap: SourceGapEvent | null): boolean {
  // The outcome itself is a non-answer contract. Keep this independent of
  // the plan so a contradictory plan event cannot reopen operative guidance.
  return sourceGap?.outcome === "source_gap_handoff";
}

export function updateSourceGapHandoffLatch(previous: boolean, data: unknown): boolean {
  if (previous) return true;
  const sourceGap = parseSourceGapEvent(data);
  // Invalid coverage signals fail closed just like an explicit handoff.
  return sourceGap === null || sourceGap.outcome === "source_gap_handoff";
}

export interface SourceGapProtocolState {
  sourceGap: SourceGapEvent | null;
  sourceGapProtocolError: string | null;
  planContractError: string | null;
  sourceGapHandoffLatched: boolean;
}

export function reduceSourceGapProtocol(
  state: SourceGapProtocolState,
  data: unknown,
  expectedRouteCategory?: string,
): SourceGapProtocolState {
  const sourceGap = parseSourceGapEvent(data);
  if (
    sourceGap &&
    expectedRouteCategory &&
    sourceGap.route_category !== expectedRouteCategory
  ) {
    const protocolError = "The source coverage signal did not match the current matter route.";
    const preservedHandoff =
      state.sourceGapHandoffLatched && state.sourceGap?.outcome === "source_gap_handoff"
        ? state.sourceGap
        : null;
    return {
      ...state,
      sourceGap: preservedHandoff ?? {
        has_gap: true,
        route_category: expectedRouteCategory,
        gap_kinds: ["invalid_source_gap_payload"],
        missing_required_sources: [],
        message: "I could not verify the source coverage for this answer. I will not show an unsupported legal conclusion.",
        handoff: "DLSA/legal aid or a qualified lawyer",
        policy: "do_not_substitute_neighboring_authority",
        outcome: "source_gap_handoff",
        reason: "invalid_source_gap_payload",
        safe_handoff_only: true,
      },
      planContractError: protocolError,
      sourceGapProtocolError: protocolError,
      sourceGapHandoffLatched: true,
    };
  }
  if (sourceGap) {
    const preservedHandoff =
      state.sourceGapHandoffLatched && state.sourceGap?.outcome === "source_gap_handoff"
        ? state.sourceGap
        : sourceGap;
    return {
      ...state,
      sourceGap: preservedHandoff,
      // A validated handoff is a complete non-answer contract. Do not leave
      // an earlier malformed-plan error visible beside the safe handoff.
      sourceGapProtocolError: null,
      planContractError: null,
      sourceGapHandoffLatched: updateSourceGapHandoffLatch(
        state.sourceGapHandoffLatched,
        data,
      ),
    };
  }
  const protocolError = "The source coverage signal was invalid; the answer is hidden until you retry.";
  const preservedHandoff =
    state.sourceGapHandoffLatched && state.sourceGap?.outcome === "source_gap_handoff"
      ? state.sourceGap
      : null;
  return {
    ...state,
    sourceGap: preservedHandoff ?? {
        has_gap: true,
        route_category: "unknown",
        gap_kinds: ["invalid_source_gap_payload"],
        missing_required_sources: [],
        message: "I could not verify the source coverage for this answer. I will not show an unsupported legal conclusion.",
        handoff: "DLSA/legal aid or a qualified lawyer",
        policy: "do_not_substitute_neighboring_authority",
        outcome: "source_gap_handoff",
        reason: "invalid_source_gap_payload",
        safe_handoff_only: true,
      },
    planContractError: protocolError,
    sourceGapProtocolError: protocolError,
    sourceGapHandoffLatched: true,
  };
}

export function canRevealPlannedAnswer(
  plan: MatterPlanEvent | null,
  planContractError: string | null,
  sourceGapHandoffLatched = false,
): boolean {
  return plan !== null && planContractError === null && !sourceGapHandoffLatched;
}

export function PlannedSentenceGate({
  plan,
  planContractError,
  sourceGapHandoffLatched,
  pending,
  children,
}: {
  plan: MatterPlanEvent | null;
  planContractError: string | null;
  sourceGapHandoffLatched: boolean;
  pending: boolean;
  children: ReactNode;
}) {
  if (canRevealPlannedAnswer(plan, planContractError, sourceGapHandoffLatched)) {
    return createElement(Fragment, null, children);
  }
  if (!pending || planContractError) return null;
  return createElement(
    "div",
    { className: "rounded-lg bg-white p-5 shadow-sm ring-1 ring-stone-200" },
    createElement(
      "p",
      { className: "text-sm text-stone-500" },
      "Validating the legal matter plan…",
    ),
  );
}

export type TimelineEntry =
  | { kind: "sentence"; sentence: SentenceEvent }
  | { kind: "gap" };

export interface AnswerState {
  pending: boolean;
  matterRoute: MatterRouteEvent | null;
  matterPlan: MatterPlanEvent | null;
  intake: IntakeEvent | null;
  planContractError: string | null;
  sourceGapProtocolError: string | null;
  sourceGapHandoffLatched: boolean;
  coverage: CoverageEvent | null;
  sourceGap: SourceGapEvent | null;
  passages: PassageEvent[];
  sources: SourcesEvent | null;
  timeline: TimelineEntry[];
  sentences: SentenceEvent[];
  stop: StopEvent | null;
  refused: RefusedEvent | null;
  relevance: RelevanceEvent | null;
  timing: TimingEvent | null;
  disclaimer: string | null;
  error: string | null;
  startedAt: number | null;
  finishedAt: number | null;
}

function invalidSourceGapForRoute(routeCategory: string): SourceGapEvent {
  return {
    has_gap: true,
    route_category: routeCategory,
    gap_kinds: ["invalid_source_gap_payload"],
    missing_required_sources: [],
    message: "I could not verify the source coverage for this answer. I will not show an unsupported legal conclusion.",
    handoff: "DLSA/legal aid or a qualified lawyer",
    policy: "do_not_substitute_neighboring_authority",
    outcome: "source_gap_handoff",
    reason: "intake_only_route_without_source_gap",
    safe_handoff_only: true,
  };
}

export const INITIAL_ANSWER_STATE: AnswerState = {
  pending: false,
  matterRoute: null,
  matterPlan: null,
  intake: null,
  planContractError: null,
  sourceGapProtocolError: null,
  sourceGapHandoffLatched: false,
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

export function applyAnswerEvent(
  state: AnswerState,
  event: string,
  data: unknown,
): AnswerState {
  if (state.error !== null && event !== "error") return state;
  // A refusal is a terminal non-answer. Only terminal metadata may follow;
  // late route/plan/sentence events must not reopen legal content.
  if (
    state.refused !== null &&
    event !== "timing" &&
    event !== "disclaimer" &&
    event !== "error"
  ) return state;
  // `timing` is the server's terminal protocol marker. Keep the disclaimer
  // as the only permitted trailing metadata event; never let a late sentence,
  // source, plan, or error reopen a completed answer.
  if (
    state.timing !== null &&
    event !== "disclaimer" &&
    event !== "source_gap" &&
    event !== "refused"
  ) return state;
  switch (event) {
    case "matter_route": {
      if (state.sourceGapHandoffLatched) return state;
      const route = parseMatterRouteEvent(data);
      if (!route) {
        return {
            ...state,
            matterRoute: null,
            planContractError: "The server sent an invalid matter-route payload.",
          };
      }
      if (route.intake_only === true) {
        return {
          ...state,
          matterRoute: route,
          matterPlan: null,
          intake: null,
          coverage: null,
          passages: [],
          sources: null,
          timeline: [],
          sentences: [],
          stop: null,
          refused: null,
          relevance: null,
          disclaimer: null,
          timing: null,
          error: null,
          sourceGap: state.sourceGap ?? invalidSourceGapForRoute(route.category),
          sourceGapProtocolError: null,
          planContractError: null,
          sourceGapHandoffLatched: true,
        };
      }
      return { ...state, matterRoute: route };
    }
    case "coverage":
      if (state.sourceGapHandoffLatched) return state;
      {
        const coverage = parseCoverageEvent(data);
        return coverage
          ? { ...state, coverage }
          : {
              ...state,
              matterPlan: null,
              coverage: null,
              planContractError: "The server sent an invalid coverage payload.",
            };
      }
    case "source_gap": {
      const protocol = reduceSourceGapProtocol({
        sourceGap: state.sourceGap,
        sourceGapProtocolError: state.sourceGapProtocolError,
        planContractError: state.planContractError,
        sourceGapHandoffLatched: state.sourceGapHandoffLatched,
      }, data, state.matterRoute?.category);
      if (!protocol.sourceGapHandoffLatched) return { ...state, ...protocol };
      return {
        ...state,
        matterRoute: state.matterRoute,
        matterPlan: null,
        // A jurisdictional source gap may be followed by a bounded intake
        // event. Clear any prior intake so it cannot survive a new handoff.
        intake: null,
        coverage: null,
        passages: [],
        sources: null,
        timeline: [],
        sentences: [],
        stop: null,
        refused: null,
        relevance: null,
        disclaimer: null,
        error: null,
        timing: null,
        ...protocol,
      };
    }
    case "intake": {
      const intake = parseIntakeEvent(data);
      if (!intake) return state;
      if (state.sourceGapHandoffLatched) {
        if (
          !state.sourceGap?.gap_kinds.includes("state_or_local_authority_gap") ||
          intake.intake_kind !== "source_gap_facts" ||
          intake.route_category !== state.sourceGap.route_category ||
          (state.matterRoute !== null && intake.route_category !== state.matterRoute.category) ||
          !intake.questions.every((question) => SOURCE_GAP_INTAKE_QUESTION_IDS.has(question.id))
        ) {
          return state;
        }
      } else if (intake.intake_kind === "source_gap_facts") {
        // A source-gap packet is only meaningful after the matching handoff.
        return state;
      }
      return intake ? { ...state, intake } : state;
    }
    case "matter_plan": {
      if (state.sourceGapHandoffLatched) return state;
      const plan = parseMatterPlan(data);
      return plan
        ? {
            ...state,
            matterPlan: plan,
            planContractError: state.sourceGapProtocolError ?? state.planContractError,
          }
        : {
            ...state,
            matterPlan: null,
            planContractError: "The server sent an invalid MatterPlan payload.",
          };
    }
    case "passages":
      if (state.sourceGapHandoffLatched) return state;
      {
        const passages = parsePassagesEvent(data);
        return passages
          ? { ...state, passages }
          : {
              ...state,
              matterPlan: null,
              passages: [],
              planContractError: "The server sent an invalid passages payload.",
            };
      }
    case "sentence": {
      const sentence = parseSentenceEvent(data);
      if (!sentence) {
        return state.sourceGapHandoffLatched
          ? state
          : {
              ...state,
              matterPlan: null,
              sentences: [],
              timeline: [],
              planContractError: "The server sent an invalid answer sentence.",
            };
      }
      // The source-gap panel is client-authored and bounded. Ignore every
      // sentence event after a handoff; even a metadata-shaped uncited string
      // must not become an alternate legal-advice channel.
      if (state.sourceGapHandoffLatched) return state;
      return {
        ...state,
        timeline: [...state.timeline, { kind: "sentence", sentence }],
        sentences: [...state.sentences, sentence],
      };
    }
    case "suppressed":
      if (state.timeline.length > 0 && state.timeline[state.timeline.length - 1].kind === "gap") {
        return state;
      }
      return { ...state, timeline: [...state.timeline, { kind: "gap" }] };
    case "stop":
      if (state.sourceGapHandoffLatched) return state;
      {
        const stop = parseStopEvent(data);
        return stop
          ? { ...state, stop }
          : {
              ...state,
              matterPlan: null,
              stop: null,
              planContractError: "The server sent an invalid stop payload.",
            };
      }
    case "refused":
      if (state.sourceGapHandoffLatched) return state;
      {
        const refused = parseRefusedEvent(data);
        return refused
          ? {
              ...state,
              matterPlan: null,
              intake: null,
              coverage: null,
              sourceGap: null,
              passages: [],
              sources: null,
              timeline: [],
              sentences: [],
              stop: null,
              relevance: null,
              disclaimer: null,
              planContractError: null,
              sourceGapProtocolError: null,
              sourceGapHandoffLatched: false,
              refused,
            }
          : {
              ...state,
              matterPlan: null,
              refused: null,
              planContractError: "The server sent an invalid refusal payload.",
            };
      }
    case "sources":
      if (state.sourceGapHandoffLatched) return state;
      {
        const sources = parsePassagesEvent(data);
        return sources
          ? { ...state, sources }
          : {
              ...state,
              matterPlan: null,
              sources: null,
              planContractError: "The server sent an invalid sources payload.",
            };
      }
    case "relevance":
      if (state.sourceGapHandoffLatched) return state;
      {
        const relevance = parseRelevanceEvent(data);
        return relevance
          ? { ...state, relevance }
          : {
              ...state,
              matterPlan: null,
              relevance: null,
              planContractError: "The server sent an invalid relevance payload.",
            };
      }
    case "timing":
      return parseTimingEvent(data)
        ? { ...state, timing: data as TimingEvent }
        : {
            ...state,
            matterPlan: null,
            sentences: [],
            timeline: [],
            planContractError: "The answer timing signal was invalid; please retry.",
            pending: false,
            error: "The answer could not be completed safely. Please retry or contact DLSA/legal aid.",
          };
    case "disclaimer":
      {
        const disclaimer = parseDisclaimerEvent(data);
        return disclaimer
          ? { ...state, disclaimer: disclaimer.text }
          : {
              ...state,
              planContractError: "The server sent an invalid disclaimer payload.",
            };
      }
    case "error":
      {
        const preservedHandoff =
          state.sourceGapHandoffLatched && state.sourceGap?.outcome === "source_gap_handoff"
            ? state.sourceGap
            : null;
        return {
          ...INITIAL_ANSWER_STATE,
          matterRoute: preservedHandoff ? state.matterRoute : null,
          sourceGap: preservedHandoff,
          sourceGapHandoffLatched: Boolean(preservedHandoff),
          sourceGapProtocolError: preservedHandoff ? state.sourceGapProtocolError : null,
          planContractError: preservedHandoff ? state.planContractError : null,
          pending: false,
          startedAt: state.startedAt,
          finishedAt: state.finishedAt,
          error: preservedHandoff
            ? null
            : "The answer could not be completed safely. Please retry or contact DLSA/legal aid.",
        };
      }
    default:
      return state;
  }
}

function isAuthorityLedgerEntry(entry: unknown): entry is AuthorityLedgerEntry {
  if (!isRecord(entry)) return false;
  return (
    isNonEmptyString(entry.source) &&
    isNonEmptyString(entry.authority_id) &&
    (entry.identity_status === "canonical" || entry.identity_status === "provisional") &&
    (entry.canonical_name === null || typeof entry.canonical_name === "string") &&
    (entry.act === null || typeof entry.act === "string") &&
    (entry.section === null || typeof entry.section === "string") &&
    (entry.source_pack_id === null || isNonEmptyString(entry.source_pack_id)) &&
    isStringArray(entry.required_anchor_patterns) &&
    typeof entry.claim_type === "string" &&
    (entry.priority === "must_cite" || entry.priority === "conditional" || entry.priority === "background") &&
    typeof entry.must_cite === "boolean" &&
    (entry.priority === "must_cite") === entry.must_cite &&
    typeof entry.conditional === "boolean" &&
    (entry.note === null || typeof entry.note === "string")
  );
}

function isEnforceableAuthorityObligation(entry: unknown): boolean {
  return (
    isAuthorityLedgerEntry(entry) &&
    entry.priority === "must_cite" &&
    entry.must_cite === true &&
    isNonEmptyString(entry.source_pack_id) &&
    isNonEmptyString(entry.authority_id) &&
    (
      entry.identity_status === "canonical" ||
      // Released deterministic workflow contracts may use a provisional
      // authority ID when the exact reviewed source pack and its required
      // section anchors are present. Generic title-only authorities remain
      // non-renderable until a registry identity is available.
      (
        entry.identity_status === "provisional" &&
        entry.note === "plan_owned_contract_required_source" &&
        entry.required_anchor_patterns.length > 0
      )
    )
  );
}

function isRetrievalSource(source: unknown): boolean {
  if (!isRecord(source)) return false;
  return (
    isNonEmptyString(source.source_pack_id) &&
    isStringArray(source.title_patterns) &&
    isNonEmptyString(source.search_query) &&
    isStringArray(source.doc_ids) &&
    isStringArray(source.anchor_patterns) &&
    isStringArray(source.source_types) &&
    typeof source.priority === "number" &&
    (source.selection_terms === undefined || isStringArray(source.selection_terms))
  );
}

function isSourceGapItem(item: unknown): boolean {
  if (!isRecord(item)) return false;
  return (
    isNonEmptyString(item.required_source) &&
    isNonEmptyString(item.kind) &&
    (item.authority_id === undefined || item.authority_id === null || typeof item.authority_id === "string") &&
    (item.source_pack_id === undefined || item.source_pack_id === null || typeof item.source_pack_id === "string") &&
    (item.identity_status === undefined || item.identity_status === null || item.identity_status === "canonical" || item.identity_status === "provisional") &&
    (item.match_mode === undefined || item.match_mode === null || isNonEmptyString(item.match_mode)) &&
    (item.required_anchor_patterns === undefined || isStringArray(item.required_anchor_patterns))
  );
}

function isPassageEvent(item: unknown): item is PassageEvent {
  if (!isRecord(item)) return false;
  const optionalString = (value: unknown) => value === null || typeof value === "string";
  return (
    typeof item.index === "number" && Number.isInteger(item.index) && item.index >= 0 &&
    isNonEmptyString(item.anchor) &&
    isNonEmptyString(item.title) &&
    optionalString(item.as_at) &&
    optionalString(item.court) &&
    optionalString(item.citation) &&
    (item.source_type === undefined || optionalString(item.source_type)) &&
    (item.document_id === undefined || optionalString(item.document_id)) &&
    (item.statute_short === undefined || optionalString(item.statute_short)) &&
    isStringArray(item.authority_ids)
  );
}

function isIntakeQuestion(question: unknown): question is IntakeQuestion {
  if (!isRecord(question)) return false;
  return (
    typeof question.id === "string" && question.id.length > 0 && question.id.length <= 80 &&
    typeof question.prompt === "string" && question.prompt.length > 0 && question.prompt.length <= 500 &&
    typeof question.reason === "string" && question.reason.length > 0 && question.reason.length <= 300 &&
    (question.input_type === "text" || question.input_type === "date" || question.input_type === "choice") &&
    Array.isArray(question.options) &&
    question.options.length <= 8 &&
    question.options.every((option) => typeof option === "string" && option.length <= 120)
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isNonNegativeFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function isUrgency(value: unknown): value is MatterPlanEvent["urgency"] {
  return value === "low" || value === "medium" || value === "high" || value === "emergency";
}

function isSentenceStatus(value: unknown): value is SentenceEvent["status"] {
  return value === "ok" || value === "guidance" || value === "weak_support" ||
    value === "unsupported" || value === "unknown_citation" || value === "meta";
}
