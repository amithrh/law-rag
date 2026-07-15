from apps.api.legal_hyde import build_legal_hyde_brief, maybe_append_legal_hyde_brief
from apps.api.matter_router import MatterRoute


def _route(confidence: float, *, category: str = "consumer") -> MatterRoute:
    return MatterRoute(
        category=category,
        label="Consumer complaint / service deficiency",
        confidence=confidence,
        urgency="medium",
        required_sources=["Consumer Protection Act 2019"],
        forums=["District Consumer Disputes Redressal Commission"],
        missing_facts=["purchase date", "invoice/order ID"],
        red_flags=[],
    )


def test_legal_hyde_suppresses_low_confidence_route():
    brief = build_legal_hyde_brief(
        "company not refunding damaged phone",
        route=_route(0.40),
    )

    assert brief is None


def test_legal_hyde_builds_source_aware_retrieval_brief_for_confident_route():
    brief = build_legal_hyde_brief(
        "company not refunding damaged phone",
        route=_route(0.90),
    )

    assert brief is not None
    assert "matter Consumer complaint" in brief
    assert "Consumer Protection Act 2019" in brief
    assert "District Consumer" in brief
    assert "company not refunding damaged phone" in brief


def test_legal_hyde_fallback_skips_court_procedure_routes():
    query = "respondent skipped pre litigation mediation can my commercial suit be rejected"
    out = maybe_append_legal_hyde_brief(
        query,
        [query],
        mode="fallback",
        max_chars=360,
        route=_route(0.90, category="court_procedure"),
    )

    assert out == [query]
