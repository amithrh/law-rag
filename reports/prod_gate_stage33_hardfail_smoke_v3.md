# Timed 100-question eval

Rows: 7
Input/output: `data/processed/timed_eval_stage33_hardfail_smoke_v3.jsonl`

## Outcome

- Refused: 0/7
- Errors: 0/7
- Relevance verdicts: {'ok': 4, 'off_topic': 2, 'partial': 1}
- Expected Act hit: 6/6 (100.0%)
- Expected Act cited hit: 6/6 (100.0%)
- Expected Act unscored: 1/7
- Expected procedure anchor cited coverage: 0/0 (0.0%)
- Answer quality flags: {'missing_next_step_section': 2, 'suppressed_sentences': 3, 'zero_ok_legal_sentences': 2, 'no_concrete_next_step': 1}
- Legal-safety gate: FAIL (1/7 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 5.8s | 17.3s | 17.6s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | n/a | n/a | n/a |
| single_expanded_retrieval_ms | 0.9s | 4.4s | 7.8s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.2s | 0.2s |
| variant_rerank_ms | 3.5s | 6.1s | 9.4s |
| retrieval_ms | 4.9s | 10.3s | 17.3s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 0.0s | 11.7s | 12.2s |
| verification_ms | 0.2s | 0.4s | 0.6s |
| relevance_ms | 0.1s | 0.1s | 0.1s |

## Route Distribution

| route | count |
| --- | ---: |
| social_welfare_identity | 1 |
| child_custody_adoption | 1 |
| employment_wages | 1 |
| tribal_caste_atrocity | 1 |
| environment_compensation | 1 |
| digital_platform_account | 1 |
| consumer | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| social_welfare_identity | 1 |
| child_custody_adoption | 1 |
| employment_wages | 1 |
| tribal_caste_atrocity | 1 |
| environment_compensation | 1 |
| digital_platform_account | 1 |
| consumer | 1 |

## Answer Quality Flags

| flag | count |
| --- | ---: |
| suppressed_sentences | 3 |
| missing_next_step_section | 2 |
| zero_ok_legal_sentences | 2 |
| no_concrete_next_step | 1 |

## Legal Safety Gate

Gate: **FAIL**

| label | count |
| --- | ---: |
| wrong_forum | 0 |
| wrong_deadline | 0 |
| wrong_regime | 0 |
| dangerous_off_topic | 1 |
| unsafe_refusal | 0 |
| dangerous_framing | 0 |

### Legal-Safety Failures

| labels | route | expected | query | reasons |
| --- | --- | --- | --- | --- |
| dangerous_off_topic | consumer | civil | my neighbor is parking his car blocking my dedicated parking slot in apartment, security g | legal/safety prompt was classified or judged off-topic without enough route/source support |

## Slowest Rows

| total | retrieval | llm | verify | route | query |
| ---: | ---: | ---: | ---: | --- | --- |
| 17.6s | 17.3s | 0.0s | 0.1s | social_welfare_identity | I want to change my gender on aadhar and 10th certificate I have not had surgery is it pos |
| 17.2s | 5.7s | 11.4s | 0.2s | consumer | my neighbor is parking his car blocking my dedicated parking slot in apartment, security g |
| 16.7s | 4.4s | 12.2s | 0.6s | tribal_caste_atrocity | non tribal sahukar took my land in mortgage 15 years now refusing return jharkhand |
| 5.8s | 5.5s | 0.0s | 0.2s | digital_platform_account | cab driver mumbai uber deactivated rating low because customer racist hindi speaker |
| 5.4s | 4.9s | 0.0s | 0.3s | employment_wages | construction company retrenched 40 of us bengali workers kept the gujaratis next day same  |
| 4.9s | 4.6s | 0.0s | 0.2s | environment_compensation | iron ore mine displaced our 12 villages no rehabilitation given keonjhar |
| 4.1s | 3.9s | 0.0s | 0.1s | child_custody_adoption | court ordered supervised visitation for my daughter but my ex's lawyer is asking unsupervi |

## Expected-Act Unscored

| persona | hint | route | query | reason |
| --- | --- | --- | --- | --- |
| stage32_final100 | Cooperative Societies Act | consumer | my neighbor is parking his car blocking my dedicated parking slot in apartment, security g | state/procedure source key unavailable or conditional |

## Expected-Act Misses

| persona | expected | route | query | top source |
| --- | --- | --- | --- | --- |

## Expected-Act Cited Misses

| persona | expected | route | query | cited answer excerpt |
| --- | --- | --- | --- | --- |

## Expected Procedure Anchor Misses

| persona | procedure | route | query | missing cited anchors |
| --- | --- | --- | --- | --- |
| none | n/a | n/a | n/a | n/a |
