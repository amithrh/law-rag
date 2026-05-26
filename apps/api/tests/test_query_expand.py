import asyncio

from apps.api.query_expand import expand_query


def test_llm_fallback_disabled_for_general_queries():
    out = asyncio.run(
        expand_query(
            "buyer deducting payment saying quality issue but no formal rejection",
            max_variants=1,
        )
    )

    assert out == ["buyer deducting payment saying quality issue but no formal rejection"]


def test_low_confidence_route_expansion_uses_deterministic_variant():
    out = asyncio.run(
        expand_query(
            "how to file private complaint before magistrate when police inaction",
            max_variants=1,
        )
    )

    assert len(out) == 2
    assert "BNSS 2023" in out[1]


def test_default_bail_expansion_targets_default_bail_not_anticipatory():
    out = asyncio.run(
        expand_query(
            "brother in jail 60 days completed no chargesheet can he get default bail",
            max_variants=1,
        )
    )

    assert len(out) == 2
    variant = out[1].lower()
    assert "default bail" in variant
    assert "section 187" in variant
    assert "section 167" in variant
    assert "anticipatory" not in variant


def test_legacy_default_bail_expansion_prefers_crpc_167():
    out = asyncio.run(
        expand_query(
            "arrested in 2023 and 90 days passed with no chargesheet default bail",
            max_variants=1,
        )
    )

    assert len(out) == 2
    assert "CrPC 1973 section 167" in out[1]
    assert "BNSS 2023 section 187" not in out[1]


def test_anticipatory_bail_expansion_keeps_anticipatory_sections():
    out = asyncio.run(
        expand_query(
            "anticipatory bail in dowry case husband family how many days valid",
            max_variants=1,
        )
    )

    assert len(out) == 2
    variant = out[1].lower()
    assert "anticipatory bail" in variant
    assert "section 482" in variant
    assert "section 438" in variant


def test_section_91_notice_expansion_maps_current_bnss_94():
    out = asyncio.run(
        expand_query(
            "police sent section 91 notice asking for my phone and whatsapp chats",
            max_variants=2,
        )
    )

    joined = "\n".join(out[1:])
    assert "BNSS 2023 section 94" in joined
    assert "CrPC 1973 section 91" in joined


def test_special_law_default_bail_expansion_mentions_ndps_extension_only_when_indexed():
    out = asyncio.run(
        expand_query(
            "brother in NDPS case arrested 110 days no chargesheet default bail possible",
            max_variants=2,
        )
    )

    assert any("NDPS Act 1985 section 36A" in item for item in out[1:])

    uapa_out = asyncio.run(
        expand_query(
            "brother arrested in UAPA 100 days no chargesheet default bail possible",
            max_variants=2,
        )
    )
    assert not any("Unlawful Activities Prevention Act" in item for item in uapa_out[1:])
