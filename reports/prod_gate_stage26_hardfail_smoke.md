# Timed 100-question eval

Rows: 13
Input/output: `data/processed/timed_eval_stage26_hardfail_smoke.jsonl`

## Outcome

- Refused: 0/13
- Errors: 0/13
- Relevance verdicts: {'partial': 3, 'ok': 10}
- Expected Act hit: 12/13 (92.3%)
- Legal-safety gate: FAIL (1/13 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 15.6s | 21.2s | 27.9s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | n/a | n/a | n/a |
| single_expanded_retrieval_ms | 1.7s | 2.0s | 6.5s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.2s | 0.2s |
| variant_rerank_ms | 3.5s | 3.7s | 9.0s |
| retrieval_ms | 5.2s | 5.8s | 15.7s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 10.7s | 15.3s | 23.1s |
| verification_ms | 0.2s | 0.3s | 0.3s |
| relevance_ms | 0.1s | 0.1s | 0.1s |

## Route Distribution

| route | count |
| --- | ---: |
| cyber_fraud_or_harassment | 3 |
| employment_wages | 2 |
| criminal_defence_bail | 1 |
| family_domestic | 1 |
| workplace_injury_compensation | 1 |
| labour_compliance | 1 |
| senior_citizen | 1 |
| business_contract_partnership | 1 |
| social_welfare_identity | 1 |
| tribal_caste_atrocity | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| criminal_defence_bail | 2 |
| employment_wages | 2 |
| cyber | 2 |
| family_domestic | 1 |
| workplace_injury_compensation | 1 |
| labour_compliance | 1 |
| senior_citizen | 1 |
| business_contract_partnership | 1 |
| social_welfare_identity | 1 |
| tribal_caste_atrocity | 1 |

## Legal Safety Gate

Gate: **FAIL**

| label | count |
| --- | ---: |
| wrong_forum | 1 |
| wrong_deadline | 0 |
| wrong_regime | 0 |
| dangerous_off_topic | 0 |
| unsafe_refusal | 0 |
| dangerous_framing | 0 |

### Legal-Safety Failures

| labels | route | expected | query | reasons |
| --- | --- | --- | --- | --- |
| wrong_forum | cyber_fraud_or_harassment | cyber_harassment | delhi police chargesheet for tweet calling cm corrupt is this 356 case | cyber_fraud_or_harassment route did not expose an expected forum |

## Slowest Rows

| total | retrieval | llm | verify | route | query |
| ---: | ---: | ---: | ---: | --- | --- |
| 27.9s | 4.6s | 23.1s | 0.3s | family_domestic | husband forces me at night even when I say no I am tired or unwell is there any law for th |
| 21.8s | 5.8s | 15.8s | 0.3s | senior_citizen | fake call from sbi pension office took 2 lakh from my account 75 yr father |
| 18.7s | 5.4s | 13.2s | 0.2s | cyber_fraud_or_harassment | telegram channel leaked my onlyfans content without permission what to do |
| 17.9s | 5.6s | 12.2s | 0.2s | cyber_fraud_or_harassment | guy from telegram crypto group rugpulled me 3 lakh whom to complain |
| 16.0s | 15.7s | 0.0s | 0.2s | criminal_defence_bail | ndps bail rejected 6 times by session court husband 3 yrs in tihar option |
| 15.7s | 5.2s | 10.4s | 0.3s | tribal_caste_atrocity | upper caste people beat my husband called us by caste name FIR not registered |
| 15.6s | 4.3s | 11.2s | 0.3s | workplace_injury_compensation | my husband lost hand in brick kiln no compensation owner saying he was careless |
| 15.3s | 4.5s | 10.7s | 0.3s | labour_compliance | code on wages applicable to me minimum wage notification gujarat for unskilled worker |
| 15.2s | 3.8s | 11.3s | 0.2s | employment_wages | i complained against my manager for harassment to HR and now they are putting me on PIP, i |
| 15.2s | 5.2s | 9.9s | 0.2s | employment_wages | construction site delhi 14 hour work no overtime contractor laughing when i ask |
| 5.8s | 5.5s | 0.0s | 0.2s | social_welfare_identity | school principal not giving SC scholarship saying papers wrong since 2 years vidarbha |
| 5.7s | 5.4s | 0.0s | 0.3s | cyber_fraud_or_harassment | delhi police chargesheet for tweet calling cm corrupt is this 356 case |
| 5.6s | 5.2s | 0.0s | 0.2s | business_contract_partnership | fanvue payment frozen 2400 usd indian creator how to release fund |

## Expected-Act Misses

| persona | expected | route | query | top source |
| --- | --- | --- | --- | --- |
| stage25_final100 | Industrial Disputes Act, POSH Act | employment_wages | i complained against my manager for harassment to HR and now they are putting me on PIP, i | PRABHU DAYAL versus SADHAN SAHKARI SAMITI MUJURI  VIKAS KHAND PANIYARA & ORS. |
