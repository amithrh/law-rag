#!/usr/bin/env python3
"""Probe judgments.ecourts.gov.in to understand the HC ingest path.

Goals (no ingest yet — just discover):
  1. Map the search-by-CNR / case-number / date-range endpoints
  2. Identify whether per-judgment URLs are deep-linkable (no session/CAPTCHA)
  3. Verify the official Govt provenance (URL ends at digiscr or
     judgments.ecourts.gov.in — not a publisher mirror)
  4. Sample 5 Delhi HC judgments by hand-crafted URL to confirm we can
     reach the canonical PDF + extract text

Output: data/processed/hc_probe.json with what we learned. The actual
adapter / ingest lands as a separate commit informed by this probe.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "packages"))

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HDRS = [
    "-A", UA,
    "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "-H", "Accept-Language: en-US,en;q=0.5",
    "-H", "Accept-Encoding: gzip, deflate, br",
]


def log(msg: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{stamp}] {msg}", flush=True)


def curl(url: str, *, max_time: int = 20) -> tuple[int, str]:
    r = subprocess.run(
        ["curl", "-sS", "-L", "--compressed", "--max-time", str(max_time),
         "-w", "\n%{http_code}", *HDRS, url],
        capture_output=True, text=True, timeout=max_time + 10,
    )
    body = r.stdout
    code = body.rsplit("\n", 1)[-1]
    return int(code) if code.isdigit() else 0, body[:-len(code) - 1]


def probe():
    findings = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "portals": {},
        "judgment_url_patterns": [],
        "samples": [],
        "next_steps": [],
    }

    # 1. The unified ecourts.gov.in portal
    log("probing https://judgments.ecourts.gov.in/")
    code, body = curl("https://judgments.ecourts.gov.in/")
    findings["portals"]["judgments.ecourts.gov.in"] = {
        "http_code": code,
        "title": _title(body),
        "has_search_form": "<form" in body.lower(),
        "javascript_only": "noscript" in body.lower() and len(body) < 30_000,
    }

    # 2. The eCourts Services portal — has the actual case search
    log("probing https://services.ecourts.gov.in/")
    code, body = curl("https://services.ecourts.gov.in/ecourtindia_v6/")
    findings["portals"]["services.ecourts.gov.in"] = {
        "http_code": code,
        "title": _title(body),
    }

    # 3. Per-HC official portals (Tier A per PLAN §1.5)
    for hc_name, url in [
        ("Delhi HC", "https://delhihighcourt.nic.in/"),
        ("Bombay HC", "https://bombayhighcourt.nic.in/"),
        ("Madras HC", "https://mhc.tn.gov.in/judis/"),
        ("Karnataka HC", "https://karnatakajudiciary.kar.nic.in/"),
        ("Calcutta HC", "https://www.calcuttahighcourt.gov.in/"),
        ("Allahabad HC", "https://www.allahabadhighcourt.in/"),
        ("Kerala HC", "https://highcourtofkerala.nic.in/"),
        ("Punjab & Haryana HC", "https://phhc.gov.in/"),
    ]:
        log(f"probing {hc_name}: {url}")
        code, body = curl(url, max_time=15)
        findings["portals"][hc_name] = {
            "http_code": code,
            "title": _title(body),
            "url": url,
            "has_judgment_link": bool(re.search(r"judg(e)?ments?|orders|verdict", body, re.I)),
        }
        time.sleep(1)

    # 4. Look for direct judgment-URL patterns in Delhi HC homepage
    log("scraping Delhi HC homepage for judgment-URL patterns")
    code, body = curl("https://delhihighcourt.nic.in/", max_time=15)
    judgment_links = re.findall(
        r'href="([^"]*(?:judg|order|verdict|case)[^"]*)"', body, re.IGNORECASE,
    )
    findings["judgment_url_patterns"] = sorted(set(judgment_links))[:30]

    # 5. Try downloading a known Delhi HC judgment PDF (if URL pattern is stable)
    # Most Delhi HC PDFs follow `https://delhihighcourt.nic.in/dhc/HC_Order_PDFs/...`
    # but the exact path needs the case_id. Without a stable case_id lookup we
    # can't construct these blindly. Mark as "needs adapter".
    findings["next_steps"] = [
        "Delhi HC: each judgment has a stable PDF URL but constructing it "
        "requires CASE_TYPE, CASE_NO, YEAR; we'd need to scrape the search "
        "results page first (dhcqrydisp_O.aspx) which has CAPTCHA.",
        "Bombay HC: similar — search by case type/number, then download.",
        "Madras HC: mhc.tn.gov.in/judis/ has direct date-range judgment "
        "listings but PDF URLs are session-stamped.",
        "Best canonical option: judgments.ecourts.gov.in/ unified portal — "
        "supports search by court/judge/case type/date with downloadable "
        "PDFs. Has CAPTCHA on search; per-judgment view URLs reportedly "
        "stable once the CNR (Case Number Record) is known. Need Playwright "
        "for the search phase.",
        "Provenance fallback: SCI scr.sci.gov.in/scrsearch/ is for SC only; "
        "no HC equivalent without going through ecourts.",
    ]

    findings["finished_at"] = datetime.now(timezone.utc).isoformat()
    out = ROOT / "data" / "processed" / "hc_probe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(findings, indent=2))
    log(f"wrote findings to {out}")

    # Pretty summary
    print()
    print("=" * 60)
    print("HC INGEST PROBE SUMMARY")
    print("=" * 60)
    for name, info in findings["portals"].items():
        title = info.get("title", "(no title)")
        print(f"  {info['http_code']:3d}  {name:25s}  {title[:60]}")
    print()
    print(f"Judgment-URL patterns found on Delhi HC: {len(findings['judgment_url_patterns'])}")
    for u in findings["judgment_url_patterns"][:5]:
        print(f"  - {u[:100]}")
    print()
    print("Next steps:")
    for s in findings["next_steps"]:
        print(f"  • {s}")


def _title(body: str) -> str:
    m = re.search(r"<title[^>]*>([^<]+)</title>", body, re.I)
    return m.group(1).strip()[:80] if m else "(no title)"


if __name__ == "__main__":
    probe()
