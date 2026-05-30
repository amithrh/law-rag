# Timed 100-question eval

Rows: 13
Input/output: `data/processed/timed_eval_stage27_hardfail_after_workplace_action_fix.jsonl`

## Outcome

- Refused: 0/13
- Errors: 0/13
- Relevance verdicts: {'ok': 8, 'partial': 5}
- Expected Act hit: 11/11 (100.0%)
- Expected Act cited hit: 11/11 (100.0%)
- Expected Act unscored: 2/13
- Answer quality flags: {}
- Legal-safety gate: PASS (0/13 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 5.7s | 7.3s | 15.3s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | n/a | n/a | n/a |
| single_expanded_retrieval_ms | 1.9s | 2.2s | 6.0s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.2s | 0.2s |
| variant_rerank_ms | 3.3s | 3.6s | 8.7s |
| retrieval_ms | 5.0s | 5.8s | 14.8s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 0.0s | 0.0s | 2.4s |
| verification_ms | 0.2s | 0.3s | 0.5s |
| relevance_ms | 0.1s | 0.1s | 0.2s |

## Route Distribution

| route | count |
| --- | ---: |
| criminal_defence_bail | 3 |
| business_contract_partnership | 1 |
| property_tenancy | 1 |
| criminal_general | 1 |
| land_revenue_records | 1 |
| family_marriage_status | 1 |
| police_fir | 1 |
| cyber_fraud_or_harassment | 1 |
| workplace_injury_compensation | 1 |
| banking_credit_dispute | 1 |
| consumer | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| criminal_defence_bail | 3 |
| business_contract_partnership | 1 |
| property_tenancy | 1 |
| criminal_general | 1 |
| land_revenue_records | 1 |
| family_marriage_status | 1 |
| police_fir | 1 |
| cyber | 1 |
| workplace_injury_compensation | 1 |
| banking_credit_dispute | 1 |
| consumer | 1 |

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
| 15.3s | 14.8s | 0.0s | 0.3s | criminal_defence_bail | false dacoity case lodged on my brother by forest guard for collecting tendu leaves dindor |
| 7.5s | 5.0s | 2.4s | 0.5s | family_marriage_status | how to legally change my surname after marriage, do i need to publish in gazette |
| 6.2s | 5.8s | 0.0s | 0.2s | workplace_injury_compensation | site mukadam beat me head injury 8 stitches when i asked for old wages mumbai |
| 5.9s | 5.6s | 0.0s | 0.2s | cyber_fraud_or_harassment | data breach at byjus my pan and aadhaar leaked, can i claim compensation under DPDP act |
| 5.9s | 5.7s | 0.0s | 0.2s | banking_credit_dispute | cooperative bank seized my buffalo for crop loan default can they take livestock |
| 5.7s | 5.5s | 0.0s | 0.2s | consumer | society management has put a fine of 25000 on me for keeping a pet without prior approval, |
| 5.7s | 5.4s | 0.0s | 0.1s | criminal_defence_bail | son 17 yrs in adult jail puzhal pocso case age proof school certificate where to file |
| 5.4s | 5.0s | 0.0s | 0.3s | criminal_defence_bail | the spa was raided last week and police took me and other girls to station I just do massa |
| 5.1s | 4.8s | 0.0s | 0.2s | police_fir | i was undertrial 5 yrs released last week need help to file police torture case |
| 4.7s | 4.4s | 0.0s | 0.2s | property_tenancy | my dad signed property to son under pressure when he was in icu can challenge |
| 4.6s | 4.2s | 0.0s | 0.3s | business_contract_partnership | company hiding behind section 43B disallowance threat to delay my msme payment |
| 4.3s | 4.0s | 0.0s | 0.1s | land_revenue_records | sarpanch giving common village land to his brother no panchayat meeting was held |
| 4.2s | 3.8s | 0.0s | 0.2s | criminal_general | daughter in law took my jewellery worth 12 lakh saying for safe keeping not returning agra |

## Expected-Act Unscored

| persona | hint | route | query | reason |
| --- | --- | --- | --- | --- |
| stage26_final100 | Gazette notification process | family_marriage_status | how to legally change my surname after marriage, do i need to publish in gazette | state/procedure source key unavailable or conditional |
| stage26_final100 | Maharashtra Cooperative Societies Act | consumer | society management has put a fine of 25000 on me for keeping a pet without prior approval, | state/procedure source key unavailable or conditional |

## Expected-Act Misses

| persona | expected | route | query | top source |
| --- | --- | --- | --- | --- |

## Expected-Act Cited Misses

| persona | expected | route | query | cited answer excerpt |
| --- | --- | --- | --- | --- |
