# Legal RAG Production Gate

Input: `data/processed/timed_eval_stage10_abort_regression_after_false_positive_fix.jsonl`
Gate: **FAIL**

## Metrics

| metric | value | target |
| --- | ---: | ---: |
| rows | 8 | >= 8 |
| scored_act_coverage | 8/8 (100.0%) | >= 85.0% |
| expected_act_hit | 4/8 (50.0%) | >= 85.0% |
| usable_answer | 0/8 (0.0%) | >= 85.0% |
| action_pack | 8/8 (100.0%) | >= 85.0% |
| route_telemetry | 8/8 (100.0%) | >= 95.0% |
| timing_telemetry | 8/8 (100.0%) | >= 95.0% |
| wall_latency_coverage | 8/8 (100.0%) | >= 100.0% |
| errors | 0 | <= 0 |
| legal_safety_hard_fails | 1 | <= 0 |
| unsafe_refusal | 0 (0.0%) | <= 2.0% |
| dangerous_framing | 0 | <= 0 |
| wrong_regime | 0 | <= 0 |
| dangerous_off_topic | 1 | <= 0 |
| wall_p50 | 22.4s | <= 20.0s |
| wall_p90 | 27.2s | <= 30.0s |

## Safety Labels

| label | count |
| --- | ---: |
| dangerous_off_topic | 1 |

## Failures

- expected_act_hit_pct 50.0 < 85.0
- usable_answer_pct 0.0 < 85.0
- legal_safety_hard_fails 1 > 0
- dangerous_off_topic 1 > 0
- wall_p50_ms 22440.25 > 20000.0
