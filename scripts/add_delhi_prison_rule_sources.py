#!/usr/bin/env python3
"""Backfill narrow official Delhi Prison Rules 2018 source chunks.

These chunks cover Delhi/Tihar prison-user questions around mulaqat/interviews,
books/library access, and parole/furlough. They intentionally add reviewed,
route-owned authority without committing generated corpus data.
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


SOURCE_URL = "https://tiharprisons.delhi.gov.in/sites/default/files/Tiharprisons/generic_multiple_files/delhi_jail_manual-2018_english.pdf"


DELHI_PRISON_RULE_CHUNKS = [
    {
        "slug": "delhi-prison-rules-2018",
        "title": "Delhi Prison Rules 2018",
        "source_url": SOURCE_URL,
        "source_type": "bare_act",
        "origin": "tihar_prisons_delhi",
        "subject_area": "criminal",
        "anchor": "delhi-prison-rules-2018/rule-1",
        "section_no": "1",
        "section_title": "Short title, extent and commencement",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Delhi Prison Rules 2018, Rule 1\n\n"
            "Rule 1 states that these are the Delhi Prisons Rules, 2018 and that, "
            "unless expressly provided otherwise, they apply to prisons in the "
            "National Capital Territory of Delhi. For Tihar, Rohini, Mandoli, or "
            "another Delhi prison question, use the Delhi rules; for other States, "
            "verify the applicable State prison rules or manual before giving a "
            "state-specific entitlement."
        ),
    },
    {
        "slug": "delhi-prison-rules-2018",
        "title": "Delhi Prison Rules 2018",
        "source_url": SOURCE_URL,
        "source_type": "bare_act",
        "origin": "tihar_prisons_delhi",
        "subject_area": "criminal",
        "anchor": "delhi-prison-rules-2018/rule-2-mulaqat",
        "section_no": "2",
        "section_title": "Mulaqat/interview definition",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Delhi Prison Rules 2018, Rule 2, definition of mulaqat/interview\n\n"
            "The rules define mulaqat or interview as a meeting of prisoners with "
            "their relatives, family, and acquaintances. This source is the Delhi "
            "starting point for family-visit or interview questions, separate from "
            "bail, parole, or furlough."
        ),
    },
    {
        "slug": "delhi-prison-rules-2018",
        "title": "Delhi Prison Rules 2018",
        "source_url": SOURCE_URL,
        "source_type": "bare_act",
        "origin": "tihar_prisons_delhi",
        "subject_area": "criminal",
        "anchor": "delhi-prison-rules-2018/rule-595-599",
        "section_no": "595-599",
        "section_title": "Interview permission, application and notice-board information",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Delhi Prison Rules 2018, Rules 595 to 599\n\n"
            "Rule 595 says a prisoner is not allowed to have an interview without "
            "the permission of the Superintendent of Prison. Rule 596 allows "
            "applications for interview orally, in writing, or through electronic "
            "medium, and says the applicant should be informed at once if the "
            "prisoner is not entitled to the interview. Rule 599 requires the "
            "Superintendent to display visitor information outside the prison, "
            "including registration time, interview time, interview duration, "
            "prisoner interview schedule, and the list of prohibited articles."
        ),
    },
    {
        "slug": "delhi-prison-rules-2018",
        "title": "Delhi Prison Rules 2018",
        "source_url": SOURCE_URL,
        "source_type": "bare_act",
        "origin": "tihar_prisons_delhi",
        "subject_area": "criminal",
        "anchor": "delhi-prison-rules-2018/rule-601-606",
        "section_no": "601-606",
        "section_title": "Interview days, hours, place and frequency",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Delhi Prison Rules 2018, Rules 601 to 606\n\n"
            "Rule 601 says the Superintendent fixes the days and hours for "
            "interviews and that interviews outside those hours need special "
            "permission. Rule 602 deals with the appointed interview area and "
            "permits face-to-face interviews for well-behaved prisoners after "
            "security considerations. Rule 606 says a prisoner may be allowed "
            "interview twice a week."
        ),
    },
    {
        "slug": "delhi-prison-rules-2018",
        "title": "Delhi Prison Rules 2018",
        "source_url": SOURCE_URL,
        "source_type": "bare_act",
        "origin": "tihar_prisons_delhi",
        "subject_area": "criminal",
        "anchor": "delhi-prison-rules-2018/rule-613-616",
        "section_no": "613-616",
        "section_title": "Interview duration, search, refusal and recorded reasons",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Delhi Prison Rules 2018, Rules 613 to 616\n\n"
            "Rule 613 says an interview ordinarily should not exceed half an hour, "
            "but the Superintendent may extend it in special or exceptional "
            "circumstances. Rule 614 allows searches before and after interview. "
            "Rule 616 permits refusal of an interview for public interest or other "
            "sufficient reasons, but requires the Superintendent to record reasons "
            "for refusal in the journal."
        ),
    },
    {
        "slug": "delhi-prison-rules-2018",
        "title": "Delhi Prison Rules 2018",
        "source_url": SOURCE_URL,
        "source_type": "bare_act",
        "origin": "tihar_prisons_delhi",
        "subject_area": "criminal",
        "anchor": "delhi-prison-rules-2018/rule-619-1029-books",
        "section_no": "619/1029",
        "section_title": "Articles during interview and prison library/books",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Delhi Prison Rules 2018, Rules 619 and 1029\n\n"
            "Rule 619 says visitors may give clothes and related permitted items "
            "to prisoners as per directions issued by the Inspector General from "
            "time to time, while food from visitors is not allowed. Rule 1029 says "
            "the prison library should have books, magazines and newspapers, that "
            "books are issued to prisoners, that donations of books by NGOs should "
            "be encouraged, and that study material available in the prison library "
            "is screened by the Superintendent so only suitable educational, social, "
            "moral, cultural, or spiritual material reaches prisoners."
        ),
    },
    {
        "slug": "delhi-prison-rules-2018",
        "title": "Delhi Prison Rules 2018",
        "source_url": SOURCE_URL,
        "source_type": "bare_act",
        "origin": "tihar_prisons_delhi",
        "subject_area": "criminal",
        "anchor": "delhi-prison-rules-2018/prisoners-rights-contact-books",
        "section_no": "Prisoners rights",
        "section_title": "Contact with outside world and books",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Delhi Prison Rules 2018, prisoners' rights handbook section\n\n"
            "The rules state that a prisoner has the right to communicate with the "
            "outside world through phone, letters, and interviews, and can "
            "communicate or interview in privacy with legal advisers, diplomats "
            "where applicable, family members, and friends, subject to restrictions "
            "under the rules. The same handbook section says a prisoner has the "
            "right to access the prison library and may possess books with the "
            "Superintendent's permission."
        ),
    },
    {
        "slug": "delhi-prison-rules-2018",
        "title": "Delhi Prison Rules 2018",
        "source_url": SOURCE_URL,
        "source_type": "bare_act",
        "origin": "tihar_prisons_delhi",
        "subject_area": "criminal",
        "anchor": "delhi-prison-rules-2018/rule-1197-1200",
        "section_no": "1197-1200",
        "section_title": "Parole and furlough purpose and definitions",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Delhi Prison Rules 2018, Rules 1197 to 1200\n\n"
            "Rules 1197 to 1200 explain parole and furlough as correctional "
            "measures. Parole is temporary release so a prisoner can maintain "
            "family and community ties and meet familial or social obligations; "
            "time spent outside prison on parole is not treated as sentence served. "
            "Furlough is short release after a qualifying period of incarceration "
            "as an incentive for good conduct and discipline, and time spent "
            "outside prison on furlough counts toward the sentence."
        ),
    },
    {
        "slug": "delhi-prison-rules-2018",
        "title": "Delhi Prison Rules 2018",
        "source_url": SOURCE_URL,
        "source_type": "bare_act",
        "origin": "tihar_prisons_delhi",
        "subject_area": "criminal",
        "anchor": "delhi-prison-rules-2018/rule-1210-1217",
        "section_no": "1210-1217",
        "section_title": "Regular parole eligibility and application processing",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Delhi Prison Rules 2018, Rules 1210 to 1217\n\n"
            "Rule 1210 sets parole eligibility conditions, including conviction "
            "custody period and good conduct requirements. Rule 1211 lists cases "
            "where parole ordinarily is not granted except where special "
            "circumstances exist, including sedition, terrorist activities and "
            "NDPS convictions, public peace concerns, serious prison violence, "
            "and other listed categories. Rule 1213 says a parole application may "
            "be submitted by the prisoner or family members to the Superintendent "
            "of Jail. Rule 1215 requires forwarding of the application, police "
            "report if any, Superintendent's specific recommendation, nominal roll, "
            "medical report where relevant, and other documents. Rule 1217 says "
            "the Government should decide the parole application within four weeks "
            "and communicate the decision through the Superintendent."
        ),
    },
    {
        "slug": "delhi-prison-rules-2018",
        "title": "Delhi Prison Rules 2018",
        "source_url": SOURCE_URL,
        "source_type": "bare_act",
        "origin": "tihar_prisons_delhi",
        "subject_area": "criminal",
        "anchor": "delhi-prison-rules-2018/rule-1220-1226",
        "section_no": "1220-1226",
        "section_title": "Furlough eligibility and application processing",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Delhi Prison Rules 2018, Rules 1220 to 1226\n\n"
            "Rule 1220 says a prisoner sentenced to five years or more of rigorous "
            "imprisonment and who has undergone three years after conviction with "
            "an unblemished record becomes eligible for furlough. Rule 1221 says "
            "the eligible prisoner may be granted seven weeks of furlough in three "
            "spells in a conviction year, with a maximum of three weeks in one "
            "spell. Rule 1223 requires good conduct, no habitual-offender status, "
            "and Indian citizenship. Rule 1224 lists categories not eligible for "
            "furlough, including sedition, terrorist activities, NDPS convictions, "
            "public peace concerns, serious prison violence or absconding, "
            "convicted foreigners, and certain medical restrictions. Rule 1226 "
            "says the convict or family member may submit a furlough application "
            "to the Superintendent of Jail with identity, relationship, pending "
            "application status, address, and reasons."
        ),
    },
    {
        "slug": "delhi-prison-rules-2018",
        "title": "Delhi Prison Rules 2018",
        "source_url": SOURCE_URL,
        "source_type": "bare_act",
        "origin": "tihar_prisons_delhi",
        "subject_area": "criminal",
        "anchor": "delhi-prison-rules-2018/rule-1234-1237",
        "section_no": "1234-1237",
        "section_title": "Fair reasons and release order for parole or furlough",
        "manual_section_backfill": True,
        "text_is_verbatim": False,
        "text": (
            "Delhi Prison Rules 2018, Rules 1234 to 1237\n\n"
            "Rule 1234 says the competent authority decides the period of release "
            "on the merits of each case with reasons specified in the order and "
            "clarifies that non-receipt of a police verification report within "
            "the specified time is not by itself a ground to reject parole or "
            "furlough. Rule 1235 says the authority must assess behavior, "
            "trustworthiness, and adverse repercussions, act fairly, and state "
            "reasons if the application is rejected. Rule 1236 deals with release "
            "after bond and signed conditions, and Rule 1237 requires prison "
            "records for parole/furlough and keeping prisoners informed of "
            "eligibility and rights."
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
        for spec in DELHI_PRISON_RULE_CHUNKS:
            inserted += await _upsert_extra_section_chunk(conn, spec)
        print(f"delhi prison rule sources: inserted/updated {inserted} section chunks")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
