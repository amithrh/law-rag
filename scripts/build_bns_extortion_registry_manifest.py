"""Build the immutable BNS section 308 registry migration from an official PDF."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from authority_registry import load_authority_registry
from authority_registry.model import AuthorityRecord, AuthorityWorkflowRecord, canonical_authority_id


EXPECTED_PDF_SHA256 = "ff92dcc72778944011807644b6033b1140ddbe6d7e9f82ac32fd419dae03aa86"
CANONICAL_URL = "https://www.indiacode.nic.in/bitstream/123456789/20062/1/a202345.pdf"
CANONICAL_KEY = "bharatiya_nyaya_sanhita_2023_section_308"
CONDITION_ID = "loan_app_private_image_extortion_current"

SECTION_TEXT = """308. Extortion.--(1) Whoever intentionally puts any person in fear of any injury to that person, or to any other, and thereby dishonestly induces the person so put in fear to deliver to any person any property, or valuable security or anything signed or sealed which may be converted into a valuable security, commits extortion.
Illustrations.
(a) A threatens to publish a defamatory libel concerning Z unless Z gives him money. He thus induces Z to give him money. A has committed extortion.
(e) A threatens Z by sending a message through an electronic device that "Your child is in my possession, and will be put to death unless you send me one lakh rupees." A thus induces Z to give him money. A has committed extortion.
(2) Whoever commits extortion shall be punished with imprisonment of either description for a term which may extend to seven years, or with fine, or with both.
(3) Whoever, in order to the committing of extortion, puts any person in fear, or attempts to put any person in fear, of any injury, shall be punished with imprisonment of either description for a term which may extend to two years, or with fine, or with both."""


def _record(pdf_bytes: bytes) -> AuthorityRecord:
    payload = {
        "schema_version": 1,
        "canonical_key": CANONICAL_KEY,
        "authority_id_expected": canonical_authority_id(
            "Bharatiya Nyaya Sanhita, 2023", "section", "308"
        ),
        "canonical_name": "Bharatiya Nyaya Sanhita, 2023",
        "aliases": ["Bharatiya Nyaya Sanhita 2023", "BNS 2023"],
        "authority_type": "statute",
        "jurisdiction": {"country": "IN", "level": "national"},
        "provision": {
            "kind": "section",
            "number": "308",
            "heading": "Extortion",
            "canonical_anchor": "/sec-308",
            "anchor_aliases": [],
        },
        "effective_from": "2024-07-01",
        "effective_to": None,
        "savings": None,
        "consolidation_as_at": None,
        "publisher": {
            "name": "Legislative Department, Ministry of Law and Justice",
            "kind": "official_government",
        },
        "canonical_url": CANONICAL_URL,
        "source_origin": "indiacode",
        "provenance": {
            "tier": "canonical",
            "verification_method": "refetch_hash_and_text",
            "raw_sha256": EXPECTED_PDF_SHA256,
            "raw_bytes_size": len(pdf_bytes),
        },
        "doc_id": "bns-2023",
        "title": "Bharatiya Nyaya Sanhita 2023",
        "statute": "Bharatiya Nyaya Sanhita 2023",
        "year": 2023,
        "subject_area": "criminal",
        "source_type": "bare_act",
        "retrieval": {
            "source_pack_id": "bns_2023_loan_app_extortion",
            "title_patterns": [
                "Bharatiya Nyaya Sanhita, 2023",
                "Bharatiya Nyaya Sanhita 2023",
                "BNS 2023",
            ],
            "doc_ids": ["bns-2023"],
            "source_types": ["bare_act"],
            "search_query": (
                "Bharatiya Nyaya Sanhita 2023 section 308 extortion fear injury "
                "threat publish reputation demand payment electronic message"
            ),
        },
        "verbatim_status": "declared",
        "text": SECTION_TEXT,
        "text_sha256": hashlib.sha256(SECTION_TEXT.encode()).hexdigest(),
    }
    return AuthorityRecord.model_validate(payload)


def _updated_workflow() -> tuple[AuthorityWorkflowRecord, str]:
    workflow = load_authority_registry().workflow_for_scenario("loan_app_harassment")
    if workflow is None:
        raise RuntimeError("loan_app_harassment workflow is missing")
    payload = workflow.model_dump(mode="json")
    payload["condition_ids"] = [*payload["condition_ids"], CONDITION_ID]
    payload["authorities"] = [
        *payload["authorities"],
        {
            "registry_key": CANONICAL_KEY,
            "role": "legal_basis",
            "required": False,
            "condition_ids": [CONDITION_ID],
        },
    ]
    return AuthorityWorkflowRecord.model_validate(payload), workflow.record_sha256


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    pdf_bytes = args.pdf.read_bytes()
    actual_hash = hashlib.sha256(pdf_bytes).hexdigest()
    if actual_hash != EXPECTED_PDF_SHA256:
        raise SystemExit(f"official PDF hash changed: {actual_hash}")

    record = _record(pdf_bytes)
    workflow, previous_workflow_hash = _updated_workflow()
    payload = {
        "migration_id": "0005_bns_extortion",
        "schema_version": 1,
        "operations": [{
            "op": "upsert",
            "record": record.model_dump(mode="json"),
            "expected_previous_record_sha256": None,
        }],
        "workflow_operations": [{
            "op": "upsert",
            "record": workflow.model_dump(mode="json"),
            "expected_previous_record_sha256": previous_workflow_hash,
        }],
    }
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")


if __name__ == "__main__":
    main()
