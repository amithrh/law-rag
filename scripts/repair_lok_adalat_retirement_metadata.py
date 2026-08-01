#!/usr/bin/env python3
"""Repair stale LSA projection-retirement metadata in an already-live corpus.

The 0027 correction was the first migration that retired the undated LSA
projections. A deployment that ran the older 0029 implementation could have
rewritten that audit marker to 0029. Authority migrations are intentionally
no-op when their manifest is already applied, so this narrowly scoped repair
is kept explicit and idempotent.
"""

from __future__ import annotations

import argparse
import asyncio
import json

import asyncpg

from apps.api.config import Settings

LEGACY_LSA_ANCHORS = (
    "legal-services-authorities-1987/sec-19",
    "legal-services-authorities-1987/sec-20",
    "legal-services-authorities-1987/sec-21",
)
EXPECTED_RETIREMENT_MIGRATION = (
    "0027_legal_services_authorities_lok_adalat_temporal_correction"
)
STALE_RETIREMENT_MIGRATIONS = (
    "0028_legal_services_authorities_lok_adalat_projection_repair",
    "0029_legal_services_authorities_lok_adalat_official_projection_retirement",
)


async def run(*, apply: bool) -> dict[str, object]:
    conn = await asyncpg.connect(Settings().resolved_database_url_host_side)
    try:
        params = [list(LEGACY_LSA_ANCHORS), list(STALE_RETIREMENT_MIGRATIONS)]
        if not apply:
            count = await conn.fetchval(
                """
                SELECT count(*)
                FROM chunks
                WHERE anchor = ANY($1::text[])
                  AND as_at IS NULL
                  AND quarantined = true
                  AND metadata->>'authority_projection_retired_by_migration' = ANY($2::text[])
                """,
                *params,
            )
            return {"status": "dry_run", "eligible_rows": int(count)}

        async with conn.transaction():
            rows = await conn.fetch(
                """
                UPDATE chunks
                SET metadata = jsonb_set(
                    metadata,
                    '{authority_projection_retired_by_migration}',
                    to_jsonb($3::text),
                    true
                )
                WHERE anchor = ANY($1::text[])
                  AND as_at IS NULL
                  AND quarantined = true
                  AND metadata->>'authority_projection_retired_by_migration' = ANY($2::text[])
                RETURNING id, anchor
                """,
                *params,
                EXPECTED_RETIREMENT_MIGRATION,
            )
        return {
            "status": "applied",
            "updated_rows": len(rows),
            "anchors": [row["anchor"] for row in rows],
            "retired_by": EXPECTED_RETIREMENT_MIGRATION,
        }
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="apply the idempotent repair; without this flag only report eligible rows",
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(apply=args.apply)), sort_keys=True))


if __name__ == "__main__":
    main()
