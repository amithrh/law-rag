#!/usr/bin/env python3
"""Backfill narrow official health-law sources for common user prompts.

This script inserts small source-backed bare-Act chunks without committing
corpus PDFs. It supports high-frequency hospital records, billing, and
overcharge questions where the full Clinical Establishments Act is not always
present in the local index.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import asyncpg

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.add_stage34_official_source_chunks import (  # noqa: E402
    _load_env,
    _upsert_extra_section_chunk,
)


CLINICAL_SOURCE_URL = "https://www.indiacode.nic.in/bitstream/123456789/2048/3/a2010-23.pdf"
MEDICAL_ETHICS_SOURCE_URL = "https://www.nmc.org.in/wp-content/uploads/2017/10/Ethics-Regulations-2002.pdf"

CLINICAL_CHUNKS = [
    {
        "slug": "clinical-establishments-2010",
        "title": "Clinical Establishments (Registration and Regulation) Act 2010",
        "source_url": CLINICAL_SOURCE_URL,
        "subject_area": "consumer",
        "anchor": "clinical-establishments-2010/sec-11",
        "section_no": "11",
        "section_title": "Registration for clinical establishments",
        "text": (
            "Clinical Establishments (Registration and Regulation) Act 2010, Section 11\n\n"
            "11. Registration for clinical establishments.--No person shall run a clinical "
            "establishment unless it has been duly registered in accordance with the provisions "
            "of this Act."
        ),
    },
    {
        "slug": "clinical-establishments-2010",
        "title": "Clinical Establishments (Registration and Regulation) Act 2010",
        "source_url": CLINICAL_SOURCE_URL,
        "subject_area": "consumer",
        "anchor": "clinical-establishments-2010/sec-12",
        "section_no": "12",
        "section_title": "Condition for registration",
        "text": (
            "Clinical Establishments (Registration and Regulation) Act 2010, Section 12\n\n"
            "12. Condition for registration.--For registration and continuation, every clinical "
            "establishment shall fulfil prescribed minimum standards of facilities and services, "
            "minimum personnel requirements, provisions for maintenance of records and reporting, "
            "and other prescribed conditions. The clinical establishment must also provide, within "
            "available staff and facilities, medical examination and treatment required to stabilise "
            "an emergency medical condition."
        ),
    },
    {
        "slug": "clinical-establishments-2010",
        "title": "Clinical Establishments (Registration and Regulation) Act 2010",
        "source_url": CLINICAL_SOURCE_URL,
        "subject_area": "consumer",
        "anchor": "clinical-establishments-2010/sec-14",
        "section_no": "14",
        "section_title": "Application for provisional certificate of registration",
        "text": (
            "Clinical Establishments (Registration and Regulation) Act 2010, Section 14\n\n"
            "14. Application for provisional certificate of registration.--For registration of a "
            "clinical establishment, an application in the prescribed form with prescribed fee is "
            "made to the authority. The application may be filed in person, by post, or online and "
            "must be accompanied by prescribed details under the Act or rules."
        ),
    },
    {
        "slug": "clinical-establishments-2010",
        "title": "Clinical Establishments (Registration and Regulation) Act 2010",
        "source_url": CLINICAL_SOURCE_URL,
        "subject_area": "consumer",
        "anchor": "clinical-establishments-2010/sec-33",
        "section_no": "33",
        "section_title": "Inspection of registered clinical establishments",
        "text": (
            "Clinical Establishments (Registration and Regulation) Act 2010, Section 33\n\n"
            "33. Inspection of registered clinical establishments.--The authority or an authorised "
            "officer may cause an inspection of, or inquiry about, any registered clinical "
            "establishment, its building, laboratories, equipment, work conducted, or any other "
            "matter connected with the establishment. The authority may communicate inspection "
            "views, advise action, require an action-taken report, and issue directions where "
            "satisfactory action is not taken."
        ),
    },
    {
        "slug": "clinical-establishments-2010",
        "title": "Clinical Establishments (Registration and Regulation) Act 2010",
        "source_url": CLINICAL_SOURCE_URL,
        "subject_area": "consumer",
        "anchor": "clinical-establishments-2010/sec-42",
        "section_no": "42",
        "section_title": "Disobedience of direction, obstruction and refusal of information",
        "text": (
            "Clinical Establishments (Registration and Regulation) Act 2010, Section 42\n\n"
            "42. Disobedience of direction, obstruction and refusal of information.--A person who "
            "wilfully disobeys a lawful direction, obstructs an empowered person or authority, "
            "wilfully withholds required information, or gives information known to be false is "
            "liable to monetary penalty under the Act after inquiry and opportunity of hearing."
        ),
    },
]

MEDICAL_ETHICS_CHUNKS = [
    {
        "slug": "medical-ethics-regulations-2002",
        "title": "Code of Medical Ethics Regulations 2002",
        "source_url": MEDICAL_ETHICS_SOURCE_URL,
        "subject_area": "consumer",
        "anchor": "medical-ethics-regulations-2002/reg-1.3.1",
        "section_no": "1.3.1",
        "section_title": "Maintenance of medical records",
        "text": (
            "Code of Medical Ethics Regulations 2002, Regulation 1.3.1\n\n"
            "1.3.1. Every physician shall maintain the medical records pertaining to "
            "indoor patients for three years from the date of commencement of treatment "
            "in the standard proforma laid down by the Medical Council of India."
        ),
    },
    {
        "slug": "medical-ethics-regulations-2002",
        "title": "Code of Medical Ethics Regulations 2002",
        "source_url": MEDICAL_ETHICS_SOURCE_URL,
        "subject_area": "consumer",
        "anchor": "medical-ethics-regulations-2002/reg-1.3.2",
        "section_no": "1.3.2",
        "section_title": "Issue medical records on request",
        "text": (
            "Code of Medical Ethics Regulations 2002, Regulation 1.3.2\n\n"
            "1.3.2. If a request is made for medical records by the patient, authorised "
            "attendant, or legal authority involved, the request may be duly acknowledged "
            "and the documents shall be issued within 72 hours."
        ),
    },
    {
        "slug": "medical-ethics-regulations-2002",
        "title": "Code of Medical Ethics Regulations 2002",
        "source_url": MEDICAL_ETHICS_SOURCE_URL,
        "subject_area": "consumer",
        "anchor": "medical-ethics-regulations-2002/reg-7.2",
        "section_no": "7.2",
        "section_title": "Professional misconduct for refusal to provide records",
        "text": (
            "Code of Medical Ethics Regulations 2002, Regulation 7.2\n\n"
            "7.2. A physician commits professional misconduct if he or she does not "
            "maintain indoor-patient medical records for three years as required by "
            "Regulation 1.3 and refuses to provide them within 72 hours when requested "
            "by the patient or authorised representative under Regulation 1.3.2."
        ),
    },
]


async def main() -> None:
    env = _load_env()
    conn = await asyncpg.connect(
        host="localhost",
        port=int(env["POSTGRES_HOST_PORT"]),
        database=env["POSTGRES_DB"],
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )
    try:
        inserted = 0
        for spec in [*CLINICAL_CHUNKS, *MEDICAL_ETHICS_CHUNKS]:
            inserted += await _upsert_extra_section_chunk(conn, spec)
        print(f"health common sources: inserted/updated {inserted} section chunks")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
