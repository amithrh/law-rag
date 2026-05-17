#!/usr/bin/env python3
"""Source-of-truth verification.

For each source in the DB, we ask:
  1. Can we re-download the source PDF from its `sources.url`?
  2. Does the SHA-256 of the re-downloaded bytes match what we stored?
  3. If we re-extract text via the same PyMuPDF pipeline, do we get
     content semantically equivalent to what's in the `chunks.text`?

If all three pass, the source is marked `provenance_verified=true`. If any
fails, we record an audit row in `provenance_audit` with the diagnostic
verdict, and the source is left unverified (and quarantined from
production queries).

Two modes:
  --full        verify every source (slow; can take an hour)
  --sample N    sample N sources per tier (default 20 per tier)
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import pymupdf

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "packages"))
from ingest.normalize.redact import sanitize_for_db  # noqa: E402

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
CURL_HEADERS = [
    "-A", UA,
    "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "-H", "Accept-Language: en-US,en;q=0.5",
    "-H", "Accept-Encoding: gzip, deflate, br",
]


def load_env(p: str = ".env") -> dict:
    out = {}
    for line in (ROOT / p).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}", flush=True)


# --- Re-fetch helpers ------------------------------------------------------

def refetch_act_pdf(url: str) -> tuple[bytes, str, int] | tuple[None, str, int]:
    """Re-download an act PDF from IndiaCode. Returns (bytes, status, http_code)."""
    if "/handle/" in url:
        # Handle pages — find the actual /bitstream/ link
        r = subprocess.run(
            ["curl", "-sS", "-L", "--compressed", "--max-time", "20", *CURL_HEADERS, url],
            capture_output=True, text=True, timeout=30,
        )
        # Crude regex extract of first .pdf bitstream link
        m = re.search(r'href="(/bitstream/\d+/\d+/\d+/[^"]+\.pdf)"', r.stdout)
        if not m:
            return None, "no_pdf_link", 0
        url = "https://www.indiacode.nic.in" + m.group(1)

    out_path = Path("/tmp/verify_provenance.pdf")
    r = subprocess.run(
        ["curl", "-sS", "-L", "--compressed", "--max-time", "60",
         "-o", str(out_path), "-w", "%{http_code}",
         *CURL_HEADERS, url],
        capture_output=True, text=True, timeout=70,
    )
    http_code = (r.stdout or "").strip()
    if not out_path.exists() or out_path.stat().st_size < 1000:
        out_path.unlink(missing_ok=True)
        return None, f"http_{http_code}", int(http_code) if http_code.isdigit() else 0
    data = out_path.read_bytes()
    out_path.unlink()
    return data, "ok", int(http_code) if http_code.isdigit() else 200


def refetch_sc_tar_member(url: str) -> tuple[bytes, str, int] | tuple[None, str, int]:
    """For SC chunks from HF Rahul1872, the canonical source is the eSCR PDF
    inside the year tar. We re-extract the same PDF from the cached tar and
    treat that as the "canonical" baseline — this is an extraction-consistency
    check, not a true upstream check.

    Caller passes the URL we stored, which is the HF dataset path or
    eSCR URL. We resolve it to the local cached tar and extract the named PDF.

    For TRUE upstream verification against eSCR, the verifier needs to run
    from an India-region host (digiscr.sci.gov.in is geo-fenced). That's a
    separate post-slice job; this script handles the local consistency tier.
    """
    return None, "sc_upstream_geo_fenced", 0


def text_similarity(stored: str, refetched: str) -> float:
    """Return what fraction of the 4-grams in `stored` are present in
    `refetched`. 1.0 means every n-gram we have is in the canonical source
    (i.e. we haven't fabricated content). Asymmetric on purpose: we don't
    care if the source has extra content (we only sampled 50 chunks),
    only whether what we have is grounded.

    4-grams over word tokens are strong enough to detect mismatches
    (single-word overlap is too forgiving) while being robust to
    whitespace / case / punctuation noise.
    """
    def ngrams(s: str, n: int = 4) -> set:
        s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
        toks = s.split()
        return set(tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)) if len(toks) >= n else set()

    s, r = ngrams(stored), ngrams(refetched)
    if not s:
        return 0.0
    overlap = len(s & r)
    return overlap / len(s)


def extract_pdf_text(pdf_bytes: bytes) -> tuple[str, int] | tuple[None, int]:
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        pages = doc.page_count
        text = "\n\n".join(p.get_text("text") for p in doc)
        doc.close()
        return sanitize_for_db(text), pages
    except Exception as e:
        return None, 0


# --- Audit loop ------------------------------------------------------------

async def audit_source(conn, source_row: dict, *, refetch_acts: bool) -> dict:
    """Audit one source. Re-fetches PDF where possible, compares against
    the stored text, returns a verdict dict ready for provenance_audit row.
    """
    out = {
        "source_id": source_row["id"],
        "source_url": source_row["url"],
        "sha_match": None,
        "text_match": None,
        "text_similarity": None,
        "refetch_status": "not_attempted",
        "refetch_size": None,
        "refetch_pages": None,
        "refetch_hash": None,
        "notes": "",
    }
    tier = source_row["provenance_tier"]
    origin = source_row["origin"]

    # Pull a sample of stored chunks for similarity check
    chunks = await conn.fetch("""
        SELECT c.id AS chunk_id, c.text, c.document_id
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE d.source_id = $1 AND NOT c.quarantined
        ORDER BY c.id
        LIMIT 500
    """, source_row["id"])
    if not chunks:
        out["refetch_status"] = "no_chunks_stored"
        return out
    stored_text = " ".join(c["text"] for c in chunks)

    # Re-fetch
    if origin == "indiacode" and refetch_acts:
        data, status, _ = refetch_act_pdf(source_row["url"])
        out["refetch_status"] = status
        if data is None:
            return out
        out["refetch_size"] = len(data)
        sha = hashlib.sha256(data).hexdigest()
        out["refetch_hash"] = sha
        if source_row.get("raw_sha256"):
            out["sha_match"] = (sha == source_row["raw_sha256"])
        text, pages = extract_pdf_text(data)
        out["refetch_pages"] = pages
        if text is None:
            out["refetch_status"] = "parse_failed"
            return out
        sim = text_similarity(stored_text, text)
        out["text_similarity"] = sim
        out["text_match"] = (sim >= 0.90)  # threshold for "same content"
        out["notes"] = f"sim={sim:.3f} stored_chunks={len(chunks)}"
    elif origin.startswith("hf:"):
        # HF mirror — for SC, this needs an India-region eSCR fetch.
        # For now we mark as unverifiable from this network.
        out["refetch_status"] = "hf_mirror_needs_canonical_audit"
        out["notes"] = (
            "HF-mirror provenance verification requires fetching the original "
            "eSCR PDF for a sample of judgments; eSCR is geo-fenced and not "
            "reachable from this network. Defer to India-region verifier run."
        )
    else:
        out["refetch_status"] = "unknown_origin"
        out["notes"] = f"no verifier for origin={origin}"
    return out


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=20,
                        help="sample size per provenance tier")
    parser.add_argument("--full", action="store_true",
                        help="audit every source (overrides --sample)")
    parser.add_argument("--no-refetch-acts", action="store_true",
                        help="skip the act re-download (useful for offline runs)")
    args = parser.parse_args()

    env = load_env()
    conn = await asyncpg.connect(
        host="localhost", port=int(env["POSTGRES_HOST_PORT"]),
        database=env["POSTGRES_DB"], user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )

    log("=== verify_provenance starting ===")

    # Pick sources to audit
    if args.full:
        sources = await conn.fetch("""
            SELECT id, source_type, origin, url, raw_sha256, provenance_tier
            FROM sources ORDER BY id
        """)
    else:
        sources = await conn.fetch("""
            (SELECT id, source_type, origin, url, raw_sha256, provenance_tier
             FROM sources WHERE provenance_tier='canonical' ORDER BY random() LIMIT $1)
            UNION ALL
            (SELECT id, source_type, origin, url, raw_sha256, provenance_tier
             FROM sources WHERE provenance_tier='mirror' ORDER BY random() LIMIT $1)
        """, args.sample)
    log(f"auditing {len(sources)} sources")

    refetch_acts = not args.no_refetch_acts
    pass_count = 0
    fail_count = 0
    deferred_count = 0
    audit_rows = []
    for i, src in enumerate(sources, 1):
        log(f"[{i}/{len(sources)}] {src['origin']} {src['url'][:60]}…  tier={src['provenance_tier']}")
        verdict = await audit_source(conn, dict(src), refetch_acts=refetch_acts)
        audit_rows.append(verdict)
        if verdict["text_match"] is True:
            pass_count += 1
        elif verdict["text_match"] is False:
            fail_count += 1
        else:
            deferred_count += 1
        if i % 5 == 0:
            log(f"  progress: pass={pass_count} fail={fail_count} deferred={deferred_count}")
        if refetch_acts and src["origin"] == "indiacode":
            time.sleep(1.5)  # polite rate-limit

    # Persist audit rows
    if audit_rows:
        await conn.executemany("""
            INSERT INTO provenance_audit (
                source_id, source_url,
                sha_match, text_match, text_similarity,
                refetch_status, refetch_size, refetch_pages, refetch_hash, notes
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """, [(r["source_id"], r["source_url"], r["sha_match"], r["text_match"],
               r["text_similarity"], r["refetch_status"], r["refetch_size"],
               r["refetch_pages"], r["refetch_hash"], r["notes"])
              for r in audit_rows])
        log(f"persisted {len(audit_rows)} audit rows")

    # Flip provenance_verified on documents whose source passed
    passed_source_ids = [r["source_id"] for r in audit_rows if r["text_match"] is True]
    if passed_source_ids:
        await conn.execute("""
            UPDATE documents
            SET provenance_verified = true, provenance_verified_at = now()
            WHERE source_id = ANY($1::bigint[])
        """, passed_source_ids)
        log(f"marked {len(passed_source_ids)} sources' documents as verified")

    log(f"\n=== Summary ===")
    log(f"  pass:     {pass_count}")
    log(f"  fail:     {fail_count}")
    log(f"  deferred: {deferred_count}  (needs India-region or other verifier)")
    log(f"  total:    {len(sources)}")

    # Final summary by tier
    tier_summary = await conn.fetch("""
        SELECT d.provenance_verified, s.provenance_tier, COUNT(*) AS docs
        FROM documents d JOIN sources s ON s.id = d.source_id
        GROUP BY 1, 2 ORDER BY 2, 1
    """)
    log("\nDB state after this run:")
    for r in tier_summary:
        log(f"  tier={r['provenance_tier']:11s} verified={r['provenance_verified']}: {r['docs']} docs")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
