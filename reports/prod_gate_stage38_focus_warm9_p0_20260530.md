# Timed 100-question eval

Rows: 10
Input/output: `data/processed/timed_eval_stage38_focus_warm9_p0_20260530.jsonl`

## Outcome

- Refused: 0/10
- Errors: 0/10
- Relevance verdicts: {'ok': 9, 'off_topic': 1}
- Expected Act hit: 10/10 (100.0%)
- Expected Act cited hit: 10/10 (100.0%)
- Expected Act unscored: 0/10
- Expected procedure anchor cited coverage: 0/0 (0.0%)
- Answer quality flags: {'missing_next_step_section': 8, 'suppressed_sentences': 1}
- Legal-safety gate: PASS (0/10 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 5.5s | 6.5s | 6.8s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | n/a | n/a | n/a |
| single_expanded_retrieval_ms | 2.2s | 2.5s | 2.7s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.1s | 0.2s |
| variant_rerank_ms | 3.6s | 3.7s | 3.8s |
| retrieval_ms | 5.2s | 6.3s | 6.6s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 0.0s | 0.0s | 0.0s |
| verification_ms | 0.1s | 0.2s | 0.3s |
| relevance_ms | 0.1s | 0.1s | 0.1s |

## Route Distribution

| route | count |
| --- | ---: |
| criminal_defence_bail | 3 |
| cyber_fraud_or_harassment | 2 |
| social_welfare_identity | 2 |
| court_procedure | 1 |
| employment_wages | 1 |
| senior_citizen | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| criminal_defence_bail | 3 |
| cyber | 2 |
| social_welfare_identity | 2 |
| court_procedure | 1 |
| employment_wages | 1 |
| senior_citizen | 1 |

## Answer Quality Flags

| flag | count |
| --- | ---: |
| missing_next_step_section | 8 |
| suppressed_sentences | 1 |

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
| 6.8s | 6.6s | 0.0s | 0.1s | social_welfare_identity | bihar kanya vivah scheme money not given by government after my daughter wedding, block of |
| 6.4s | 6.2s | 0.0s | 0.1s | criminal_defence_bail | NDPS case 50 gram ganja, first time accused, can I get bail and which court should I appro |
| 6.2s | 6.0s | 0.0s | 0.1s | cyber_fraud_or_harassment | ex boyfriend leaked my private nudes on telegram and whatsapp, police saying delete links  |
| 6.1s | 5.9s | 0.0s | 0.1s | senior_citizen | maintenance tribunal ordered my son to pay but he stopped paying, how do I enforce the sen |
| 5.9s | 5.5s | 0.0s | 0.3s | criminal_defence_bail | son 17 yrs in adult jail puzhal pocso case, age proof school certificate where to file app |
| 5.1s | 5.0s | 0.0s | 0.0s | criminal_defence_bail | 482 CrPC quashing FIR in high court what documents needed, FIR is from 2023 and chargeshee |
| 5.0s | 4.7s | 0.0s | 0.2s | social_welfare_identity | kanya vivah scheme money not given after my daughter wedding, district office keeps saying |
| 5.0s | 4.8s | 0.0s | 0.1s | cyber_fraud_or_harassment | otp fraud 2 lakh lost from bank account, bank says my fault no refund, should I go cyber p |
| 4.6s | 4.5s | 0.0s | 0.0s | court_procedure | judgment debtor not paying money decree can court attach property or do I file fresh prope |
| 4.4s | 4.2s | 0.0s | 0.1s | employment_wages | boss saying i signed paper give up wages but i dont read english kannada bangalore, can he |

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
