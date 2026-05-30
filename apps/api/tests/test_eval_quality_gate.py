from __future__ import annotations

import math

from scripts.eval_quality_gate import GateConfig, evaluate_gate, score_rows


def _row(**overrides):
    row = {
        "query": "consumer refund for defective phone",
        "expected_category": "consumer",
        "expected_act_hint": "Consumer Protection Act",
        "expected_act_hit": True,
        "route_category": "consumer",
        "route_required_sources": ["Consumer Protection Act 2019"],
        "route_forums": ["District Consumer Disputes Redressal Commission"],
        "route_missing_facts": ["purchase date"],
        "action_pack_id": "consumer",
        "action_pack_next_steps": ["Collect invoice and written complaint history."],
        "relevance_verdict": "ok",
        "refused": False,
        "error": None,
        "sentence_count": 2,
        "ok_sentences": 2,
        "weak_sentences": 0,
        "suppressed_count": 0,
        "source_count": 2,
        "answer_text": "You can use consumer complaint route.",
        "timing": {
            "total_ms": 1_000,
            "retrieval_ms": 200,
            "llm_stream_ms": 700,
            "verification_ms": 100,
        },
        "wall_ms": 1_000,
    }
    row.update(overrides)
    return row


def test_gate_passes_when_real_eval_metrics_cross_thresholds():
    rows = [_row() for _ in range(10)]
    metrics = score_rows(rows)
    failures = evaluate_gate(
        metrics,
        GateConfig(
            min_rows=10,
            max_wall_p50_ms=2_000,
            max_wall_p90_ms=2_000,
        ),
    )

    assert failures == []


def test_gate_fails_on_low_act_hit_and_safety_hard_failures():
    rows = [_row() for _ in range(9)]
    rows.append(
        _row(
            expected_act_hit=False,
            route_category="general_legal",
            route_forums=[],
            route_required_sources=[],
            action_pack_id=None,
            action_pack_next_steps=[],
            refused=True,
            relevance_verdict=None,
            sentence_count=0,
            ok_sentences=0,
            source_count=0,
        )
    )

    metrics = score_rows(rows)
    failures = evaluate_gate(
        metrics,
        GateConfig(
            min_rows=10,
            min_expected_act_hit_pct=95.0,
            min_usable_answer_pct=95.0,
            min_action_pack_pct=95.0,
            max_wall_p50_ms=2_000,
            max_wall_p90_ms=2_000,
        ),
    )

    assert any("expected_act_hit_pct" in failure for failure in failures)
    assert any("usable_answer_pct" in failure for failure in failures)
    assert any("action_pack_pct" in failure for failure in failures)
    assert any("legal_safety_hard_fails" in failure for failure in failures)


def test_gate_fails_when_timing_or_route_telemetry_is_missing():
    rows = [
        _row(route_category=None, timing=None),
        _row(route_category=None, timing=None),
        _row(),
        _row(),
    ]

    metrics = score_rows(rows)
    failures = evaluate_gate(
        metrics,
        GateConfig(
            min_rows=4,
            min_route_telemetry_pct=75.0,
            min_timing_telemetry_pct=75.0,
            max_wall_p50_ms=2_000,
            max_wall_p90_ms=2_000,
        ),
    )

    assert any("route_telemetry_pct" in failure for failure in failures)
    assert any("timing_telemetry_pct" in failure for failure in failures)


def test_gate_fails_when_expected_act_scoring_coverage_is_too_low():
    rows = [_row(expected_act_hit=None) for _ in range(9)]
    rows.append(_row(expected_act_hit=True))

    metrics = score_rows(rows)
    failures = evaluate_gate(
        metrics,
        GateConfig(
            min_rows=10,
            min_scored_act_coverage_pct=85.0,
            max_wall_p50_ms=2_000,
            max_wall_p90_ms=2_000,
        ),
    )

    assert any("scored_act_coverage_pct" in failure for failure in failures)


def test_gate_fails_when_wall_latency_is_missing_on_rows():
    rows = [_row(wall_ms=None) for _ in range(9)]
    rows.append(_row(wall_ms=1_000))

    metrics = score_rows(rows)
    failures = evaluate_gate(
        metrics,
        GateConfig(
            min_rows=10,
            max_wall_p50_ms=2_000,
            max_wall_p90_ms=2_000,
        ),
    )

    assert any("wall_latency_coverage_pct" in failure for failure in failures)


def test_gate_does_not_count_ungrounded_ok_answer_as_usable():
    rows = [
        _row(ok_sentences=0, source_count=0),
        _row(),
        _row(),
        _row(),
    ]

    metrics = score_rows(rows)
    failures = evaluate_gate(
        metrics,
        GateConfig(
            min_rows=4,
            min_usable_answer_pct=100.0,
            max_wall_p50_ms=2_000,
            max_wall_p90_ms=2_000,
        ),
    )

    assert any("usable_answer_pct" in failure for failure in failures)


def test_gate_requires_real_timing_fields_and_meaningful_action_pack():
    rows = [
        _row(timing={"x": 1}, action_pack_next_steps=[]),
        _row(),
        _row(),
        _row(),
    ]

    metrics = score_rows(rows)
    failures = evaluate_gate(
        metrics,
        GateConfig(
            min_rows=4,
            min_action_pack_pct=100.0,
            min_timing_telemetry_pct=100.0,
            max_wall_p50_ms=2_000,
            max_wall_p90_ms=2_000,
        ),
    )

    assert any("timing_telemetry_pct" in failure for failure in failures)
    assert any("action_pack_pct" in failure for failure in failures)


def test_gate_rejects_nan_infinite_and_negative_telemetry():
    rows = [
        _row(
            wall_ms=math.nan,
            timing={
                "total_ms": math.nan,
                "retrieval_ms": 1,
                "llm_stream_ms": 1,
                "verification_ms": 1,
            },
        ),
        _row(
            wall_ms=math.inf,
            timing={
                "total_ms": math.inf,
                "retrieval_ms": 1,
                "llm_stream_ms": 1,
                "verification_ms": 1,
            },
        ),
        _row(
            wall_ms=-1,
            timing={
                "total_ms": -1,
                "retrieval_ms": 1,
                "llm_stream_ms": 1,
                "verification_ms": 1,
            },
        ),
        _row(),
    ]

    metrics = score_rows(rows)
    failures = evaluate_gate(
        metrics,
        GateConfig(
            min_rows=4,
            min_timing_telemetry_pct=100.0,
            max_wall_p50_ms=2_000,
            max_wall_p90_ms=2_000,
        ),
    )

    assert any("timing_telemetry_pct" in failure for failure in failures)
    assert any("wall_latency_coverage_pct" in failure for failure in failures)


def test_gate_rejects_blank_action_pack_fields():
    rows = [
        _row(
            action_pack_next_steps=[""],
            route_forums=[" "],
            route_missing_facts=[""],
            route_required_sources=[" "],
        ),
        _row(),
        _row(),
        _row(),
    ]

    metrics = score_rows(rows)
    failures = evaluate_gate(
        metrics,
        GateConfig(
            min_rows=4,
            min_action_pack_pct=100.0,
            max_wall_p50_ms=2_000,
            max_wall_p90_ms=2_000,
        ),
    )

    assert any("action_pack_pct" in failure for failure in failures)


def test_gate_rejects_weak_or_suppressed_answers_as_usable():
    rows = [
        _row(weak_sentences=2),
        _row(suppressed_count=1),
        _row(),
        _row(),
    ]

    metrics = score_rows(rows)
    failures = evaluate_gate(
        metrics,
        GateConfig(
            min_rows=4,
            min_usable_answer_pct=100.0,
            max_wall_p50_ms=2_000,
            max_wall_p90_ms=2_000,
        ),
    )

    assert any("usable_answer_pct" in failure for failure in failures)


def test_gate_rejects_boolean_sentence_and_source_counts():
    rows = [
        _row(ok_sentences=True, source_count=True),
        _row(),
        _row(),
        _row(),
    ]

    metrics = score_rows(rows)
    failures = evaluate_gate(
        metrics,
        GateConfig(
            min_rows=4,
            min_usable_answer_pct=100.0,
            max_wall_p50_ms=2_000,
            max_wall_p90_ms=2_000,
        ),
    )

    assert any("usable_answer_pct" in failure for failure in failures)
