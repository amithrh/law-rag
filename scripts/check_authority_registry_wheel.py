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
        "authority_registry/migrations/0008_bank_freeze_authority_family.json",
        "authority_registry/migrations/0009_bnss_106_provenance_refresh.json",
        "authority_registry/migrations/0010_crpc_102_provenance_refresh.json",
        "authority_registry/migrations/0011_pmla_asset_freeze_authority_family.json",
        "authority_registry/migrations/0012_pmla_consolidation_snapshot.json",
        "authority_registry/migrations/0013_pmla_complete_restraint_checks.json",
        "authority_registry/migrations/0014_pmla_section_17_verbatim_correction.json",
        "authority_registry/migrations/0015_pmla_retire_undated_projections.json",
        "authority_registry/migrations/0016_pmla_retire_split_aliases.json",
        "authority_registry/migrations/0017_uapa_43d_bail_authority.json",
        "authority_registry/migrations/0018_uapa_statute_only_workflow.json",
        "authority_registry/migrations/0019_crpc_device_return_authority.json",
        "authority_registry/migrations/0020_bnss_device_return_authority.json",
        "authority_registry/migrations/0021_bnss_section_531_savings.json",
        "authority_registry/migrations/0022_crpc_154_fir_information_authority.json",
        "authority_registry/migrations/0023_bnss_173_175_fir_authorities.json",
        "authority_registry/migrations/0024_crpc_154_vehicle_theft_pack.json",
        "authority_registry/migrations/0025_msmed_sale_of_goods_authorities.json",
        "authority_registry/migrations/0026_legal_services_authorities_lok_adalat.json",
        "authority_registry/migrations/0027_legal_services_authorities_lok_adalat_temporal_correction.json",
        "authority_registry/migrations/0028_legal_services_authorities_lok_adalat_projection_repair.json",
        "authority_registry/migrations/0029_legal_services_authorities_lok_adalat_official_projection_retirement.json",
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
        "pmla_ed_asset_freeze": 4,
        "uapa_prima_facie_bail": 1,
        "police_seized_device_return": 5,
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
    uapa = registry.by_key("unlawful_activities_prevention_act_1967_section_43d")
    if uapa is None or uapa.authority_id_expected != "authority_4a9efaf22e5cf2d3d226":
        raise SystemExit("wheel registry did not resolve the UAPA Section 43D authority")
    device_authorities = {
        "bharatiya_nagarik_suraksha_sanhita_2023_section_531": (
            "authority_a304a271d59fa95369a8", "/sec-531",
            "9cf147f18554612d57da2cba6fce8b5a3b155ff7c095add54a556d20bdf134c1",
        ),
        "code_of_criminal_procedure_1973_section_451": (
            "authority_b56a3ee70bc63e048163", "/sec-451",
            "9847cbaf8a0323dad0f36060394cbd5498e4a6a4915e1125171e39db6368ce6f",
        ),
        "code_of_criminal_procedure_1973_section_457": (
            "authority_316cb0d8a467b1d9a046", "/sec-457",
            "cecdd07e21af9a63e45bea695dbe207683911f2d623c7b9b167f3d30d7cf3ec8",
        ),
        "bharatiya_nagarik_suraksha_sanhita_2023_section_497": (
            "authority_d988aed56b26c0cd5541", "/sec-497",
            "2471438464a4deab9b1f6c21e6c9c8db0c33fc7950a2b8db62234a8255140467",
        ),
        "bharatiya_nagarik_suraksha_sanhita_2023_section_503": (
            "authority_351a65c5e6d8e32eb406", "/sec-503",
            "8fac744427f17d597924242678bebc88e06b657b81f621b116fc2e923f0cd059",
        ),
    }
    for key, expected in device_authorities.items():
        authority = registry.by_key(key)
        actual = (
            authority.authority_id_expected,
            authority.provision.canonical_anchor,
            authority.text_sha256,
        ) if authority is not None else None
        if actual != expected:
            raise SystemExit(f"wheel registry did not resolve device authority {key}")
    print(
        "wheel registry ok: "
        f"{record.canonical_key}, wrong_bank_debit, loan_app_harassment, custody, "
        "pmla, uapa_prima_facie_bail, device_return_exact_authorities=5"
    )


if __name__ == "__main__":
    main()
