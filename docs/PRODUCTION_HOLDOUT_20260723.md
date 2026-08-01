# Fresh 500-Prompt Holdout Report

Date: 2026-07-23

This report records the post-review live holdout for the current Codex
worktree. It contains aggregate metrics only. The prompt and row-level result
files remain under `/tmp` and are not repository data.

## Run

- Prompt pack: `/tmp/law-rag-20260723-fresh500/prompts/human_messy_500_fresh_2026072301.jsonl`
- Prompt rows: 500
- Unique generated queries: 500
- Unique source queries: 500
- Priority mix: 182 critical, 318 high
- API: `http://127.0.0.1:8002`
- Runtime fingerprint: `76152e11f50f3d41cb3820780d73e634af3057a4c05df4e32906416fd66043bb`
- Timed results: `/tmp/law-rag-20260723-fresh500/timed_eval_500_final.jsonl`
- Timed report: `/tmp/law-rag-20260723-fresh500/timed_eval_500_final.md`
- Common-user report: `/tmp/law-rag-20260723-fresh500/common_user_gate_final.md`

The run completed all `500/500` requests with zero transport errors, zero API
errors, and zero refused in-scope prompts.

## Scorecard

| Metric | Result | Gate | Status |
| --- | ---: | ---: | --- |
| Common-user product pass | 163/500 (32.6%) | >=95% | FAIL |
| High-priority product pass | 82/318 (25.8%) | >=95% | FAIL |
| Critical product pass | 81/182 (44.5%) | 100% | FAIL |
| Expected Act cited | 210/485 (43.3%) | >=93.5% | FAIL |
| Expected Act hit | 212/485 (43.7%) | >=85% | FAIL |
| Must-term coverage | 352/500 (70.4%) | >=95% | FAIL |
| Usable answer | 192/500 (38.4%) | >=85% | FAIL |
| Action pack | 269/500 (53.8%) | >=85% | FAIL |
| Route match | 500/500 (100%) | >=95% | PASS |
| First cited source actionable | 269/269 (100%) | >=95% | PASS |
| Legal-safety hard fails | 0/500 | 0 | PASS |
| Dangerous framing | 0 | 0 | PASS |
| Wall p50 | 5.0s | <=10s | PASS |
| Wall p90 | 5.8s | <=20s | PASS |
| LLM-path p90 | 21.0s | <=20s | FAIL |
| Visible source gaps | 231/500 | 0 | FAIL |

The strict quality gate also measured `0/500` unsafe refusals, `0` unknown
citation indices, and `0` wrong-regime safety labels. The system is safer and
more deterministic than before, but it is not production-ready as a general
legal assistant.

## What Improved

The reviewed retrieval-plan fix makes an owned workflow augment every matching
route source-pack variant with its exact reviewed anchors, search terms, and,
where declared, exact document IDs. This fixed the live SC/ST false-FIR path:
the API retrieved and verified official Sections 18 and 18A instead of handing
off because the police-FIR route had only requested Sections 3/4/14.

The certificate path remains fail-closed. ST and ambiguous SC/ST certificate
appeal queries stop on the missing State-specific rule rather than inventing a
deadline or forum. The live holdout recorded zero safety hard failures.

## Main Blockers

1. 231 rows became visible source-gap handoffs. They had route metadata but no
   usable source-backed answer, which is why the interface feels empty on many
   common questions.
2. The largest fully failing route families were trademark/IP, IBC/NCLT,
   environment compensation, workplace injury, business licensing, land
   records, street vendors, prison visitation/parole, manual scavenging, child
   marriage, and reproductive rights.
3. The model answer layer is not the primary blocker. The dominant issue is
   missing or insufficiently bound reviewed source packs and route-owned answer
   contracts.
4. 18 LLM-path rows had a p90 of 21.0s. Latency is secondary to quality for
   now, but the answer path still needs a hard timeout/fallback policy.

## Verification

- Independent review found no P0/P1 issues.
- Review P2: owner document IDs were not propagated into merged retrieval
  plans. Fixed by constraining every matching pack variant to the contract's
  exact document IDs.
- Focused post-fix tests: `4 passed` for PAN/document identity and `3 passed`
  for SC/ST owner paths.
- Affected no-stack regression suite: `1279 passed, 11 deselected`.

## Next Quality Queue

1. Build reviewed authority packs and deterministic contracts for the largest
   measured clusters: labour/EPF/ESI/MGNREGA, prison visitation/parole, local
   welfare, trademarks/IP, IBC/NCLT, environment/land acquisition, and local
   licensing.
2. Make every source-gap handoff carry a useful, route-specific intake/action
   pack and expose the missing authority clearly in the UI.
3. Add authority-obligation citation checks for the 16 uncited MatterPlan
   obligations and the 18 route citation gaps.
4. Fix the one bad general-legal fallback and the five suppressed-sentence
   rows before the next holdout.
5. Rerun a new exact-prompt-excluded 500 only after the focused packs and
   contracts pass their own tests. Do not call the product ready until the
   common-user and safety gates pass together.
