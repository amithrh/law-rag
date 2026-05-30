# Legal RAG Production Gate

Input: `data/processed/timed_eval_stage15_template_gate.jsonl`
Gate: **FAIL**

## Metrics

| metric | value | target |
| --- | ---: | ---: |
| rows | 8 | >= 8 |
| scored_act_coverage | 7/8 (87.5%) | >= 85.0% |
| expected_act_hit | 7/7 (100.0%) | >= 85.0% |
| usable_answer | 5/8 (62.5%) | >= 85.0% |
| action_pack | 8/8 (100.0%) | >= 85.0% |
| route_telemetry | 8/8 (100.0%) | >= 95.0% |
| timing_telemetry | 8/8 (100.0%) | >= 95.0% |
| wall_latency_coverage | 8/8 (100.0%) | >= 100.0% |
| errors | 0 | <= 0 |
| legal_safety_hard_fails | 0 | <= 0 |
| unsafe_refusal | 0 (0.0%) | <= 2.0% |
| dangerous_framing | 0 | <= 0 |
| wrong_regime | 0 | <= 0 |
| dangerous_off_topic | 0 | <= 0 |
| wall_p50 | 15.6s | <= 20.0s |
| wall_p90 | 23.7s | <= 30.0s |

## Safety Labels

| label | count |
| --- | ---: |

## Failures

- usable_answer_pct 62.5 < 85.0
