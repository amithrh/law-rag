# Legal RAG Production Gate

Input: `data/processed/timed_eval_stage38_focus_warm9_p0_20260530.jsonl`
Gate: **PASS**

## Metrics

| metric | value | target |
| --- | ---: | ---: |
| rows | 10 | >= 10 |
| scored_act_coverage | 10/10 (100.0%) | >= 85.0% |
| expected_act_hit | 10/10 (100.0%) | >= 85.0% |
| usable_answer | 9/10 (90.0%) | >= 85.0% |
| action_pack | 10/10 (100.0%) | >= 85.0% |
| route_telemetry | 10/10 (100.0%) | >= 95.0% |
| timing_telemetry | 10/10 (100.0%) | >= 95.0% |
| wall_latency_coverage | 10/10 (100.0%) | >= 100.0% |
| errors | 0 | <= 0 |
| legal_safety_hard_fails | 0 | <= 0 |
| unsafe_refusal | 0 (0.0%) | <= 2.0% |
| dangerous_framing | 0 | <= 0 |
| wrong_regime | 0 | <= 0 |
| dangerous_off_topic | 0 | <= 0 |
| wall_p50 | 5.5s | <= 20.0s |
| wall_p90 | 6.5s | <= 30.0s |

## Safety Labels

| label | count |
| --- | ---: |
