import { createElement, Fragment, type ReactNode } from "react";

import type { AuthorityLedgerEntry, MatterPlanEvent } from "./types";

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

export function canRevealPlannedAnswer(
  plan: MatterPlanEvent | null,
  planContractError: string | null,
): boolean {
  return plan !== null && planContractError === null;
}

export function PlannedSentenceGate({
  plan,
  planContractError,
  pending,
  children,
}: {
  plan: MatterPlanEvent | null;
  planContractError: string | null;
  pending: boolean;
  children: ReactNode;
}) {
  if (canRevealPlannedAnswer(plan, planContractError)) {
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

function isAuthorityLedgerEntry(entry: unknown): entry is AuthorityLedgerEntry {
  if (!isRecord(entry)) return false;
  return (
    isNonEmptyString(entry.source) &&
    isNonEmptyString(entry.authority_id) &&
    (entry.identity_status === "canonical" || entry.identity_status === "provisional") &&
    (entry.canonical_name === null || typeof entry.canonical_name === "string") &&
    (entry.act === null || typeof entry.act === "string") &&
    (entry.section === null || typeof entry.section === "string") &&
    (entry.source_pack_id === null || typeof entry.source_pack_id === "string") &&
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
    isNonEmptyString(entry.authority_id)
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
    typeof source.priority === "number"
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

function isUrgency(value: unknown): value is MatterPlanEvent["urgency"] {
  return value === "low" || value === "medium" || value === "high" || value === "emergency";
}
