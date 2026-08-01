from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from apps.api.legal_issue_plan import authority_ids_for_passage, build_matter_plan
from apps.api.matter_router import route_matter
from apps.api.source_packs import source_packs_for_route
from pydantic import ValidationError

from authority_registry.ingest import build_projection
from authority_registry.loader import (
    build_authority_registry,
    load_authority_migrations,
    load_authority_registry,
    reconcile_applied_migrations,
)
from authority_registry.model import AuthorityRecord

QUERY = "undertrial in jail for more than half maximum sentence under CrPC 436A"


def _record_payload() -> dict:
    record = load_authority_registry().by_key("crpc_1973_section_436a")
    assert record is not None
    return record.model_dump(mode="json")


def test_crpc_436a_registry_preserves_existing_authority_identity():
    record = load_authority_registry().by_key("crpc_1973_section_436a")
    assert record is not None
    assert record.authority_id_expected == "authority_348b7d2511bb3e5a2618"
    assert record.effective_from.isoformat() == "2006-06-23"
    assert record.effective_to.isoformat() == "2024-06-30"
    assert record.savings is not None
    assert record.savings.provision == "Section 531"
    assert record.publisher.kind == "official_government"
    assert record.canonical_url.startswith("https://www.indiacode.nic.in/")
    assert record.source_origin == "indiacode"
    assert record.provenance.raw_sha256 == (
        "2f28d487c18d33f65195d7ab99cb5dc8fd4dcf232c7deb18dee7f8fa289891b9"
    )
    assert record.verbatim_status == "declared"


@pytest.mark.parametrize(
    "missing_path",
    [
        ("jurisdiction",),
        ("effective_from",),
        ("publisher",),
        ("canonical_url",),
        ("provision", "canonical_anchor"),
        ("text_sha256",),
        ("savings",),
    ],
)
def test_registry_rejects_missing_required_legal_metadata(missing_path):
    payload = _record_payload()
    target = payload
    for key in missing_path[:-1]:
        target = target[key]
    target.pop(missing_path[-1])
    with pytest.raises(ValidationError):
        AuthorityRecord.model_validate(payload)


def test_registry_rejects_text_hash_or_identity_drift():
    bad_text = _record_payload()
    bad_text["text"] += " changed"
    with pytest.raises(ValidationError, match="text_sha256"):
        AuthorityRecord.model_validate(bad_text)

    bad_id = _record_payload()
    bad_id["authority_id_expected"] = "authority_00000000000000000000"
    with pytest.raises(ValidationError, match="authority_id_expected"):
        AuthorityRecord.model_validate(bad_id)


def test_registry_migration_hash_and_order_are_deterministic():
    migrations = load_authority_migrations()
    registry = build_authority_registry(migrations)
    assert [item.manifest.migration_id for item in migrations] == [
        "0001_crpc_436a",
        "0002_rbi_grievance_family",
        "0003_it_act_private_image",
        "0004_it_act_66e_verbatim_correction",
        "0005_bns_extortion",
        "0006_custody_authority_family",
        "0007_custody_answer_citation_policy",
        "0008_bank_freeze_authority_family",
        "0009_bnss_106_provenance_refresh",
        "0010_crpc_102_provenance_refresh",
        "0011_pmla_asset_freeze_authority_family",
        "0012_pmla_consolidation_snapshot",
        "0013_pmla_complete_restraint_checks",
        "0014_pmla_section_17_verbatim_correction",
        "0015_pmla_retire_undated_projections",
        "0016_pmla_retire_split_aliases",
        "0017_uapa_43d_bail_authority",
        "0018_uapa_statute_only_workflow",
        "0019_crpc_device_return_authority",
        "0020_bnss_device_return_authority",
        "0021_bnss_section_531_savings",
        "0022_crpc_154_fir_information_authority",
        "0023_bnss_173_175_fir_authorities",
        "0024_crpc_154_vehicle_theft_pack",
        "0025_msmed_sale_of_goods_authorities",
        "0026_legal_services_authorities_lok_adalat",
        "0027_legal_services_authorities_lok_adalat_temporal_correction",
        "0028_legal_services_authorities_lok_adalat_projection_repair",
        "0029_legal_services_authorities_lok_adalat_official_projection_retirement",
    ]
    assert all(len(item.manifest_sha256) == 64 for item in migrations)
    # Section 531 is already canonicalized by 0006; 0021 only activates it
    # in the seized-device workflow.
    assert len(registry.records) == 52
    assert {workflow.scenario_id for workflow in registry.workflows} == {
        "arrest_custody_station_case_not_disclosed",
        "bank_account_freeze_legal_hold",
        "wrong_bank_debit",
        "loan_app_harassment",
        "pmla_ed_asset_freeze",
        "police_seized_device_return",
        "uapa_prima_facie_bail",
        "vehicle_theft_fir_refusal",
    }


def test_applied_migrations_must_be_exact_hash_matched_prefix():
    migrations = load_authority_migrations()
    assert reconcile_applied_migrations(migrations, []) == migrations
    applied = [(migrations[0].manifest.migration_id, migrations[0].manifest_sha256)]
    assert reconcile_applied_migrations(migrations, applied) == migrations[1:]
    with pytest.raises(ValueError, match="exact hash-matched prefix"):
        reconcile_applied_migrations(
            migrations,
            [(migrations[0].manifest.migration_id, "0" * 64)],
        )


def test_pmla_authorities_pin_the_official_pdf_consolidation_snapshot():
    registry = load_authority_registry()
    for section in (5, 17, 8, 26):
        record = registry.by_key(
            f"prevention_of_money_laundering_act_2002_section_{section}"
        )
        assert record is not None
        assert record.consolidation_as_at == date(2024, 8, 30)


def test_msmed_and_sale_of_goods_records_are_explicit_and_hash_pinned():
    registry = load_authority_registry()
    expected = {
        "msmed_2006_section_15": ("15", "authority_14b3ca26914b4862dc29"),
        "msmed_2006_section_16": ("16", "authority_84e3db3e8d92860b7ac6"),
        "msmed_2006_section_18": ("18", "authority_f96da9f5d7d66e9c94d2"),
        "sale_of_goods_1930_section_31": ("31", "authority_ca972b62188fc00d2d93"),
        "sale_of_goods_1930_section_32": ("32", "authority_ad5352abbebc38174948"),
        "sale_of_goods_1930_section_55": ("55", "authority_e82f7a1ce9d8cd81476e"),
        "sale_of_goods_1930_section_56": ("56", "authority_712ff6f224db04da10af"),
    }
    for key, (section, authority_id) in expected.items():
        record = registry.by_key(key)
        assert record is not None
        assert record.authority_id_expected == authority_id
        assert record.provision.number == section
        assert record.provenance.raw_sha256
        assert record.provenance.raw_bytes_size in {242312, 377988}
        assert record.canonical_url.startswith("https://www.indiacode.nic.in/")


def test_lok_adalat_authorities_pin_the_current_consolidated_text_date():
    registry = load_authority_registry()
    expected = {
        "legal_services_authorities_act_1987_section_19": "authority_4311cfc807f876973217",
        "legal_services_authorities_act_1987_section_20": "authority_73374f30d45eec49c931",
        "legal_services_authorities_act_1987_section_21": "authority_71a26d0ccbf7b61f6d84",
    }
    for key, authority_id in expected.items():
        record = registry.by_key(key)
        assert record is not None
        assert record.authority_id_expected == authority_id
        assert record.effective_from == date(1994, 10, 29)
        assert record.consolidation_as_at == date(1994, 10, 29)
        assert record.provenance.raw_sha256 == (
            "3aae5d5c9f8c2ad100c0553c351af559e35fb36c3fc68a921fd1e64dd4a9318f"
        )
        assert record.provenance.tier == "canonical"


def test_lok_adalat_matter_plan_binds_all_operating_sections_canonically():
    query = "how do I approach Lok Adalat for pending traffic challan settlement"
    plan = build_matter_plan(query, route_matter(query))
    entries = {
        entry.registry_key: entry
        for entry in plan.authority_ledger
        if entry.registry_key and entry.registry_key.startswith(
            "legal_services_authorities_act_1987_section_"
        )
    }
    assert set(entries) == {
        "legal_services_authorities_act_1987_section_19",
        "legal_services_authorities_act_1987_section_20",
        "legal_services_authorities_act_1987_section_21",
    }
    assert all(entry.identity_status == "canonical" for entry in entries.values())
    assert {entry.section for entry in entries.values()} == {
        "Section 19",
        "Section 20",
        "Section 21",
    }
    source = next(
        source
        for source in plan.retrieval_sources
        if source.source_pack_id == "legal_services_authorities_1987_lok_adalat"
    )
    assert set(source.authority_ids) == {
        entry.authority_id for entry in entries.values()
    }


@pytest.mark.parametrize(
    "query,scenario_id",
    [
        ("Bank deducted money wrongly and customer care is not helping", "wrong_bank_debit"),
        ("Loan app is harassing my contacts", "loan_app_harassment"),
        ("my bank account is frozen, what do i do", "bank_account_freeze_legal_hold"),
    ],
)
def test_rbi_workflows_make_plan_authorities_and_actions_canonical(query, scenario_id):
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    rbi_entries = [
        entry
        for entry in plan.authority_ledger
        if entry.registry_key and entry.registry_key.startswith("rbi_integrated_ombudsman")
    ]
    assert len(rbi_entries) == 5
    assert all(entry.authority_id for entry in rbi_entries)
    assert all(entry.identity_status == "canonical" for entry in rbi_entries)
    assert all(
        entry.section in {"Clause 1", "Clause 3", "Clause 6", "Clause 9", "Clause 10"}
        for entry in rbi_entries
    )
    assert "RBI Complaint Management System / Ombudsman" in plan.forums
    assert plan.remedies
    assert len(plan.deadlines) == 2
    assert plan.documents
    assert plan.escalation
    workflow = load_authority_registry().workflow_for_scenario(scenario_id)
    assert workflow is not None
    expected_authority_ids = {
        load_authority_registry().by_key(requirement.registry_key).authority_id_expected
        for requirement in workflow.authorities
        if requirement.required
    }
    assert {
        authority_id
        for source in plan.retrieval_sources
        for authority_id in source.authority_ids
    } == expected_authority_ids
    assert all(source.authority_ids for source in plan.retrieval_sources)
    assert "consumer_protection_2019" not in {
        source.source_pack_id for source in plan.retrieval_sources
    }


def test_rbi_registry_uses_current_official_consolidation_and_correct_clauses():
    registry = load_authority_registry()
    records = [
        record
        for record in registry.records
        if record.canonical_key.startswith("rbi_integrated_ombudsman_2021_clause_")
    ]
    assert [
        record.provision.number
        for record in sorted(records, key=lambda item: int(item.provision.number))
    ] == [
        "1",
        "3",
        "6",
        "9",
        "10",
    ]
    assert all(record.authority_type == "scheme" for record in records)
    assert all(record.source_origin == "rbi" for record in records)
    assert all(record.publisher.kind == "official_regulator" for record in records)
    assert all(
        record.provenance.raw_sha256
        == "26c4931c9de9000757c1643741da59ca6e12330605fb2b13f29e3bc16ad46c12"
        for record in records
    )
    assert all(record.provenance.raw_bytes_size == 178811 for record in records)
    assert registry.by_key("rbi_integrated_ombudsman_2021_clause_2") is None


def test_vehicle_theft_plan_binds_crpc_154_to_the_exact_source_pack():
    query = "My bike is stolen and police are not filing FIR"
    plan = build_matter_plan(query, route_matter(query))
    record = load_authority_registry().by_key(
        "code_of_criminal_procedure_1973_section_154"
    )

    assert record is not None
    crpc_entries = [
        entry
        for entry in plan.authority_ledger
        if entry.registry_key == record.canonical_key
    ]
    assert len(crpc_entries) == 1
    assert crpc_entries[0].section == "Section 154"
    assert crpc_entries[0].identity_status == "canonical"
    source = next(
        source
        for source in plan.retrieval_sources
        if source.source_pack_id == "crpc_1973_vehicle_theft_fir"
    )
    assert source.authority_ids == [record.authority_id_expected]


def test_vehicle_theft_plan_binds_current_bnss_fir_authorities_canonically():
    query = "My bike is stolen and police are not filing FIR; incident was on 1 August 2024"
    plan = build_matter_plan(query, route_matter(query))
    registry = load_authority_registry()
    expected = {
        "bharatiya_nagarik_suraksha_sanhita_2023_section_173",
        "bharatiya_nagarik_suraksha_sanhita_2023_paragraph_173_4",
        "bharatiya_nagarik_suraksha_sanhita_2023_section_175",
    }
    entries = {
        entry.registry_key: entry
        for entry in plan.authority_ledger
        if entry.registry_key in expected
    }

    assert set(entries) == expected
    assert all(entry.identity_status == "canonical" for entry in entries.values())
    assert {entry.section for entry in entries.values()} == {
        "Section 173", "Section 173(4)", "Section 175",
    }
    source = next(
        source
        for source in plan.retrieval_sources
        if source.source_pack_id == "bnss_2023_vehicle_theft_fir"
    )
    assert set(source.authority_ids) == {
        registry.by_key(key).authority_id_expected for key in expected
    }


def test_rbi_loan_app_registry_owns_current_conduct_and_data_provisions():
    registry = load_authority_registry()
    digital_11 = registry.by_key("rbi_digital_lending_2025_paragraph_11")
    digital_12 = registry.by_key("rbi_digital_lending_2025_paragraph_12")
    recovery_2 = registry.by_key("rbi_recovery_agents_2022_paragraph_2")

    assert digital_11 is not None and digital_11.effective_from == date(2025, 5, 8)
    assert digital_12 is not None and "contact list" in digital_12.text
    assert recovery_2 is not None and "family members" in recovery_2.text
    assert digital_12.provenance.raw_sha256 == (
        "2dd838cf9bcb58f27bec0c0f5485cf1c764ad238454dea8c9041516375d2321b"
    )
    assert recovery_2.provenance.raw_sha256 == (
        "cc5242ff92976d44db58d77485a795f48031f20da39473d5b44cfdd4abeac84c"
    )

    workflow = registry.workflow_for_scenario("loan_app_harassment")
    assert workflow is not None
    assert {item.registry_key for item in workflow.authorities} >= {
        "rbi_digital_lending_2025_paragraph_11",
        "rbi_digital_lending_2025_paragraph_12",
        "rbi_recovery_agents_2022_paragraph_2",
        "information_technology_act_2000_section_66e",
    }


def test_private_image_authority_is_canonical_and_conditionally_activated():
    registry = load_authority_registry()
    section_66e = registry.by_key("information_technology_act_2000_section_66e")
    assert section_66e is not None
    assert section_66e.authority_id_expected == "authority_ad90922325a79b902a63"
    assert section_66e.provenance.raw_sha256 == (
        "e71725fa32e892f887308816046c42275fc855b5cbb4ee1063cdbd518f165140"
    )
    assert section_66e.provenance.raw_bytes_size == 832355

    generic_query = "Loan app is harassing my contacts and calling my boss"
    generic_plan = build_matter_plan(generic_query, route_matter(generic_query))
    assert all(
        entry.registry_key != "information_technology_act_2000_section_66e"
        for entry in generic_plan.authority_ledger
    )
    assert "it_act_2000_loan_app_private_image" not in {
        source.source_pack_id for source in generic_plan.retrieval_sources
    }

    image_query = (
        "Unregistered loan app is blackmailing me with a morphed nude photo "
        "if I do not pay tonight"
    )
    image_plan = build_matter_plan(image_query, route_matter(image_query))
    image_entry = next(
        entry
        for entry in image_plan.authority_ledger
        if entry.registry_key == "information_technology_act_2000_section_66e"
    )
    assert image_entry.authority_id == section_66e.authority_id_expected
    assert image_entry.must_cite is True
    assert image_entry.conditional is True
    image_source = next(
        source
        for source in image_plan.retrieval_sources
        if source.source_pack_id == "it_act_2000_loan_app_private_image"
    )
    assert image_source.authority_ids == [section_66e.authority_id_expected]
    assert image_source.anchor_patterns == ["/sec-66E"]

    extortion = registry.by_key("bharatiya_nyaya_sanhita_2023_section_308")
    assert extortion is not None
    assert extortion.authority_id_expected == "authority_1377e9f3337ec9d06de0"
    extortion_entry = next(
        entry
        for entry in image_plan.authority_ledger
        if entry.registry_key == "bharatiya_nyaya_sanhita_2023_section_308"
    )
    assert extortion_entry.must_cite is True
    assert extortion_entry.conditional is True
    assert any(
        source.source_pack_id == "bns_2023_loan_app_extortion"
        and source.authority_ids == [extortion.authority_id_expected]
        and source.anchor_patterns == ["/sec-308"]
        for source in image_plan.retrieval_sources
    )


def test_optional_consolidation_field_preserves_existing_crpc_record_hash():
    record = load_authority_registry().by_key("crpc_1973_section_436a")
    assert record is not None
    assert record.consolidation_as_at is None
    assert record.record_sha256 == (
        "fd65becc36609e42e4d2aab77344911fbc2d2e196fe3d207a55b049391947e5d"
    )


def test_rbi_projection_carries_consolidation_date_at_document_and_chunk_scope():
    record = load_authority_registry().by_key("rbi_integrated_ombudsman_2021_clause_3")
    assert record is not None
    projection = build_projection(record)
    assert projection.document_metadata["consolidation_as_at"] == "2022-08-05"
    assert projection.chunk_metadata["consolidation_as_at"] == "2022-08-05"


def test_matter_plan_and_source_pack_consume_the_registry_record():
    route = route_matter(QUERY)
    plan = build_matter_plan(QUERY, route)
    entry = next(
        item for item in plan.authority_ledger if item.registry_key == "crpc_1973_section_436a"
    )
    assert entry.authority_id == "authority_348b7d2511bb3e5a2618"
    assert entry.source_pack_id == "crpc_1973"
    assert entry.required_anchor_patterns == ["/sec-436-a", "/sec-436A", "/sec-436a"]

    pack = next(item for item in source_packs_for_route(route, QUERY) if item.id == "crpc_1973")
    assert pack.title_patterns == (
        "Code of Criminal Procedure 1973",
        "Code of Criminal Procedure, 1973",
    )
    assert pack.doc_ids == ("crpc-1973",)
    assert pack.anchor_patterns == ("/sec-436-a", "/sec-436A", "/sec-436a")


def test_neighboring_section_cannot_satisfy_registry_authority():
    route = route_matter(QUERY)
    plan = build_matter_plan(QUERY, route)
    assert authority_ids_for_passage(
        plan,
        title="Code of Criminal Procedure 1973",
        anchor="crpc-1973/sec-436-a",
        source_pack_id="crpc_1973",
        source_type="bare_act",
    ) == ["authority_348b7d2511bb3e5a2618"]
    assert (
        authority_ids_for_passage(
            plan,
            title="Code of Criminal Procedure 1973",
            anchor="crpc-1973/sec-437",
            source_pack_id="crpc_1973",
            source_type="bare_act",
        )
        == []
    )


def test_rbi_clause_passage_maps_only_to_its_exact_registry_authority():
    query = "Bank deducted money wrongly and customer care is not helping"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    clause_9 = next(
        entry
        for entry in plan.authority_ledger
        if entry.registry_key == "rbi_integrated_ombudsman_2021_clause_9"
    )
    assert authority_ids_for_passage(
        plan,
        title="Reserve Bank - Integrated Ombudsman Scheme, 2021",
        anchor="rbi-integrated-ombudsman-2021/sec-9",
        source_pack_id="rbi_integrated_ombudsman_2021",
        source_type="bare_act",
    ) == [clause_9.authority_id]


def test_manifest_is_data_only_and_contains_no_local_path():
    for path in Path("packages/authority_registry/migrations").glob("*.json"):
        payload = json.loads(path.read_text())
        text = json.dumps(payload)
        assert "file:///" not in text
        assert "/Users/" not in text


def test_custody_registry_uses_gazette_for_bnss_section_58():
    registry = load_authority_registry()
    record = registry.by_key(
        "bharatiya_nagarik_suraksha_sanhita_2023_section_58"
    )
    assert record is not None
    assert record.source_origin == "mha_gazette"
    assert record.provenance.raw_sha256 == (
        "5e60e2afe30d0fe7eca4f8126301146b76c86a444e690581f81eb564843517fe"
    )
    assert "twenty-four hours" in record.text
    assert "section 187" in record.text


@pytest.mark.parametrize(
    "query,required_keys,forbidden_prefixes",
    (
        (
            "Police picked my son from home and will not tell me the station",
            {
                "constitution_of_india_article_22",
                "constitution_of_india_article_226",
                "bharatiya_nagarik_suraksha_sanhita_2023_section_531",
            },
            (
                "bharatiya_nagarik_suraksha_sanhita_2023_section_36",
                "code_of_criminal_procedure_1973_section_",
            ),
        ),
        (
            "Police picked my son from home in May 2023 and gave no FIR copy",
            {
                "bharatiya_nagarik_suraksha_sanhita_2023_section_531",
                "code_of_criminal_procedure_1973_section_41b",
                "code_of_criminal_procedure_1973_section_41c",
                "code_of_criminal_procedure_1973_section_50",
                "code_of_criminal_procedure_1973_section_50a",
                "code_of_criminal_procedure_1973_section_56",
                "code_of_criminal_procedure_1973_section_57",
            },
            ("bharatiya_nagarik_suraksha_sanhita_2023_section_36",),
        ),
        (
            "Police picked my son from home in August 2025 and gave no FIR copy",
            {
                "bharatiya_nagarik_suraksha_sanhita_2023_section_36",
                "bharatiya_nagarik_suraksha_sanhita_2023_section_37",
                "bharatiya_nagarik_suraksha_sanhita_2023_section_47",
                "bharatiya_nagarik_suraksha_sanhita_2023_section_48",
                "bharatiya_nagarik_suraksha_sanhita_2023_section_57",
                "bharatiya_nagarik_suraksha_sanhita_2023_section_58",
            },
            ("code_of_criminal_procedure_1973_section_",),
        ),
        (
            "Police picked my son today in Nagaland and hide the station",
            {"bharatiya_nagarik_suraksha_sanhita_2023_section_1"},
            (
                "bharatiya_nagarik_suraksha_sanhita_2023_section_36",
                "code_of_criminal_procedure_1973_section_",
            ),
        ),
    ),
)
def test_custody_registry_selects_one_procedural_regime(
    query: str,
    required_keys: set[str],
    forbidden_prefixes: tuple[str, ...],
):
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    keys = {entry.registry_key for entry in plan.authority_ledger if entry.registry_key}
    assert required_keys <= keys
    assert all(not any(key.startswith(prefix) for prefix in forbidden_prefixes) for key in keys)


def test_custody_registry_separates_retrieval_from_answer_citation_policy():
    query = "Police picked my brother from home in May 2023 and gave no FIR copy"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    entries = {
        entry.registry_key: entry
        for entry in plan.authority_ledger
        if entry.registry_key
    }
    assert entries["code_of_criminal_procedure_1973_section_50"].must_cite is False
    assert entries["code_of_criminal_procedure_1973_section_56"].must_cite is False
    assert entries["code_of_criminal_procedure_1973_section_41c"].must_cite is True
    assert entries["code_of_criminal_procedure_1973_section_50a"].must_cite is True
