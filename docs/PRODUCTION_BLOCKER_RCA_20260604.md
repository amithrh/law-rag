# Production-blocker RCA — reviewer-missed common-user failures

**Date:** 2026-06-04
**Branch:** `codex/latency-hardening`
**Status:** fixed for the reviewed blocker set; not a production launch sign-off.

## What Happened

The pipeline was reported as improved after focused blocker and common-user gates passed, but subagent review found additional common real-user failures:

- Mixed off-topic + self-harm text routed to `off_topic` instead of crisis support.
- Hindi/Hinglish self-harm phrases routed to `general_legal`.
- Third-party POCSO helper facts could be framed as accused defence.
- Physical stalking with "not online" could still route to cyber.
- Prospective will-drafting questions such as "Can I make a will?" routed as generic property.
- Broad `WEAK_SUPPORT` promotion could let weak model prose through whenever it cited a bare Act.

These are product blockers because they affect safety, user role, forum choice, and the first legal route a user sees.

## Impact

The failures were not mainly retrieval misses. They were route/intake and answer-layer misses:

- A crisis user may receive no safety-first response.
- A survivor/helper may receive accused-side framing.
- A physical stalking user may be sent to the cyber path.
- A will-drafting user may receive transfer/property guidance instead of Indian Succession / Registration sources.
- Citation metrics can improve while answer quality remains weak if weak prose is over-promoted.

## Root Cause

1. **Known-failure eval overfit**

   The first blocker gate used exact prompts from the review cluster. It proved those strings were fixed, but it did not prove adjacent user language was fixed. The set lacked adversarial variants such as Hindi/Hinglish crisis, explicit negation ("not online"), third-party POCSO helper roles, and prospective will-drafting.

2. **Route ordering violated safety priority**

   Crisis detection was placed after off-topic detection. This meant a mixed query containing an off-topic phrase and self-harm intent could be refused as outside legal scope.

3. **Language coverage was English-first**

   Devanagari expansion covered domestic violence, police, tenancy, and wages, but not self-harm. Hinglish self-harm phrases were also absent from `_is_self_harm_crisis`.

4. **Role detection was string-fragile**

   POCSO/sexual-offence accused routing accepted broad patterns such as "student filed" instead of requiring a clear first-person accused context (`against me`, `on me`, `my bail`, `I am accused`) or close partner filing context.

5. **Negation was not modelled**

   Physical stalking exclusion from cyber worked only when no platform/online term appeared. The phrase "not online" still contained the token `online`, so cyber context won.

6. **Bare-word avoidance overcorrected**

   The fix for future-tense `will` correctly stopped `he will beat me` from routing to succession, but it missed prospective will-intent verbs (`make/write/draft/execute a will`).

7. **Citation correctness was mistaken for product quality**

   The broad weak-support exception allowed weak sentences if they cited any bare Act or required source pack. That improved citation metrics but could allow low-confidence prose into user-visible answers.

## Fixes Applied

- Moved self-harm crisis routing before off-topic.
- Added Hindi/Hinglish self-harm detection and Devanagari expansion.
- Tightened POCSO/sexual-offence role disambiguation.
- Added explicit physical-stalking detection and cyber negation handling.
- Added prospective will-drafting routing and source-pack coverage.
- Removed broad `WEAK_SUPPORT` promotion for arbitrary model prose.
- Added narrow deterministic templates for:
  - crisis/self-harm safety,
  - physical stalking police/FIR route,
  - prospective will drafting,
  - direct threat,
  - MACT,
  - wage/salary,
  - POCSO accused.
- Added regression tests for the exact missed classes.

## Verification

Local tests:

- `PYTHONPATH=. .venv/bin/pytest apps/api/tests/test_matter_router.py apps/api/tests/test_source_packs.py apps/api/tests/test_llm_prompt.py -q`
  - `347 passed`
- Endpoint/common-user slice:
  - `8 passed`
- `git diff --check`
  - clean

Live API gates on `127.0.0.1:8038`:

- Reviewer probes:
  - `4/4 product_pass`
  - `4/4 route_match`
  - `4/4 expected_act_cited`
  - p50 `5.0s`, p90 `11.2s`
- Original reviewer blockers:
  - `7/7 product_pass`
  - `7/7 route_match`
  - `7/7 expected_act_cited`
  - p50 `5.1s`, p90 `6.4s`
- Focused common-user regressions:
  - `18/18 product_pass`
  - `18/18 route_match`
  - `18/18 expected_act_cited`
  - p50 `5.9s`, p90 `11.6s`

## What This Does Not Prove

These passes prove the fixed failure classes and adjacent probes are no longer broken. They do not prove production readiness.

Remaining proof required:

- Fresh unseen 500-prompt common-user eval.
- Adversarial coverage for role ambiguity, mixed language, negation, off-topic + crisis, date/regime, state/forum traps, and legal-but-out-of-corpus queries.
- Human review of legal best-action quality, not only route/source/citation metrics.
- Maintained crisis/help resource metadata.
- Better intake/clarifying behavior for `general_legal`.

## New Guardrails

Before claiming production improvement:

1. Run known blocker regression gates.
2. Run fresh unseen prompts, not only known failures.
3. Include adversarial variants for every fixed class.
4. Require subagent review before final reporting.
5. Treat route/citation pass as necessary but not sufficient.
6. Never broaden weak-support promotion for model prose without a template-only proof.
7. Safety/crisis detection must run before off-topic or coverage refusal.
