# law-rag Agent Guide

## Product Goal

Build a trustworthy Indian legal-help product, not a citation chatbot. The
user journey is:

`raw problem -> focused intake -> matter plan -> verified authorities -> action pack -> escalation or handoff`

The product must be explicit about source, jurisdiction, incident date, user
role, uncertainty, and limits. It must never substitute a nearby law merely
because it has a citation.

## Repository Reality

- The substantive implementation is in this worktree. Do not mistake the
  sparse parent checkout for the application repository.
- The current system has accumulated many prompt-specific routes, source packs,
  templates, and evaluation matchers. Treat any new keyword branch as a
  potential regression across those layers.
- `main.py` is a serving coordinator, not the place for new legal policy. New
  policy belongs in a versioned data contract or a reviewed authority/action
  pack.

## Non-Negotiable Product Rules

1. Safety and role detection run before coverage refusal, source selection, or
   freeform generation.
2. Critical matters must be served by reviewed, source-backed action packs;
   never by an LLM-only answer.
3. State-specific, personal-law, date-regime, and forum-dependent matters must
   ask for missing facts when those facts could change the answer.
4. Never claim that an authority is controlling unless it is provenance-verified
   and jurisdictionally applicable.
5. Do not use a citation score as a proxy for legal usefulness. The answer must
   state an appropriate next action, forum, documents, and uncertainty.
6. Do not silently turn a known source gap into generic advice. Show the gap and
   offer a safe escalation or handoff.

## Before Making a Change

1. Identify the actual matter type, user role, jurisdiction, incident date,
   desired outcome, and safety level. Use canonical `MatterPlan v2` as the
   target contract. Retrieval already consumes its source policy; migrate
   remaining answer, source-gap, evaluation, and UI owners into the same plan.
2. Determine whether the failure is caused by intake, routing, source coverage,
   retrieval, answer ownership, citation matching, evaluation metadata, or UI.
   Do not patch the first visible symptom.
3. Check whether an existing rule/template/source pack already owns the case.
   Avoid creating a competing owner.
4. Add positive, negative-neighbor, and paraphrase tests. A fix for an exact
   phrase is not a fix for the legal scenario.
5. For any source change, record canonical URL, publisher, effective date,
   jurisdiction, verbatim status, and provenance decision.

## Architecture Direction

The target is a single declarative matter contract consumed by routing,
retrieval, answer rendering, and evaluation. It should contain:

- normalized issue and secondary issues;
- user role, urgency, jurisdiction, incident-date regime, and case stage;
- required and conditional authorities with section anchors;
- conditions, remedy, forum, limitation/deadline, documents, and escalation;
- source coverage/provenance state and the precise missing facts.

Do not add another independent truth system in `main.py`, `matter_router.py`,
`source_packs.py`, `authority_graph.py`, `common_workflow_contracts.py`, or an
eval script. Prefer migrating one supported matter family into the shared
contract and deleting the superseded owner.

## Self-Learning Loop

The product may learn from usage, but it must not auto-edit legal policy or
auto-train itself from unreviewed user conversations.

For every answer, store a redacted, retention-controlled record containing:

- anonymized query and selected matter plan;
- route confidence, missing facts, jurisdiction/date status, and source packs;
- retrieved authority anchors, citations shown, source-gap state, latency, and
  verifier outcomes;
- explicit user feedback and, when available, whether the action pack was
  useful or escalated.

Route feedback into a human review queue. Reviewers label: correct route,
authority adequacy, harmful framing, missing authority, user usefulness, and
outcome. Only reviewed examples can enter training or eval datasets.

Training order:

1. Train/evaluate a route and fact-extraction classifier.
2. Fine-tune the reranker on reviewed query-authority pairs.
3. Re-evaluate on a locked holdout that was never used to create rules.
4. Consider generator fine-tuning only after the matter-plan and authority
   layers are stable. Never fine-tune the generator on raw user text.

## Evaluation Rules

Maintain three separate datasets:

1. Regression set: known failures and negative neighbors; used on every change.
2. Locked holdout: independently human/lawyer-labelled; never used for prompts,
   rules, source packs, or training.
3. Production-review sample: redacted, consented, manually adjudicated traffic.

Generated paraphrases of the regression set are useful diagnostics, but are
not launch evidence. Do not report them as real-user validation.

Release gates must include:

- zero dangerous framing and zero unsafe critical-route refusal;
- verified source provenance for surfaced controlling authorities;
- no visible source gap for supported routes;
- human-reviewed actionability and jurisdiction correctness;
- no regression on the locked holdout;
- p90 latency budget for both deterministic and LLM paths.

## Verification Commands

Use the explicit Python path until CI and packaging are corrected:

```bash
PYTHONPATH=. .venv/bin/pytest apps/api/tests -q
PYTHONPATH=. .venv/bin/pytest -q
cd apps/web && npm run type-check
```

The default pytest suite includes the API tests. Keep the explicit API command
for a fast serving-path-only diagnosis.

Run the ownership audit after every scored eval. It is a guardrail for answer
owner drift, not a replacement for legal-quality review:

```bash
PYTHONPATH=. .venv/bin/python scripts/audit_answer_ownership.py results.jsonl --report docs/ownership-audit.md
```

## Do Not Do These Things

- Do not add a source just to raise expected-Act hit.
- Do not tune templates against a prompt that is part of the launch holdout.
- Do not weaken a source-gap or safety guard to reduce refusals.
- Do not present a state-law summary as a verified statute section.
- Do not ship document generation before the matter plan and authority pack are
  reviewed.
- Do not declare production readiness while the worktree is dirty, the API
  suite fails, or launch evidence has no true holdout rows.
