import asyncio

from apps.api.query_expand import expand_query


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
