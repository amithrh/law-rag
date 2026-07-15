from collections import Counter

from scripts.legal_hyde_regression_gate import GateConfig, evaluate_gate


def _summary(**overrides):
    base = {
        "rows": 3,
        "prompt_signatures": ["p1", "p2", "p3"],
        "errors": 0,
        "refused": 0,
        "verdicts": Counter({"ok": 3}),
        "act_hits": 3,
        "act_scored": 3,
        "act_hit_rate": 1.0,
        "act_cited_hits": 3,
        "act_cited_scored": 3,
        "act_cited_hit_rate": 1.0,
        "safety": {"hard_fails": 0},
        "wall_latency_count": 3,
        "wall_p50": 10_000.0,
        "wall_p90": 15_000.0,
    }
    base.update(overrides)
    return base


def test_legal_hyde_gate_passes_on_tied_quality_and_latency():
    failures = evaluate_gate(
        _summary(),
        _summary(),
        config=GateConfig(),
    )

    assert failures == []


def test_legal_hyde_gate_fails_quality_safety_and_latency_regressions():
    failures = evaluate_gate(
        _summary(),
        _summary(
            refused=1,
            verdicts=Counter({"ok": 2}),
            act_hits=2,
            act_hit_rate=2 / 3,
            act_cited_hits=2,
            act_cited_hit_rate=2 / 3,
            safety={"hard_fails": 1},
            wall_p50=10_001.0,
            wall_p90=15_001.0,
        ),
        config=GateConfig(),
    )

    joined = "\n".join(failures)
    assert "expected Act hit regressed" in joined
    assert "expected Act cited hit regressed" in joined
    assert "relevance ok decreased" in joined
    assert "refusals increased" in joined
    assert "legal-safety hard fails increased" in joined
    assert "wall p50 latency regressed" in joined
    assert "wall p90 latency regressed" in joined


def test_legal_hyde_gate_fails_different_prompt_set():
    failures = evaluate_gate(
        _summary(prompt_signatures=["p1", "p2", "p3"]),
        _summary(prompt_signatures=["p1", "DIFFERENT", "p3"]),
        config=GateConfig(),
    )

    assert any("prompt set/order changed" in failure for failure in failures)


def test_legal_hyde_gate_fails_missing_latency_telemetry():
    failures = evaluate_gate(
        _summary(wall_latency_count=3, wall_p50=10_000.0, wall_p90=15_000.0),
        _summary(wall_latency_count=2, wall_p50=None, wall_p90=15_000.0),
        config=GateConfig(),
    )

    joined = "\n".join(failures)
    assert "experiment wall latency telemetry incomplete: 2/3" in joined
    assert "wall p50 latency telemetry missing" in joined
