import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  canRevealPlannedAnswer,
  parseMatterPlan,
  PlannedSentenceGate,
} from "./matter-plan.ts";

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

test("accepts a render-safe MatterPlan v2 payload", () => {
  assert.equal(parseMatterPlan(validPlan())?.primary_issue, "consumer");
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
});

test("production sentence gate never renders streamed text without a valid plan", () => {
  const sentence = createElement("p", null, "PRIVATE LEGAL ANSWER");
  const render = (plan, planContractError, pending) => renderToStaticMarkup(
    createElement(
      PlannedSentenceGate,
      { plan, planContractError, pending },
      sentence,
    ),
  );
  const plan = parseMatterPlan(validPlan());

  const beforePlan = render(null, null, true);
  const interrupted = render(null, "stream interrupted", false);
  const malformed = render(parseMatterPlan({ ...validPlan(), authority_ledger: [] }), null, false);
  const validated = render(plan, null, false);

  assert.equal(beforePlan.includes("PRIVATE LEGAL ANSWER"), false);
  assert.equal(beforePlan.includes("Validating the legal matter plan"), true);
  assert.equal(interrupted.includes("PRIVATE LEGAL ANSWER"), false);
  assert.equal(malformed.includes("PRIVATE LEGAL ANSWER"), false);
  assert.equal(validated.includes("PRIVATE LEGAL ANSWER"), true);
});
