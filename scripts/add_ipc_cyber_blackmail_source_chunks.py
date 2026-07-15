#!/usr/bin/env python3
"""Backfill narrow IPC sections for old-regime cyber blackmail routes."""
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


IPC_SOURCE_URL = (
    "https://www.indiacode.nic.in/bitstream/123456789/4219/1/"
    "THE-INDIAN-PENAL-CODE-1860.pdf"
)


IPC_CYBER_BLACKMAIL_CHUNKS = [
    {
        "slug": "ipc-1860",
        "title": "Indian Penal Code 1860",
        "source_url": IPC_SOURCE_URL,
        "subject_area": "criminal",
        "anchor": "ipc-1860/sec-384",
        "section_no": "384",
        "section_title": "Punishment for extortion",
        "text": (
            "Indian Penal Code 1860, Section 384\n\n"
            "Section 384 is the punishment source for extortion. A person who "
            "commits extortion shall be punished with imprisonment of either "
            "description for a term which may extend to three years, or with "
            "fine, or with both.\n\n"
            "For old-regime online blackmail or demand-for-money facts, verify "
            "the incident date, threat/demand messages, account identifiers, "
            "and money trail before applying IPC extortion framing."
        ),
    },
    {
        "slug": "ipc-1860",
        "title": "Indian Penal Code 1860",
        "source_url": IPC_SOURCE_URL,
        "subject_area": "criminal",
        "anchor": "ipc-1860/sec-499",
        "section_no": "499",
        "section_title": "Defamation",
        "text": (
            "Indian Penal Code 1860, Section 499\n\n"
            "Section 499 defines defamation. Whoever, by words, signs, or "
            "visible representations, makes or publishes an imputation "
            "concerning any person intending to harm, or knowing or having "
            "reason to believe that such imputation will harm, that person's "
            "reputation, subject to the statutory explanations and exceptions, "
            "is said to defame that person.\n\n"
            "For old-regime deepfake or reputation-harm facts, use this only "
            "after checking the exact publication, identity, date, and exception "
            "issues."
        ),
    },
    {
        "slug": "ipc-1860",
        "title": "Indian Penal Code 1860",
        "source_url": IPC_SOURCE_URL,
        "subject_area": "criminal",
        "anchor": "ipc-1860/sec-503",
        "section_no": "503",
        "section_title": "Criminal intimidation",
        "text": (
            "Indian Penal Code 1860, Section 503\n\n"
            "Section 503 defines criminal intimidation. Whoever threatens "
            "another with injury to person, reputation, or property, or to the "
            "person or reputation of anyone in whom that person is interested, "
            "with intent to cause alarm or to make the person do or omit an act "
            "which the person is not legally bound to do or omit, commits "
            "criminal intimidation.\n\n"
            "For old-regime cyber threats, preserve the threat messages, sender "
            "identity, date, platform complaint, and police complaint record."
        ),
    },
    {
        "slug": "ipc-1860",
        "title": "Indian Penal Code 1860",
        "source_url": IPC_SOURCE_URL,
        "subject_area": "criminal",
        "anchor": "ipc-1860/sec-506",
        "section_no": "506",
        "section_title": "Punishment for criminal intimidation",
        "text": (
            "Indian Penal Code 1860, Section 506\n\n"
            "Section 506 is the punishment source for criminal intimidation. "
            "It punishes criminal intimidation, with higher punishment where "
            "the threat is to cause death, grievous hurt, destruction of "
            "property by fire, an offence punishable with death or life "
            "imprisonment, or imputing unchastity to a woman.\n\n"
            "For an online threat or blackmail question, match the exact threat "
            "and incident date before applying this section."
        ),
    },
    {
        "slug": "ipc-1860",
        "title": "Indian Penal Code 1860",
        "source_url": IPC_SOURCE_URL,
        "subject_area": "criminal",
        "anchor": "ipc-1860/sec-509",
        "section_no": "509",
        "section_title": "Word, gesture or act intended to insult the modesty of a woman",
        "text": (
            "Indian Penal Code 1860, Section 509\n\n"
            "Section 509 covers words, sounds, gestures, objects, or intrusions "
            "on privacy intended to insult the modesty of a woman. It applies "
            "where the accused intends that the word or sound be heard, the "
            "gesture or object be seen, or intrudes upon privacy for that "
            "purpose.\n\n"
            "For old-regime intimate-image or deepfake harassment facts, verify "
            "the survivor's identity, publication or threat trail, privacy "
            "intrusion, and incident date before relying on this source."
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
        for spec in IPC_CYBER_BLACKMAIL_CHUNKS:
            count = await _upsert_extra_section_chunk(conn, spec)
            print(f"{spec['slug']}: inserted/updated {count} chunk at {spec['anchor']}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
