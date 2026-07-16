#!/usr/bin/env python3
"""Build the immutable arrest/custody authority-family migration.

The India Code BNSS PDF currently extracts section 58 incorrectly. This builder
therefore pins BNSS records to the enacted Gazette PDF and checks every declared
provision against normalized text extracted from the official source bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from authority_registry.model import (
    AuthorityRecord,
    AuthorityWorkflowRecord,
    canonical_authority_id,
)


CONSTITUTION_SHA256 = "4c8e93689ec245e26db08e22b5ff3ad645c98736f0e5b7c8b6638acd7861f85b"
BNSS_GAZETTE_SHA256 = "5e60e2afe30d0fe7eca4f8126301146b76c86a444e690581f81eb564843517fe"
CRPC_SHA256 = "2f28d487c18d33f65195d7ab99cb5dc8fd4dcf232c7deb18dee7f8fa289891b9"

CONSTITUTION_URL = (
    "https://www.legislative.gov.in/static/uploads/2025/07/"
    "c9fe9c9b6840524844316f74bb1c556c.pdf"
)
BNSS_GAZETTE_URL = (
    "https://www.mha.gov.in/sites/default/files/250884_2_english_01042024.pdf"
)
CRPC_URL = (
    "https://www.indiacode.nic.in/bitstream/123456789/13624/1/"
    "the_code_of_criminal_procedure%2C_1973.pdf"
)


@dataclass(frozen=True)
class Provision:
    canonical_key: str
    canonical_name: str
    aliases: tuple[str, ...]
    number: str
    heading: str
    effective_from: str
    effective_to: str | None
    canonical_url: str
    source_origin: str
    publisher_name: str
    raw_sha256: str
    doc_id: str
    title: str
    year: int
    source_pack_id: str
    text: str
    role: str
    required: bool
    condition_ids: tuple[str, ...] = ()


ARTICLE_22 = """22. Protection against arrest and detention in certain cases.--(1) No person who is arrested shall be detained in custody without being informed, as soon as may be, of the grounds for such arrest nor shall he be denied the right to consult, and to be defended by, a legal practitioner of his choice.
(2) Every person who is arrested and detained in custody shall be produced before the nearest magistrate within a period of twenty-four hours of such arrest excluding the time necessary for the journey from the place of arrest to the court of the magistrate and no such person shall be detained in custody beyond the said period without the authority of a magistrate.
(3) Nothing in clauses (1) and (2) shall apply--
(a) to any person who for the time being is an enemy alien; or
(b) to any person who is arrested or detained under any law providing for preventive detention."""

ARTICLE_226 = """226. Power of High Courts to issue certain writs.--(1) Notwithstanding anything in article 32, every High Court shall have power, throughout the territories in relation to which it exercises jurisdiction, to issue to any person or authority, including in appropriate cases, any Government, within those territories directions, orders or writs, including writs in the nature of habeas corpus, mandamus, prohibition, quo warranto and certiorari, or any of them, for the enforcement of any of the rights conferred by Part III and for any other purpose.
(2) The power conferred by clause (1) to issue directions, orders or writs to any Government, authority or person may also be exercised by any High Court exercising jurisdiction in relation to the territories within which the cause of action, wholly or in part, arises for the exercise of such power, notwithstanding that the seat of such Government or authority or the residence of such person is not within those territories."""

BNSS_TEXT = {
    "1": """1. Short title, extent and commencement.--(1) This Act may be called the Bharatiya Nagarik Suraksha Sanhita, 2023.
(2) The provisions of this Sanhita, other than those relating to Chapters IX, XI and XII thereof, shall not apply--
(a) to the State of Nagaland;
(b) to the tribal areas,
but the concerned State Government may, by notification, apply such provisions or any of them to the whole or part of the State of Nagaland or such tribal areas, as the case may be, with such supplemental, incidental or consequential modifications, as may be specified in the notification.""",
    "36": """36. Procedure of arrest and duties of officer making arrest.--Every police officer while making an arrest shall--
(a) bear an accurate, visible and clear identification of his name which will facilitate easy identification;
(b) prepare a memorandum of arrest which shall be--
(i) attested by at least one witness, who is a member of the family of the person arrested or a respectable member of the locality where the arrest is made;
(ii) countersigned by the person arrested; and
(c) inform the person arrested, unless the memorandum is attested by a member of his family, that he has a right to have a relative or a friend or any other person named by him to be informed of his arrest.""",
    "37": """37. Designated police officer.--The State Government shall--
(a) establish a police control room in every district and at State level;
(b) designate a police officer in every district and in every police station, not below the rank of Assistant Sub-Inspector of Police who shall be responsible for maintaining the information about the names and addresses of the persons arrested, nature of the offence with which charged, which shall be prominently displayed in any manner including in digital mode in every police station and at the district headquarters.""",
    "47": """47. Person arrested to be informed of grounds of arrest and of right to bail.--(1) Every police officer or other person arresting any person without warrant shall forthwith communicate to him full particulars of the offence for which he is arrested or other grounds for such arrest.
(2) Where a police officer arrests without warrant any person other than a person accused of a non-bailable offence, he shall inform the person arrested that he is entitled to be released on bail and that he may arrange for sureties on his behalf.""",
    "48": """48. Obligation of person making arrest to inform about the arrest, etc., to a relative or a friend.--(1) Every police officer or other person making any arrest under this Sanhita shall forthwith give the information regarding such arrest and place where the arrested person is being held to any of his relatives, friends or such other persons as may be disclosed or nominated by the arrested person for the purpose of giving such information and also to the designated police officer in the district.
(2) The police officer shall inform the arrested person of his rights under sub-section (1) as soon as he is brought to the police station.
(3) An entry of the fact as to who has been informed of the arrest of such person shall be made in a book to be kept in the police station in such form as may be provided by rules.
(4) It shall be the duty of the Magistrate before whom such arrested person is produced, to satisfy himself that the requirements of sub-section (2) and sub-section (3) have been complied with in respect of such arrested person.""",
    "57": """57. Person arrested to be taken before Magistrate or officer in charge of police station.--A police officer making an arrest without warrant shall, without unnecessary delay and subject to the provisions herein contained as to bail, take or send the person arrested before a Magistrate having jurisdiction in the case, or before the officer in charge of a police station.""",
    "58": """58. Person arrested not to be detained more than twenty-four hours.--No police officer shall detain in custody a person arrested without warrant for a longer period than under all the circumstances of the case is reasonable, and such period shall not, in the absence of a special order of a Magistrate under section 187, exceed twenty-four hours exclusive of the time necessary for the journey from the place of arrest to the Magistrate's Court, whether having jurisdiction or not.""",
    "531": """531. Repeal and savings.--(1) The Code of Criminal Procedure, 1973 is hereby repealed.
(2) Notwithstanding such repeal--
(a) if, immediately before the date on which this Sanhita comes into force, there is any appeal, application, trial, inquiry or investigation pending, then, such appeal, application, trial, inquiry or investigation shall be disposed of, continued, held or made, as the case may be, in accordance with the provisions of the Code of Criminal Procedure, 1973, as in force immediately before such commencement, as if this Sanhita had not come into force.""",
}

CRPC_TEXT = {
    "41B": """41B. Procedure of arrest and duties of officer making arrest.--Every police officer while making an arrest shall--
(a) bear an accurate, visible and clear identification of his name which will facilitate easy identification;
(b) prepare a memorandum of arrest which shall be--
(i) attested by at least one witness, who is a member of the family of the person arrested or a respectable member of the locality where the arrest is made;
(ii) countersigned by the person arrested; and
(c) inform the person arrested, unless the memorandum is attested by a member of his family, that he has a right to have a relative or a friend named by him to be informed of his arrest.""",
    "41C": """41C. Control room at districts.--(1) The State Government shall establish a police control room--
(a) in every district; and
(b) at State level.
(2) The State Government shall cause to be displayed on the notice board kept outside the control rooms at every district, the names and addresses of the persons arrested and the name and designation of the police officers who made the arrests.
(3) The control room at the Police Headquarters at the State level shall collect from time to time, details about the persons arrested, nature of the offence with which they are charged and maintain a database for the information of the general public.""",
    "50": """50. Person arrested to be informed of grounds of arrest and of right to bail.--(1) Every police officer or other person arresting any person without warrant shall forthwith communicate to him full particulars of the offence for which he is arrested or other grounds for such arrest.
(2) Where a police officer arrests without warrant any person other than a person accused of a non-bailable offence, he shall inform the person arrested that he is entitled to be released on bail and that he may arrange for sureties on his behalf.""",
    "50A": """50A. Obligation of person making arrest to inform about the arrest, etc., to a nominated person.--(1) Every police officer or other person making any arrest under this Code shall forthwith give the information regarding such arrest and place where the arrested person is being held to any of his friends, relatives or such other persons as may be disclosed or nominated by the arrested person for the purpose of giving such information.
(2) The police officer shall inform the arrested person of his rights under sub-section (1) as soon as he is brought to the police station.
(3) An entry of the fact as to who has been informed of the arrest of such person shall be made in a book to be kept in the police station in such form as may be prescribed in this behalf by the State Government.
(4) It shall be the duty of the Magistrate before whom such arrested person is produced, to satisfy himself that the requirements of sub-section (2) and sub-section (3) have been complied with in respect of such arrested person.""",
    "56": """56. Person arrested to be taken before Magistrate or officer in charge of police station.--A police officer making an arrest without warrant shall, without unnecessary delay and subject to the provisions herein contained as to bail, take or send the person arrested before a Magistrate having jurisdiction in the case, or before the officer in charge of a police station.""",
    "57": """57. Person arrested not to be detained more than twenty-four hours.--No police officer shall detain in custody a person arrested without warrant for a longer period than under all the circumstances of the case is reasonable, and such period shall not, in the absence of a special order of a Magistrate under section 167, exceed twenty-four hours exclusive of the time necessary for the journey from the place of arrest to the Magistrate's Court.""",
}


def _normalized(value: str) -> str:
    value = value.replace("‘", "'").replace("’", "'").replace("―", "-")
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _pdf_text(path: Path, expected_sha256: str) -> tuple[bytes, str]:
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise SystemExit(f"official PDF hash changed for {path}: {actual}")
    document = pymupdf.open(stream=raw, filetype="pdf")
    try:
        text = "\n".join(page.get_text("text") for page in document)
    finally:
        document.close()
    return raw, text


def _assert_source_contains(source_text: str, declared_text: str, label: str) -> None:
    source_tokens = _normalized(source_text).split()
    body = declared_text.split("--", 1)[-1]
    tokens = _normalized(body).split()
    # PDF columns and footnotes can interrupt long provisions. Check multiple
    # substantial windows so a heading-only or neighboring-section hit fails.
    windows = [tokens[:28], tokens[len(tokens) // 2 : len(tokens) // 2 + 28], tokens[-28:]]
    for window in windows:
        positions = [index for index, token in enumerate(source_tokens) if token == window[0]]
        matched = False
        for position in positions:
            cursor = position
            for token in window[1:]:
                next_positions = (
                    index
                    for index in range(cursor + 1, min(len(source_tokens), cursor + 301))
                    if source_tokens[index] == token
                )
                cursor = next(next_positions, -1)
                if cursor < 0:
                    break
            else:
                matched = True
                break
        if not matched:
            raise SystemExit(
                f"official source does not contain ordered text for {label}: "
                f"{' '.join(window)}"
            )


def _record(item: Provision, raw_size: int) -> AuthorityRecord:
    kind = "article" if item.canonical_name == "Constitution of India" else "section"
    normalized_number = re.sub(r"(?<=\d)([A-Za-z])$", r"-\1", item.number).lower()
    canonical_anchor = f"/sec-{normalized_number}"
    anchor_aliases = []
    if normalized_number != item.number:
        anchor_aliases = [f"/sec-{item.number}", f"/sec-{item.number.lower()}"]
    savings = None
    if item.effective_to is not None:
        savings = {
            "authority": "Bharatiya Nagarik Suraksha Sanhita, 2023",
            "provision": "Section 531",
            "canonical_url": BNSS_GAZETTE_URL,
            "effect": (
                "CrPC continues for an appeal, application, trial, inquiry, or investigation "
                "pending immediately before 1 July 2024."
            ),
        }
    payload = {
        "schema_version": 1,
        "canonical_key": item.canonical_key,
        "authority_id_expected": canonical_authority_id(
            item.canonical_name, kind, item.number
        ),
        "canonical_name": item.canonical_name,
        "aliases": list(item.aliases),
        "authority_type": "statute",
        "jurisdiction": {"country": "IN", "level": "national"},
        "provision": {
            "kind": kind,
            "number": item.number,
            "heading": item.heading,
            "canonical_anchor": canonical_anchor,
            "anchor_aliases": anchor_aliases,
        },
        "effective_from": item.effective_from,
        "effective_to": item.effective_to,
        "savings": savings,
        "consolidation_as_at": "2025-11-11" if kind == "article" else None,
        "publisher": {
            "name": item.publisher_name,
            "kind": "official_government",
        },
        "canonical_url": item.canonical_url,
        "source_origin": item.source_origin,
        "provenance": {
            "tier": "canonical",
            "verification_method": "refetch_hash_and_text",
            "raw_sha256": item.raw_sha256,
            "raw_bytes_size": raw_size,
        },
        "doc_id": item.doc_id,
        "title": item.title,
        "statute": item.title,
        "year": item.year,
        "subject_area": "constitutional" if kind == "article" else "criminal",
        "source_type": "bare_act",
        "retrieval": {
            "source_pack_id": item.source_pack_id,
            "title_patterns": [item.canonical_name, *item.aliases],
            "doc_ids": [item.doc_id],
            "source_types": ["bare_act"],
            "search_query": f"{item.canonical_name} {kind} {item.number} {item.heading}",
        },
        "verbatim_status": "declared",
        "text": item.text,
        "text_sha256": hashlib.sha256(item.text.encode()).hexdigest(),
    }
    return AuthorityRecord.model_validate(payload)


def _provisions() -> list[Provision]:
    items = [
        Provision(
            "constitution_of_india_article_22", "Constitution of India", (), "22",
            "Protection against arrest and detention in certain cases", "1950-01-26", None,
            CONSTITUTION_URL, "legislative_department",
            "Legislative Department, Ministry of Law and Justice", CONSTITUTION_SHA256,
            "constitution-india", "Constitution of India", 1950,
            "constitution_article_22", ARTICLE_22, "legal_basis", True,
        ),
        Provision(
            "constitution_of_india_article_226", "Constitution of India", (), "226",
            "Power of High Courts to issue certain writs", "1979-08-01", None,
            CONSTITUTION_URL, "legislative_department",
            "Legislative Department, Ministry of Law and Justice", CONSTITUTION_SHA256,
            "constitution-india", "Constitution of India", 1950,
            "constitution_article_226_habeas", ARTICLE_226, "remedy", True,
        ),
    ]
    bnss_meta = {
        "1": ("Short title, extent and commencement", "scope", "custody_bnss_geographic_exception"),
        "36": ("Procedure of arrest and duties of officer making arrest", "legal_basis", "custody_current_bnss"),
        "37": ("Designated police officer", "forum", "custody_current_bnss"),
        "47": ("Person arrested to be informed of grounds of arrest and of right to bail", "legal_basis", "custody_current_bnss"),
        "48": ("Obligation of person making arrest to inform about the arrest, etc., to a relative or a friend", "legal_basis", "custody_current_bnss"),
        "57": ("Person arrested to be taken before Magistrate or officer in charge of police station", "legal_basis", "custody_current_bnss"),
        "58": ("Person arrested not to be detained more than twenty-four hours", "legal_basis", "custody_current_bnss"),
        "531": ("Repeal and savings", "scope", "custody_legacy_or_unknown"),
    }
    for number, (heading, role, condition) in bnss_meta.items():
        items.append(Provision(
            f"bharatiya_nagarik_suraksha_sanhita_2023_section_{number}",
            "Bharatiya Nagarik Suraksha Sanhita 2023",
            ("Bharatiya Nagarik Suraksha Sanhita, 2023", "BNSS 2023"),
            number, heading, "2024-07-01", None, BNSS_GAZETTE_URL, "mha_gazette",
            "Legislative Department, Ministry of Law and Justice", BNSS_GAZETTE_SHA256,
            "bnss-2023", "Bharatiya Nagarik Suraksha Sanhita 2023", 2023,
            "bnss_2023_custody_registry", BNSS_TEXT[number], role, False, (condition,),
        ))
    crpc_meta = {
        "41B": ("Procedure of arrest and duties of officer making arrest", "2010-11-01", "legal_basis"),
        "41C": ("Control room at districts", "2010-11-01", "forum"),
        "50": ("Person arrested to be informed of grounds of arrest and of right to bail", "1974-04-01", "legal_basis"),
        "50A": ("Obligation of person making arrest to inform about the arrest, etc., to a nominated person", "2006-06-23", "legal_basis"),
        "56": ("Person arrested to be taken before Magistrate or officer in charge of police station", "1974-04-01", "legal_basis"),
        "57": ("Person arrested not to be detained more than twenty-four hours", "1974-04-01", "legal_basis"),
    }
    for number, (heading, effective_from, role) in crpc_meta.items():
        items.append(Provision(
            f"code_of_criminal_procedure_1973_section_{number.lower()}",
            "Code of Criminal Procedure 1973", ("Code of Criminal Procedure, 1973", "CrPC 1973"),
            number, heading, effective_from, "2024-06-30", CRPC_URL, "indiacode",
            "Legislative Department, Ministry of Law and Justice", CRPC_SHA256,
            "crpc-1973", "Code of Criminal Procedure 1973", 1973,
            "crpc_1973_custody_registry", CRPC_TEXT[number], role, False,
            ("custody_legacy_crpc",),
        ))
    return items


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--constitution-pdf", type=Path, required=True)
    parser.add_argument("--bnss-gazette-pdf", type=Path, required=True)
    parser.add_argument("--crpc-pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    constitution_raw, constitution_text = _pdf_text(
        args.constitution_pdf, CONSTITUTION_SHA256
    )
    bnss_raw, bnss_text = _pdf_text(args.bnss_gazette_pdf, BNSS_GAZETTE_SHA256)
    crpc_raw, crpc_text = _pdf_text(args.crpc_pdf, CRPC_SHA256)
    source_by_hash = {
        CONSTITUTION_SHA256: (constitution_raw, constitution_text),
        BNSS_GAZETTE_SHA256: (bnss_raw, bnss_text),
        CRPC_SHA256: (crpc_raw, crpc_text),
    }

    records = []
    requirements = []
    for item in _provisions():
        raw, source_text = source_by_hash[item.raw_sha256]
        _assert_source_contains(source_text, item.text, item.canonical_key)
        record = _record(item, len(raw))
        records.append(record)
        requirements.append({
            "registry_key": item.canonical_key,
            "role": item.role,
            "required": item.required,
            "condition_ids": list(item.condition_ids),
        })

    workflow = AuthorityWorkflowRecord.model_validate({
        "schema_version": 1,
        "scenario_id": "arrest_custody_station_case_not_disclosed",
        "owner_token": "authority_graph:arrest_custody_station_case_not_disclosed",
        "condition_ids": [
            "custody_current_bnss",
            "custody_legacy_crpc",
            "custody_legacy_or_unknown",
            "custody_bnss_geographic_exception",
        ],
        "authorities": requirements,
        "forums": [
            "District or State police control room / designated police officer",
            "nearest Magistrate",
            "jurisdictional High Court for habeas corpus",
            "District Legal Services Authority",
        ],
        "remedies": [
            "verify custody location and arrest record",
            "enforce grounds, lawyer access, nominated-person intimation, and production safeguards",
            "seek urgent habeas corpus assistance where custody is hidden or production is not shown",
        ],
        "deadline_rules": [
            "Article 22(2) requires production before the nearest Magistrate within twenty-four hours excluding journey time; preventive-detention and enemy-alien exceptions require separate review.",
        ],
        "documents": [
            "pickup time and place",
            "officer, vehicle, CCTV, and witness details",
            "calls and messages",
            "arrest memo, grounds, FIR/case details, and remand or production order if available",
        ],
        "escalation": [
            "contact DLSA or a criminal lawyer immediately",
            "use the High Court habeas corpus route where the person or station remains hidden",
        ],
    })
    payload = {
        "migration_id": "0006_custody_authority_family",
        "schema_version": 1,
        "operations": [
            {
                "op": "upsert",
                "record": record.model_dump(mode="json"),
                "expected_previous_record_sha256": None,
            }
            for record in records
        ],
        "workflow_operations": [{
            "op": "upsert",
            "record": workflow.model_dump(mode="json", exclude_none=True),
            "expected_previous_record_sha256": None,
        }],
    }
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")


if __name__ == "__main__":
    main()
