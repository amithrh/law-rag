# Fresh 500-Prompt Holdout Report

Date: 2026-07-28

This report records the post-review live holdout for the current Codex
worktree. The prompt rows and raw outputs remain under `/tmp`; no evaluation
data was added to the repository.

## Run

- Prompt pack: `/tmp/law-rag-20260728-fresh500/prompts/human_messy_500_fresh_2026072801.jsonl`
- Prompt rows: 500
- Wording: fresh generated human-like rewrites with prior generated prompt text excluded
- Evaluation caveat: these are synthetic human-like prompts, not production user logs
- Source basis: the curated `data/eval_500` source inventory was reused for comparable coverage scoring
- Priority mix: 182 critical, 318 high
- API: `http://127.0.0.1:8002`
- Runtime fingerprint: `764ab0abd8876e1195904609a9d312d779b3dc0e7d691232ac8ac2b269fa6a89`
- Timed results: `/tmp/law-rag-20260728-fresh500/timed_eval_500_final.jsonl`
- Timed report: `/tmp/law-rag-20260728-fresh500/timed_eval_500_final.md`
- Common-user report: `/tmp/law-rag-20260728-fresh500/common_user_gate_final.md`
- Safety report: `/tmp/law-rag-20260728-fresh500/safety_final.md`

All `500/500` requests completed with zero transport errors, zero API errors,
and zero refused in-scope prompts.

## Scorecard

| Metric | Result | Gate | Status |
| --- | ---: | ---: | --- |
| Common-user product pass | 160/500 (32.0%) | >=95% | FAIL |
| High-priority product pass | 81/318 (25.5%) | >=95% | FAIL |
| Critical product pass | 79/182 (43.4%) | 100% | FAIL |
| Expected Act cited | 207/485 (42.7%) | >=93.5% | FAIL |
| Expected Act hit | 209/485 (43.1%) | >=85% | FAIL |
| Must-term coverage | 352/500 (70.4%) | >=95% | FAIL |
| Route match | 500/500 (100%) | >=95% | PASS |
| First cited source actionable | 266/266 (100%) | >=95% | PASS |
| MatterPlan contract validity | 266/266 applicable rows | 100% | PASS |
| Legal-safety hard fails | 0/500 | 0 | PASS |
| Wall p50 | 5.5s | <=10s | PASS |
| Wall p90 | 6.3s | <=20s | PASS |
| LLM-path p90 | 25.0s | <=20s | FAIL |
| Visible source-gap handoffs | 234/500 | 0 | FAIL |
| Route required-source gaps | 12/500 | 0 | FAIL |
| Route citation gaps | 18/500 | 0 | FAIL |
| Timing telemetry coverage | 266/500 (53.2%) | >=95% | FAIL |

The safety gate passed all `500/500` rows, including source-gap handoffs. This
means the system is failing closed more reliably; it does not mean the product
is ready. The dominant failure is that the system cannot yet provide a
source-backed answer for too many ordinary legal matters.

## What The Run Proves

1. The request path is stable: no transport errors, API errors, or unsafe
   hard-fail responses occurred.
2. Routing is strong on this pack: `500/500` rows matched an allowed route.
3. The reviewed answer contracts are structurally valid whenever an answer
   row is produced, and the first cited source was actionable in every such
   row.
4. The main bottleneck is authority coverage and binding, not raw request
   latency. `234/500` rows became visible source-gap handoffs, and `249/500`
   rows had zero usable legal sentences under the quality rubric.
5. The LLM path is a minority path (`18/500`) but remains too slow at p90
   (`25.0s`) and cannot compensate for missing reviewed authority packs.

## Main Blockers

### 1. Coverage gaps are still product-visible

The largest repeated failure families are social-welfare/identity, employment
and EPF/ESI, trademarks/IP, IBC/NCLT, environment and land acquisition,
business licensing, prison visitation/parole, local land records, education,
and some consumer, cheque-bounce, and marriage matters. These are not solved
by asking users to rephrase; the route is often correct but the controlling
authority is absent or not retrievable.

### 2. Retrieved authorities are not always cited in the answer contract

The run recorded `15` uncited MatterPlan authority obligations and `18` route
required-source citation gaps. This is smaller than the corpus gap, but it is
high risk because a user can receive a plausible action path without seeing the
authority that should support it.

### 3. Safe handoff is not yet a useful one-step experience

The handoff is now bounded and safe, but `234` rows still stop before a
source-backed answer. The interface can therefore look like a refusal or an
empty result on common questions even when routing succeeded. The next fix
must add reviewed source packs and useful route-owned intake for the measured
clusters without reopening uncited server-controlled advice.

### 4. Small contract and operations defects remain

There was one bad general-legal fallback, four suppressed-sentence rows, one
dangling next-step header, three missing next-step sections, and only `266/500`
rows carried timing telemetry. These are not the largest quality problem, but
they must be removed before a production gate can pass.

## Verification

- Frontend unit tests: `26/26` passed.
- Frontend type-check: passed.
- Frontend production build: passed.
- Backend focused intake/source-gap/endpoint suite: `249 passed, 49 deselected`.
- Live 500-row safety evaluation: `500/500` pass, `0` hard fails.
- Independent implementation review: no remaining P1 issues after the final
  source-gap/refusal boundary hardening.

The post-holdout independent review classified the current blockers as P1:
core Act/provenance quality, non-answer volume, and relevance. It also called
out P2 observability/answer-shape defects and LLM-path latency. The review
agrees that expanding the corpus alone is insufficient: every outcome needs a
typed owner (verified answer, safe handoff, or refusal), and every enforced
authority obligation must be present in the final cited answer.

## Production Decision

**Not production-ready.** The current implementation is safer and more
deterministic than the earlier baseline, but it is materially below the
quality gate: `32.0%` product pass, `42.7%` expected Act cited coverage, and
`234/500` visible source gaps. Do not market it as a general one-stop legal
solution yet.

## Next Engineering Stages

1. Add reviewed authority packs and deterministic source contracts for the
   largest measured clusters, starting with EPF/ESI and labour, welfare and
   identity, trademark/IP, IBC/NCLT, prison routes, and environment/land.
2. Add an authority-obligation citation gate that blocks answer completion
   when a retrieved required authority is not cited, then test the affected
   routes directly.
3. Fix the one bad fallback, complete telemetry for source-gap rows, and
   remove the remaining answer-shape defects.
4. Run focused route tests and an independent review after each stage.
5. Rerun a new exact-prompt-excluded 500-row holdout. Production readiness
   requires the common-user, safety, provenance, and latency gates to pass
   together on a fresh holdout.
