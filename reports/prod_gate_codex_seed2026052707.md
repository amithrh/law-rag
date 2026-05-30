# Legal RAG Production Gate

Input: `data/processed/final100_codex_seed2026052707.jsonl`
Gate: **FAIL**

## Metrics

| metric | value | target |
| --- | ---: | ---: |
| rows | 100 | >= 100 |
| scored_act_coverage | 49/100 (49.0%) | >= 85.0% |
| expected_act_hit | 25/49 (51.0%) | >= 85.0% |
| usable_answer | 47/100 (47.0%) | >= 85.0% |
| action_pack | 76/100 (76.0%) | >= 85.0% |
| route_telemetry | 100/100 (100.0%) | >= 95.0% |
| timing_telemetry | 77/100 (77.0%) | >= 95.0% |
| wall_latency_coverage | 100/100 (100.0%) | >= 100.0% |
| errors | 0 | <= 0 |
| legal_safety_hard_fails | 36 | <= 0 |
| unsafe_refusal | 23 (23.0%) | <= 2.0% |
| dangerous_framing | 0 | <= 0 |
| wrong_regime | 0 | <= 0 |
| dangerous_off_topic | 2 | <= 0 |
| wall_p50 | 19.4s | <= 20.0s |
| wall_p90 | 24.3s | <= 30.0s |

## Safety Labels

| label | count |
| --- | ---: |
| unsafe_refusal | 23 |
| wrong_forum | 19 |
| wrong_deadline | 4 |
| dangerous_off_topic | 2 |

## Failures

- scored_act_coverage_pct 49.0 < 85.0
- expected_act_hit_pct 51.02040816326531 < 85.0
- usable_answer_pct 47.0 < 85.0
- action_pack_pct 76.0 < 85.0
- timing_telemetry_pct 77.0 < 95.0
- legal_safety_hard_fails 36 > 0
- dangerous_off_topic 2 > 0
- unsafe_refusal_pct 23.0 > 2.0
