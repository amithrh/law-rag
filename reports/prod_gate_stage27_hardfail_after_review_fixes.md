# Timed 100-question eval

Rows: 13
Input/output: `data/processed/timed_eval_stage27_hardfail_after_review_fixes.jsonl`

## Outcome

- Refused: 0/13
- Errors: 0/13
- Relevance verdicts: {'ok': 10, 'partial': 2, 'no_relevance': 1}
- Expected Act hit: 8/12 (66.7%)
- Expected Act cited hit: 4/12 (33.3%)
- Answer quality flags: {'expected_act_not_cited': 8, 'dangling_next_step_header': 2, 'no_concrete_next_step': 1}
- Legal-safety gate: PASS (0/13 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 17.6s | 25.8s | 29.7s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | n/a | n/a | n/a |
| single_expanded_retrieval_ms | 1.9s | 2.2s | 5.8s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.2s | 0.2s |
| variant_rerank_ms | 3.4s | 3.8s | 8.3s |
| retrieval_ms | 5.2s | 5.9s | 14.2s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 12.0s | 14.8s | 23.2s |
| verification_ms | 0.3s | 0.4s | 0.6s |
| relevance_ms | 0.1s | 0.1s | 0.2s |

## Route Distribution

| route | count |
| --- | ---: |
| criminal_defence_bail | 3 |
| criminal_general | 1 |
| business_contract_partnership | 1 |
| land_revenue_records | 1 |
| cyber_fraud_or_harassment | 1 |
| banking_credit_dispute | 1 |
| police_fir | 1 |
| workplace_injury_compensation | 1 |
| consumer | 1 |
| family_marriage_status | 1 |
| property_tenancy | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| criminal_defence_bail | 3 |
| criminal_general | 1 |
| business_contract_partnership | 1 |
| land_revenue_records | 1 |
| cyber | 1 |
| banking_credit_dispute | 1 |
| police_fir | 1 |
| workplace_injury_compensation | 1 |
| consumer | 1 |
| family_marriage_status | 1 |
| property_tenancy | 1 |

## Answer Quality Flags

| flag | count |
| --- | ---: |
| expected_act_not_cited | 8 |
| dangling_next_step_header | 2 |
| no_concrete_next_step | 1 |

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
| 29.7s | 14.2s | 15.3s | 0.3s | criminal_general | daughter in law took my jewellery worth 12 lakh saying for safe keeping not returning agra |
| 27.5s | 4.1s | 23.2s | 0.2s | land_revenue_records | sarpanch giving common village land to his brother no panchayat meeting was held |
| 18.8s | 5.8s | 13.0s | 0.3s | banking_credit_dispute | cooperative bank seized my buffalo for crop loan default can they take livestock |
| 18.5s | 6.0s | 12.3s | 0.3s | workplace_injury_compensation | site mukadam beat me head injury 8 stitches when i asked for old wages mumbai |
| 18.0s | 5.1s | 12.8s | 0.4s | family_marriage_status | how to legally change my surname after marriage, do i need to publish in gazette |
| 17.7s | 5.6s | 12.0s | 0.6s | property_tenancy | my dad signed property to son under pressure when he was in icu can challenge |
| 17.6s | 5.2s | 12.2s | 0.1s | criminal_defence_bail | false dacoity case lodged on my brother by forest guard for collecting tendu leaves dindor |
| 15.4s | 5.0s | 10.3s | 0.3s | police_fir | i was undertrial 5 yrs released last week need help to file police torture case |
| 14.2s | 4.2s | 9.8s | 0.3s | business_contract_partnership | company hiding behind section 43B disallowance threat to delay my msme payment |
| 6.0s | 5.7s | 0.0s | 0.2s | cyber_fraud_or_harassment | data breach at byjus my pan and aadhaar leaked, can i claim compensation under DPDP act |
| 5.9s | 5.5s | 0.0s | 0.2s | consumer | society management has put a fine of 25000 on me for keeping a pet without prior approval, |
| 4.8s | 4.5s | 0.0s | 0.1s | criminal_defence_bail | son 17 yrs in adult jail puzhal pocso case age proof school certificate where to file |
| 4.1s | 3.7s | 0.0s | 0.3s | criminal_defence_bail | the spa was raided last week and police took me and other girls to station I just do massa |

## Expected-Act Misses

| persona | expected | route | query | top source |
| --- | --- | --- | --- | --- |
| stage26_final100 | Income Tax Act, MSMED Act | business_contract_partnership | company hiding behind section 43B disallowance threat to delay my msme payment | Indian Contract Act 1872 |
| stage26_final100 | Cooperative Societies Act, SARFAESI | banking_credit_dispute | cooperative bank seized my buffalo for crop loan default can they take livestock | Banking Regulation Act 1949 |
| stage26_final100 | BNS, BNSS, IPC, NHRC Act | police_fir | i was undertrial 5 yrs released last week need help to file police torture case | Constitution of India |
| stage26_final100 | Cooperative Societies Act | consumer | society management has put a fine of 25000 on me for keeping a pet without prior approval, | Consumer Protection Act 2019 |

## Expected-Act Cited Misses

| persona | expected | route | query | cited answer excerpt |
| --- | --- | --- | --- | --- |
| stage26_final100 | BNS, PWDVA | criminal_general | daughter in law took my jewellery worth 12 lakh saying for safe keeping not returning agra | **Short answer** If your daughter-in-law has taken your jewellery without your consent, it may constitute economic abuse |
| stage26_final100 | Income Tax Act, MSMED Act | business_contract_partnership | company hiding behind section 43B disallowance threat to delay my msme payment | **Short answer** If a company is using Section 43B of the Companies Act 2013 to delay payment to you as an MSME, you may |
| stage26_final100 | Panchayati Raj Act | land_revenue_records | sarpanch giving common village land to his brother no panchayat meeting was held | **Short answer** If a Sarpanch transfers village land to a family member without holding a Panchayat meeting, it may be  |
| stage26_final100 | Cooperative Societies Act, SARFAESI | banking_credit_dispute | cooperative bank seized my buffalo for crop loan default can they take livestock | **Short answer** The Banking Regulation Act 1949 does not explicitly prohibit this practice [7]. **What you can do next* |
| stage26_final100 | BNS, BNSS, IPC, NHRC Act | police_fir | i was undertrial 5 yrs released last week need help to file police torture case | **Short answer** If you believe you were subjected to police torture during your trial, you can file a complaint with th |
| stage26_final100 | BNS, Forest Rights Act | criminal_defence_bail | false dacoity case lodged on my brother by forest guard for collecting tendu leaves dindor | **Short answer** If a false dacoity case is lodged against your brother by a forest guard for collecting tendu leaves, y |
| stage26_final100 | Cooperative Societies Act | consumer | society management has put a fine of 25000 on me for keeping a pet without prior approval, | **Short answer** The indexed pet-specific source is a Mumbai/BMC guideline aligned with AWBI materials, so first confirm |
| stage26_final100 | Indian Contract Act, Transfer of Property Act | property_tenancy | my dad signed property to son under pressure when he was in icu can challenge | **Short answer** If your father signed the property transfer under pressure while in the ICU, this may be considered und |
