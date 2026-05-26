from __future__ import annotations

import json
from pathlib import Path

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


def test_street_vendor_gets_bare_act_pack():
    route = route_matter("vegetable cart pune municipal seized everything")
    assert route.category == "street_vendor_municipal"
    assert "street_vendors_2014" in _pack_ids("vegetable cart pune municipal seized everything")


def test_gratuity_and_pf_employment_get_indexed_source_packs():
    assert "gratuity_1972" in _pack_ids("father epf trust delayed gratuity 18 months")
    ids = _pack_ids("employer deducted PF but EPFO passbook empty")
    assert "epf_1952" in ids
    assert "social_security_code_2020" in ids


def test_senior_gift_transfer_gets_section_23_preference():
    query = "my father gifted flat to my brother but now brother stopped giving food can gift be cancelled"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    assert "senior_citizens_2007" in [pack.id for pack in packs]
    assert any("/sec-23" in pack.anchor_patterns for pack in packs)


def test_wage_query_gets_code_on_wages_pack():
    assert "code_on_wages_2019" in _pack_ids(
        "contractor is paying less than minimum wage and no overtime"
    )


def test_nrega_query_gets_mgnrega_pack():
    assert "mgnrega_2005" in _pack_ids(
        "worked 42 days under nrega but job card mate says payment rejected"
    )


def test_construction_injury_gets_bocw_pack():
    assert "bocw_1996" in _pack_ids(
        "construction site fall broke spine no bocw card contractor says no compensation"
    )


def test_generic_site_injury_does_not_get_bocw_pack():
    assert "bocw_1996" not in _pack_ids(
        "warehouse site accident hand broken company refuses compensation"
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


def test_legacy_default_bail_gets_crpc_167_pack():
    query = "arrested in 2023 and 90 days passed with no chargesheet default bail"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    ids = [pack.id for pack in packs]
    assert "crpc_1973" in ids
    assert "bnss_2023" not in ids
    crpc_pack = next(pack for pack in packs if pack.id == "crpc_1973")
    assert "/sec-167" in crpc_pack.anchor_patterns
    assert "/sec-161-j" in crpc_pack.anchor_patterns


def test_unclear_default_bail_gets_both_bnss_and_crpc_packs():
    query = "brother in jail 90 days no chargesheet can he get default bail"
    route = route_matter(query)
    ids = [pack.id for pack in source_packs_for_route(route, query)]
    assert "bnss_2023" in ids
    assert "crpc_1973" in ids


def test_ndps_default_bail_gets_ndps_pack():
    query = "brother in NDPS case arrested 110 days no chargesheet default bail possible"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    ids = [pack.id for pack in packs]
    assert "ndps_1985" in ids
    ndps_pack = next(pack for pack in packs if pack.id == "ndps_1985")
    assert "/sec-35-b" in ndps_pack.anchor_patterns
    assert "/sec-37" in ndps_pack.anchor_patterns


def test_section_91_notice_gets_bnss_94_and_crpc_91_when_date_unclear():
    query = "police sent section 91 notice asking for my phone and whatsapp chats what to do"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}
    assert by_id["bnss_2023"].anchor_patterns == ("/sec-94",)
    assert by_id["crpc_1973"].anchor_patterns == ("/sec-91",)


def test_section_91_notice_with_fir_still_prioritizes_production_sections():
    query = "police sent section 91 notice in FIR 123 asking for phone"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}
    assert by_id["bnss_2023"].anchor_patterns == ("/sec-94",)
    assert by_id["crpc_1973"].anchor_patterns == ("/sec-91",)


def test_default_bail_with_fir_still_prioritizes_remand_sections():
    query = "FIR 2025 arrested 90 days no chargesheet default bail"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}
    assert by_id["bnss_2023"].anchor_patterns == ("/sec-187",)
    assert "crpc_1973" not in by_id


def test_mixed_date_default_bail_gets_dual_procedure_packs():
    query = "arrested in 2025 for FIR from 2023 90 days no chargesheet default bail"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    by_id = {pack.id: pack for pack in packs}
    assert by_id["bnss_2023"].anchor_patterns == ("/sec-187",)
    assert by_id["crpc_1973"].anchor_patterns[:4] == ("/sec-161-j", "/sec-161-k", "/sec-161-l", "/sec-161-m")


def test_legacy_criminal_query_does_not_force_new_codes():
    assert "bnss_2023" not in _pack_ids("false ipc 420 case from 2020 can i get bail")


def test_legal_aid_query_gets_legal_services_pack():
    assert "legal_services_authorities_1987" in _pack_ids(
        "free legal aid for woman domestic violence case how to apply in dlsa"
    )


def test_lok_adalat_award_challenge_gets_section_21_pack():
    query = "lok adalat award passed without my consent can I challenge it"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    assert "legal_services_authorities_1987" in [pack.id for pack in packs]
    assert any("/sec-21" in pack.anchor_patterns for pack in packs)


def test_cheque_bounce_pack_prioritizes_138_and_142():
    query = "cheque bounced yesterday when should i send legal notice and file 138 case"
    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    assert "ni_act_1881" in [pack.id for pack in packs]
    assert any(pack.anchor_patterns == ("/sec-138", "/sec-142") for pack in packs)


def test_passport_route_does_not_claim_missing_passports_act_pack():
    query = "passport police verification adverse report because old criminal case what remedy"
    route = route_matter(query)
    assert route.category == "passport_police_verification"
    assert source_packs_for_route(route, query) == []


def test_forest_and_pesa_queries_get_tribal_source_packs():
    forest_ids = _pack_ids(
        "forest officer stopped us collecting tendu leaves in community forest"
    )
    assert "fra_2006" in forest_ids
    assert "scst_poa_1989" not in forest_ids
    ids = _pack_ids("mining company started blasting without gram sabha consent in scheduled area")
    assert "pesa_1996" in ids


def test_new_source_pack_doc_ids_are_registered_locally():
    registry = Path(__file__).resolve().parents[3] / "data" / "processed" / "acts.jsonl"
    if not registry.exists():
        pytest.skip("local acts.jsonl registry is not present")
    slugs = set()
    with registry.open() as f:
        for line in f:
            line = line.strip()
            if line:
                slugs.add(json.loads(line)["slug"])
    needed = {
        "street-vendors-2014",
        "fra-2006",
        "pesa-1996",
        "mgnrega-2005",
        "bocw-1996",
        "crpc-1973",
    }
    assert not (needed - slugs)


def test_source_pack_config_defaults():
    s = Settings(database_url="postgresql://x")
    assert s.required_source_pack_enabled is True
    assert s.required_source_pack_limit_per_pack == 4
    assert s.required_source_pack_min_score == pytest.approx(0.42)
    assert s.required_source_pack_boost == pytest.approx(0.10)
