# 500-Prompt Broad Product Eval - Patch18d

Date: 2026-06-11

Branch: `codex/latency-hardening`

Verdict: **not production ready yet**, but materially improved versus the earlier broad 500-prompt reports.

## Command

Backend:

```bash
DATABASE_URL=postgresql://lawrag:change-me-locally@127.0.0.1:5433/lawrag \
REDIS_HOST=127.0.0.1 REDIS_PORT=6380 \
OLLAMA_API_HOST=127.0.0.1 OLLAMA_HOST=127.0.0.1 OLLAMA_PORT=11434 \
UV_CACHE_DIR=/tmp/uv-cache-law-rag PYTHONPATH=. \
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8056
```

Timed eval:

```bash
UV_CACHE_DIR=/tmp/uv-cache-law-rag PYTHONPATH=. uv run python scripts/eval_timed_100.py \
  --api http://127.0.0.1:8056 \
  --queries-dir data/eval_500 \
  --limit 500 \
  --seed 2026061115 \
  --timeout-s 180 \
  --out /tmp/law_rag_stage_router_source_patch18/timed_eval500_patch18d_seed2026061115.jsonl \
  --report /tmp/law_rag_stage_router_source_patch18/timed_eval500_patch18d_seed2026061115.md
```

Product gate:

```bash
UV_CACHE_DIR=/tmp/uv-cache-law-rag PYTHONPATH=. uv run python scripts/eval_common_user_gate.py \
  /tmp/law_rag_stage_router_source_patch18/timed_eval500_patch18d_seed2026061115.jsonl \
  --prompts data/eval_500 \
  --report /tmp/law_rag_stage_router_source_patch18/product_gate_eval500_patch18d_seed2026061115.md \
  --failures-jsonl /tmp/law_rag_stage_router_source_patch18/product_gate_eval500_patch18d_seed2026061115.failures.jsonl \
  --min-rows 500 \
  --allow-fail
```

## Gate Result

Gate: **FAIL**

| Metric | Result | Target |
| --- | ---: | ---: |
| Rows | 500 | >= 500 |
| Product pass | 454/500 (90.8%) | >= 95.0% |
| Route match | 500/500 (100.0%) | >= 95.0% |
| Expected Act cited | 474/485 (97.7%) | >= 93.5% |
| First cited actionable | 500/500 (100.0%) | >= 95.0% |
| Refusals | 0 | 0 |
| Errors | 0 | 0 |
| Safety hard fails | 0 | 0 |
| p50 latency | 6.5s | <= 10.0s |
| p90 latency | 16.5s | <= 20.0s |
| LLM-path p90 | 21.7s (71 rows) | <= 20.0s |
| Template-path p90 | 7.0s (429 rows) | informational |
| Safe source gaps | 3 | 0 |
| Route source-gap rows | 3 | 0 |

## What Improved

Compared with the earlier 2026-06-04 broad `data/eval_500` report, this run improved from `338/500` product pass (`67.6%`) to `454/500` (`90.8%`). It also removed bad route fallbacks and safety hard fails in this run.

Compared with the Stage 5 fresh human-messy report, product pass improved from `321/500` (`64.2%`) to `454/500` (`90.8%`), expected Act cited improved from `92.1%` to `97.7%`, and p90 latency improved from `18.7s` to `16.5s`.

This is real progress, but it is still below the production gate.

## Failure Counts

| Failure | Count |
| --- | ---: |
| relevance_not_ok | 35 |
| expected_act_not_cited | 11 |
| expected_act_missing | 4 |
| route_required_source_gap | 3 |
| zero_ok_legal_sentences | 1 |

Failure owner split:

| Owner | Failures |
| --- | ---: |
| legacy_grounded_template | 21 |
| authority_graph | 18 |
| llm | 4 |
| common_workflow_contracts | 3 |

## Main Failure Clusters

1. Customs and trade: drawback rejection, import reclassification, ICEGATE/bill-of-entry hold. These are being handled as generic tax/GST and need a customs route/source contract.
2. Legal aid and undertrial representation: jail lawyer access, NALSA eligibility, undertrial lawyer not attending hearings. The answer is often legally sourced but not direct enough for user intent.
3. Criminal special-law defence: NDPS quantity, bhang/MDMA, UAPA default bail, PMLA interim/pre-arrest. These need variant-specific authority contracts and stronger expected-Act citation.
4. Family/domestic mixed facts: domestic violence plus divorce, residence exclusion, minimization after assault, streedhan after death. The router sees the domain, but the answer sometimes misses the exact remedy split.
5. Cheque bounce: stop-payment and company/signatory liability variants need Section 138 plus Section 141 handling.
6. Welfare and identity schemes: scholarship delay, Kanya Vivah scheme, mutation after death and succession-linked mutation source gaps.
7. Witch-branding/stalking/community harm: repeated victim-side witch-branding prompts need a stronger state-law/criminal safety path.
8. Labour/workplace: child labour age dispute, principal-employer accident liability, migrant return fare, gig termination, gratuity interest.
9. Procedure explainers: Article 32 vs 226, D.K. Basu/arrest memo, mutual-consent mediation, commercial pre-institution mediation, ex-parte set-aside. Some pass but are slow or too generic.

## Production Blockers

1. Product pass is `90.8%`, below the `95%` gate.
2. Critical-row metadata is absent in this prompt pack, so the strict `100% critical pass` production claim cannot be proven from this run.
3. LLM-path p90 is `21.7s`, above the `20s` gate even though overall p90 passes.
4. There are still `3` safe source gaps and `3` route source-gap rows.
5. Legacy templates still own too many failures. The next quality gains should replace brittle legacy answers with source-gated workflow contracts.

## Next Fix Order

1. Add a `customs_trade` route/source/action contract for drawback, bill of entry, misdeclaration, valuation/SVB, reclassification, show-cause/adjudication, and appeal.
2. Harden legal-aid and undertrial answer contracts: jail lawyer meeting, free lawyer/NALSA, lawyer not attending, DLSA/jail legal-aid clinic, trial-court custody review.
3. Add criminal-special-law contracts for NDPS quantity and Section 37, UAPA default bail vs 43D, PMLA interim/pre-arrest, and state prohibition/bhang edge cases.
4. Patch family/domestic mixed-remedy contracts: violence plus divorce, residence exclusion, streedhan after death, "should I stay" safety framing.
5. Patch cheque-bounce variants: stop payment, company drawer/signatory, Section 141, notice and limitation.
6. Fix source-gap rows: GST godown sealing, gig/platform termination, mutation after death.
7. Convert slow common LLM paths into deterministic contracts for court procedure, tax notices, commercial mediation, family status, manual-scavenging safety, consumer filing, and business contract workflows.
8. Rerun targeted failure-family evals, then a fresh 500 broad eval with critical/high-priority metadata enabled.

## Subagent Review

The review subagent agreed this is not production-ready. It called out:

- Product pass must reach at least `475/500`; this run has `454/500`.
- The critical gate is not proven because this prompt pack has `0` critical rows.
- Source gaps must be driven to `0`.
- Criminal special-law bail is the highest-risk answer layer: NDPS quantity/Section 37, UAPA default bail/43D, PMLA Section 45/proviso, and anticipatory-before-arrest need priority.
- Legacy templates own too many failures and should be replaced with specific contracts for customs, cheque bounce company/stop-payment, wills, inheritance, welfare/scholarship, stalking/witch-branding, and POSH retaliation.
- Authority-graph over-selection is visible in legal-aid, prison furlough/mulaqat, and tribal-land examples.
- Family/DV mixed-intent answers must preserve safety-first framing while still answering the user's divorce/residence/property question.
- The evaluator likely has some false negatives, but also false positives where route/citation passes hide weak legal nuance. The run still fails even after accounting for that.

## Artifact Paths

- Timed JSONL: `/tmp/law_rag_stage_router_source_patch18/timed_eval500_patch18d_seed2026061115.jsonl`
- Timed report: `/tmp/law_rag_stage_router_source_patch18/timed_eval500_patch18d_seed2026061115.md`
- Product gate report: `/tmp/law_rag_stage_router_source_patch18/product_gate_eval500_patch18d_seed2026061115.md`
- Product gate failures: `/tmp/law_rag_stage_router_source_patch18/product_gate_eval500_patch18d_seed2026061115.failures.jsonl`
