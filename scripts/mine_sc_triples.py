#!/usr/bin/env python3
"""Mine training triples from the SC judgment corpus.

The pattern this exploits — Indian SC judgments routinely cite a
section, then quote it verbatim:

    "Section 138 of the Negotiable Instruments Act, 1881 reads as
    follows: '138. Dishonour of cheque for insufficiency...'  The
    appellant contends that..."

Each such occurrence gives us a free (query, positive, hard-negative)
training triple:

  - query:           the issue paragraph (often the first few lines of
                     the case, framed in legal terms)
  - positive:        the bare-act chunk for the cited section
  - hard negative:   another section from the SAME act, OR a related
                     SC case that doesn't resolve to this section

For ~473K SC chunks we expect 50K-100K usable triples after
deduplication and filtering. Cost: free, ~30 min on the existing
corpus, no GPU needed.

Output:
  data/training/sc_triples.jsonl

  each line:
    {
      "query":        "...case issue paragraph...",
      "positive_anchor":  "negotiable-instruments-1881/sec-138",
      "positive_text":    "...bare-act body...",
      "hard_negative_anchor": "negotiable-instruments-1881/sec-139",
      "hard_negative_text":   "...adjacent section body...",
      "source_sc_anchor": "2021-insc-172#para-27",
      "source_sc_case":   "SUMETI VIJ versus M/S PARAMOUNT TECH FAB",
      "confidence":       "high|medium|low"
    }

Usage:
  PYTHONPATH=. .venv/bin/python scripts/mine_sc_triples.py \\
      --out data/training/sc_triples.jsonl \\
      --max 50000

  # Probe small slice first
  PYTHONPATH=. .venv/bin/python scripts/mine_sc_triples.py \\
      --out /tmp/probe.jsonl --max 200
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

import asyncpg

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# Patterns that indicate "the SC is quoting a section verbatim". We
# capture the section number + the surrounding context to find the
# corresponding bare-act chunk.
#
# Examples:
#   "Section 138 of the Negotiable Instruments Act, 1881..."
#   "Section 138, NI Act"
#   "s. 138 of the N.I. Act"
#   "Article 21 of the Constitution"
_SECTION_REF_RE = re.compile(
    r"""
    (?:Section|S\.|Article)            # "Section" or "S." or "Article"
    \s+
    (\d{1,4}[A-Z]{0,3})                # group 1: section number (138, 25F, 80EE, 144A)
    (?:                                # optional sub-clause/paragraph
        \s*\(\s*\d+\s*\)                 # (1) (2)
        (?:\s*\(\s*[a-z]\s*\))?          # (a) (b)
    )?
    \s*(?:of\s*the\s*)?
    (                                  # group 2: Act name proxy (a few words)
        [A-Z][A-Za-z\.\s&,'\-]{4,80}?
    )
    (?:Act|Code|Sanhita|Constitution)
    (?:                                # optional year/citation
        \s*,?\s*\d{4}
    )?
    """,
    re.VERBOSE,
)


def _load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


# Map common SC-quoted Act-name proxies to our `doc_id` slugs.
# Imperfect — we'll auto-validate via a chunk lookup downstream.
_ACT_NAME_HINTS = {
    "negotiable instrument": "negotiable-instruments-1881",
    "n.i.": "negotiable-instruments-1881",
    "ni ": "negotiable-instruments-1881",
    "transfer of property": "transfer-of-property-1882",
    "tpa": "transfer-of-property-1882",
    "indian contract": "indian-contract-1872",
    "hindu marriage": "hindu-marriage-1955",
    "hindu succession": "hindu-succession-1956",
    "hindu adoptions": "hindu-adoptions-maintenance-1956",
    "industrial disputes": "industrial-disputes-1947",
    "code of civil": "cpc-1908",
    "civil procedure": "cpc-1908",
    "cpc": "cpc-1908",
    "limitation act": "limitation-1963",
    "consumer protection": "consumer-protection-2019",
    "constitution": "constitution-india",
    "income-tax": "income-tax-1961",
    "income tax": "income-tax-1961",
    "central goods": "cgst-2017",
    "companies": "companies-2013",
    "rera": "rera-2016",
    "real estate": "rera-2016",
    "sarfaesi": "sarfaesi-2002",
    "prevention of money laundering": "pmla-2002",
    "narcotic drugs": "ndps-1985",
    "ndps": "ndps-1985",
    "dowry prohibition": "dowry-prohibition-1961",
    "domestic violence": "domestic-violence-2005",
    "protection of women": "domestic-violence-2005",
    "senior citizens": "senior-citizens-2007",
    "maintenance and welfare": "senior-citizens-2007",
    "specific relief": "specific-relief-1963",
    "rti": "rti-2005",
    "right to information": "rti-2005",
    "motor vehicles": "motor-vehicles-1988",
    "bharatiya nyaya": "bns-2023",
    "bharatiya nagarik": "bnss-2023",
    "bharatiya sakshya": "sakshya-adhiniyam-2023",
    "iso": "itpa-1956",
    "immoral traffic": "itpa-1956",
    "pocso": "pocso-2012",
    "protection of children": "pocso-2012",
    "rte": "rte-2009",
    "right to education": "rte-2009",
    "right of children": "rte-2009",
    "information technology": "it-2000",
    "digital personal data": "dpdp-2023",
    "posh": "posh-2013",
    "sexual harassment of women": "posh-2013",
    "factories": "factories-1948",
    "epf": "epf-1952",
    "employees provident": "epf-1952",
    "esi": "esi-1948",
    "employees state insurance": "esi-1948",
    "child marriage": "child-marriage-2006",
    "stamp": "indian-stamp-1899",
    "ibc": "ibc-2016",
    "insolvency": "ibc-2016",
    "arbitration": "arbitration-1996",
    "mediation": "mediation-2023",
    "telecommunications": "telecommunications-2023",
    "fema": "fema-1999",
    "customs": "customs-1962",
    "citizenship": "citizenship-1955",
    "passport": "citizenship-1955",  # ish — passports also in Passport Act
    "registration": "registration-1908",
    "succession act": "indian-succession-1925",
    "indian succession": "indian-succession-1925",
    "easements": "easements-1882",
    "wages": "code-on-wages-2019",
    "code on wages": "code-on-wages-2019",
    "shariat": "shariat-1937",
    "muslim women": "muslim-women-2019",
    "divorce act": "indian-divorce-1869",
    "family courts": "family-courts-1984",
    "guardians and wards": "guardians-wards-1890",
    "rights of persons with disabilities": "rpwd-2016",
    "rpwd": "rpwd-2016",
    "mental healthcare": "mental-healthcare-2017",
    "transgender": "transgender-2019",
    "medical termination": "mtp-1971",
    "mtp": "mtp-1971",
    "prevention of corruption": "prevention-of-corruption-1988",
    "sc/st": "sc-st-poa-1989",
    "scheduled castes": "sc-st-poa-1989",
    "limited liability": "llp-2008",
    "llp": "llp-2008",
    "partnership": "partnership-1932",
    "integrated goods": "igst-2017",
    "trade unions": "trade-unions-1926",
    "payment of gratuity": "gratuity-1972",
    "gratuity": "gratuity-1972",
    "maternity benefit": "maternity-benefit-1961",
    "equal remuneration": "equal-remuneration-1976",
    "aadhaar": "aadhaar-2016",
    "land acquisition": "rfctlarr-2013",
    "fair compensation": "rfctlarr-2013",
    "copyright": "copyright-1957",
    "immigration": "immigration-foreigners-2025",
    "foreigners": "immigration-foreigners-2025",
    "social security": "social-security-code-2020",
    "industrial relations": "industrial-relations-code-2020",
    "occupational safety": "osh-code-2020",
    "legal services authorities": "legal-services-authorities-1987",
    "nalsa": "legal-services-authorities-1987",
}


def _guess_act_slug(act_name_text: str) -> str | None:
    """Best-effort match of an SC-quoted Act name to our doc_id."""
    lower = act_name_text.lower()
    # Longest-match wins
    candidates = []
    for hint, slug in _ACT_NAME_HINTS.items():
        if hint in lower:
            candidates.append((len(hint), slug))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default=str(ROOT / "data/training/sc_triples.jsonl"),
                   help="output JSONL path")
    p.add_argument("--max", type=int, default=50000,
                   help="cap total triples (None = no cap)")
    p.add_argument("--probe", action="store_true",
                   help="probe-mode: 200 triples, verbose output, no file write")
    args = p.parse_args()

    env = _load_env()
    dsn = (
        f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@localhost:{env['POSTGRES_HOST_PORT']}/{env['POSTGRES_DB']}"
    )
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=4)

    if args.probe:
        cap = 200
        print("=== PROBE MODE — 200 triples max, verbose ===\n")
    else:
        cap = args.max

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # First pass: build a lookup of all bare-act sections we can match against
    print("Building bare-act section index...")
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT c.id, c.anchor, c.text,
                   c.metadata->>'section_no' AS sec_no,
                   d.doc_id
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.source_type = 'bare_act'
              AND c.metadata->>'section_no' IS NOT NULL
        """)
    # Index: (doc_id, section_no) -> (chunk_id, anchor, text)
    bare_act_index: dict[tuple[str, str], tuple[int, str, str]] = {}
    sections_by_act: dict[str, list[tuple[str, int, str, str]]] = defaultdict(list)
    for r in rows:
        key = (r["doc_id"], r["sec_no"])
        # Keep the first chunk for each section (anchor without sub-suffix)
        if key not in bare_act_index or "-" not in r["anchor"].split("/sec-")[-1]:
            bare_act_index[key] = (r["id"], r["anchor"], r["text"])
        sections_by_act[r["doc_id"]].append((r["sec_no"], r["id"], r["anchor"], r["text"]))
    print(f"  indexed {len(bare_act_index):,} (act, section) pairs "
          f"across {len(sections_by_act)} acts")

    # Second pass: scan SC chunks for section references
    print("Scanning SC chunks for section references...")
    triples = []
    skipped = {"no_match": 0, "no_neighbor": 0, "too_short": 0}
    seen_keys = set()

    async with pool.acquire() as conn:
        offset = 0
        batch = 5000
        while True:
            rows = await conn.fetch(
                "SELECT c.id, c.anchor, c.text, d.title "
                "FROM chunks c JOIN documents d ON d.id = c.document_id "
                "WHERE c.source_type = 'sc_judgment' "
                "AND length(c.text) > 200 "
                "ORDER BY c.id "
                "LIMIT $1 OFFSET $2",
                batch, offset,
            )
            if not rows:
                break
            offset += batch

            for sc_row in rows:
                text = sc_row["text"]
                for m in _SECTION_REF_RE.finditer(text):
                    if len(triples) >= cap:
                        break
                    sec_no = m.group(1)
                    act_name_text = m.group(2).strip()
                    slug = _guess_act_slug(act_name_text)
                    if not slug:
                        skipped["no_match"] += 1
                        continue
                    key = (slug, sec_no)
                    pos = bare_act_index.get(key)
                    if not pos:
                        skipped["no_match"] += 1
                        continue
                    # Hard negative: a different section from the same act
                    same_act = sections_by_act.get(slug, [])
                    other_secs = [s for s in same_act if s[0] != sec_no]
                    if not other_secs:
                        skipped["no_neighbor"] += 1
                        continue
                    neg = random.choice(other_secs)
                    # Deduplicate by (sc_chunk, positive_anchor)
                    dedup_key = (sc_row["id"], pos[1])
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    # Query proxy: extract a window around the section
                    # reference (the case-issue context)
                    qstart = max(0, m.start() - 200)
                    qend = min(len(text), m.end() + 50)
                    query = text[qstart:qend].strip()
                    # Clean up newlines / multiple spaces
                    query = re.sub(r"\s+", " ", query)
                    if len(query) < 50:
                        skipped["too_short"] += 1
                        continue

                    triples.append({
                        "query": query,
                        "positive_anchor": pos[1],
                        "positive_text": pos[2],
                        "hard_negative_anchor": neg[2],
                        "hard_negative_text": neg[3],
                        "source_sc_anchor": sc_row["anchor"],
                        "source_sc_case": sc_row["title"][:80],
                        "matched_act_name": act_name_text[:60],
                        "matched_slug": slug,
                        "section_no": sec_no,
                        "confidence": "high",  # all matches via explicit ref + slug map
                    })

                if len(triples) >= cap:
                    break

            if len(triples) >= cap:
                break

            if len(triples) > 0 and (len(triples) // 1000) > ((len(triples) - len(rows)*5) // 1000):
                print(f"  {len(triples):,} triples mined so far "
                      f"(offset={offset:,})")

    await pool.close()

    print(f"\n=== Mined {len(triples):,} triples ===")
    print(f"  skipped: no_match={skipped['no_match']:,} "
          f"no_neighbor={skipped['no_neighbor']:,} "
          f"too_short={skipped['too_short']:,}")

    if args.probe:
        print("\n=== First 3 triples ===")
        for t in triples[:3]:
            print(f"\nquery: {t['query'][:150]!r}")
            print(f"  positive: {t['positive_anchor']}")
            print(f"  hard neg: {t['hard_negative_anchor']}")
            print(f"  source:   {t['source_sc_anchor']}  [{t['source_sc_case']}]")
        # Histogram of acts
        from collections import Counter
        act_dist = Counter(t["matched_slug"] for t in triples)
        print(f"\n=== Top 10 acts by triple count (out of {len(act_dist)}) ===")
        for slug, n in act_dist.most_common(10):
            print(f"  {slug:<35} {n:>5}")
        return

    with out_path.open("w") as f:
        for t in triples:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(triples):,} triples to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
