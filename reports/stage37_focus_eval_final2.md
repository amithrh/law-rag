# Stage37 focused timed eval

Focused 12-prompt blocker regression. This validates the Stage37 repaired prompts only; it is not a production gate or blind 100-prompt benchmark.

Rows: 12
Input/output: `data/processed/timed_eval_stage37_focus_final2_20260530.jsonl`

## Outcome

- Refused: 0/12
- Errors: 0/12
- Relevance verdicts: {'ok': 12}
- Expected Act hit: 12/12 (100.0%)
- Expected Act cited hit: 12/12 (100.0%)
- Expected Act unscored: 0/12
- Expected procedure anchor cited coverage: 0/0 (0.0%)
- Answer quality flags: {}
- Legal-safety gate: PASS (0/12 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 6.1s | 6.7s | 7.2s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | n/a | n/a | n/a |
| single_expanded_retrieval_ms | 2.2s | 2.5s | 2.9s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.2s | 0.2s |
| variant_rerank_ms | 3.6s | 3.8s | 3.9s |
| retrieval_ms | 5.7s | 6.4s | 6.8s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 0.0s | 0.0s | 0.0s |
| verification_ms | 0.2s | 0.3s | 0.3s |
| relevance_ms | 0.1s | 0.1s | 0.1s |

## Route Distribution

| route | count |
| --- | ---: |
| bonded_labour_rescue | 4 |
| cyber_fraud_or_harassment | 2 |
| criminal_defence_bail | 2 |
| banking_credit_dispute | 1 |
| social_welfare_identity | 1 |
| child_custody_adoption | 1 |
| arrest_custody_safeguard | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| bonded_labour_rescue | 4 |
| cyber | 2 |
| criminal_defence_bail | 2 |
| banking_credit_dispute | 1 |
| social_welfare_identity | 1 |
| child_custody_adoption | 1 |
| arrest_custody_safeguard | 1 |

## Answer Quality Flags

| flag | count |
| --- | ---: |
| none | 0 |

## Legal Safety Gate

Gate: **PASS**

| label | count |
| --- | ---: |
| wrong_forum | 0 |
| wrong_deadline | 0 |
| wrong_regime | 0 |
| dangerous_off_topic | 0 |
| unsafe_refusal | 0 |
| dangerous_framing | 0 |

### Legal-Safety Failures

| labels | route | expected | query | reasons |
| --- | --- | --- | --- | --- |

## Slowest Rows

| total | retrieval | llm | verify | route | query |
| ---: | ---: | ---: | ---: | --- | --- |
| 7.2s | 6.8s | 0.0s | 0.2s | social_welfare_identity | ration card west bengal not working in chennai shop no rice for family one nation one card |
| 6.7s | 6.2s | 0.0s | 0.3s | child_custody_adoption | my husband took our 5 year old to delhi during fight and is not letting me meet how do I g |
| 6.6s | 6.4s | 0.0s | 0.1s | bonded_labour_rescue | release certificate not given to bonded labour rehab money pending 3 years jharkhand |
| 6.5s | 6.3s | 0.0s | 0.1s | bonded_labour_rescue | brick kiln owner up keeping family hostage advance 25000 cannot go home wife sick |
| 6.3s | 5.8s | 0.0s | 0.3s | criminal_defence_bail | 16 yr daughter arrested theft put in observation home or jail how to verify age |
| 6.1s | 5.8s | 0.0s | 0.2s | cyber_fraud_or_harassment | he took my private pictures during video call now threatening to put on telegram |
| 6.0s | 5.6s | 0.0s | 0.2s | arrest_custody_safeguard | papa arrest 5 din ho gaya magistrate ke samne kab le jana hota hai |
| 5.8s | 5.5s | 0.0s | 0.2s | criminal_defence_bail | police came to spa where I work in delhi I ran away am I in trouble do I need lawyer they  |
| 5.3s | 4.9s | 0.0s | 0.3s | cyber_fraud_or_harassment | my schoolmate is making deepfake nude videos of girls in class using AI and circulating I  |
| 5.3s | 4.8s | 0.0s | 0.3s | banking_credit_dispute | private cooperative bank fd of grandfather not honoured nominee facing harassment |
| 5.2s | 4.8s | 0.0s | 0.2s | bonded_labour_rescue | bonded labour rehabilitation 200000 release certificate how to get jharkhand sdm office |
| 4.8s | 4.6s | 0.0s | 0.1s | bonded_labour_rescue | thekedar took my aadhaar original 6 months back not returning he keeping bihar workers id |

## Expected-Act Unscored

| persona | hint | route | query | reason |
| --- | --- | --- | --- | --- |
| none | n/a | n/a | n/a | n/a |

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
