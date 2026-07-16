#!/usr/bin/env python3
"""Build the custody workflow-only answer-citation policy migration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from authority_registry.loader import build_authority_registry, load_authority_migrations
from authority_registry.model import AuthorityWorkflowRecord


SUPPORTING_ONLY = {
    "bharatiya_nagarik_suraksha_sanhita_2023_section_47",
    "bharatiya_nagarik_suraksha_sanhita_2023_section_57",
    "code_of_criminal_procedure_1973_section_50",
    "code_of_criminal_procedure_1973_section_56",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    migrations = tuple(
        item
        for item in load_authority_migrations()
        if item.manifest.migration_id <= "0006_custody_authority_family"
    )
    registry = build_authority_registry(migrations)
    previous = registry.workflow_for_scenario(
        "arrest_custody_station_case_not_disclosed"
    )
    if previous is None:
        raise SystemExit("custody workflow is missing from migration 0006")

    workflow_payload = previous.model_dump(mode="json", exclude_none=True)
    for requirement in workflow_payload["authorities"]:
        if requirement["registry_key"] in SUPPORTING_ONLY:
            requirement["answer_must_cite"] = False
    workflow = AuthorityWorkflowRecord.model_validate(workflow_payload)
    payload = {
        "migration_id": "0007_custody_answer_citation_policy",
        "schema_version": 1,
        "operations": [],
        "workflow_operations": [{
            "op": "upsert",
            "record": workflow.model_dump(mode="json", exclude_none=True),
            "expected_previous_record_sha256": previous.record_sha256,
        }],
    }
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")


if __name__ == "__main__":
    main()
