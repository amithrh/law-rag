# Timed 100-question eval

Rows: 13
Input/output: `data/processed/timed_eval_stage27_hardfail_smoke.jsonl`

## Outcome

- Refused: 0/13
- Errors: 0/13
- Relevance verdicts: {'ok': 12, 'off_topic': 1}
- Expected Act hit: 7/13 (53.8%)
- Legal-safety gate: FAIL (1/13 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 18.7s | 26.6s | 33.2s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | n/a | n/a | n/a |
| single_expanded_retrieval_ms | 1.9s | 2.2s | 6.5s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.2s | 0.2s |
| variant_rerank_ms | 3.4s | 3.9s | 9.4s |
| retrieval_ms | 5.2s | 6.0s | 16.0s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 13.0s | 16.7s | 23.7s |
| verification_ms | 0.3s | 0.5s | 1.2s |
| relevance_ms | 0.1s | 0.1s | 0.2s |

## Route Distribution

| route | count |
| --- | ---: |
| criminal_defence_bail | 3 |
| consumer | 1 |
| land_revenue_records | 1 |
| criminal_general | 1 |
| workplace_injury_compensation | 1 |
| police_fir | 1 |
| cyber_fraud_or_harassment | 1 |
| family_marriage_status | 1 |
| business_contract_partnership | 1 |
| banking_credit_dispute | 1 |
| property_tenancy | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| criminal_defence_bail | 3 |
| consumer | 1 |
| land_revenue_records | 1 |
| criminal_general | 1 |
| workplace_injury_compensation | 1 |
| police_fir | 1 |
| cyber | 1 |
| family_marriage_status | 1 |
| business_contract_partnership | 1 |
| banking_credit_dispute | 1 |
| property_tenancy | 1 |

## Legal Safety Gate

Gate: **FAIL**

| label | count |
| --- | ---: |
| wrong_forum | 0 |
| wrong_deadline | 0 |
| wrong_regime | 1 |
| dangerous_off_topic | 0 |
| unsafe_refusal | 0 |
| dangerous_framing | 0 |

### Legal-Safety Failures

| labels | route | expected | query | reasons |
| --- | --- | --- | --- | --- |
| wrong_regime | cyber_fraud_or_harassment | cyber | data breach at byjus my pan and aadhaar leaked, can i claim compensation under DPDP act | criminal route did not expose a BNS/BNSS/BSA vs IPC/CrPC regime state |

## Slowest Rows

| total | retrieval | llm | verify | route | query |
| ---: | ---: | ---: | ---: | --- | --- |
| 33.2s | 16.0s | 17.0s | 1.2s | consumer | society management has put a fine of 25000 on me for keeping a pet without prior approval, |
| 28.3s | 4.4s | 23.7s | 0.3s | land_revenue_records | sarpanch giving common village land to his brother no panchayat meeting was held |
| 19.7s | 4.0s | 15.6s | 0.4s | criminal_general | daughter in law took my jewellery worth 12 lakh saying for safe keeping not returning agra |
| 19.1s | 6.0s | 12.9s | 0.3s | workplace_injury_compensation | site mukadam beat me head injury 8 stitches when i asked for old wages mumbai |
| 19.1s | 6.0s | 13.0s | 0.2s | banking_credit_dispute | cooperative bank seized my buffalo for crop loan default can they take livestock |
| 18.8s | 5.7s | 13.0s | 0.2s | cyber_fraud_or_harassment | data breach at byjus my pan and aadhaar leaked, can i claim compensation under DPDP act |
| 18.7s | 4.5s | 14.1s | 0.3s | criminal_defence_bail | son 17 yrs in adult jail puzhal pocso case age proof school certificate where to file |
| 18.4s | 5.2s | 13.0s | 0.5s | family_marriage_status | how to legally change my surname after marriage, do i need to publish in gazette |
| 18.0s | 5.8s | 12.1s | 0.3s | property_tenancy | my dad signed property to son under pressure when he was in icu can challenge |
| 17.5s | 4.2s | 13.1s | 0.2s | criminal_defence_bail | false dacoity case lodged on my brother by forest guard for collecting tendu leaves dindor |
| 16.5s | 5.1s | 11.3s | 0.3s | criminal_defence_bail | the spa was raided last week and police took me and other girls to station I just do massa |
| 16.5s | 5.0s | 11.3s | 0.3s | police_fir | i was undertrial 5 yrs released last week need help to file police torture case |
| 14.8s | 5.3s | 9.4s | 0.3s | business_contract_partnership | company hiding behind section 43B disallowance threat to delay my msme payment |

## Expected-Act Misses

| persona | expected | route | query | top source |
| --- | --- | --- | --- | --- |
| stage26_final100 | Cooperative Societies Act | consumer | society management has put a fine of 25000 on me for keeping a pet without prior approval, | Consumer Protection Act 2019 |
| stage26_final100 | Juvenile Justice Act | criminal_defence_bail | son 17 yrs in adult jail puzhal pocso case age proof school certificate where to file | Bharatiya Nagarik Suraksha Sanhita 2023 |
| stage26_final100 | BNS, BNSS, IPC, NHRC Act | police_fir | i was undertrial 5 yrs released last week need help to file police torture case | Bharatiya Nagarik Suraksha Sanhita 2023 |
| stage26_final100 | State Welfare Scheme | family_marriage_status | how to legally change my surname after marriage, do i need to publish in gazette | W.P.(C)/221/2024 of QUDSIYA Vs CBSE & ANR. |
| stage26_final100 | Income Tax Act, MSMED Act | business_contract_partnership | company hiding behind section 43B disallowance threat to delay my msme payment | Indian Contract Act 1872 |
| stage26_final100 | Cooperative Societies Act, SARFAESI | banking_credit_dispute | cooperative bank seized my buffalo for crop loan default can they take livestock | Banking Regulation Act 1949 |
