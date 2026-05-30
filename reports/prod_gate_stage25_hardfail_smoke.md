# Timed 100-question eval

Rows: 13
Input/output: `data/processed/timed_eval_stage25_hardfail_smoke.jsonl`

## Outcome

- Refused: 0/13
- Errors: 0/13
- Relevance verdicts: {'partial': 2, 'ok': 9, 'no_relevance': 2}
- Expected Act hit: 11/13 (84.6%)
- Legal-safety gate: FAIL (1/13 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 17.4s | 24.1s | 32.4s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | n/a | n/a | n/a |
| single_expanded_retrieval_ms | 2.0s | 2.1s | 6.4s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.2s | 0.2s |
| variant_rerank_ms | 3.6s | 3.8s | 9.7s |
| retrieval_ms | 5.5s | 6.0s | 16.2s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 12.4s | 16.1s | 18.5s |
| verification_ms | 0.3s | 0.3s | 0.3s |
| relevance_ms | 0.1s | 0.1s | 0.1s |

## Route Distribution

| route | count |
| --- | ---: |
| cyber_fraud_or_harassment | 3 |
| employment_wages | 2 |
| workplace_injury_compensation | 1 |
| tribal_caste_atrocity | 1 |
| family_domestic | 1 |
| labour_compliance | 1 |
| criminal_defence_bail | 1 |
| business_contract_partnership | 1 |
| social_welfare_identity | 1 |
| senior_citizen | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| cyber | 3 |
| employment_wages | 2 |
| workplace_injury_compensation | 1 |
| tribal_caste_atrocity | 1 |
| family_domestic | 1 |
| labour_compliance | 1 |
| criminal_defence_bail | 1 |
| business_contract_partnership | 1 |
| social_welfare_identity | 1 |
| senior_citizen | 1 |

## Legal Safety Gate

Gate: **FAIL**

| label | count |
| --- | ---: |
| wrong_forum | 0 |
| wrong_deadline | 1 |
| wrong_regime | 0 |
| dangerous_off_topic | 0 |
| unsafe_refusal | 0 |
| dangerous_framing | 0 |

### Legal-Safety Failures

| labels | route | expected | query | reasons |
| --- | --- | --- | --- | --- |
| wrong_deadline | cyber_fraud_or_harassment | cyber_harassment | delhi police chargesheet for tweet calling cm corrupt is this 356 case | deadline-sensitive prompt lacked a deadline-aware route/answer signal |

## Slowest Rows

| total | retrieval | llm | verify | route | query |
| ---: | ---: | ---: | ---: | --- | --- |
| 32.4s | 16.2s | 16.0s | 0.3s | workplace_injury_compensation | my husband lost hand in brick kiln no compensation owner saying he was careless |
| 24.6s | 6.0s | 18.5s | 0.3s | family_domestic | husband forces me at night even when I say no I am tired or unwell is there any law for th |
| 22.2s | 5.9s | 16.2s | 0.3s | senior_citizen | fake call from sbi pension office took 2 lakh from my account 75 yr father |
| 20.3s | 6.1s | 14.3s | 0.3s | criminal_defence_bail | ndps bail rejected 6 times by session court husband 3 yrs in tihar option |
| 19.2s | 5.5s | 13.6s | 0.2s | cyber_fraud_or_harassment | telegram channel leaked my onlyfans content without permission what to do |
| 18.1s | 5.3s | 12.8s | 0.2s | business_contract_partnership | fanvue payment frozen 2400 usd indian creator how to release fund |
| 17.4s | 5.6s | 11.7s | 0.3s | social_welfare_identity | school principal not giving SC scholarship saying papers wrong since 2 years vidarbha |
| 17.2s | 4.7s | 12.4s | 0.3s | cyber_fraud_or_harassment | delhi police chargesheet for tweet calling cm corrupt is this 356 case |
| 17.1s | 4.8s | 12.2s | 0.3s | cyber_fraud_or_harassment | guy from telegram crypto group rugpulled me 3 lakh whom to complain |
| 16.6s | 5.7s | 10.9s | 0.3s | labour_compliance | code on wages applicable to me minimum wage notification gujarat for unskilled worker |
| 16.5s | 5.1s | 11.3s | 0.2s | employment_wages | i complained against my manager for harassment to HR and now they are putting me on PIP, i |
| 15.0s | 4.3s | 10.6s | 0.3s | tribal_caste_atrocity | upper caste people beat my husband called us by caste name FIR not registered |
| 15.0s | 4.2s | 10.7s | 0.3s | employment_wages | construction site delhi 14 hour work no overtime contractor laughing when i ask |

## Expected-Act Misses

| persona | expected | route | query | top source |
| --- | --- | --- | --- | --- |
| stage25_final100 | Industrial Disputes Act, POSH Act | employment_wages | i complained against my manager for harassment to HR and now they are putting me on PIP, i | PRABHU DAYAL versus SADHAN SAHKARI SAMITI MUJURI  VIKAS KHAND PANIYARA & ORS. |
| stage25_final100 | Constitution | social_welfare_identity | school principal not giving SC scholarship saying papers wrong since 2 years vidarbha | Right to Information Act 2005 |
