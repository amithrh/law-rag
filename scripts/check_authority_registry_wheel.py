#!/usr/bin/env python3
"""Assert an installed wheel can load its embedded authority manifests."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    if not args.wheel.exists():
        raise SystemExit(f"wheel not found: {args.wheel}")
    expected = {
        "authority_registry/migrations/0001_crpc_436a.json",
        "authority_registry/migrations/0002_rbi_grievance_family.json",
        "authority_registry/migrations/0003_it_act_private_image.json",
        "authority_registry/migrations/0004_it_act_66e_verbatim_correction.json",
        "authority_registry/migrations/0005_bns_extortion.json",
        "authority_registry/migrations/0006_custody_authority_family.json",
        "authority_registry/migrations/0007_custody_answer_citation_policy.json",
    }
    with zipfile.ZipFile(args.wheel) as archive:
        missing = expected - set(archive.namelist())
        if missing:
            raise SystemExit(f"wheel is missing {sorted(missing)}")
    sys.path.insert(0, str(args.wheel))
    from authority_registry import load_authority_registry  # noqa: PLC0415

    registry = load_authority_registry()
    record = registry.by_key("crpc_1973_section_436a")
    if record is None or record.authority_id_expected != "authority_348b7d2511bb3e5a2618":
        raise SystemExit("wheel registry did not resolve the CrPC 436A authority")
    expected_workflow_sizes = {
        "wrong_bank_debit": 5,
        "loan_app_harassment": 10,
        "arrest_custody_station_case_not_disclosed": 16,
    }
    for scenario_id, authority_count in expected_workflow_sizes.items():
        workflow = registry.workflow_for_scenario(scenario_id)
        if workflow is None or len(workflow.authorities) != authority_count:
            raise SystemExit(f"wheel registry did not resolve workflow {scenario_id}")
    custody = registry.workflow_for_scenario(
        "arrest_custody_station_case_not_disclosed"
    )
    custody_policy = {
        item.registry_key: item.answer_must_cite for item in custody.authorities
    }
    if custody_policy["code_of_criminal_procedure_1973_section_50"] is not False:
        raise SystemExit("wheel registry lost the custody supporting-only citation policy")
    if custody_policy["code_of_criminal_procedure_1973_section_41c"] is False:
        raise SystemExit("wheel registry weakened the custody-location citation policy")
    print(
        "wheel registry ok: "
        f"{record.canonical_key}, wrong_bank_debit, loan_app_harassment, custody"
    )


if __name__ == "__main__":
    main()
