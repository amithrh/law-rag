# Production Holdout Report: 2026-07-29

## Release Decision

**NO-GO.** The current build is operationally healthy and the safety evaluator
passed all 500 rows, but legal-quality, evidence-coverage, and latency gates
remain substantially below the production bar.

This report is based on the final corrected preflight-cache run, not the two
diagnostic runs that were intentionally stopped while fixing transient model
probe behavior.

## What Was Tested

- **Prompts:** 500 fresh, human-like synthetic prompts from the authority36
  holdout pack. They are not production user logs and should not be described
  as real user traffic.
- **Input:** `/tmp/law-rag-20260728-authority36-fresh500/prompts/human_messy_500_authority36_2026072804.jsonl`
- **Output:** `/tmp/law-rag-20260729-preflight500c/timed_eval_500.jsonl`
- **Build fingerprint:**
  `bc336050eafc888bee29f6430a12b3748c434f47dd25dcc1dc73037c4eeb4898`
- **Service state during run:** 500/500 requests completed; 0 service errors;
  0 `llm_unavailable` responses.

## Results

| Gate | Result | Target | Status |
| --- | ---: | ---: | --- |
| Product pass | 179/500 (35.8%) | >=95% | FAIL |
| Route match | 500/500 (100%) | >=95% | PASS |
| Expected Act cited | 229/485 (47.2%) | >=93.5% | FAIL |
| Required terms | 72.4% | >=95% | FAIL |
| Timing telemetry | 285/500 (57.0%) | >=95% | FAIL |
| p50 latency | 24.8s | <=10s internal gate | FAIL |
| p90 latency | 36.6s | <=20s | FAIL |
| LLM-path p90 | 59.0s | <=20s | FAIL |
| Safe source-gap handling | 215 rows | must be explicit and useful | PASS safety / FAIL completeness |
| Safety hard fails | 0/500 | 0 | PASS |

Compared with the prior completed post-fix 500 run, product pass improved from
34.2% to 35.8% and expected-Act citation from 45.2% to 47.2%. That is a real
but small improvement. The run also had no model-admission failure burst. It
does not yet demonstrate a product-quality breakthrough.

## Failure Concentration

The failure ledger contains 321 strict failures:

| Primary cause | Rows |
| --- | ---: |
| Source or retrieval gap | 253 |
| Variant answer gap | 25 |
| Answer support floor | 14 |
| Route-required source gap | 14 |
| Scenario specificity gap | 12 |
| Missing next-step section | 2 |
| Citation discipline gap | 1 |

The dominant problem is not that the router cannot name a category. It is that
the answer cannot ground the route in an accepted, scoped authority and then
turn that authority into a scenario-specific next step. The system therefore
fails safely in many cases, but safe refusal/source-gap is not the one-step user
solution.

## Changes Verified In This Run

- Route-derived required authorities now remain bound to their source pack and
  cannot silently fall through to an unrelated LLM answer.
- Model preflight requests are single-flight per event loop and cache only
  positive availability for a short TTL.
- A transient refresh failure preserves the last known-good preflight state;
  the actual chat call remains the final authority and still emits a safe
  unavailable result if generation truly fails.
- Focused regression suite: `266 passed`.
- Backend and frontend health checks are green on the same fingerprint.

## Independent Review

The independent release review agreed with the NO-GO decision. It verified the
single-flight, non-negative-caching, and last-known-good behavior, but flagged
two follow-ups before production: a stale known-good preflight response still
reports `ok=true`, and the preflight cache is process-local rather than shared
across API workers. These are operational follow-ups; they do not change the
larger conclusion that evidence coverage is the dominant product blocker.

## Next Fix Order

1. Promote and verify the highest-harm missing authorities first: criminal
   custody/bail/FIR, domestic/family safety, cyber/financial harm, and welfare.
   Do not mark local or unofficial text as provenance-verified.
2. Add an answer-owner contract: every route-required Act must either appear in
   a cited answer sentence or force a source-gap handoff; unrelated judgments
   must not satisfy the route.
3. Add scenario-specific authority packs and tests for the failure-ledger
   variants, especially custody, caste/tribal harm, false charges, land
   alienation, labour/welfare, and bank/platform money disputes.
4. Re-run the same holdout plus a sealed new holdout after each material stage;
   reject any change that regresses safety, Act citation, source-gap precision,
   or latency.
5. Only after evidence and answer gates are near target, run the Redis-backed
   production topology smoke test and tune latency.

No raw corpus, database, or benchmark data was pushed by this work.
