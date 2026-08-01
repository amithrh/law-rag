from scripts.profile_matter_plan_inventory import profile


def test_inventory_profile_reports_plan_and_binding_counts() -> None:
    result = profile([
        {"query": "My bike is stolen and police is not filing FIR"},
        {"query": ""},
    ])

    assert result["rows"] == 2
    assert result["plans"] == 1
    assert result["categories"]["police_fir"] == 1
    assert isinstance(result["integrity_gap_kinds"], dict)
    assert isinstance(result["binding_failures"], dict)


def test_inventory_does_not_count_inactive_intake_pointer_as_binding_failure() -> None:
    result = profile([
        {"query": "ESI inspector notice says short contribution for casual workers how to contest"},
    ])

    assert result["binding_failures"].get("missing_source_pack", 0) == 0
