from __future__ import annotations

import pytest

from apps.api.config import Settings
from apps.api.matter_router import route_matter
from apps.api.source_packs import source_packs_for_route


def _pack_ids(query: str) -> list[str]:
    route = route_matter(query)
    return [pack.id for pack in source_packs_for_route(route, query)]


def test_scst_atrocity_route_gets_exact_bare_act_pack():
    assert "scst_poa_1989" in _pack_ids(
        "mob attacked our pahan during sarna puja calling adivasi non hindu"
    )


def test_domestic_violence_route_gets_pwdva_pack():
    assert "pwdva_2005" in _pack_ids(
        "my husband's mother taunts me daily for not bringing more dowry"
    )


def test_cyber_intimate_threat_gets_it_act_pack():
    assert "it_act_2000" in _pack_ids(
        "bf secretly recorded us during sex now threatening to upload"
    )


def test_missing_corpus_street_vendor_does_not_claim_a_pack():
    route = route_matter("vegetable cart pune municipal seized everything")
    assert route.category == "street_vendor_municipal"
    assert source_packs_for_route(route, "vegetable cart pune municipal seized everything") == []


def test_gratuity_employment_gets_gratuity_pack_but_pf_does_not_fake_epf_act():
    assert "gratuity_1972" in _pack_ids("father epf trust delayed gratuity 18 months")
    assert _pack_ids("employer deducted PF but EPFO passbook empty") == []


def test_source_pack_config_defaults():
    s = Settings(database_url="postgresql://x")
    assert s.required_source_pack_enabled is True
    assert s.required_source_pack_limit_per_pack == 4
    assert s.required_source_pack_min_score == pytest.approx(0.42)
    assert s.required_source_pack_boost == pytest.approx(0.10)
