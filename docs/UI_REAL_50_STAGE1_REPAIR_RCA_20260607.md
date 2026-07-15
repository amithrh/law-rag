# UI-Real 50 Stage-1 Repair RCA - 2026-06-07

## Scope

This note records the burned UI-real 50 diagnostic after repairing the visible common-user failures. This prompt pack is not fresh product proof anymore because it was inspected and patched against. It is a regression diagnostic before moving to a fresh gate.

Prompt pack:

- `/tmp/law_rag_ui_real_50_seed2026060703/prompts_stage1_patch/human_messy_50_seed2026060703_stage1_patch.jsonl`

Final diagnostic outputs:

- timed eval: `/tmp/law_rag_ui_real_50_seed2026060703/out_stage1_patch4/timed_eval_ui_real_50_stage1_patch4.jsonl`
- product gate: `/tmp/law_rag_ui_real_50_seed2026060703/out_stage1_patch4/product_gate_ui_real_50_stage1_patch4.md`
- failures: `/tmp/law_rag_ui_real_50_seed2026060703/out_stage1_patch4/product_gate_ui_real_50_failures_stage1_patch4.jsonl`

## Final Diagnostic Metrics

Gate status: FAIL, but only on source-gap gates.

| metric | value | target |
| --- | ---: | ---: |
| product pass | 49/50 (98.0%) | >= 95% |
| critical pass | 18/18 (100.0%) | 100% |
| route match | 50/50 (100.0%) | >= 95% |
| expected Act cited | 47/48 (97.9%) | >= 93.5% |
| first cited actionable | 50/50 (100.0%) | >= 95% |
| must terms | 50/50 (100.0%) | >= 95% |
| errors/refusals/bad fallback | 0/0/0 | 0 |
| safety hard fails | 0 | 0 |
| p50 latency | 6.9s | <= 10s |
| p90 latency | 17.6s | <= 20s |
| LLM-path p90 | 19.2s | <= 20s |
| safe source gaps | 1 | 0 |
| route source-gap rows | 17 | 0 |

## What Was Actually Fixed

### Acid-threat critical failure

Failure before patch:

- Query: `please help my mother in law is threatening to throw acid on me...`
- BNS Section 125 was retrieved but not cited.
- The answer cited only PWDVA, so the gate flagged `expected_act_not_cited` and `zero_ok_legal_sentences`.

Fix:

- Made the domestic-safety authority graph render the BNS line source-close and conditional.
- The answer now says to verify BNS Section 125 only if the facts show an act done rashly or negligently endangering human life or personal safety.
- Added a narrow verifier bridge for this exact server-authored acid/life-safety wording on domestic/police safety routes.
- Avoided broad `safety_primary` auto-promotion.

Live proof:

- one-row acid check: `/tmp/law_rag_single_acid_check/acid_eval.jsonl`
- result: `route=police_fir`, `act_hit=True`, `cited=True`
- full diagnostic row also passed in `out_stage1_patch4`.

### NDPS runtime error

Failure introduced during the acid patch:

- Query: `husband ndps 200 gram heroin commercial bail rejected 3 times...`
- HTTP 500 from `authority_graph._source_anchor` helper name collision.

Fix:

- Removed the duplicate two-argument `_source_anchor`.
- Reused the existing three-argument helper.
- Added/ran focused NDPS and acid tests.

Live proof:

- one-row NDPS check: `/tmp/law_rag_single_ndps_check/ndps_eval.jsonl`
- result: `route=criminal_defence_bail`, `act_hit=True`, `cited=True`
- full diagnostic row passed in `out_stage1_patch4`.

## Eval Metadata Corrections

The regenerated stage prompt metadata corrected scenario-specific must terms. These are diagnostic corrections, not product improvements by themselves.

Examples:

- marriage age: `legal age`, `21`, `18`, `child marriage`, `consent`
- prison/books/mulaqat: `prison`, `jail`, `mulaqat`, `books`, `superintendent`
- creator/Fanvue payout: `platform`, `payout`, `foreign exchange`, `income tax`, `gst`, `bank`
- Christian widow/stepchildren: `succession`, `widow`, `stepchildren`, `lineal descendants`, `civil`
- employment notice period: `notice period`, `offer letter`, `60 days`, `90 days`, `hr`, `contract`
- pet society fine: `civil`, `society`, `cooperative`, `fine`, `pet`

Rationale: the old labels were often broad family/property/employment buckets that failed to measure the concrete user issue.

## Remaining Product Blocker

The only product-failing row in this burned diagnostic is Tamil Nadu shop-license renewal:

- Query: `tamil nadu shop license renewal pending 2 years coimbatore shopkeeper penalty...`
- Route: `business_license_compliance`
- Failure: `expected_act_missing`, `expected_act_not_cited`
- Missing source: state Shops and Establishments Act/rules.

The current answer honestly avoids FSSAI unless food-safety facts exist and uses RTI/written-records steps, but it cannot cite the expected Tamil Nadu state source because that source is not in the retrieved index.

Do not fix this by citing FSSAI, generic RTI, or a judgment as the controlling authority. The product-ready fix is one of:

1. add verified Tamil Nadu shop/trade-license source coverage, or
2. mark this as an explicit state/local source gap and keep it from being counted as fully solved.

## Source-Gap Ledger From This Diagnostic

The gate still reports 17 route source-gap rows:

- national labour sources: 7
- state/local authority sources: 4
- constitutional authority sources: 3
- national statute retrieval gaps: 2
- supporting records gap: 1
- national criminal source gap: 1
- national tax source gap: 1
- conditional authority gap: 1

This is the next architecture stage. The route/answer layer can now pass many common prompts, but production readiness requires source coverage and source-slot ownership.

## Next Gate Discipline

- This burned UI-real 50 must remain diagnostic only.
- Next product evidence must use a fresh prompt pack.
- Do not run 500 as the next debugging step.
- Next sequence: Pro review -> source-gap stage -> targeted tests -> fresh UI-real 50 v2 -> fresh 200 -> fresh 500.

## Patch5 Source-Gap Repair Addendum

After Pro review, the Tamil Nadu/Coimbatore shop-license row was treated as a
real product gap, not evaluator noise. The repair was intentionally source-led:

- added `scripts/add_tamil_nadu_shop_sources.py`, an idempotent backfill for
  official IndiaCode Tamil Nadu Shops and Establishments Act chunks and the
  Coimbatore Corporation D&O trade-licence renewal/penalty page;
- added `tamil_nadu_shops_establishments_1947` and
  `coimbatore_trade_license_2026` source packs;
- fixed the local-source type mismatch by classifying the Coimbatore page as a
  `guideline` and allowing the pack to fetch guideline/official-guidance
  chunks, not only `bare_act`;
- made `shop_license_renewal` a primary workflow so the answer does not fall
  back to a judgment or generic LLM paragraph when exact sources are available;
- added positive source-pack tests, non-pollution tests for other states, and
  common-workflow tests for both exact-source and source-gap behavior.

Focused proof:

- `PYTHONPATH=. .venv/bin/python -m pytest apps/api/tests/test_common_workflow_contracts.py apps/api/tests/test_source_packs.py -q`
  -> `262 passed, 1 warning`
- one-row Coimbatore eval:
  `/tmp/law_rag_single_tn_shop_check/tn_shop_eval2.jsonl`
  -> `route=business_license_compliance`, `act_hit=True`, `cited=True`,
  `16.1s`
- the answer cited:
  - `Coimbatore City Municipal Corporation Licensing of Offensive Trades`
  - `Tamil Nadu Shops and Establishments Act 1947`
  - `Right to Information Act 2005`

Burned UI-real 50 patch5 diagnostic:

- timed eval:
  `/tmp/law_rag_ui_real_50_seed2026060703/out_stage1_patch5/timed_eval_ui_real_50_stage1_patch5.jsonl`
- product gate:
  `/tmp/law_rag_ui_real_50_seed2026060703/out_stage1_patch5/product_gate_ui_real_50_stage1_patch5.md`

Patch5 result:

| metric | value | target |
| --- | ---: | ---: |
| product pass | 50/50 (100.0%) | >= 95% |
| high priority pass | 32/32 (100.0%) | >= 95% |
| critical pass | 18/18 (100.0%) | 100% |
| route match | 50/50 (100.0%) | >= 95% |
| expected Act cited | 48/48 (100.0%) | >= 93.5% |
| first cited actionable | 50/50 (100.0%) | >= 95% |
| errors/refusals/bad fallback | 0/0/0 | 0 |
| safety hard fails | 0 | 0 |
| p50 latency | 6.9s | <= 10s |
| p90 latency | 17.3s | <= 20s |
| LLM-path p90 | 20.4s | <= 20s |
| safe source gaps | 1 | 0 |
| route source-gap rows | 16 | 0 |

This means the visible product failure was repaired, but production readiness is
still not proven. The gate still fails because this is only 50 burned rows, the
critical-row count is below the production gate, one LLM-path p90 value is just
over 20 seconds, and route-source gaps remain.

Remaining source-gap families from patch5:

- state prison/parole/furlough and Tihar visit/book rules;
- FSSAI Licensing and Registration Regulations for food notice/misbranding;
- CGST/GST registration authority;
- Code on Wages / Payment of Wages / Industrial Disputes sources;
- Article 21/22/226 constitutional liberty anchors;
- exact criminal-compounding source for Lok Adalat questions;
- state BOCW/labour welfare source for construction accidents;
- society/pet fine conditional civil or society-law source;
- Aadhaar Act and RTI records route for lost ration/Aadhaar reconstruction;
- constitutional reproductive-autonomy/privacy precedent for late MTP cases;
- Copyright Act source for platform copyright-strike questions.

## Patch6 Chhattisgarh Tonahi Source-Gap Repair

The remaining safe-source-gap row was a Chhattisgarh `tonhi` false-case prompt:

- query:
  `can u tell they say i am tonhi after child died in village false case filed chhattisgarh what can i do`
- expected source:
  `Chhattisgarh Tonahi Pratadna Nivaran Act 2005`

Repair:

- added `scripts/add_chhattisgarh_tonahi_sources.py`, an idempotent IndiaCode
  backfill for sections 1, 2, 3, 4, 5, and 10;
- added/validated `chhattisgarh_tonahi_2005` source-pack selection for
  Chhattisgarh, common misspelling `chattisgarh`, and district aliases;
- fixed the source-title mismatch by letting answer templates recognize
  `Tonahi`, not only user spelling `tonhi`;
- preserved state-source filters so Chhattisgarh law is dropped for Assam,
  Jharkhand/Ranchi/Gumla, Bihar, and state-unknown prompts;
- improved victim and accused answer wording so exact Chhattisgarh matches name
  the Chhattisgarh Tonahi Act instead of generic `state-specific law`.

Focused proof:

- compile:
  `PYTHONPATH=. .venv/bin/python -m py_compile apps/api/main.py apps/api/source_packs.py apps/api/common_workflow_contracts.py scripts/add_chhattisgarh_tonahi_sources.py`
  -> passed
- tests:
  `PYTHONPATH=. .venv/bin/python -m pytest apps/api/tests/test_source_packs.py::test_witch_false_case_does_not_trigger_generic_child_pocso_packs apps/api/tests/test_source_packs.py::test_witch_branding_ranchi_uses_national_criminal_sources_not_assam_pack apps/api/tests/test_source_packs.py::test_tribal_witch_branding_gets_poa_and_criminal_sources apps/api/tests/test_endpoints.py::test_state_specific_filter_drops_wrong_state_witch_act apps/api/tests/test_endpoints.py::test_witch_branding_victim_template_does_not_use_wrong_state_act apps/api/tests/test_endpoints.py::test_witch_branding_victim_template_cites_chhattisgarh_tonahi_source apps/api/tests/test_endpoints.py::test_grounded_template_for_witch_accused_false_case_keeps_tonhi_context apps/api/tests/test_endpoints.py::test_stage24_templates_do_not_inject_smoke_specific_facts_for_near_misses -q`
  -> `8 passed`
- exact one-row eval:
  `/tmp/law_rag_single_chhattisgarh_tonahi_check/tonahi_eval.jsonl`
  -> `criminal_defence_bail`, `act_hit=True`, `cited=True`, `16.7s`,
  first cited source `Chhattisgarh Tonahi Pratadna Nivaran Act 2005`
- negative-neighbor probe:
  `/tmp/law_rag_tonahi_neighbor_out/tonahi_neighbors_eval.jsonl`
  -> `0/10` non-Chhattisgarh prompts cited the Chhattisgarh Act; `2/2`
  Chhattisgarh positives cited and named it.

This removes the known Tonahi safe-source-gap from the burned UI-real 50
diagnostic, but it does not make the system production-ready. The remaining
work is still the route-source-gap ledger, LLM-tail ownership, fresh UI-real 50
v2, fresh 200, and only then fresh 500.
