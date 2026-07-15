#!/usr/bin/env python3
"""Backfill narrow state-law chunks for Stage 37 source-gap repairs.

These chunks target high-risk common-user gaps where the route is already
correct but the local index lacks the controlling state source. They update the
local DB only; generated corpus/vector data is not committed.
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


MAHARASHTRA_PROHIBITION_URL = (
    "https://www.indiacode.nic.in/bitstream/123456789/16375/1/"
    "the_maharashtra_prohibition_act.pdf"
)
ODISHA_TRANSFER_URL = (
    "https://law.odisha.gov.in/sites/default/files/2020-12/"
    "act_1072276522_1440758691.pdf"
)
AP_TRANSFER_URL = (
    "https://landwise-production.s3.us-west-2.amazonaws.com/2022/03/"
    "India_AP_Scheduled-Areas-Land-Transfer-Regulation_1959-1.pdf"
)
JHARKHAND_WITCH_URL = (
    "https://www.casemine.com/search/in/prevention%2Bof%2Bwitch%2Bdaain%2Bpractices%2Bact"
)

SECONDARY_REFERENCE_DOC_IDS = (
    "andhra-pradesh-scheduled-areas-land-transfer-regulation-1959",
    "jharkhand-prevention-witch-daain-practices-2001",
)

NON_VERBATIM_STAGE37_DOC_IDS = (
    "maharashtra-state-excise-act-prohibition-1949",
    "orissa-scheduled-areas-transfer-immovable-property-st-1956",
    "andhra-pradesh-scheduled-areas-land-transfer-regulation-1959",
    "jharkhand-prevention-witch-daain-practices-2001",
)


CHUNKS = [
    {
        "slug": "maharashtra-state-excise-act-prohibition-1949",
        "title": "Maharashtra Prohibition Act 1949",
        "source_url": MAHARASHTRA_PROHIBITION_URL,
        "origin": "indiacode",
        "source_type": "official_summary",
        "subject_area": "criminal",
        "anchor": "maharashtra-state-excise-act-prohibition-1949/sec-2",
        "section_no": "2",
        "section_title": "Definitions relevant to intoxicant, intoxicating drug, hemp, ganja and bhang",
        "text_is_verbatim": False,
        "text": (
            "Maharashtra Prohibition Act 1949, Section 2\n\n"
            "Section 2 contains definitions used by the State prohibition/excise framework. "
            "For Maharashtra bhang facts, verify whether the police paper invokes the "
            "Maharashtra Prohibition Act, the NDPS Act, or another local rule. The definition "
            "lane is relevant to bhang/intoxicant or intoxicating-drug issues, while the exact "
            "offence, permit, possession, seizure and quantity facts must be checked from the "
            "FIR, notice, seizure memo, and lab/FSL record."
        ),
    },
    {
        "slug": "maharashtra-state-excise-act-prohibition-1949",
        "title": "Maharashtra Prohibition Act 1949",
        "source_url": MAHARASHTRA_PROHIBITION_URL,
        "origin": "indiacode",
        "source_type": "official_summary",
        "subject_area": "criminal",
        "anchor": "maharashtra-state-excise-act-prohibition-1949/sec-66",
        "section_no": "66",
        "section_title": "Penalty provision to verify when Maharashtra prohibition/excise is invoked",
        "text_is_verbatim": False,
        "text": (
            "Maharashtra Prohibition Act 1949, Section 66\n\n"
            "Section 66 is a penalty/offence source under the Maharashtra prohibition/excise "
            "framework. In a bhang-lassi or Holi incident, do not assume punishment from NDPS "
            "alone. First verify whether the paper cites the Maharashtra Prohibition Act, any "
            "permit or possession allegation, or NDPS sections, and keep the two tracks separate."
        ),
    },
    {
        "slug": "orissa-scheduled-areas-transfer-immovable-property-st-1956",
        "title": "Orissa Scheduled Areas Transfer of Immovable Property (By Scheduled Tribes) Regulation 1956",
        "source_url": ODISHA_TRANSFER_URL,
        "origin": "law.odisha.gov.in",
        "source_type": "official_summary",
        "subject_area": "tribal_land",
        "anchor": "orissa-scheduled-areas-transfer-immovable-property-st-1956/sec-3",
        "section_no": "3",
        "section_title": "Transfer of immovable property by a member of Scheduled Tribe",
        "text_is_verbatim": False,
        "text": (
            "Orissa Scheduled Areas Transfer of Immovable Property (By Scheduled Tribes) "
            "Regulation 1956, Section 3\n\n"
            "Section 3 is the controlling Odisha Scheduled Area tribal-land transfer source. "
            "It treats transfer of immovable property in a Scheduled Area by a member of a "
            "Scheduled Tribe as void unless the statutory exception, competent-authority "
            "permission, or permitted transferee route applies. For Nuapada, Koraput, "
            "Kalahandi, Sundargarh, Keonjhar, Rayagada, or other Odisha Scheduled Area facts, "
            "verify the khata, mutation order, transfer deed, tribal status, possession, and "
            "competent-authority record before treating the matter as ordinary mutation."
        ),
    },
    {
        "slug": "andhra-pradesh-scheduled-areas-land-transfer-regulation-1959",
        "title": "Andhra Pradesh Scheduled Areas Land Transfer Regulation 1959",
        "source_url": AP_TRANSFER_URL,
        "origin": "landwise",
        "source_type": "secondary_reference",
        "subject_area": "tribal_land",
        "anchor": "andhra-pradesh-scheduled-areas-land-transfer-regulation-1959/sec-3",
        "section_no": "3",
        "section_title": "Transfer of immovable property in Scheduled Areas",
        "text_is_verbatim": False,
        "text": (
            "Andhra Pradesh Scheduled Areas Land Transfer Regulation 1959, Section 3\n\n"
            "Section 3 is the controlling Scheduled Area land-transfer source to verify for "
            "agency-area Andhra Pradesh facts. A transfer of immovable property in a Scheduled "
            "Area to a non-tribal or otherwise contrary to the Regulation may need restoration, "
            "cancellation, or revenue-authority action rather than ordinary mutation advice. "
            "Use this source with the village/agency-area status, tribal status, transfer deed, "
            "mutation order, possession facts, and competent-authority permission record."
        ),
    },
    {
        "slug": "jharkhand-prevention-witch-daain-practices-2001",
        "title": "Jharkhand Prevention of Witch (Daain) Practices Act 2001",
        "source_url": JHARKHAND_WITCH_URL,
        "origin": "state-law-secondary-index",
        "source_type": "secondary_reference",
        "subject_area": "criminal",
        "anchor": "jharkhand-prevention-witch-daain-practices-2001/sec-3",
        "section_no": "3",
        "section_title": "Identification of Witch (Daain)",
        "text_is_verbatim": False,
        "text": (
            "Jharkhand Prevention of Witch (Daain) Practices Act 2001, Section 3\n\n"
            "Section 3 is the state witch-branding source to verify when a person in "
            "Jharkhand is called daain, dayan, witch, or accused of witchcraft. The route "
            "should not rely only on generic BNS/BNSS assault or FIR provisions where the "
            "facts include witch-identification words, village pressure, expulsion, beating, "
            "or public humiliation."
        ),
    },
    {
        "slug": "jharkhand-prevention-witch-daain-practices-2001",
        "title": "Jharkhand Prevention of Witch (Daain) Practices Act 2001",
        "source_url": JHARKHAND_WITCH_URL,
        "origin": "state-law-secondary-index",
        "source_type": "secondary_reference",
        "subject_area": "criminal",
        "anchor": "jharkhand-prevention-witch-daain-practices-2001/sec-4",
        "section_no": "4",
        "section_title": "Offence route to verify for witch-practice accusation",
        "text_is_verbatim": False,
        "text": (
            "Jharkhand Prevention of Witch (Daain) Practices Act 2001, Section 4\n\n"
            "Section 4 should be checked with the exact FIR or complaint words where the "
            "allegation is that someone used witch-practice/daain accusations or related acts. "
            "For victim-side questions, preserve the exact words, place, witnesses, injury proof, "
            "threats, panchayat/village pressure, and police-refusal proof."
        ),
    },
    {
        "slug": "jharkhand-prevention-witch-daain-practices-2001",
        "title": "Jharkhand Prevention of Witch (Daain) Practices Act 2001",
        "source_url": JHARKHAND_WITCH_URL,
        "origin": "state-law-secondary-index",
        "source_type": "secondary_reference",
        "subject_area": "criminal",
        "anchor": "jharkhand-prevention-witch-daain-practices-2001/sec-5",
        "section_no": "5",
        "section_title": "Harassment or harm linked to witch identification",
        "text_is_verbatim": False,
        "text": (
            "Jharkhand Prevention of Witch (Daain) Practices Act 2001, Section 5\n\n"
            "Section 5 should be checked when witch-identification is connected with "
            "harassment, beating, social boycott, expulsion, dispossession, or public "
            "humiliation. Use it with BNS hurt/intimidation and BNSS FIR/Magistrate routes, "
            "but keep the Jharkhand state Act as the controlling witch-branding source."
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
        for spec in CHUNKS:
            inserted += await _upsert_extra_section_chunk(conn, spec)
        await _quarantine_nonverbatim_stage37_chunks(conn)
        print(f"stage37 state-gap sources: inserted/updated {inserted} section chunks")
    finally:
        await conn.close()


async def _quarantine_nonverbatim_stage37_chunks(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        UPDATE chunks c
        SET source_type = CASE
                WHEN d.doc_id = ANY($2::text[]) THEN 'secondary_reference'
                ELSE 'official_summary'
            END,
            quarantined = TRUE
        FROM documents d
        WHERE c.document_id = d.id
          AND d.doc_id = ANY($1::text[])
        """,
        list(NON_VERBATIM_STAGE37_DOC_IDS),
        list(SECONDARY_REFERENCE_DOC_IDS),
    )


if __name__ == "__main__":
    asyncio.run(main())
