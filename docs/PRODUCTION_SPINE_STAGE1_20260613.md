# Production Spine Stage 1 - 2026-06-13

## Goal

Move the system from "best-effort RAG answer" toward a product launch gate for Indian legal help. The critical product rule is simple: if the route is high-risk, the app must not let a freeform LLM invent the path, and if the controlling source is missing, the user must see that gap.

## Built

- Runtime source-gap detector in `apps/api/source_gap.py`.
- `/answer` SSE now emits a `source_gap` event before answer generation when route-required authority is missing from the retrieved source window.
- Critical launch routes now fail closed when no reviewed deterministic answer contract exists:
  - arrest/custody safeguard
  - bonded labour / forced labour rescue
  - criminal defence/bail
  - criminal general
  - domestic/family violence
  - labour exploitation/discrimination
  - police FIR
  - tribal/caste atrocity
- Frontend renders a visible amber notice for controlling-source gaps.
- Timed eval captures source-gap visibility in JSONL output.
- New launch holdout gate checks:
  - hard prompt metadata exists
  - true lawyer/manual holdout rows exist
  - no LLM-owned critical route rows
  - missing authority is visible to the user

## Verification

Passed:

```text
python3 -m py_compile apps/api/source_gap.py scripts/eval_launch_holdout_gate.py apps/api/main.py scripts/eval_timed_100.py scripts/eval_common_user_gate.py
UV_CACHE_DIR=/tmp/uv-cache-law-rag PYTHONPATH=. uv run pytest apps/api/tests/test_source_gap.py apps/api/tests/test_launch_holdout_gate.py apps/api/tests/test_eval_common_user_gate.py apps/api/tests/test_eval_timed_100.py apps/api/tests/test_endpoints.py::test_stage_goal_exact_failures_get_deterministic_answer_owners -q
cd apps/web && npm run type-check
```

Result:

```text
76 passed, 2 warnings
type-check passed
```

`npm run lint` was not usable as a non-interactive gate because the current Next.js lint command prompts to configure ESLint.

## Launch Gate Baseline

Ran the new launch gate on the cached fresh-500 eval:

```text
UV_CACHE_DIR=/tmp/uv-cache-law-rag PYTHONPATH=. uv run python scripts/eval_launch_holdout_gate.py data/processed/timed_eval_500_fresh_exact_20260613_seed2026061307.jsonl --prompts data/eval_human_messy_500_fresh_exact_seed2026061307/human_messy_500_fresh_exact_seed2026061307.jsonl --report reports/launch_holdout_gate_on_fresh500_20260613.md --failures-jsonl reports/launch_holdout_gate_on_fresh500_20260613.failures.jsonl --allow-fail
```

Result: **FAIL**, as intended for the current state.

Key numbers:

- product pass: 336/500 (67.2%)
- high-priority pass: 260/317 (82.0%)
- critical-priority pass: 76/183 (41.5%)
- expected Act cited: 474/485 (97.7%)
- metadata errors: 1193
- true holdout rows: 0
- LLM-owned critical rows: 15
- non-reviewed critical rows: 118
- missing visible source-gap rows: 5

Important caveat: this was run against a cached eval created before the runtime `source_gap` SSE event existed. It is a useful baseline, not proof that the new source-gap UI event fails. A fresh `/answer` eval is required for that measurement.

## What This Means

This stage does not claim production readiness. It adds the missing product guardrail that tells us honestly why the system is not ready.

Before launch, the repo still needs:

- an independently labelled lawyer/manual holdout set;
- no LLM-owned or legacy-template-owned critical-route answers;
- source-gap visibility measured on fresh `/answer` output;
- reviewed deterministic contracts for the critical routes still falling to LLM;
- a non-interactive web lint or frontend quality gate.

## Review Fixes Applied

The subagent review found four issues and the stage now addresses the critical ones:

- Conditional criminal-regime source strings such as `BNSS 2023 / CrPC 1973 ... based on incident date` are no longer skipped by runtime or eval source-gap checks.
- Critical routes now require a reviewed `primary` or `safety_primary` workflow contract; legacy templates no longer satisfy the launch guard.
- Early refusal paths now emit `source_gap` when route-required sources are missing.
- Authority-graph workflow telemetry now preserves required sources and source indices into the workflow event/eval row.

A follow-up review found three additional product risks, also fixed in this stage:

- BNSS/CrPC dual-regime source matching is now section-family aware. A BNSS FIR source no longer satisfies a bail-source requirement.
- `bonded_labour_rescue` is now treated as a critical launch route in runtime and eval gates.
- Source-gap kind classification now prioritizes the missing required source over query words, so a missing BNSS/CrPC source in a witch-branding query is still labelled as a national criminal source gap.

A final review found two more BNSS/CrPC edge cases, also fixed:

- Runtime no longer mixes a regime name from one passage with a section anchor from another unrelated passage.
- Eval no longer falls back to token/aggregate scoring after a hard dual-regime source check fails.
- Section-anchor checks no longer treat `sec-359` as satisfying `sec-35`.
