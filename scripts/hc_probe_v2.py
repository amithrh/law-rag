#!/usr/bin/env python3
"""Probe v2 — narrow in on a concrete HC ingest path.

This builds on `scripts/hc_probe.py` (which broadly mapped 8 HCs + the
unified ecourts portal). It does three things the v1 probe didn't:

  1. Inspects the **actual search form** at
     https://judgments.ecourts.gov.in/pdfsearch/ to document the CAPTCHA
     scheme, form fields, and AJAX endpoints — so we know exactly what
     scraping would entail if the open-data path went away.

  2. Inspects the Delhi HC search interfaces (`/app/case-number`,
     `/app/get-case-type-status`) to document their per-portal CAPTCHA.

  3. Verifies the **AWS Open Data Registry "Indian High Court Judgments"**
     bucket (`s3://indian-high-court-judgments`) is reachable
     anonymously over plain HTTPS, lists Delhi HC's 2024 partition,
     pulls the metadata parquet, and fetches one sample PDF + extracts
     its first page of text — confirming end-to-end OSS-only ingest is
     feasible without ever solving a CAPTCHA.

Writes `data/processed/hc_probe_v2.json` summarising findings. No DB
writes, no ingest.

robots.txt note: probed at session start. Both
`judgments.ecourts.gov.in/robots.txt` and
`delhihighcourt.nic.in/robots.txt` return 404 (no robots policy
declared). The S3 bucket has no robots.txt — public-data buckets don't
use them. We self-throttle to 1 req/sec regardless to be a good
citizen.
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
OUT_PATH = ROOT / "data" / "processed" / "hc_probe_v2.json"
S3_BUCKET = "https://indian-high-court-judgments.s3.ap-south-1.amazonaws.com"
COURT_CODES_URL = "https://raw.githubusercontent.com/vanga/indian-high-court-judgments/main/court-codes.json"
DELHI_HC_CODE = "7_26"   # per upstream court-codes.json — High Court of Delhi

UA = "Mozilla/5.0 (law-rag/hc_probe_v2; +https://github.com/amitmishra/law-rag)"
HDRS = {"User-Agent": UA, "Accept": "*/*"}


def log(msg: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{stamp}] {msg}", flush=True)


def http_get(url: str, *, timeout: float = 30.0) -> httpx.Response:
    return httpx.get(url, headers=HDRS, timeout=timeout, follow_redirects=True)


def probe_robots() -> dict:
    """Document robots.txt status for both portals + the S3 bucket."""
    out: dict[str, dict] = {}
    for url in [
        "https://judgments.ecourts.gov.in/robots.txt",
        "https://delhihighcourt.nic.in/robots.txt",
        f"{S3_BUCKET}/robots.txt",
    ]:
        r = http_get(url, timeout=15)
        out[url] = {
            "http_code": r.status_code,
            "body_first_500": r.text[:500] if r.status_code == 200 else None,
            "note": "no robots policy declared" if r.status_code == 404 else "see body",
        }
        time.sleep(1)
    return out


def probe_ecourts_pdfsearch() -> dict:
    """Document the CAPTCHA-gated unified search at /pdfsearch/."""
    r = http_get("https://judgments.ecourts.gov.in/pdfsearch/")
    text = r.text
    forms = re.findall(r"<form[^>]+>.*?</form>", text, re.S)
    primary_form = forms[0] if forms else ""
    field_names = sorted(set(re.findall(r"name=['\"]([^'\"]+)['\"]", primary_form)))
    captcha_img = re.findall(
        r'<img[^>]*id=[\'"]captcha_image[\'"][^>]*src=[\'"]([^\'"]+)[\'"]', text
    )
    return {
        "http_code": r.status_code,
        "captcha_scheme": "securimage (open-source PHP; distorted-text PNG)",
        "captcha_img_src_sample": captcha_img[0] if captcha_img else None,
        "captcha_audio_available": "captcha_image_audio" in text,
        "form_field_names": field_names,
        "ajax_required": True,
        "session_cookies_required": True,
        "bypass_notes": (
            "Securimage uses server-side session state — the image is bound "
            "to PHPSESSID. OCR on the distorted text is possible but the "
            "current Securimage build adds heavy noise. Audio CAPTCHA is "
            "available (speech-to-text via Whisper is OSS) but only as a "
            "last resort; we use the AWS Open Data path instead."
        ),
    }


def probe_delhi_hc() -> dict:
    """Document Delhi HC's two search surfaces and the 'latest judgments'
    listing that doesn't have a CAPTCHA."""
    out: dict[str, dict] = {}
    # /web/judgement/fetch-data — server-rendered "latest 293" judgments,
    # **no CAPTCHA**. Useful as an incremental tail-feed but only ~1 month
    # deep, no date-range query support.
    r = http_get("https://delhihighcourt.nic.in/web/judgement/fetch-data")
    pdfs = re.findall(r"showFileJudgment/([A-Z0-9_]+\.pdf)", r.text)
    dates = re.findall(r">(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})<", r.text)
    out["latest_judgments_feed"] = {
        "url": "https://delhihighcourt.nic.in/web/judgement/fetch-data",
        "http_code": r.status_code,
        "captcha": False,
        "judgments_in_response": len(pdfs),
        "date_first": dates[0] if dates else None,
        "date_last": dates[-1] if dates else None,
        "pagination_supported": False,
        "useful_as": "incremental tail-feed (~1 month deep)",
    }

    # /app/case-number — full case search but CAPTCHA-gated. The CAPTCHA
    # is a 4-digit numeric code rendered **inside the HTML source**
    # (`<span id="captcha-code">NNNN</span>`), making it trivially
    # auto-solvable. We don't need this path because the S3 bucket is
    # simpler, but record it as a fallback.
    r = http_get("https://delhihighcourt.nic.in/app/case-number")
    cap_code_match = re.search(
        r'<span[^>]+id=[\'"]captcha-code[\'"][^>]*>([^<]+)</span>', r.text
    )
    out["case_number_search"] = {
        "url": "https://delhihighcourt.nic.in/app/case-number",
        "http_code": r.status_code,
        "captcha": True,
        "captcha_scheme": (
            "4-digit numeric, plaintext in HTML <span id='captcha-code'>"
            f" — sample value: {cap_code_match.group(1) if cap_code_match else 'not found'}"
        ),
        "captcha_bypass": (
            "Trivial — answer is in the page source. Just regex it out. "
            "No external service or OCR needed."
        ),
        "form_fields": sorted(
            set(re.findall(r"name=['\"]([^'\"]+)['\"]", r.text))
        )[:20],
    }
    return out


def probe_open_data_bucket() -> dict:
    """Verify the AWS Open Data bucket is reachable anonymously and
    contains Delhi HC's 2024 slice."""
    out: dict = {}

    # 1. court codes mapping
    r = http_get(COURT_CODES_URL)
    if r.status_code == 200:
        out["court_codes"] = r.json()
    else:
        out["court_codes_fetch_failed"] = r.status_code

    # 2. List years available
    r = http_get(
        f"{S3_BUCKET}/?list-type=2"
        "&prefix=metadata/parquet/&delimiter=/&max-keys=200"
    )
    xml = re.sub(r'xmlns="[^"]+"', "", r.text)
    root = ET.fromstring(xml)
    years = [
        int(p.text.split("=")[1].rstrip("/"))
        for p in root.findall(".//CommonPrefixes/Prefix")
        if p.text and "year=" in p.text
    ]
    out["years_available"] = {"min": min(years), "max": max(years), "count": len(years)}

    # 3. For 2024 — list all courts present
    r = http_get(
        f"{S3_BUCKET}/?list-type=2"
        "&prefix=metadata/parquet/year=2024/&delimiter=/&max-keys=100"
    )
    xml = re.sub(r'xmlns="[^"]+"', "", r.text)
    root = ET.fromstring(xml)
    courts_2024 = [p.text for p in root.findall(".//CommonPrefixes/Prefix")]
    out["courts_in_2024"] = len(courts_2024)

    # 4. Delhi HC 2024 — list benches + the parquet file size
    r = http_get(
        f"{S3_BUCKET}/?list-type=2"
        f"&prefix=metadata/parquet/year=2024/court={DELHI_HC_CODE}/"
    )
    xml = re.sub(r'xmlns="[^"]+"', "", r.text)
    root = ET.fromstring(xml)
    pq_keys = [
        (k.findtext("Key"), int(k.findtext("Size") or 0))
        for k in root.findall(".//Contents")
    ]
    out["delhi_hc_2024_parquet"] = pq_keys

    # 5. List PDF directory size for Delhi HC 2024 (sample 10)
    r = http_get(
        f"{S3_BUCKET}/?list-type=2"
        f"&prefix=data/pdf/year=2024/court={DELHI_HC_CODE}/bench=dhcdb/&max-keys=10"
    )
    xml = re.sub(r'xmlns="[^"]+"', "", r.text)
    root = ET.fromstring(xml)
    pdf_samples = [
        (k.findtext("Key"), int(k.findtext("Size") or 0))
        for k in root.findall(".//Contents")
    ]
    out["delhi_hc_2024_pdf_samples"] = pdf_samples
    is_truncated = "<IsTruncated>true</IsTruncated>" in r.text
    out["delhi_hc_2024_pdfs_truncated_at_10"] = is_truncated

    # 6. data.tar / data.index.json — bulk archive
    r = http_get(
        f"{S3_BUCKET}/?list-type=2"
        f"&prefix=data/tar/year=2024/court={DELHI_HC_CODE}/"
    )
    xml = re.sub(r'xmlns="[^"]+"', "", r.text)
    root = ET.fromstring(xml)
    out["delhi_hc_2024_tar"] = [
        (k.findtext("Key"), int(k.findtext("Size") or 0))
        for k in root.findall(".//Contents")
    ]

    # 7. Fetch the parquet and inspect schema / row count
    try:
        import pyarrow.parquet as pq

        url = (
            f"{S3_BUCKET}/metadata/parquet/year=2024"
            f"/court={DELHI_HC_CODE}/bench=dhcdb/metadata.parquet"
        )
        log(f"  downloading parquet ({pq_keys[0][1] / 1e6:.1f} MB)...")
        r = httpx.get(url, headers=HDRS, timeout=180)
        table = pq.read_table(io.BytesIO(r.content))
        out["parquet_schema"] = {f.name: str(f.type) for f in table.schema}
        out["parquet_rows"] = table.num_rows
        first = table.slice(0, 1).to_pylist()[0]
        # Strip the giant raw_html field from the sample
        first.pop("raw_html", None)
        if "description" in first and isinstance(first["description"], str):
            first["description"] = first["description"][:200] + "..."
        out["parquet_first_row_sample"] = first
    except Exception as e:
        out["parquet_fetch_error"] = repr(e)

    # 8. Fetch one PDF + extract text (sanity end-to-end)
    if pdf_samples:
        sample_key = pdf_samples[3][0]  # pick the 4th (the first 3 are tiny stubs)
        url = f"{S3_BUCKET}/{sample_key}"
        log(f"  fetching sample PDF {sample_key}...")
        r = httpx.get(url, headers=HDRS, timeout=60)
        try:
            import fitz

            doc = fitz.open(stream=r.content, filetype="pdf")
            page1 = doc[0].get_text()
            out["pdf_sanity"] = {
                "url": url,
                "bytes": len(r.content),
                "content_type": r.headers.get("content-type"),
                "pages": len(doc),
                "page1_text_first_400": page1[:400],
            }
        except Exception as e:
            out["pdf_sanity_error"] = repr(e)

    return out


def main():
    findings: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "robots_txt": {},
        "ecourts_pdfsearch": {},
        "delhi_hc": {},
        "open_data_bucket": {},
        "recommendation": {},
    }

    log("=== probe v2: starting ===")

    log("checking robots.txt for both portals + the S3 bucket")
    findings["robots_txt"] = probe_robots()

    log("probing https://judgments.ecourts.gov.in/pdfsearch/")
    findings["ecourts_pdfsearch"] = probe_ecourts_pdfsearch()
    time.sleep(1)

    log("probing https://delhihighcourt.nic.in/{web/judgement/fetch-data,app/case-number}")
    findings["delhi_hc"] = probe_delhi_hc()
    time.sleep(1)

    log("probing s3://indian-high-court-judgments (AWS Open Data, anonymous)")
    findings["open_data_bucket"] = probe_open_data_bucket()

    findings["recommendation"] = {
        "chosen_hc": "Delhi HC",
        "chosen_court_code": DELHI_HC_CODE,
        "chosen_path": "AWS Open Data Registry — s3://indian-high-court-judgments",
        "rationale": [
            "Anonymous HTTPS access — no CAPTCHA, no Playwright, no session juggling.",
            "Curated upstream of the canonical ecourts.gov.in source (CC-BY-4.0).",
            "Quarterly refresh cadence (good enough for our weekly rebuild slice).",
            "Same code generalises to all 25 HCs via the court_codes.json mapping.",
            "Per-judgment provenance is preserved via the CNR + pdf_link in the parquet.",
        ],
        "fallback_paths": [
            "Delhi HC /web/judgement/fetch-data — ~293 latest judgments, no CAPTCHA, "
            "useful as a tail-feed if the S3 bucket goes stale.",
            "Delhi HC /app/case-number — CAPTCHA is plaintext in HTML, trivially "
            "bypassable; only needed if we want non-Delhi HCs not in the S3 bucket "
            "(none currently — bucket has all 25).",
            "judgments.ecourts.gov.in/pdfsearch/ — Securimage CAPTCHA, only worth "
            "implementing if upstream stops updating. Audio CAPTCHA + Whisper OSS as "
            "the path; no paid services.",
        ],
    }
    findings["finished_at"] = datetime.now(timezone.utc).isoformat()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(findings, indent=2, default=str))
    log(f"wrote findings to {OUT_PATH}")

    print()
    print("=" * 60)
    print("HC INGEST PROBE v2 SUMMARY")
    print("=" * 60)
    rec = findings["recommendation"]
    print(f"  chosen HC: {rec['chosen_hc']} (court_code={rec['chosen_court_code']})")
    print(f"  chosen path: {rec['chosen_path']}")
    bucket = findings["open_data_bucket"]
    if "parquet_rows" in bucket:
        print(f"  Delhi HC 2024 rows in parquet: {bucket['parquet_rows']:,}")
    if "pdf_sanity" in bucket:
        s = bucket["pdf_sanity"]
        print(f"  sanity PDF: {s['bytes']:,} bytes, {s['pages']} pages, OK")
    print()
    print("Next: scripts/bulk_ingest_hc.py --max-docs 5  (uses adapter hc.py)")


if __name__ == "__main__":
    main()
