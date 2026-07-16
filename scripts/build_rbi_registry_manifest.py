#!/usr/bin/env python3
"""Build the immutable RBI Ombudsman authority/workflow migration."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pymupdf

from authority_registry.model import canonical_authority_id

CANONICAL_URL = (
    "https://systemhealth.rbi.org.in/cms.rbi.org.in/cms/assets/Documents/"
    "Ombudsman_Scheme_English.pdf"
)
CANONICAL_NAME = "Reserve Bank - Integrated Ombudsman Scheme, 2021"
CLAUSES = {
    "1": ("Short Title, Commencement, Extent and Application", "2"),
    "3": ("Definitions", "4"),
    "6": ("Establishment of a Centralised Receipt and Processing Centre", "7"),
    "9": ("Grounds of Complaint", "10"),
    "10": ("Grounds for non-maintainability of a Complaint", "11"),
}
DIGITAL_LENDING_URL = (
    "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/"
    "36NT8C402BE7C2A349E0BFFF3C526668CD7A.PDF"
)
DIGITAL_LENDING_NAME = "Reserve Bank of India (Digital Lending) Directions, 2025"
RECOVERY_CIRCULAR_URL = (
    "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/"
    "NT1085404663A577943BBB344A37057621C17.PDF"
)
RECOVERY_CIRCULAR_NAME = (
    "Outsourcing of Financial Services - Responsibilities of regulated entities "
    "employing Recovery Agents"
)


def _extract_text(pdf_path: Path) -> str:
    document = pymupdf.open(pdf_path)
    try:
        return "\n".join(page.get_text("text") for page in document)
    finally:
        document.close()


def _extract_clause(text: str, number: str, next_number: str) -> str:
    match = re.search(
        rf"(?ms)^{re.escape(number)}\.\s+.*?(?=^{re.escape(next_number)}\.\s+)",
        text,
    )
    if not match:
        raise ValueError(f"could not isolate RBI Scheme clause {number}")
    lines = [line.rstrip() for line in match.group(0).strip().splitlines()]
    return "\n".join(line for line in lines if not re.fullmatch(r"\s*\d+\s*", line))


def _authority(number: str, heading: str, text: str, raw_hash: str, size: int) -> dict:
    return {
        "schema_version": 1,
        "canonical_key": f"rbi_integrated_ombudsman_2021_clause_{number}",
        "authority_id_expected": canonical_authority_id(CANONICAL_NAME, "clause", number),
        "canonical_name": CANONICAL_NAME,
        "aliases": ["Reserve Bank Integrated Ombudsman Scheme 2021"],
        "authority_type": "scheme",
        "jurisdiction": {"country": "IN", "level": "national"},
        "provision": {
            "kind": "clause",
            "number": number,
            "heading": heading,
            "canonical_anchor": f"/sec-{number}",
            "anchor_aliases": [f"/clause-{number}"],
        },
        "effective_from": "2021-11-12",
        "effective_to": None,
        "savings": None,
        "consolidation_as_at": "2022-08-05",
        "publisher": {"name": "Reserve Bank of India", "kind": "official_regulator"},
        "canonical_url": CANONICAL_URL,
        "source_origin": "rbi",
        "provenance": {
            "tier": "canonical",
            "verification_method": "refetch_hash_and_text",
            "raw_sha256": raw_hash,
            "raw_bytes_size": size,
        },
        "doc_id": "rbi-integrated-ombudsman-2021",
        "title": "Reserve Bank Integrated Ombudsman Scheme 2021",
        "statute": "Reserve Bank Integrated Ombudsman Scheme 2021",
        "year": 2021,
        "subject_area": "consumer",
        "source_type": "bare_act",
        "retrieval": {
            "source_pack_id": "rbi_integrated_ombudsman_2021",
            "title_patterns": [
                CANONICAL_NAME,
                "Reserve Bank Integrated Ombudsman Scheme 2021",
            ],
            "doc_ids": ["rbi-integrated-ombudsman-2021"],
            "source_types": ["bare_act"],
            "search_query": f"{CANONICAL_NAME} clause {number} {heading}",
        },
        "verbatim_status": "declared",
        "text": text,
        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
    }


def _extract_numbered_block(text: str, number: str, next_number: str) -> str:
    matches = list(re.finditer(
        rf"(?ms)^\s*{re.escape(number)}\.\s+.*?(?=^\s*{re.escape(next_number)}\.\s+)",
        text,
    ))
    if not matches:
        raise ValueError(f"could not isolate RBI paragraph {number}")
    match = max(matches, key=lambda item: len(item.group(0)))
    lines = [line.rstrip() for line in match.group(0).strip().splitlines()]
    cleaned = [
        line for line in lines
        if line.strip() not in {"Withdrawn", "n", "aw", "ithdr", "W"}
        and not re.fullmatch(r"\s*\d+\s*", line)
    ]
    return "\n".join(cleaned)


def _regulator_authority(
    *,
    canonical_key: str,
    canonical_name: str,
    aliases: list[str],
    authority_type: str,
    provision_number: str,
    heading: str,
    anchor: str,
    effective_from: str,
    canonical_url: str,
    raw_hash: str,
    raw_size: int,
    doc_id: str,
    title: str,
    source_type: str,
    source_pack_id: str,
    text: str,
) -> dict:
    return {
        "schema_version": 1,
        "canonical_key": canonical_key,
        "authority_id_expected": canonical_authority_id(
            canonical_name, "paragraph", provision_number
        ),
        "canonical_name": canonical_name,
        "aliases": aliases,
        "authority_type": authority_type,
        "jurisdiction": {"country": "IN", "level": "national"},
        "provision": {
            "kind": "paragraph",
            "number": provision_number,
            "heading": heading,
            "canonical_anchor": anchor,
            "anchor_aliases": [],
        },
        "effective_from": effective_from,
        "effective_to": None,
        "savings": None,
        "consolidation_as_at": None,
        "publisher": {"name": "Reserve Bank of India", "kind": "official_regulator"},
        "canonical_url": canonical_url,
        "source_origin": "rbi",
        "provenance": {
            "tier": "canonical",
            "verification_method": "refetch_hash_and_text",
            "raw_sha256": raw_hash,
            "raw_bytes_size": raw_size,
        },
        "doc_id": doc_id,
        "title": title,
        "statute": title,
        "year": int(effective_from[:4]),
        "subject_area": "consumer",
        "source_type": source_type,
        "retrieval": {
            "source_pack_id": source_pack_id,
            "title_patterns": [canonical_name, *aliases],
            "doc_ids": [doc_id],
            "source_types": [source_type],
            "search_query": f"{canonical_name} paragraph {provision_number} {heading}",
        },
        "verbatim_status": "declared",
        "text": text,
        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
    }


def _workflow(scenario_id: str, owner_token: str) -> dict:
    authorities = [
        {"registry_key": "rbi_integrated_ombudsman_2021_clause_1", "role": "scope"},
        {"registry_key": "rbi_integrated_ombudsman_2021_clause_3", "role": "scope"},
        {"registry_key": "rbi_integrated_ombudsman_2021_clause_6", "role": "forum"},
        {"registry_key": "rbi_integrated_ombudsman_2021_clause_9", "role": "legal_basis"},
        {"registry_key": "rbi_integrated_ombudsman_2021_clause_10", "role": "maintainability"},
    ]
    if scenario_id == "loan_app_harassment":
        authorities = [
            {"registry_key": "rbi_digital_lending_2025_paragraph_11", "role": "remedy"},
            {"registry_key": "rbi_digital_lending_2025_paragraph_12", "role": "legal_basis"},
            {"registry_key": "rbi_recovery_agents_2022_paragraph_2", "role": "legal_basis"},
            *authorities,
        ]
    return {
        "schema_version": 1,
        "scenario_id": scenario_id,
        "owner_token": owner_token,
        "condition_ids": [f"{scenario_id}_facts", "rbi_regulated_entity_check"],
        "authorities": authorities,
        "forums": ["RBI Complaint Management System / Ombudsman"],
        "remedies": [
            "written grievance to the regulated entity",
            "RBI Ombudsman complaint for an eligible deficiency in service",
        ],
        "deadline_rules": [
            "wait for rejection or 30 days without a reply before the Ombudsman complaint",
            "file within one year of the reply, or one year and 30 days from the written complaint if there is no reply",
        ],
        "documents": [
            "written complaint to the regulated entity",
            "reply or proof that 30 days passed without reply",
            "transaction/account/loan records and complaint reference",
        ],
        "escalation": [
            "RBI CMS only after confirming the provider is a regulated entity and Clause 10 maintainability"
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--digital-lending-pdf", type=Path, required=True)
    parser.add_argument("--recovery-agents-pdf", type=Path, required=True)
    args = parser.parse_args()
    pdf_bytes = args.pdf.read_bytes()
    full_text = _extract_text(args.pdf)
    records = [
        _authority(
            number,
            heading,
            _extract_clause(full_text, number, next_number),
            hashlib.sha256(pdf_bytes).hexdigest(),
            len(pdf_bytes),
        )
        for number, (heading, next_number) in CLAUSES.items()
    ]
    digital_bytes = args.digital_lending_pdf.read_bytes()
    digital_text = _extract_text(args.digital_lending_pdf)
    recovery_bytes = args.recovery_agents_pdf.read_bytes()
    recovery_text = _extract_text(args.recovery_agents_pdf)
    records.extend([
        _regulator_authority(
            canonical_key="rbi_digital_lending_2025_paragraph_11",
            canonical_name=DIGITAL_LENDING_NAME,
            aliases=["RBI Digital Lending Directions 2025"],
            authority_type="rule",
            provision_number="11",
            heading="Grievance redressal",
            anchor="/para-11",
            effective_from="2025-05-08",
            canonical_url=DIGITAL_LENDING_URL,
            raw_hash=hashlib.sha256(digital_bytes).hexdigest(),
            raw_size=len(digital_bytes),
            doc_id="rbi-digital-lending-directions-2025",
            title=DIGITAL_LENDING_NAME,
            source_type="guideline",
            source_pack_id="rbi_digital_lending_directions_2025",
            text=_extract_numbered_block(digital_text, "11", "12"),
        ),
        _regulator_authority(
            canonical_key="rbi_digital_lending_2025_paragraph_12",
            canonical_name=DIGITAL_LENDING_NAME,
            aliases=["RBI Digital Lending Directions 2025"],
            authority_type="rule",
            provision_number="12",
            heading="Collection, usage and sharing of data with third parties",
            anchor="/para-12",
            effective_from="2025-05-08",
            canonical_url=DIGITAL_LENDING_URL,
            raw_hash=hashlib.sha256(digital_bytes).hexdigest(),
            raw_size=len(digital_bytes),
            doc_id="rbi-digital-lending-directions-2025",
            title=DIGITAL_LENDING_NAME,
            source_type="guideline",
            source_pack_id="rbi_digital_lending_directions_2025",
            text=_extract_numbered_block(digital_text, "12", "13"),
        ),
        _regulator_authority(
            canonical_key="rbi_recovery_agents_2022_paragraph_2",
            canonical_name=RECOVERY_CIRCULAR_NAME,
            aliases=["RBI Recovery Agents Circular 2022"],
            authority_type="circular",
            provision_number="2",
            heading="Prohibition on intimidation, harassment and privacy intrusion",
            anchor="/para-2",
            effective_from="2022-08-12",
            canonical_url=RECOVERY_CIRCULAR_URL,
            raw_hash=hashlib.sha256(recovery_bytes).hexdigest(),
            raw_size=len(recovery_bytes),
            doc_id="rbi-recovery-agents-2022",
            title=RECOVERY_CIRCULAR_NAME,
            source_type="circular",
            source_pack_id="rbi_recovery_agents_2022",
            text=_extract_numbered_block(recovery_text, "2", "3"),
        ),
    ])
    payload = {
        "migration_id": "0002_rbi_grievance_family",
        "schema_version": 1,
        "operations": [
            {"op": "upsert", "record": record, "expected_previous_record_sha256": None}
            for record in records
        ],
        "workflow_operations": [
            {
                "op": "upsert",
                "record": _workflow("wrong_bank_debit", "authority_graph:wrong_bank_debit"),
                "expected_previous_record_sha256": None,
            },
            {
                "op": "upsert",
                "record": _workflow(
                    "loan_app_harassment", "common_workflow_contracts:loan_app_harassment"
                ),
                "expected_previous_record_sha256": None,
            },
        ],
    }
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")


if __name__ == "__main__":
    main()
