import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  applyAnswerEvent,
  canRevealPlannedAnswer,
  INITIAL_ANSWER_STATE,
  isSafeSourceGapHandoff,
  parseCoverageEvent,
  parseDisclaimerEvent,
  parseIntakeEvent,
  parseMatterPlan,
  parseMatterRouteEvent,
  parsePassagesEvent,
  parseRefusedEvent,
  parseRelevanceEvent,
  parseSentenceEvent,
  parseSourceGapEvent,
  parseStopEvent,
  parseTimingEvent,
  PlannedSentenceGate,
  reduceSourceGapProtocol,
  updateSourceGapHandoffLatch,
} from "./matter-plan.ts";
import { isCurrentRequest } from "./request-guard.ts";
import { parseSseData } from "./sse.ts";

function validPlan() {
  return {
    schema_version: 2,
    plan_id: "matter_plan_v2_contract_test",
    primary_issue: "consumer",
    primary_label: "Consumer complaint",
    confidence: 0.9,
    user_role: "consumer_or_customer",
    jurisdiction: { state: null, city: null, forum_mentioned: null, needs_state: false },
    incident_date_status: "not_required_or_not_detected",
    urgency: "medium",
    legal_regime: null,
    case_stage: "pre_complaint_or_unknown",
    desired_outcome: "refund_or_compensation",
    action_pack_id: "consumer",
    action_pack_title: "Consumer complaint path",
    required_facts: [],
    secondary_issues: [],
    forums: [],
    remedies: [],
    deadlines: [],
    documents: [],
    next_steps: [],
    portals: [],
    escalation: [],
    cautions: [],
    safety_flags: [],
    authority_ledger: [{
      source: "Consumer Protection Act 2019",
      authority_id: "authority_consumer",
      identity_status: "canonical",
      canonical_name: "consumer protection act 2019",
      act: "Consumer Protection Act 2019",
      section: null,
      source_pack_id: "consumer_protection_2019",
      required_anchor_patterns: ["/sec-35"],
      claim_type: "legal_basis",
      priority: "must_cite",
      must_cite: true,
      conditional: false,
      note: null,
    }],
    retrieval_sources: [{
      source_pack_id: "consumer_protection_2019",
      title_patterns: ["Consumer Protection Act 2019"],
      search_query: "consumer complaint",
      doc_ids: ["consumer-protection-2019"],
      anchor_patterns: ["/sec-35"],
      source_types: ["bare_act"],
      priority: 1,
    }],
    answer_policy: {
      required_primary_owner: "server_template_or_verified_llm",
      fallback_owner: "source_gap_handoff",
      allow_freeform_llm: true,
      requires_reviewed_contract: false,
    },
  };
}

function validIntake() {
  return {
    schema_version: 1,
    intake_kind: "source_gap_facts",
    route_category: "business_license_compliance",
    questions: [{
      id: "jurisdiction",
      prompt: "Which state is this in?",
      reason: "Local procedure can differ.",
      input_type: "text",
      options: [],
    }],
    privacy_note: "Do not share full account numbers.",
  };
}

function validRoute(label = "Consumer complaint") {
  return {
    category: "consumer",
    label,
    confidence: 0.8,
    urgency: "medium",
    required_sources: [],
    forums: ["National Consumer Helpline"],
    missing_facts: ["invoice"],
    red_flags: [],
    action_pack: {
      id: "consumer",
      title: "Consumer complaint path",
      next_steps: ["Keep the invoice."],
      documents: ["invoice"],
      portals: [],
      escalation: ["DLSA"],
      cautions: [],
    },
    legal_regime: null,
  };
}

test("accepts a render-safe MatterPlan v2 payload", () => {
  assert.equal(parseMatterPlan(validPlan())?.primary_issue, "consumer");
});

test("accepts an intake-only route payload and rejects malformed route logistics", () => {
  const route = {
    category: "consumer",
    label: "Consumer complaint",
    confidence: 0.8,
    urgency: "medium",
    required_sources: [],
    forums: ["National Consumer Helpline"],
    missing_facts: ["invoice"],
    red_flags: [],
    action_pack: {
      id: "consumer",
      title: "Consumer complaint path",
      next_steps: ["Keep the invoice."],
      documents: ["invoice"],
      portals: [],
      escalation: ["DLSA"],
      cautions: [],
    },
    legal_regime: null,
  };
  assert.equal(parseMatterRouteEvent(route)?.forums[0], "National Consumer Helpline");
  assert.equal(parseMatterRouteEvent({ ...route, forums: "consumer" }), null);
  assert.equal(parseMatterRouteEvent({ ...route, action_pack: { ...route.action_pack, documents: "invoice" } }), null);
  const safeRoute = {
    ...route,
    forums: [],
    intake_only: true,
    action_pack: {
      ...route.action_pack,
      next_steps: [],
      documents: [],
      portals: [],
      escalation: [],
      cautions: [],
    },
  };
  assert.equal(parseMatterRouteEvent(safeRoute)?.intake_only, true);
  assert.equal(parseMatterRouteEvent({ ...safeRoute, forums: ["consumer"] }), null);
  assert.equal(parseMatterRouteEvent({ ...safeRoute, required_sources: ["CPA"] }), null);
});

test("intake-only routes reject server-supplied operational steps", () => {
  const route = {
    ...validRoute(),
    forums: [],
    required_sources: [],
    intake_only: true,
    action_pack: {
      ...validRoute().action_pack,
      next_steps: ["File a complaint within 30 days."],
      portals: [],
      escalation: [],
      cautions: [],
    },
    legal_regime: null,
  };
  assert.equal(parseMatterRouteEvent(route), null);
  assert.equal(parseMatterRouteEvent({
    ...route,
    action_pack: { ...route.action_pack, next_steps: [], documents: ["filing form"] },
  }), null);
});

test("rejects malformed sentence events before they reach the renderer", () => {
  const valid = {
    text: "Keep the invoice [1].",
    status: "ok",
    citations: [1],
    entailment_score: 0.8,
    reason: null,
    auto_cited: false,
  };
  assert.equal(parseSentenceEvent(valid)?.citations[0], 1);
  assert.equal(parseSentenceEvent({ ...valid, citations: ["1"] }), null);
  assert.equal(parseSentenceEvent({ ...valid, status: "unknown" }), null);
  assert.equal(parseSentenceEvent({ ...valid, text: "" }), null);
});

test("rejects malformed auxiliary SSE payloads before render", () => {
  assert.equal(parseCoverageEvent({ sources_searched: [], subjects_in_results: [], passages_used: 1 })?.passages_used, 1);
  assert.equal(parseCoverageEvent({ sources_searched: "bare_act", subjects_in_results: [], passages_used: 1 }), null);
  assert.equal(parsePassagesEvent([])?.length, 0);
  assert.equal(parsePassagesEvent([{ index: 0, anchor: "a", title: "t", as_at: null, court: null, citation: null, authority_ids: [] }])?.length, 1);
  assert.equal(parsePassagesEvent([{ index: 0, anchor: "a", title: "t", as_at: null, court: null, citation: null }]), null);
  assert.equal(parseStopEvent({ reason: "x", message: "y", unsupported_count: 0, emitted_count: 1 })?.emitted_count, 1);
  assert.equal(parseStopEvent({ reason: "x" }), null);
  assert.equal(parseRefusedEvent({ message: "x", disclaimer: "y" })?.message, "x");
  assert.equal(parseRefusedEvent({ message: "x", disclaimer: "y", reason: "off_topic" })?.reason, "off_topic");
  assert.equal(parseRefusedEvent({ message: "x", disclaimer: 7 }), null);
  assert.equal(parseRelevanceEvent({ score: 0.5, verdict: "ok", threshold: 0.4, band: 0.1 })?.verdict, "ok");
  assert.equal(parseRelevanceEvent({ score: -1, verdict: "ok", threshold: 0.4, band: 0.1 }), null);
  assert.equal(parseDisclaimerEvent({ text: "notice" })?.text, "notice");
  assert.equal(parseDisclaimerEvent({ text: "" }), null);
});

test("accepts bounded intake events and rejects malformed or future payloads", () => {
  assert.equal(parseIntakeEvent(validIntake())?.questions[0].id, "jurisdiction");
  assert.equal(parseIntakeEvent({ ...validIntake(), intake_kind: "unknown" }), null);
  assert.equal(parseIntakeEvent({
    ...validIntake(),
    questions: [{ ...validIntake().questions[0], id: "legal_advice" }],
  }), null);
  assert.equal(parseIntakeEvent({ ...validIntake(), schema_version: 2 }), null);
  assert.equal(parseIntakeEvent({ ...validIntake(), questions: [] }), null);
  assert.equal(parseIntakeEvent({
    ...validIntake(),
    questions: [{ ...validIntake().questions[0], input_type: "choice", options: ["safe"] }],
  })?.questions[0].input_type, "choice");
  assert.equal(parseIntakeEvent({
    ...validIntake(),
    questions: [{ ...validIntake().questions[0], prompt: "" }],
  }), null);
});

test("malformed SSE JSON fails closed instead of being skipped", () => {
  assert.deepEqual(parseSseData('{"ok":true}'), { ok: true });
  assert.throws(() => parseSseData("not-json"), /malformed JSON/);
});

test("validates source-gap handoffs and rejects malformed payloads", () => {
  const valid = {
    has_gap: true,
    route_category: "police_fir",
    gap_kinds: ["missing_required_authority"],
    missing_required_sources: [{ required_source: "BNSS 2023", kind: "missing" }],
    message: "A required authority is missing.",
    handoff: "DLSA/legal aid",
    policy: "do_not_substitute_neighboring_authority",
    outcome: "source_gap_handoff",
    reason: "low_coverage",
    safe_handoff_only: true,
  };
  assert.equal(parseSourceGapEvent(valid)?.safe_handoff_only, true);
  assert.equal(
    parseSourceGapEvent({
      ...valid,
      missing_required_sources: [{
        required_source: "current chemical-injury/hurt authority",
        kind: "national_criminal_source_gap",
        match_mode: "acid_incident_authority_pair",
        required_anchor_patterns: ["/sec-124"],
      }],
    })?.missing_required_sources[0].match_mode,
    "acid_incident_authority_pair",
  );
  assert.equal(parseSourceGapEvent({ ...valid, safe_handoff_only: "yes" }), null);
  assert.equal(parseSourceGapEvent({ ...valid, missing_required_sources: [{ kind: "missing" }] }), null);
  assert.equal(parseSourceGapEvent({ ...valid, outcome: "ordinary_answer" }), null);
  assert.equal(parseSourceGapEvent({ ...valid, outcome: undefined, safe_handoff_only: undefined }), null);
  assert.equal(parseSourceGapEvent({ ...valid, has_gap: false }), null);
  assert.equal(parseSourceGapEvent({
    ...valid,
    has_gap: false,
    gap_kinds: [],
    missing_required_sources: [],
    outcome: undefined,
    safe_handoff_only: undefined,
  }), null);
  assert.equal(parseSourceGapEvent({ ...valid, safe_handoff_only: false }), null);
  assert.equal(parseSourceGapEvent({ ...valid, outcome: undefined, safe_handoff_only: true }), null);
  assert.equal(parseSourceGapEvent({
    ...valid,
    has_gap: false,
    outcome: undefined,
    safe_handoff_only: undefined,
    gap_kinds: ["contradictory_no_gap"],
    missing_required_sources: [],
  }), null);
  assert.equal(
    isSafeSourceGapHandoff(parseSourceGapEvent(valid)),
    true,
  );
  assert.equal(
    isSafeSourceGapHandoff(
      parseSourceGapEvent({ ...valid, safe_handoff_only: false }),
    ),
    false,
  );
  assert.equal(
    isSafeSourceGapHandoff(
      parseSourceGapEvent({ ...valid, safe_handoff_only: false }),
    ),
    false,
  );
});

test("requires a complete timing payload for a terminal stream", () => {
  const valid = {
    total_ms: 123.4,
    llm_model: "qwen3:14b",
    llm_model_available: true,
    retrieved_count: 8,
    passages_used: 8,
    expansion_variant_count: 0,
    sentence_count: 2,
  };
  assert.equal(parseTimingEvent(valid)?.total_ms, 123.4);
  assert.equal(parseTimingEvent({ ...valid, total_ms: -1 }), null);
  assert.equal(parseTimingEvent({ ...valid, llm_model_available: "yes" }), null);
  assert.equal(parseTimingEvent({ ...valid, retrieved_count: "8" }), null);
});

test("stale or aborted streams cannot update the current request", () => {
  const first = new AbortController();
  assert.equal(isCurrentRequest(1, 1, first.signal), true);
  assert.equal(isCurrentRequest(1, 2, first.signal), false);
  first.abort();
  assert.equal(isCurrentRequest(1, 1, first.signal), false);
});

test("rejects stale schemas and malformed render arrays", () => {
  assert.equal(parseMatterPlan({ ...validPlan(), schema_version: 1 }), null);
  assert.equal(parseMatterPlan({ ...validPlan(), forums: "District Commission" }), null);
  assert.equal(parseMatterPlan({ ...validPlan(), authority_ledger: [{}] }), null);
  assert.equal(parseMatterPlan({ ...validPlan(), authority_ledger: [] }), null);
  assert.equal(parseMatterPlan({ ...validPlan(), retrieval_sources: [] }), null);
  assert.equal(parseMatterPlan({
    ...validPlan(),
    authority_ledger: [{ ...validPlan().authority_ledger[0], authority_id: null }],
  }), null);
  assert.equal(parseMatterPlan({
    ...validPlan(),
    authority_ledger: [{ ...validPlan().authority_ledger[0], source: "" }],
  }), null);
  assert.equal(parseMatterPlan({
    ...validPlan(),
    authority_ledger: [{ ...validPlan().authority_ledger[0], must_cite: false }],
  }), null);
  assert.equal(parseMatterPlan({ ...validPlan(), primary_label: "  " }), null);
  assert.equal(parseMatterPlan({
    ...validPlan(),
    answer_policy: { ...validPlan().answer_policy, fallback_owner: "" },
  }), null);
});

test("reveals answer only after a valid plan and hides malformed or interrupted streams", () => {
  const plan = parseMatterPlan(validPlan());
  assert.equal(canRevealPlannedAnswer(null, null), false);
  assert.equal(canRevealPlannedAnswer(parseMatterPlan({ ...validPlan(), schema_version: 1 }), null), false);
  assert.equal(canRevealPlannedAnswer(null, "stream interrupted"), false);
  assert.equal(canRevealPlannedAnswer(plan, null), true);
  assert.equal(canRevealPlannedAnswer(plan, "invalid later event"), false);
  assert.equal(canRevealPlannedAnswer(plan, null, true), false);
  const handoff = {
    has_gap: true,
    route_category: "police_fir",
    gap_kinds: ["missing_required_authority"],
    missing_required_sources: [{ required_source: "BNSS 2023", kind: "missing" }],
    message: "A required authority is missing.",
    handoff: "DLSA/legal aid",
    policy: "do_not_substitute_neighboring_authority",
    outcome: "source_gap_handoff",
    safe_handoff_only: true,
  };
  let latched = updateSourceGapHandoffLatch(false, handoff);
  assert.equal(latched, true);
  assert.equal(updateSourceGapHandoffLatch(latched, { has_gap: false }), true);
  assert.equal(canRevealPlannedAnswer(plan, null, latched), false);

  let protocol = reduceSourceGapProtocol({
    sourceGap: null,
    sourceGapProtocolError: null,
    planContractError: null,
    sourceGapHandoffLatched: false,
  }, handoff);
  protocol = reduceSourceGapProtocol(protocol, {
    has_gap: false,
    route_category: "police_fir",
    gap_kinds: [],
    missing_required_sources: [],
    message: "no gap",
    handoff: "ignored",
    policy: "do_not_substitute_neighboring_authority",
  });
  assert.equal(protocol.sourceGap?.outcome, "source_gap_handoff");
  assert.equal(protocol.sourceGapHandoffLatched, true);
  assert.equal(canRevealPlannedAnswer(plan, protocol.planContractError, protocol.sourceGapHandoffLatched), false);
});

test("source-gap handoff remains latched across a complete out-of-order stream", () => {
  const handoff = {
    has_gap: true,
    route_category: "consumer",
    gap_kinds: ["missing_required_authority"],
    missing_required_sources: [{ required_source: "Consumer Protection Act 2019", kind: "missing" }],
    message: "The required source is missing.",
    handoff: "DLSA/legal aid or a qualified lawyer",
    policy: "do_not_substitute_neighboring_authority",
    outcome: "source_gap_handoff",
    reason: "required_source_gap",
    safe_handoff_only: true,
  };
  const noGap = {
    has_gap: false,
    route_category: "consumer",
    gap_kinds: [],
    missing_required_sources: [],
    message: "No gap",
    handoff: "ignored",
    policy: "do_not_substitute_neighboring_authority",
  };
  let state = { ...INITIAL_ANSWER_STATE, pending: true };
  state = applyAnswerEvent(state, "matter_route", validRoute("Original route"));
  state = applyAnswerEvent(state, "sentence", {
    text: "OPERATIVE ANSWER THAT MUST STAY HIDDEN",
    status: "ok",
    citations: [1],
    entailment_score: 0.9,
    reason: null,
  });
  state = applyAnswerEvent(state, "source_gap", handoff);
  state = applyAnswerEvent(state, "matter_plan", validPlan());
  state = applyAnswerEvent(state, "sources", []);
  state = applyAnswerEvent(state, "relevance", {
    score: 0.9,
    verdict: "ok",
    threshold: 0.7,
    band: 0.1,
  });
  state = applyAnswerEvent(state, "stop", {
    reason: "insufficient_support",
    message: "stop",
    unsupported_count: 0,
    emitted_count: 0,
  });
  state = applyAnswerEvent(state, "source_gap", noGap);
  state = applyAnswerEvent(state, "matter_route", validRoute("Late replacement route"));

  assert.equal(state.sourceGapHandoffLatched, true);
  assert.equal(state.matterRoute?.label, "Original route");
  assert.equal(state.sourceGap?.outcome, "source_gap_handoff");
  assert.equal(state.sourceGap?.reason, "required_source_gap");
  assert.equal(state.sentences.length, 0);
  assert.equal(state.matterPlan, null);
  assert.equal(state.sources, null);
  assert.equal(state.relevance, null);
  assert.equal(state.stop, null);
  state = applyAnswerEvent(state, "sentence", {
    text: "**What you can do next** Keep your records and contact DLSA/legal aid for source-backed intake. This is an intake handoff, not a conclusion about your rights or deadline.",
    status: "guidance",
    citations: [],
    entailment_score: null,
    reason: "source-gap intake handoff; no unsupported legal conclusion",
    auto_cited: false,
  });
  state = applyAnswerEvent(state, "sentence", {
    text: "OPERATIVE ANSWER THAT MUST STAY HIDDEN",
    status: "ok",
    citations: [1],
    entailment_score: 0.9,
    reason: null,
  });
  assert.equal(state.sentences.length, 0);
  assert.equal(canRevealPlannedAnswer(state.matterPlan, state.planContractError, state.sourceGapHandoffLatched), false);
  const rendered = renderToStaticMarkup(createElement(
    PlannedSentenceGate,
    {
      plan: state.matterPlan,
      planContractError: state.planContractError,
      sourceGapHandoffLatched: state.sourceGapHandoffLatched,
      pending: false,
    },
    createElement("p", null, "OPERATIVE ANSWER THAT MUST STAY HIDDEN"),
  ));
  assert.equal(rendered.includes("OPERATIVE ANSWER THAT MUST STAY HIDDEN"), false);
});

test("source-gap sentence events never become a second advice channel", () => {
  const handoff = {
    has_gap: true,
    route_category: "police_fir",
    gap_kinds: ["national_criminal_source_gap"],
    missing_required_sources: [{
      required_source: "current chemical-injury/hurt authority",
      kind: "national_criminal_source_gap",
      match_mode: "acid_incident_authority_pair",
      required_anchor_patterns: ["/sec-124"],
    }],
    message: "The controlling authority could not be verified.",
    handoff: "DLSA/legal aid",
    policy: "do_not_substitute_neighboring_authority",
    outcome: "source_gap_handoff",
    reason: "required_source_gap",
    safe_handoff_only: true,
  };
  let state = {
    ...INITIAL_ANSWER_STATE,
    planContractError: "The server sent an invalid MatterPlan v2 contract.",
  };
  state = applyAnswerEvent(state, "source_gap", handoff);
  state = applyAnswerEvent(state, "sentence", {
    text: "**What you can do next** Keep the records and contact DLSA/legal aid for source-backed intake. This is an intake handoff, not a conclusion about your rights or deadline.",
    status: "guidance",
    citations: [],
    entailment_score: null,
    reason: "source-gap intake handoff; no unsupported legal conclusion",
    auto_cited: false,
  });
  state = applyAnswerEvent(state, "timing", {
    total_ms: 10,
    llm_model: "contract-test-model",
    llm_model_available: true,
    retrieved_count: 0,
    passages_used: 0,
    expansion_variant_count: 0,
  });
  assert.equal(state.sourceGapHandoffLatched, true);
  assert.equal(state.matterPlan, null);
  assert.equal(state.planContractError, null);
  assert.equal(state.error, null);
  assert.equal(state.sentences.length, 0);
});

test("a refusal is terminal and rejects late answer content", () => {
  let state = { ...INITIAL_ANSWER_STATE, pending: true };
  state = applyAnswerEvent(state, "matter_route", validRoute());
  state = applyAnswerEvent(state, "matter_plan", validPlan());
  state = applyAnswerEvent(state, "sentence", {
    text: "A sentence that must be cleared",
    status: "ok",
    citations: [1],
    entailment_score: 0.9,
    reason: null,
  });
  state = applyAnswerEvent(state, "refused", {
    message: "No verified source.",
    disclaimer: "Please consult a lawyer.",
    reason: "low_coverage",
  });
  state = applyAnswerEvent(state, "matter_plan", validPlan());
  state = applyAnswerEvent(state, "sentence", {
    text: "Late unsupported answer",
    status: "ok",
    citations: [1],
    entailment_score: 0.9,
    reason: null,
  });
  assert.equal(state.refused?.reason, "low_coverage");
  assert.equal(state.matterPlan, null);
  assert.equal(state.sentences.length, 0);
  assert.equal(state.timeline.length, 0);
});

test("source-gap handoff can show bounded retry intake without reopening the answer", () => {
  const handoff = {
    has_gap: true,
    route_category: "business_license_compliance",
    gap_kinds: ["state_or_local_authority_gap"],
    missing_required_sources: [{ required_source: "state motor vehicle rules", kind: "state_or_local_authority_gap" }],
    message: "The state procedure needs verification.",
    handoff: "DLSA/legal aid or a qualified lawyer",
    policy: "do_not_substitute_neighboring_authority",
    outcome: "source_gap_handoff",
    reason: "required_source_gap",
    safe_handoff_only: true,
  };
  const intake = {
    schema_version: 1,
    intake_kind: "source_gap_facts",
    route_category: "business_license_compliance",
    questions: [{
      id: "jurisdiction",
      prompt: "Which state and city or district is this in?",
      reason: "The local procedure can change with jurisdiction.",
      input_type: "text",
      options: [],
    }],
    privacy_note: "Do not share full account numbers.",
  };
  let state = { ...INITIAL_ANSWER_STATE, pending: true };
  state = applyAnswerEvent(state, "source_gap", handoff);
  state = applyAnswerEvent(state, "matter_plan", validPlan());
  state = applyAnswerEvent(state, "intake", intake);

  assert.equal(state.sourceGapHandoffLatched, true);
  assert.equal(state.matterPlan, null);
  assert.equal(state.intake?.questions[0].id, "jurisdiction");
  assert.equal(canRevealPlannedAnswer(state.matterPlan, state.planContractError, state.sourceGapHandoffLatched), false);
});

test("source-gap latch rejects generic, mismatched, or authority-seeking intake", () => {
  const handoff = {
    has_gap: true,
    route_category: "business_license_compliance",
    gap_kinds: ["state_or_local_authority_gap"],
    missing_required_sources: [{ required_source: "municipal by-laws", kind: "state_or_local_authority_gap" }],
    message: "The local authority needs verification.",
    handoff: "DLSA/legal aid or a qualified lawyer",
    policy: "do_not_substitute_neighboring_authority",
    outcome: "source_gap_handoff",
    reason: "required_source_gap",
    safe_handoff_only: true,
  };
  let state = { ...INITIAL_ANSWER_STATE, pending: true };
  state = applyAnswerEvent(state, "source_gap", handoff);

  state = applyAnswerEvent(state, "intake", {
    ...validIntake(),
    intake_kind: undefined,
    route_category: undefined,
  });
  assert.equal(state.intake, null);

  state = applyAnswerEvent(state, "intake", {
    ...validIntake(),
    route_category: "consumer",
  });
  assert.equal(state.intake, null);

  state = applyAnswerEvent(state, "intake", {
    ...validIntake(),
    questions: [{ ...validIntake().questions[0], id: "forum" }],
  });
  assert.equal(state.intake, null);

  state = applyAnswerEvent(state, "intake", validIntake());
  assert.equal(state.intake?.questions[0].id, "jurisdiction");
});

test("source-gap intake cannot disagree with a retained matter route", () => {
  const handoff = {
    has_gap: true,
    route_category: "business_license_compliance",
    gap_kinds: ["state_or_local_authority_gap"],
    missing_required_sources: [{ required_source: "municipal by-laws", kind: "state_or_local_authority_gap" }],
    message: "The local authority needs verification.",
    handoff: "DLSA/legal aid or a qualified lawyer",
    policy: "do_not_substitute_neighboring_authority",
    outcome: "source_gap_handoff",
    reason: "required_source_gap",
    safe_handoff_only: true,
  };
  let state = { ...INITIAL_ANSWER_STATE, pending: true };
  state = applyAnswerEvent(state, "matter_route", validRoute());
  state = applyAnswerEvent(state, "source_gap", handoff);
  assert.equal(state.sourceGap?.route_category, "consumer");
  assert.equal(state.sourceGap?.reason, "invalid_source_gap_payload");
  state = applyAnswerEvent(state, "intake", {
    ...validIntake(),
    route_category: "business_license_compliance",
  });
  assert.equal(state.intake, null);
});

test("non-jurisdictional source gaps clear and reject retry intake", () => {
  const handoff = {
    has_gap: true,
    route_category: "consumer",
    gap_kinds: ["missing_required_authority"],
    missing_required_sources: [{ required_source: "Consumer Protection Act 2019", kind: "missing" }],
    message: "The required source is missing.",
    handoff: "DLSA/legal aid or a qualified lawyer",
    policy: "do_not_substitute_neighboring_authority",
    outcome: "source_gap_handoff",
    reason: "required_source_gap",
    safe_handoff_only: true,
  };
  let state = { ...INITIAL_ANSWER_STATE, intake: validIntake() };
  state = applyAnswerEvent(state, "source_gap", handoff);
  state = applyAnswerEvent(state, "intake", validIntake());

  assert.equal(state.intake, null);
  assert.equal(state.matterPlan, null);
  assert.equal(state.sourceGapHandoffLatched, true);
});

test("stream errors clear content and reject every late answer event", () => {
  let state = { ...INITIAL_ANSWER_STATE, pending: true };
  state = applyAnswerEvent(state, "error", { message: "internal database detail" });
  assert.equal(state.error, "The answer could not be completed safely. Please retry or contact DLSA/legal aid.");
  assert.equal(state.matterPlan, null);
  assert.equal(state.sentences.length, 0);
  state = applyAnswerEvent(state, "matter_plan", validPlan());
  state = applyAnswerEvent(state, "coverage", { sources_searched: ["bare_act"], subjects_in_results: [], passages_used: 1 });
  state = applyAnswerEvent(state, "sentence", {
    text: "LATE OPERATIVE ANSWER",
    status: "ok",
    citations: [1],
    entailment_score: 0.9,
    reason: null,
  });
  assert.equal(state.matterPlan, null);
  assert.equal(state.coverage, null);
  assert.equal(state.sentences.length, 0);
});

test("a valid timing event closes the stream against late operative events", () => {
  let state = { ...INITIAL_ANSWER_STATE, pending: true };
  state = applyAnswerEvent(state, "timing", {
    total_ms: 123.4,
    llm_model: "qwen3:14b",
    llm_model_available: true,
    retrieved_count: 1,
    passages_used: 1,
    expansion_variant_count: 0,
    sentence_count: 1,
  });
  state = applyAnswerEvent(state, "sentence", {
    text: "LATE OPERATIVE ANSWER",
    status: "ok",
    citations: [1],
    entailment_score: 0.9,
    reason: null,
  });
  state = applyAnswerEvent(state, "sources", []);
  state = applyAnswerEvent(state, "error", { message: "late error" });

  assert.equal(state.timing?.total_ms, 123.4);
  assert.equal(state.sentences.length, 0);
  assert.equal(state.sources, null);
  assert.equal(state.error, null);
});

test("late source-gap or refusal events replace visible content after timing", () => {
  const handoff = {
    has_gap: true,
    route_category: "consumer",
    gap_kinds: ["missing_required_authority"],
    missing_required_sources: [{ required_source: "Consumer Protection Act 2019", kind: "missing" }],
    message: "The required source is missing.",
    handoff: "DLSA/legal aid",
    policy: "do_not_substitute_neighboring_authority",
    outcome: "source_gap_handoff",
    reason: "required_source_gap",
    safe_handoff_only: true,
  };
  let state = { ...INITIAL_ANSWER_STATE, pending: true };
  state = applyAnswerEvent(state, "matter_route", validRoute());
  state = applyAnswerEvent(state, "matter_plan", validPlan());
  state = applyAnswerEvent(state, "sentence", {
    text: "Visible answer before late safety event",
    status: "ok",
    citations: [1],
    entailment_score: 0.9,
    reason: null,
  });
  state = applyAnswerEvent(state, "timing", {
    total_ms: 5,
    llm_model: "test",
    llm_model_available: true,
    retrieved_count: 1,
    passages_used: 1,
    expansion_variant_count: 0,
  });
  state = applyAnswerEvent(state, "source_gap", handoff);
  assert.equal(state.sourceGapHandoffLatched, true);
  assert.equal(state.matterPlan, null);
  assert.equal(state.sentences.length, 0);

  state = { ...INITIAL_ANSWER_STATE, pending: true };
  state = applyAnswerEvent(state, "matter_route", validRoute());
  state = applyAnswerEvent(state, "matter_plan", validPlan());
  state = applyAnswerEvent(state, "sentence", {
    text: "Visible answer before late refusal",
    status: "ok",
    citations: [1],
    entailment_score: 0.9,
    reason: null,
  });
  state = applyAnswerEvent(state, "timing", {
    total_ms: 5,
    llm_model: "test",
    llm_model_available: true,
    retrieved_count: 1,
    passages_used: 1,
    expansion_variant_count: 0,
  });
  state = applyAnswerEvent(state, "refused", {
    message: "No verified source.",
    disclaimer: "Please consult a lawyer.",
    reason: "low_coverage",
  });
  assert.equal(state.refused?.reason, "low_coverage");
  assert.equal(state.matterPlan, null);
  assert.equal(state.sentences.length, 0);
});

test("a transport error preserves an already-established source-gap handoff", () => {
  const handoff = {
    has_gap: true,
    route_category: "police_fir",
    gap_kinds: ["national_criminal_source_gap"],
    missing_required_sources: [{ required_source: "BNS acid authority", kind: "missing" }],
    message: "The required source is missing.",
    handoff: "DLSA/legal aid",
    policy: "do_not_substitute_neighboring_authority",
    outcome: "source_gap_handoff",
    reason: "required_source_gap",
    safe_handoff_only: true,
  };
  let state = { ...INITIAL_ANSWER_STATE, pending: true };
  state = applyAnswerEvent(state, "matter_route", validRoute("FIR route"));
  state = applyAnswerEvent(state, "source_gap", handoff);
  state = applyAnswerEvent(state, "error", { message: "truncated stream" });

  assert.equal(state.sourceGap?.outcome, "source_gap_handoff");
  assert.equal(state.sourceGapHandoffLatched, true);
  assert.equal(state.error, null);
  assert.equal(state.matterRoute?.label, "FIR route");
  assert.equal(state.matterPlan, null);
});

test("rejects unverified mandatory authority provenance", () => {
  assert.equal(parseMatterPlan({
    ...validPlan(),
    authority_ledger: [{
      ...validPlan().authority_ledger[0],
      identity_status: "provisional",
    }],
  }), null);
  assert.equal(parseMatterPlan({
    ...validPlan(),
    authority_ledger: [{
      ...validPlan().authority_ledger[0],
      source_pack_id: "",
    }],
  }), null);
});

test("accepts exact reviewed workflow provenance with provisional authority identity", () => {
  const reviewedWorkflowPlan = {
    ...validPlan(),
    authority_ledger: [{
      ...validPlan().authority_ledger[0],
      authority_id: "authority_provisional_consumer_workflow",
      identity_status: "provisional",
      required_anchor_patterns: ["/sec-35", "/sec-38", "/sec-39"],
      note: "plan_owned_contract_required_source",
    }],
  };
  assert.equal(parseMatterPlan(reviewedWorkflowPlan)?.primary_issue, "consumer");
  assert.equal(parseMatterPlan({
    ...reviewedWorkflowPlan,
    authority_ledger: [{
      ...reviewedWorkflowPlan.authority_ledger[0],
      required_anchor_patterns: [],
    }],
  }), null);
});

test("production sentence gate never renders streamed text without a valid plan", () => {
  const sentence = createElement("p", null, "PRIVATE LEGAL ANSWER");
  const render = (plan, planContractError, pending, sourceGapHandoffLatched = false) => renderToStaticMarkup(
    createElement(
      PlannedSentenceGate,
      { plan, planContractError, pending, sourceGapHandoffLatched },
      sentence,
    ),
  );
  const plan = parseMatterPlan(validPlan());

  const beforePlan = render(null, null, true);
  const interrupted = render(null, "stream interrupted", false);
  const malformed = render(parseMatterPlan({ ...validPlan(), authority_ledger: [] }), null, false);
  const lateHandoff = render(plan, null, false, true);
  const validated = render(plan, null, false);

  assert.equal(beforePlan.includes("PRIVATE LEGAL ANSWER"), false);
  assert.equal(beforePlan.includes("Validating the legal matter plan"), true);
  assert.equal(interrupted.includes("PRIVATE LEGAL ANSWER"), false);
  assert.equal(malformed.includes("PRIVATE LEGAL ANSWER"), false);
  assert.equal(lateHandoff.includes("PRIVATE LEGAL ANSWER"), false);
  assert.equal(validated.includes("PRIVATE LEGAL ANSWER"), true);
});
