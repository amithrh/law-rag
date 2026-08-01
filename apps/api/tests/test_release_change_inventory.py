from scripts.release_change_inventory import _categorize, _parse_porcelain_v1_z


def test_release_change_inventory_groups_release_concerns():
    assert _categorize("apps/api/main.py") == "api_runtime"
    assert _categorize("apps/api/tests/test_endpoints.py") == "api_tests"
    assert _categorize("packages/authority_registry/migrations/0001.json") == (
        "authority_registry"
    )
    assert _categorize("scripts/eval_timed_100.py") == "evaluation_evidence"
    assert _categorize("scripts/repair_canonical_act_chunks.py") == "data_and_retrieval"
    assert _categorize("infra/docker-compose.prod.yml") == "infrastructure_and_ci"
    assert _categorize("docs/PRODUCT_RECOVERY_TODO.md") == "documentation_and_governance"


def test_release_change_inventory_parses_untracked_and_rename_records():
    changes = _parse_porcelain_v1_z(
        b" M apps/api/main.py\0?? docs/new.md\0R  apps/web/new.ts\0apps/web/old.ts\0"
    )

    by_path = {change.path: change for change in changes}
    assert by_path["apps/api/main.py"].status == " M"
    assert by_path["docs/new.md"].status == "??"
    assert by_path["apps/web/new.ts"].original_path == "apps/web/old.ts"
