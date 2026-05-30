# Legal RAG Production Gate

Input: `data/processed/timed_eval_stage12_source_prompt_gate.jsonl`
Gate: **FAIL**

## Metrics

| metric | value | target |
| --- | ---: | ---: |
| rows | 8 | >= 8 |
| scored_act_coverage | 7/8 (87.5%) | >= 85.0% |
| expected_act_hit | 7/7 (100.0%) | >= 85.0% |
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
| dangerous_off_topic | 0 | <= 0 |
| wall_p50 | 21.3s | <= 20.0s |
| wall_p90 | 25.5s | <= 30.0s |

## Safety Labels

| label | count |
| --- | ---: |
| wrong_forum | 1 |

## Failures

- usable_answer_pct 0.0 < 85.0
- legal_safety_hard_fails 1 > 0
- wall_p50_ms 21278.3 > 20000.0
