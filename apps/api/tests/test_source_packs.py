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


def test_gratuity_and_pf_employment_get_indexed_source_packs():
    assert "gratuity_1972" in _pack_ids("father epf trust delayed gratuity 18 months")
    ids = _pack_ids("employer deducted PF but EPFO passbook empty")
    assert "epf_1952" in ids
    assert "social_security_code_2020" in ids


def test_wage_query_gets_code_on_wages_pack():
    assert "code_on_wages_2019" in _pack_ids(
        "contractor is paying less than minimum wage and no overtime"
    )


def test_rti_route_gets_rti_pack():
    query = "I filed an RTI and it was rejected what is first appeal time limit"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    assert "rti_2005" in [pack.id for pack in packs]
    assert any("/sec-19" in pack.anchor_patterns for pack in packs)


def test_police_fir_gets_bnss_and_bns_current_packs():
    query = "police refused to register FIR for theft of my bike"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    ids = [pack.id for pack in packs]
    assert "bnss_2023" in ids
    assert "bns_2023" in ids
    assert any("/sec-173" in pack.anchor_patterns for pack in packs)
    assert any("/sec-303" in pack.anchor_patterns for pack in packs)


def test_legacy_criminal_query_does_not_force_new_codes():
    assert "bnss_2023" not in _pack_ids("false ipc 420 case from 2020 can i get bail")


def test_source_pack_config_defaults():
    s = Settings(database_url="postgresql://x")
    assert s.required_source_pack_enabled is True
    assert s.required_source_pack_limit_per_pack == 4
    assert s.required_source_pack_min_score == pytest.approx(0.42)
    assert s.required_source_pack_boost == pytest.approx(0.10)
