#!/usr/bin/env python3
"""Add Stage35 official chunks for final100 safety hard-fail routes.

These are small section-level backfills for Acts that either were absent from
the local corpus or were chunked without the exact sections needed by required
source packs.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path

import asyncpg

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from apps.api.config import get_settings  # noqa: E402
from apps.api.embeddings import (  # noqa: E402
    embedding_to_halfvec_literal,
    get_embedder,
    sparse_to_jsonb,
)


CHUNKS = [
    {
        "slug": "tamil-nadu-online-gambling-2022",
        "title": "Tamil Nadu Prohibition of Online Gambling and Regulation of Online Games Act 2022",
        "year": 2023,
        "subject_area": "digital_platform",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/19512/1/online_game_act.pdf",
        "origin": "indiacode",
        "anchor": "tamil-nadu-online-gambling-2022/sec-2",
        "section_no": "2",
        "section_title": "Definitions",
        "text": (
            "Tamil Nadu Prohibition of Online Gambling and Regulation of Online Games Act 2022, Section 2\n\n"
            "Section 2 defines online gambling as online wagering or betting and includes playing any "
            "online game of chance for money or other stakes. It defines online gambling service as a "
            "service for online wagering or betting or for any online game of chance where the customer "
            "gives, agrees to give, or puts up money or another stake. It defines online game of chance "
            "to include a game where chance dominates skill, chance can be eliminated only by superlative "
            "skill, the game is presented as involving chance, or the game uses cards, dice, a wheel, or "
            "a random outcome or event generator."
        ),
    },
    {
        "slug": "tamil-nadu-online-gambling-2022",
        "title": "Tamil Nadu Prohibition of Online Gambling and Regulation of Online Games Act 2022",
        "year": 2023,
        "subject_area": "digital_platform",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/19512/1/online_game_act.pdf",
        "origin": "indiacode",
        "anchor": "tamil-nadu-online-gambling-2022/sec-7",
        "section_no": "7",
        "section_title": "Prohibition of online gambling and online games of chance",
        "text": (
            "Tamil Nadu Prohibition of Online Gambling and Regulation of Online Games Act 2022, Section 7\n\n"
            "Section 7 prohibits online gambling and playing online games of chance in Tamil Nadu. "
            "The prohibition applies where money or other stakes are used and where the online game "
            "is a game of chance under the Act."
        ),
    },
    {
        "slug": "tamil-nadu-online-gambling-2022",
        "title": "Tamil Nadu Prohibition of Online Gambling and Regulation of Online Games Act 2022",
        "year": 2023,
        "subject_area": "digital_platform",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/19512/1/online_game_act.pdf",
        "origin": "indiacode",
        "anchor": "tamil-nadu-online-gambling-2022/sec-9",
        "section_no": "9",
        "section_title": "Prohibition of transfer of funds",
        "text": (
            "Tamil Nadu Prohibition of Online Gambling and Regulation of Online Games Act 2022, Section 9\n\n"
            "Section 9 prohibits banks, financial institutions, payment gateway providers, or other "
            "persons from extending banking, financial, payment, or fund-transfer services for online "
            "gambling or online games of chance prohibited by the Act."
        ),
    },
    {
        "slug": "tamil-nadu-online-gambling-2022",
        "title": "Tamil Nadu Prohibition of Online Gambling and Regulation of Online Games Act 2022",
        "year": 2023,
        "subject_area": "digital_platform",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/19512/1/online_game_act.pdf",
        "origin": "indiacode",
        "anchor": "tamil-nadu-online-gambling-2022/sec-14",
        "section_no": "14",
        "section_title": "Restrictions on non-local online games providers",
        "text": (
            "Tamil Nadu Prohibition of Online Gambling and Regulation of Online Games Act 2022, Section 14\n\n"
            "Section 14 restricts non-local online games providers from providing any online gambling "
            "service, allowing play of online games of chance specified in the Schedule with money or "
            "other stakes, or allowing any other online game contrary to regulations in Tamil Nadu. "
            "A non-local provider is not deemed to contravene the restriction if it has exercised due "
            "diligence or provided geo-blocking in Tamil Nadu."
        ),
    },
    {
        "slug": "tamil-nadu-online-gambling-2022",
        "title": "Tamil Nadu Prohibition of Online Gambling and Regulation of Online Games Act 2022",
        "year": 2023,
        "subject_area": "digital_platform",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/19512/1/online_game_act.pdf",
        "origin": "indiacode",
        "anchor": "tamil-nadu-online-gambling-2022/sec-16",
        "section_no": "16",
        "section_title": "Penalty for contravention",
        "text": (
            "Tamil Nadu Prohibition of Online Gambling and Regulation of Online Games Act 2022, Section 16\n\n"
            "Section 16 provides penalties for a person who indulges in online gambling or plays an "
            "online game of chance specified in the Schedule with money or other stakes in "
            "contravention of section 7, and for contraventions of the advertising, registration, and "
            "non-local provider restriction provisions."
        ),
    },
    {
        "slug": "public-gambling-1867",
        "title": "The Public Gambling Act, 1867",
        "year": 1867,
        "subject_area": "criminal",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/15437/1/publicgamblingact1867.pdf",
        "origin": "indiacode",
        "anchor": "public-gambling-1867/sec-3",
        "section_no": "3",
        "section_title": "Penalty for owning or keeping gaming-house",
        "text": (
            "The Public Gambling Act, 1867, Section 3\n\n"
            "Section 3 provides punishment for any person owning, occupying, using, keeping, or "
            "having the care or management of a common gaming-house, or assisting in conducting "
            "the business of a common gaming-house."
        ),
    },
    {
        "slug": "public-gambling-1867",
        "title": "The Public Gambling Act, 1867",
        "year": 1867,
        "subject_area": "criminal",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/15437/1/publicgamblingact1867.pdf",
        "origin": "indiacode",
        "anchor": "public-gambling-1867/sec-12",
        "section_no": "12",
        "section_title": "Act not to apply to certain games",
        "text": (
            "The Public Gambling Act, 1867, Section 12\n\n"
            "Section 12 says that nothing in the foregoing provisions of the Public Gambling Act "
            "shall be held to apply to any game of mere skill wherever played."
        ),
    },
    {
        "slug": "public-gambling-1867",
        "title": "The Public Gambling Act, 1867",
        "year": 1867,
        "subject_area": "criminal",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/15437/1/publicgamblingact1867.pdf",
        "origin": "indiacode",
        "anchor": "public-gambling-1867/sec-13",
        "section_no": "13",
        "section_title": "Gaming in public streets",
        "text": (
            "The Public Gambling Act, 1867, Section 13\n\n"
            "Section 13 concerns persons found playing for money or other valuable thing with cards, "
            "dice, counters, or other instruments of gaming in a public street, place, or thoroughfare, "
            "where the game is not a game of mere skill."
        ),
    },
    {
        "slug": "indian-succession-1925",
        "title": "Indian Succession Act 1925",
        "year": 1925,
        "subject_area": "family",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2385/1/192539.pdf",
        "origin": "indiacode",
        "anchor": "indian-succession-1925/sec-50",
        "section_no": "50",
        "section_title": "General principles relating to intestate succession",
        "text": (
            "Indian Succession Act 1925, Section 50\n\n"
            "Section 50 sets general principles for intestate succession among Parsis. A lineal "
            "descendant conceived at the date of death and later born alive is treated without "
            "distinction from one born during the lifetime of the deceased. A predeceased lineal "
            "descendant who left no widow, widower, lineal descendant, or widow or widower of a "
            "lineal descendant is not counted in determining how the intestate property is divided. "
            "A widow or widower of a relative who remarried during the intestate's lifetime is not "
            "entitled to a share and is deemed not to exist at the intestate's death."
        ),
    },
    {
        "slug": "indian-succession-1925",
        "title": "Indian Succession Act 1925",
        "year": 1925,
        "subject_area": "family",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2385/1/192539.pdf",
        "origin": "indiacode",
        "anchor": "indian-succession-1925/sec-51",
        "section_no": "51",
        "section_title": "Division among widower, children and parents",
        "text": (
            "Indian Succession Act 1925, Section 51\n\n"
            "Section 51 provides that the property of which a Parsi dies intestate is divided as "
            "follows. Where the Parsi leaves a widow or widower and children, the widow or "
            "widower and each child receive equal shares. Where the Parsi leaves children but "
            "no widow or widower, the property is divided among the children in equal shares. "
            "Where one or both parents are also left in addition to children or widow or widower "
            "and children, each parent receives a share equal to half the share of each child."
        ),
    },
    {
        "slug": "indian-succession-1925",
        "title": "Indian Succession Act 1925",
        "year": 1925,
        "subject_area": "family",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2385/1/192539.pdf",
        "origin": "indiacode",
        "anchor": "indian-succession-1925/sec-54",
        "section_no": "54",
        "section_title": "Division where no lineal descendant",
        "text": (
            "Indian Succession Act 1925, Section 54\n\n"
            "Section 54 applies where a Parsi dies without leaving any lineal descendant but leaves "
            "a widow or widower or a widow or widower of a lineal descendant. It sets rules for "
            "the shares of the widow or widower and widows or widowers of lineal descendants, "
            "and directs the residue to relatives in the order specified in Part I of Schedule II, "
            "with male and female relatives in the same degree of propinquity receiving equal shares."
        ),
    },
]

_EMBED_CACHE: dict[str, tuple[str, str]] = {}


def _embed(text: str) -> tuple[str, str]:
    cached = _EMBED_CACHE.get(text)
    if cached is not None:
        return cached
    dense, sparse = get_embedder().encode_with_sparse([text])
    out = (embedding_to_halfvec_literal(dense[0]), sparse_to_jsonb(sparse[0]))
    _EMBED_CACHE[text] = out
    return out


async def _upsert_chunk(conn: asyncpg.Connection, spec: dict) -> None:
    source_hash = hashlib.sha256(spec["source_url"].encode()).hexdigest()
    source_id = await conn.fetchval(
        """
        INSERT INTO sources (source_type, origin, url, canonical_url_hash, metadata)
        VALUES ('bare_act', $1, $2, $3, $4)
        ON CONFLICT (canonical_url_hash) DO UPDATE
          SET source_type = EXCLUDED.source_type,
              origin = EXCLUDED.origin,
              metadata = EXCLUDED.metadata
        RETURNING id
        """,
        spec["origin"],
        spec["source_url"],
        source_hash,
        json.dumps({"slug": spec["slug"], "stage35_backfill": True}),
    )
    doc_id = await conn.fetchval("SELECT id FROM documents WHERE doc_id = $1", spec["slug"])
    if doc_id is None:
        doc_id = await conn.fetchval(
            """
            INSERT INTO documents (source_id, doc_id, title, statute_short,
                                   statute_year, subject_area, metadata)
            VALUES ($1, $2, $3, $3, $4, $5, $6)
            RETURNING id
            """,
            source_id,
            spec["slug"],
            spec["title"],
            spec["year"],
            spec["subject_area"],
            json.dumps({"source_url": spec["source_url"], "stage35_backfill": True}),
        )
    else:
        await conn.execute(
            """
            UPDATE documents
            SET source_id = COALESCE(source_id, $1),
                title = $2,
                statute_short = COALESCE(statute_short, $2),
                statute_year = COALESCE(statute_year, $3),
                subject_area = COALESCE(subject_area, $4)
            WHERE id = $5
            """,
            source_id,
            spec["title"],
            spec["year"],
            spec["subject_area"],
            doc_id,
        )

    embedding, embedding_sparse = _embed(spec["text"])
    metadata = {
        "section_no": spec["section_no"],
        "section_title": spec["section_title"],
        "stage35_backfill": True,
        "source_url": spec["source_url"],
    }
    existing_chunk_id = await conn.fetchval(
        """
        SELECT id
        FROM chunks
        WHERE document_id = $1
          AND anchor = $2
          AND as_at IS NULL
        ORDER BY id
        LIMIT 1
        """,
        doc_id,
        spec["anchor"],
    )
    if existing_chunk_id:
        await conn.execute(
            """
            UPDATE chunks
            SET source_type = 'bare_act',
                subject_area = $1,
                paragraph_no = NULL,
                token_count = $2,
                text = $3,
                embedding = $4::halfvec,
                embedding_sparse = $5::jsonb,
                chunk_strategy = 'section',
                metadata = $6
            WHERE id = $7
            """,
            spec["subject_area"],
            len(spec["text"].split()),
            spec["text"],
            embedding,
            embedding_sparse,
            json.dumps(metadata),
            existing_chunk_id,
        )
        return

    await conn.execute(
        """
        INSERT INTO chunks (
            document_id, source_type, subject_area, anchor, paragraph_no,
            token_count, text, embedding, embedding_sparse, chunk_strategy,
            as_at, metadata
        )
        VALUES ($1, 'bare_act', $2, $3, NULL, $4, $5, $6::halfvec, $7::jsonb,
                'section', NULL, $8)
        """,
        doc_id,
        spec["subject_area"],
        spec["anchor"],
        len(spec["text"].split()),
        spec["text"],
        embedding,
        embedding_sparse,
        json.dumps(metadata),
    )


async def main() -> None:
    conn = await asyncpg.connect(get_settings().resolved_database_url_host_side)
    try:
        for spec in CHUNKS:
            await _upsert_chunk(conn, spec)
            print(f"upserted {spec['anchor']}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
