from __future__ import annotations

import json
from pathlib import Path

import pytest
from apps.api.legal_issue_plan import authority_ids_for_passage, build_matter_plan
from apps.api.matter_router import route_matter
from apps.api.source_packs import source_packs_for_route
from pydantic import ValidationError

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
    assert [item.manifest.migration_id for item in migrations] == ["0001_crpc_436a"]
    assert len(migrations[0].manifest_sha256) == 64
    assert [record.canonical_key for record in registry.records] == ["crpc_1973_section_436a"]


def test_applied_migrations_must_be_exact_hash_matched_prefix():
    migrations = load_authority_migrations()
    assert reconcile_applied_migrations(migrations, []) == migrations
    applied = [(migrations[0].manifest.migration_id, migrations[0].manifest_sha256)]
    assert reconcile_applied_migrations(migrations, applied) == ()
    with pytest.raises(ValueError, match="exact hash-matched prefix"):
        reconcile_applied_migrations(
            migrations,
            [(migrations[0].manifest.migration_id, "0" * 64)],
        )


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


def test_manifest_is_data_only_and_contains_no_local_path():
    path = Path("packages/authority_registry/migrations/0001_crpc_436a.json")
    payload = json.loads(path.read_text())
    text = json.dumps(payload)
    assert "file:///" not in text
    assert "/Users/" not in text
