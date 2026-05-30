# Legal RAG Production Gate

Input: `data/processed/timed_eval_stage38_new100_seed2026053001.jsonl`
Gate: **FAIL**

## Metrics

| metric | value | target |
| --- | ---: | ---: |
| rows | 100 | >= 100 |
| scored_act_coverage | 99/100 (99.0%) | >= 85.0% |
| expected_act_hit | 84/99 (84.8%) | >= 85.0% |
| usable_answer | 38/100 (38.0%) | >= 85.0% |
| action_pack | 98/100 (98.0%) | >= 85.0% |
| route_telemetry | 100/100 (100.0%) | >= 95.0% |
| timing_telemetry | 100/100 (100.0%) | >= 95.0% |
| wall_latency_coverage | 100/100 (100.0%) | >= 100.0% |
| errors | 0 | <= 0 |
| legal_safety_hard_fails | 2 | <= 0 |
| unsafe_refusal | 0 (0.0%) | <= 2.0% |
| dangerous_framing | 0 | <= 0 |
| wrong_regime | 0 | <= 0 |
| dangerous_off_topic | 2 | <= 0 |
| wall_p50 | 15.9s | <= 20.0s |
| wall_p90 | 20.9s | <= 30.0s |

## Safety Labels

| label | count |
| --- | ---: |
| dangerous_off_topic | 2 |

## Failures

- expected_act_hit_pct 84.84848484848484 < 85.0
- usable_answer_pct 38.0 < 85.0
- legal_safety_hard_fails 2 > 0
- dangerous_off_topic 2 > 0
