# Fresh 500 Human-Messy Product Eval - 2026-06-18

Verdict: **not production ready**, but the failure is now concrete and narrower than before.

This run used a fresh generated 500-prompt human-style pack, not the older curated 100/200 prompts. The prompts were generated from `data/eval_500` with new messy UI wording and exact-query exclusions for prior 500 prompt packs.

## Commands

```bash
PYTHONPATH=. .venv/bin/python scripts/build_human_messy_eval.py \
  --source data/eval_500 \
  --out-dir /tmp/law_rag_20260618_broad500_fresh/prompts \
  --limit 500 \
  --seed 2026061801 \
  --filename human_messy_500_seed2026061801.jsonl \
  --exclude-exact-prompts data/eval_human_messy_500_stage_e9_seed2026061709 \
  --exclude-exact-prompts data/eval_human_messy_500_stage_e9b_seed2026061712 \
  --exclude-exact-prompts data/eval_human_messy_500_fresh_seed2026061307 \
  --exclude-exact-prompts data/eval_human_messy_500_fresh_exact_seed2026061307

PYTHONPATH=. .venv/bin/python scripts/eval_timed_100.py \
  --api http://127.0.0.1:8000 \
  --queries-dir /tmp/law_rag_20260618_broad500_fresh/prompts \
  --limit 500 \
  --seed 2026061801 \
  --timeout-s 120 \
  --out /tmp/law_rag_20260618_broad500_fresh/results/timed_eval_500_seed2026061801.jsonl \
  --report /tmp/law_rag_20260618_broad500_fresh/results/timed_eval_500_seed2026061801.md

PYTHONPATH=. .venv/bin/python scripts/eval_common_user_gate.py \
  /tmp/law_rag_20260618_broad500_fresh/results/timed_eval_500_seed2026061801.jsonl \
  --prompts /tmp/law_rag_20260618_broad500_fresh/prompts \
  --report /tmp/law_rag_20260618_broad500_fresh/results/common_user_gate_500_seed2026061801.md \
  --failures-jsonl /tmp/law_rag_20260618_broad500_fresh/results/common_user_gate_500_seed2026061801.failures.jsonl \
  --allow-fail

PYTHONPATH=. .venv/bin/python scripts/build_failure_ledger.py \
  /tmp/law_rag_20260618_broad500_fresh/results/timed_eval_500_seed2026061801.jsonl \
  --prompts /tmp/law_rag_20260618_broad500_fresh/prompts \
  --jsonl /tmp/law_rag_20260618_broad500_fresh/results/failure_ledger_500_seed2026061801.jsonl \
  --csv /tmp/law_rag_20260618_broad500_fresh/results/failure_ledger_500_seed2026061801.csv \
  --report /tmp/law_rag_20260618_broad500_fresh/results/failure_ledger_500_seed2026061801.md
```

## Headline Metrics

| metric | result | production gate |
| --- | ---: | ---: |
| rows | 500 | >= 500 |
| errors | 0/500 | 0 |
| refusals | 0/500 | 0 |
| relevance OK | 497/500 | should be near 100% |
| expected Act hit | 478/485 (98.6%) | >= 85% minimum, higher for launch |
| expected Act cited | 461/485 (95.1%) | >= 93.5% |
| strict product pass | 469/500 (93.8%) | >= 95% |
| common-user product pass | 440/500 (88.0%) | >= 95% |
| critical pass | 158/183 (86.3%) | 100% |
| route match | 499/500 (99.8%) | >= 95% |
| first cited actionable | 500/500 (100.0%) | >= 95% |
| safety hard fails | 1/500 | 0 |
| visible source-gap rows | 6/500 | 0 |
| p50 latency | 7.1s | <= 10s |
| p90 latency | 8.8s | <= 20s |
| LLM-path p90 | 22.6s | <= 20s |
| max latency | 31.7s | should be much lower |

## Improvement Read

This is not the same stagnant system we had earlier, but it is still not launch-grade.

Compared with the Stage 5 fresh human-messy 500 report from 2026-06-04:

| metric | Stage 5 fresh 500 | 2026-06-18 fresh 500 | delta |
| --- | ---: | ---: | ---: |
| common-user product pass | 321/500 (64.2%) | 440/500 (88.0%) | +23.8pp |
| expected Act cited | 446/484 (92.1%) | 461/485 (95.1%) | +3.0pp |
| relevance OK | 432/500 | 497/500 | +65 |
| refusals/errors | 0/500 | 0/500 | flat good |
| p50 latency | 6.5s | 7.1s | slightly worse |
| p90 latency | 18.7s | 8.8s | better |

Compared with Patch18d curated `data/eval_500`, this fresh human-messy run is harder. Patch18d had `454/500` product pass on the curated set; this fresh pack has `440/500` common-user product pass, but a stricter timed pass of `469/500`.

## Why We Are Still Not Production Ready

1. **One safety hard fail remains.**
   - Query: `urgent brother in jail 18 months UAPA bail when prima facie case made out kya hota how to complain`
   - Problem: answer fell into an undertrial/legal-aid framing and cited BNSS/CrPC undertrial-release concepts, but UAPA bail requires a stricter UAPA-specific answer path.

2. **Citation discipline is still below launch quality.**
   - `24` rows had `expected_act_not_cited`.
   - Retrieval often found the right authority, but the answer did not cite it in the actionable sentence.
   - Main clusters: cyber image/privacy abuse, family/domestic, labour/wage, business/MSME, environmental/tribal consent.

3. **Route-required source gaps still appear.**
   - `6` visible source-gap rows.
   - Missing source families:
     - Article 17 / Protection of Civil Rights Act for temple-entry/public-access untouchability.
     - EPFO/EPS pension authority.
     - BNSS/CrPC bail procedure in UAPA/default bail variants.
     - BNSS/CrPC complaint procedure for discrimination/wage-retaliation criminal route.

4. **Critical pass is too low.**
   - Critical pass was `158/183` (`86.3%`), but launch needs `100%` for critical safety/criminal/cyber/family prompts.

5. **Common-user specificity is still weak.**
   - Product gate pass was `440/500` (`88.0%`), below the `95%` target.
   - `27` rows missed scenario-specific terms even when the broad answer was legally plausible.

6. **LLM fallback latency is still above the gate.**
   - Overall p90 is good at `8.8s`, but LLM-path p90 is `22.6s`.
   - Slow families: court procedure, Aadhaar/social welfare, disability, FSSAI/business licensing, family-marriage, GST/customs.

## Failure Ledger Summary

| root cause | rows | critical |
| --- | ---: | ---: |
| scenario_specificity_gap | 23 | 2 |
| citation_discipline_gap | 15 | 7 |
| route_required_source_gap | 6 | 3 |
| source_or_retrieval_gap | 5 | 4 |
| answer_support_floor | 4 | 4 |
| missing_next_step_section | 4 | 4 |
| variant_answer_gap | 2 | 0 |
| legal_safety_hard_fail | 1 | 1 |

## Fix Order

1. **UAPA / criminal-defence safety gate**
   - Stop UAPA bail from falling into generic undertrial-release framing.
   - Require UAPA 43D and custody/prolonged-incarceration authority where the query mentions UAPA, prima facie, 43D, long custody, or no trial.

2. **Cyber image/privacy citation gate**
   - For deepfake, leaked nudes, therapist chats, unsolicited sexual images, OnlyFans/content leak, and lookalike porn, require the relevant IT Act / BNS / DPDP / takedown authority to be cited in the answer.

3. **Family/domestic citation gate**
   - For streedhan, marital sexual coercion, disabled infant abandonment, dowry/DV, and maintenance, require PWDVA / family-court / criminal source citation based on subtype.

4. **Tribal/caste/public-access source contracts**
   - Add or enforce Article 17 and Protection of Civil Rights Act for temple/public-access discrimination.
   - Cleanly split scheduled-area/tribal land transfer from ordinary land mutation records.

5. **EPFO/EPS and social-welfare source packs**
   - Add/enforce EPF/EPS pension authority for pension arrears and Aadhaar mismatch pension prompts.
   - Add state welfare scheme handling for Kanya Vivah-like benefit denials.

6. **Convert slow LLM procedure routes into reviewed workflows**
   - Court procedure: affidavit/notary, pre-litigation mediation, ex parte setting aside, summons/service, transfer, condonation.
   - Administrative: caste certificate, Aadhaar/social welfare, FSSAI category notices.

## Artifacts

- Prompts: `/tmp/law_rag_20260618_broad500_fresh/prompts/human_messy_500_seed2026061801.jsonl`
- Timed JSONL: `/tmp/law_rag_20260618_broad500_fresh/results/timed_eval_500_seed2026061801.jsonl`
- Timed report: `/tmp/law_rag_20260618_broad500_fresh/results/timed_eval_500_seed2026061801.md`
- Product gate report: `/tmp/law_rag_20260618_broad500_fresh/results/common_user_gate_500_seed2026061801.md`
- Failure ledger: `/tmp/law_rag_20260618_broad500_fresh/results/failure_ledger_500_seed2026061801.md`
