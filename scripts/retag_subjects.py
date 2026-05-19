#!/usr/bin/env python3
"""Re-tag documents.subject_area using the rewritten title-aware classifier.

Background (audit, 2026-05-19): the original `infer_subject_area` scored
all SUBJECT_AREA_KEYWORDS categories with equal weight per match. Because
the `criminal` category had ~15 short, common keywords ("FIR", "bail",
"IPC", "CrPC"), it would win on most documents — even when those words
appeared only tangentially in tax / customs / land cases. Distribution
before fix: 14,112 of 16,147 SC docs (87%) tagged criminal.

The rewritten classifier (packages/ingest/adapters/base.py):
  1. Title override: case titles like "Commissioner of Income Tax v ..."
     short-circuit to the correct category.
  2. Length-weighted keyword scoring: "Bharatiya Nyaya Sanhita" (3
     words) scores 3 vs "FIR" (1 word).
  3. Min-confidence floor (2.0 weighted points). Below that → None.

This script:
  - Walks every document in the DB, pulls its title + first ~10kB of
    text (joined from the first few chunks).
  - Computes the NEW subject_area.
  - UPDATEs documents.subject_area in batches.
  - Logs the before/after distribution + a sample of changes.

Run with:
  PYTHONPATH=. .venv/bin/python scripts/retag_subjects.py
  PYTHONPATH=. .venv/bin/python scripts/retag_subjects.py --commit
  PYTHONPATH=. .venv/bin/python scripts/retag_subjects.py --limit 100 --commit
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

import asyncpg

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from ingest.adapters.base import infer_subject_area  # noqa: E402


SQL_FETCH = """
SELECT d.id, d.title, d.subject_area AS old_subject,
       (SELECT string_agg(c.text, ' ' ORDER BY c.id)
          FROM (
              SELECT id, text FROM chunks
               WHERE document_id = d.id
               ORDER BY id
               LIMIT 5
          ) c) AS sample_text
FROM documents d
ORDER BY d.id
"""

SQL_UPDATE = "UPDATE documents SET subject_area = $1 WHERE id = $2"


async def main(commit: bool, limit: int | None) -> None:
    from apps.api.config import get_settings
    s = get_settings()
    dsn = s.resolved_database_url_host_side

    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(SQL_FETCH)
        if limit:
            rows = rows[:limit]

        before = Counter(r["old_subject"] for r in rows)
        after_counter: Counter[str | None] = Counter()
        changes: list[tuple[int, str, str | None, str | None]] = []

        print(f"=== Retagging {len(rows)} docs "
              f"({'COMMIT' if commit else 'DRY RUN'}) ===\n", flush=True)

        for r in rows:
            old_subject = r["old_subject"]
            title = r["title"] or ""
            sample_text = r["sample_text"] or ""
            new_subject = infer_subject_area(sample_text, title=title)
            after_counter[new_subject] += 1
            if new_subject != old_subject:
                changes.append((r["id"], title[:60], old_subject, new_subject))
                if commit:
                    await conn.execute(SQL_UPDATE, new_subject, r["id"])

        print(f"=== Before ({sum(before.values())} docs) ===")
        for subj, n in sorted(before.items(), key=lambda kv: -kv[1]):
            print(f"  {str(subj):20s} {n:>6d}")

        print(f"\n=== After ({sum(after_counter.values())} docs) ===")
        for subj, n in sorted(after_counter.items(), key=lambda kv: -kv[1]):
            print(f"  {str(subj):20s} {n:>6d}")

        n_changed = len(changes)
        print(f"\n=== Changes: {n_changed} docs "
              f"({100*n_changed/max(1,len(rows)):.1f}% of inspected) ===")
        by_transition: dict[tuple, list] = {}
        for cid, title, old, new in changes:
            by_transition.setdefault((old, new), []).append((cid, title))
        for (old, new), items in sorted(by_transition.items(),
                                        key=lambda kv: -len(kv[1])):
            print(f"\n  {str(old):15s} → {str(new):15s}  ({len(items)} docs)")
            for cid, title in items[:3]:
                print(f"    #{cid:>6d}  {title}")

        if not commit:
            print("\n(DRY RUN — pass --commit to write the changes)")
    finally:
        await conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--commit", action="store_true",
                   help="actually UPDATE the DB (default: dry run)")
    p.add_argument("--limit", type=int, default=None,
                   help="cap inspection to first N docs (for smoke testing)")
    args = p.parse_args()
    asyncio.run(main(commit=args.commit, limit=args.limit))
