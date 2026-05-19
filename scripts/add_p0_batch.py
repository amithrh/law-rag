#!/usr/bin/env python3
"""P0 corpus expansion — ingest the 25 highest-priority missing acts.

Built from docs/ACTS_GAP_ANALYSIS.md. Three ingest patterns supported:

  1. handle_id=...        — fetch from indiacode.nic.in/handle/123456789/<id>
                            (bypasses the buggy name-search in resolve_handle())
  2. cached_pdf=...       — use an already-downloaded PDF in data/raw/acts/
                            (for IPC/IEA which gather.py fetched but never ingested)
  3. pdf_url=...          — fetch a direct PDF URL
                            (for off-IndiaCode sources like IT Act 2025 on
                             incometaxindia.gov.in)

Idempotent on slug: skips any (slug) where the documents row already has
chunks. Dense-only embeddings — sparse vectors get filled in by the
backfill_sparse_embeddings.py script which is filtered on
embedding_sparse IS NULL.

Why explicit-handle override:
The existing scripts/gather_more_data.py and scripts/add_more_acts.py
search by act name. For several acts (TPA, Contract, IT 2000, Companies
2013, RBI 1934, Wildlife 1972) IndiaCode's search returns the wrong
"Other-collection" handle as the first result — typically a
Repealing/Amending Act, a J&K-only extension, or an unrelated 1948
"Transfer to Public Ownership" act. Hard-coding the handles dodges all
those failure modes.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import asyncpg
import numpy as np
import pymupdf
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "packages"))
from chunking.act import chunk_act  # noqa: E402
from ingest.adapters.base import infer_subject_area  # noqa: E402
from ingest.normalize.redact import redact  # noqa: E402

# ----------------------------------------------------------------------
# P0 batch — see docs/ACTS_GAP_ANALYSIS.md §6 for justification per act.
#   slug       : doc_id in the DB (lowercase, hyphenated)
#   title      : human-readable Act title (gets stored as documents.title)
#   handle_id  : IndiaCode handle (preferred path for most)
#   cached_pdf : alternative — use a local PDF instead of fetching
#   pdf_url    : alternative — fetch this direct URL (off-IndiaCode)
#   min_size   : minimum PDF size (bytes) to consider valid
#   as_at      : effective date — used for year-aware retrieval filters
#   subject_area : explicit tag (otherwise inferred from text + title)
# ----------------------------------------------------------------------
P0: list[dict[str, Any]] = [
    # --- DEFERRED: IPC 1860 + IEA 1872 --------------------------------
    # All three cached `ipc-1860__*.pdf` and `indian-evidence-act-1872__h2408.pdf`
    # files in data/raw/acts/ turned out to be amendments/Gazette extracts,
    # not the full bare Acts (verified via pymupdf: 5-16 pages, first-page
    # text shows "Criminal Law (Amendment) Act 2018" etc, not "1. Short
    # title and extent..."). IndiaCode CENT handles for IPC h=12850 and
    # IEA h=12846 list the right titles but serve no PDF bitstream
    # (presumably de-listed after BNS 2023 / BSA 2023 superseded them).
    # legislative.gov.in URLs 404. Since BNS, BNSS, BSA are already in
    # corpus AND every SC judgment quotes IPC/CrPC/IEA sections verbatim,
    # retrieval for "Section X IPC" hits via those routes. Deferring the
    # bare-Act ingest of these three to a follow-up that tries Indian
    # Kanoon or archive.org as alt sources.

    # --- procedural / civil --------------------------------------------
    # CrPC: h=15272 has the right meta title but on close inspection also
    # serves no bitstream. Same de-listing pattern as IPC/IEA. Deferred
    # along with them.

    {"slug": "cpc-1908", "title": "Code of Civil Procedure 1908",
     "handle_id": "2191", "min_size": 300_000,
     "subject_area": "civil_general"},
    {"slug": "limitation-1963", "title": "Limitation Act 1963",
     "handle_id": "1565", "subject_area": "civil_general"},

    # --- property / civil substantive ----------------------------------
    {"slug": "transfer-of-property-1882",
     "title": "Transfer of Property Act 1882",
     "handle_id": "2338", "subject_area": "property"},
    {"slug": "indian-contract-1872", "title": "Indian Contract Act 1872",
     "handle_id": "2187", "subject_area": "civil_general"},
    {"slug": "registration-1908", "title": "Registration Act 1908",
     "handle_id": "2190", "subject_area": "property"},

    # --- family / personal --------------------------------------------
    {"slug": "hindu-succession-1956",
     "title": "Hindu Succession Act 1956 (with 2005 amendment)",
     "handle_id": "1713", "subject_area": "family"},
    {"slug": "hindu-adoptions-maintenance-1956",
     "title": "Hindu Adoptions and Maintenance Act 1956",
     "handle_id": "1638", "subject_area": "family"},
    {"slug": "shariat-1937",
     "title": "Muslim Personal Law (Shariat) Application Act 1937",
     "handle_id": "2303", "subject_area": "family"},
    {"slug": "dissolution-muslim-marriages-1939",
     "title": "Dissolution of Muslim Marriages Act 1939",
     "handle_id": "2404", "subject_area": "family"},
    {"slug": "guardians-wards-1890",
     "title": "Guardians and Wards Act 1890",
     "handle_id": "2318", "subject_area": "family"},

    # --- welfare / vulnerable groups ----------------------------------
    # h=2024 is WRONG (Private Security Agencies 2005). h=12901 is the real
    # Child Marriage Act 2006 handle (PDF stored at bitstream /2055/4/).
    {"slug": "child-marriage-2006",
     "title": "Prohibition of Child Marriage Act 2006",
     "handle_id": "12901", "subject_area": "family"},
    # h=2128/2127 are empty. POCSO real handle is 12903 (file at /2079/1/);
    # JJ 2015 real handle is 17101.
    {"slug": "pocso-2012",
     "title": "Protection of Children from Sexual Offences Act 2012",
     "handle_id": "12903", "subject_area": "criminal"},
    {"slug": "jj-2015",
     "title": "Juvenile Justice (Care and Protection of Children) Act 2015",
     "handle_id": "17101", "subject_area": "criminal"},
    {"slug": "posh-2013",
     "title": "Sexual Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act 2013",
     "handle_id": "2104", "subject_area": "service_employment"},

    # --- labour codes (2020) ------------------------------------------
    {"slug": "social-security-code-2020",
     "title": "Code on Social Security 2020",
     "handle_id": "16823", "subject_area": "service_employment"},
    {"slug": "industrial-relations-code-2020",
     "title": "Industrial Relations Code 2020",
     "handle_id": "22040", "subject_area": "service_employment"},
    {"slug": "osh-code-2020",
     "title": "Occupational Safety, Health and Working Conditions Code 2020",
     "handle_id": "22041", "subject_area": "service_employment"},

    # --- finance / commercial -----------------------------------------
    {"slug": "negotiable-instruments-1881",
     "title": "Negotiable Instruments Act 1881",
     "handle_id": "2189", "subject_area": "civil_general"},
    {"slug": "income-tax-1961", "title": "Income-tax Act 1961",
     "handle_id": "2435", "min_size": 500_000,
     "subject_area": "tax"},
    {"slug": "companies-2013", "title": "Companies Act 2013",
     "handle_id": "2114", "min_size": 300_000,
     "subject_area": "company_securities"},
    # h=12697 has the right title but no PDF on its page. h=7771 hosts the
    # actual cgst-act.pdf bitstream.
    {"slug": "cgst-2017", "title": "Central Goods and Services Tax Act 2017",
     "handle_id": "7771", "subject_area": "tax"},
    {"slug": "rera-2016", "title": "Real Estate (Regulation and Development) Act 2016",
     "handle_id": "2158", "subject_area": "property"},

    # --- cyber / IT ---------------------------------------------------
    {"slug": "it-2000", "title": "Information Technology Act 2000",
     "handle_id": "13116", "subject_area": "civil_general"},
    {"slug": "dpdp-2023", "title": "Digital Personal Data Protection Act 2023",
     "handle_id": "22037", "subject_area": "civil_general"},

    # --- constitutional / access --------------------------------------
    {"slug": "constitution-india",
     "title": "Constitution of India",
     "handle_id": "19632", "min_size": 1_000_000,
     "subject_area": "constitutional"},
    # h=21427 has no PDF. h=21338 has a malformed href (missing close quote)
    # plus the linked PDFs are state-level Rajasthan Hindi rules — wrong
    # target. h=12883 / h=10899 / h=14064 all point to the same bitstream
    # /1925/1/198739.pdf (English central Act). Using h=12883.
    {"slug": "legal-services-authorities-1987",
     "title": "Legal Services Authorities Act 1987",
     "handle_id": "12883", "subject_area": "civil_general"},
    {"slug": "mediation-2023", "title": "Mediation Act 2023",
     "handle_id": "19637", "subject_area": "civil_general"},

    # --- P1 add-ons: user-reported gaps from UI testing 2026-05-19 -----
    # "school not admitting my child" → RTE Act 2009. h=19908 (CENT 2505)
    # has the right title but serves no PDF; h=13682 (col 2493) hosts the
    # clean `rte_act_2009.pdf` bitstream.
    {"slug": "rte-2009",
     "title": "Right of Children to Free and Compulsory Education Act 2009",
     "handle_id": "13682", "subject_area": "education"},

    # "landlord won't return my deposit" → State Rent Acts (the user's
    # operative law for security-deposit-on-tenancy disputes). Five
    # largest states by tenancy-dispute volume.
    {"slug": "mh-rent-control-1999",
     "title": "Maharashtra Rent Control Act 1999",
     "handle_id": "15817", "subject_area": "property"},
    {"slug": "up-urban-tenancy-2021",
     "title": "Uttar Pradesh Urban Buildings (Regulation of Letting, Rent and Eviction) Act 2021",
     "handle_id": "19204", "subject_area": "property"},
    {"slug": "tn-tenancy-2017",
     "title": "Tamil Nadu Regulation of Rights and Responsibilities of Landlords and Tenants Act 2017",
     "handle_id": "20507", "subject_area": "property"},
    {"slug": "ka-rent-1999", "title": "Karnataka Rent Act 1999",
     "handle_id": "7810", "subject_area": "property"},
    {"slug": "wb-premises-tenancy-1997",
     "title": "West Bengal Premises Tenancy Act 1997",
     "handle_id": "14542", "subject_area": "property"},

    # --- P1 expansion round 2: lay-user query coverage (2026-05-19) ---
    # ITPA: user-flagged via "i am prostitute can police catch me" — Act
    # criminalises soliciting / brothel-keeping but not sex work per se;
    # the bare-act text is needed to give a non-misleading answer.
    {"slug": "itpa-1956",
     "title": "Immoral Traffic (Prevention) Act 1956",
     "handle_id": "20019", "subject_area": "criminal"},

    # Drug law — high pro-bono query volume
    {"slug": "ndps-1985",
     "title": "Narcotic Drugs and Psychotropic Substances Act 1985",
     "handle_id": "21511", "subject_area": "criminal"},

    # Dowry — top family-criminal query
    {"slug": "dowry-prohibition-1961",
     "title": "Dowry Prohibition Act 1961",
     "handle_id": "1679", "subject_area": "criminal"},

    # Money laundering — ED proceedings; politically prominent
    {"slug": "pmla-2002",
     "title": "Prevention of Money Laundering Act 2002",
     "handle_id": "2036", "subject_area": "criminal"},

    # IBC — corporate / personal insolvency
    {"slug": "ibc-2016",
     "title": "Insolvency and Bankruptcy Code 2016",
     "handle_id": "2154", "subject_area": "company_securities"},

    # SARFAESI — bank repossession; MSME/home-loan disputes
    {"slug": "sarfaesi-2002",
     "title": "Securitisation and Reconstruction of Financial Assets and Enforcement of Security Interest Act 2002",
     "handle_id": "2006", "subject_area": "property"},

    # Arbitration — alternate dispute resolution
    {"slug": "arbitration-1996",
     "title": "Arbitration and Conciliation Act 1996",
     "handle_id": "21922", "subject_area": "civil_general"},

    # Mental Healthcare — advance directives, decriminalisation of suicide
    {"slug": "mental-healthcare-2017",
     "title": "Mental Healthcare Act 2017",
     "handle_id": "2249", "subject_area": "constitutional"},

    # Rights of PwD — disability rights
    {"slug": "rpwd-2016",
     "title": "Rights of Persons with Disabilities Act 2016",
     "handle_id": "2155", "subject_area": "constitutional"},

    # Transgender Rights — self-identification, anti-discrimination
    {"slug": "transgender-2019",
     "title": "Transgender Persons (Protection of Rights) Act 2019",
     "handle_id": "13091", "subject_area": "constitutional"},

    # Customs — imports/duty/smuggling
    {"slug": "customs-1962",
     "title": "Customs Act 1962",
     "handle_id": "2475", "subject_area": "tax"},

    # FEMA — NRI/FX queries
    {"slug": "fema-1999",
     "title": "Foreign Exchange Management Act 1999",
     "handle_id": "1988", "subject_area": "tax"},

    # Indian Stamp Act — stamp duty
    {"slug": "indian-stamp-1899",
     "title": "Indian Stamp Act 1899",
     "handle_id": "15510", "subject_area": "property"},

    # Citizenship Act — citizenship queries (CAA-adjacent)
    {"slug": "citizenship-1955",
     "title": "Citizenship Act 1955",
     "handle_id": "1522", "subject_area": "constitutional"},

    # MTP Act — abortion law
    {"slug": "mtp-1971",
     "title": "Medical Termination of Pregnancy Act 1971",
     "handle_id": "1593", "subject_area": "family"},

    # POCSO/JJ/PCMA already in corpus; add Prevention of Corruption (1988)
    {"slug": "prevention-of-corruption-1988",
     "title": "Prevention of Corruption Act 1988",
     "handle_id": "1558", "subject_area": "criminal"},

    # --- P1 expansion round 3 (2026-05-19): labour predecessors + IDs ---
    # The four labour-code predecessor Acts are still in partial force
    # until section-wise commencement of SS Code 2020 / IR Code 2020 /
    # OSH Code 2020 completes. Heavily queried standalone.
    {"slug": "industrial-disputes-1947",
     "title": "Industrial Disputes Act 1947",
     "handle_id": "20952", "subject_area": "service_employment"},
    {"slug": "factories-1948",
     "title": "Factories Act 1948",
     "handle_id": "20951", "subject_area": "service_employment"},
    {"slug": "epf-1952",
     "title": "Employees' Provident Funds and Miscellaneous Provisions Act 1952",
     "handle_id": "2152", "subject_area": "service_employment"},
    {"slug": "esi-1948",
     "title": "Employees' State Insurance Act 1948",
     "handle_id": "20349", "subject_area": "service_employment"},
    {"slug": "gratuity-1972",
     "title": "Payment of Gratuity Act 1972",
     "handle_id": "22091", "subject_area": "service_employment"},
    {"slug": "maternity-benefit-1961",
     "title": "Maternity Benefit Act 1961",
     "handle_id": "20954", "subject_area": "service_employment"},
    {"slug": "trade-unions-1926",
     "title": "Trade Unions Act 1926",
     "handle_id": "20965", "subject_area": "service_employment"},
    {"slug": "equal-remuneration-1976",
     "title": "Equal Remuneration Act 1976",
     "handle_id": "20950", "subject_area": "service_employment"},

    # ID / cyber
    {"slug": "aadhaar-2016",
     "title": "Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016",
     "handle_id": "2160", "subject_area": "constitutional"},
    {"slug": "telecommunications-2023",
     "title": "Telecommunications Act 2023",
     "handle_id": "20101", "subject_area": "civil_general"},

    # Commercial
    {"slug": "llp-2008",
     "title": "Limited Liability Partnership Act 2008",
     "handle_id": "2023", "subject_area": "company_securities"},
    {"slug": "partnership-1932",
     "title": "Indian Partnership Act 1932",
     "handle_id": "2394", "subject_area": "company_securities"},
    {"slug": "igst-2017",
     "title": "Integrated Goods and Services Tax Act 2017",
     "handle_id": "2251", "subject_area": "tax"},

    # Family / personal law expansion
    {"slug": "family-courts-1984",
     "title": "Family Courts Act 1984",
     "handle_id": "12869", "subject_area": "family"},
    {"slug": "muslim-women-2019",
     "title": "Muslim Women (Protection of Rights on Marriage) Act 2019",
     "handle_id": "11564", "subject_area": "family"},
    {"slug": "indian-divorce-1869",
     "title": "Divorce Act 1869 (Indian Divorce Act — Christian marriages)",
     "handle_id": "2280", "subject_area": "family"},

    # SC/ST Prevention of Atrocities
    {"slug": "sc-st-poa-1989",
     "title": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989",
     "handle_id": "1920", "subject_area": "criminal"},

    # Immigration (replaces Foreigners Act 1946 + 3 others; effective 1 Sep 2025)
    {"slug": "immigration-foreigners-2025",
     "title": "Immigration and Foreigners Act 2025",
     "handle_id": "21918", "subject_area": "constitutional"},

    # --- P1 round 4: final stragglers (2026-05-19) -----------------
    # Indian Succession 1925 — wills/probate for Christians, Parsis,
    # Jews; default rules for non-Hindus and non-Muslims.
    {"slug": "indian-succession-1925",
     "title": "Indian Succession Act 1925",
     "handle_id": "2385", "subject_area": "family"},

    # RFCTLARR — Land Acquisition (replaces 1894 Act); compensation
    # framework heavily queried in tribal / farmer / displaced-person
    # cases.
    {"slug": "rfctlarr-2013",
     "title": "Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act 2013",
     "handle_id": "12916", "subject_area": "property"},

    # Copyright — music/film/software/journalism queries
    {"slug": "copyright-1957",
     "title": "Copyright Act 1957",
     "handle_id": "1367", "subject_area": "civil_general"},
]

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
HEADERS = [
    "-A", UA,
    "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "-H", "Accept-Language: en-US,en;q=0.5",
    "-H", "Accept-Encoding: gzip, deflate, br",
]


def fetch_text(url: str) -> str:
    r = subprocess.run(
        ["curl", "-sS", "-L", "--compressed", "--max-time", "30",
         *HEADERS, url],
        capture_output=True, text=True, timeout=40,
    )
    return r.stdout


def fetch_bytes(url: str, out_path: Path, min_size: int = 50_000) -> int:
    r = subprocess.run(
        ["curl", "-sS", "-L", "--compressed", "--max-time", "120",
         "-w", "%{http_code}", *HEADERS, "-o", str(out_path), url],
        capture_output=True, text=True, timeout=140,
    )
    http_code = (r.stdout or "").strip()
    if not out_path.exists() or out_path.stat().st_size < min_size:
        sz = out_path.stat().st_size if out_path.exists() else 0
        out_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"fetch failed for {url} — got {sz}B (need ≥{min_size}B), HTTP={http_code}"
        )
    return out_path.stat().st_size


def find_pdf_link(handle_id: str) -> str | None:
    """Find the best English PDF bitstream link on an IndiaCode handle page.

    IndiaCode hosts both English and Hindi PDFs with the same handle. Their
    naming convention is loose but recognisable: English files start with
    'a' or 'A' (e.g. `aA1908-05.pdf`, `A1963-36.pdf`); Hindi files start with
    'h' or 'H' (e.g. `H2007-06.pdf`). When that's ambiguous we fall back to
    link text and language hints. This scored picker handles all three.
    """
    handle_url = f"https://www.indiacode.nic.in/handle/123456789/{handle_id}"
    html = fetch_text(handle_url)
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[int, str]] = []
    for a in soup.find_all("a", href=re.compile(r"/bitstream/.*\.pdf$", re.I)):
        # IndiaCode HTML often has leading whitespace in href values
        # (e.g. ' /bitstream/...'); a naked concat with the host yields a
        # malformed URL "https://www.indiacode.nic.in /bitstream/..." that
        # curl returns HTTP 000 for. Strip defensively.
        href = a["href"].strip()
        text = a.get_text(strip=True).lower()
        fname = href.rsplit("/", 1)[-1].lower()
        score = 0
        # Strongest signal: explicit language hint in link text
        if "english" in text or "(eng)" in text:
            score += 100
        if any(w in text for w in ("hindi", "हिंदी", "हिन्दी", "(hin)")):
            score -= 100
        # Filename convention: 'a' prefix = English, 'h' prefix = Hindi
        if fname.startswith(("a",)):
            score += 20
        if fname.startswith(("h",)):
            score -= 20
        # Path-level hint
        if "eng" in href.lower():
            score += 5
        # 'the_' prefix is a "consolidated" English version (often best)
        if fname.startswith("the_"):
            score += 30
        candidates.append((score, href))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


def load_env(p: str = ".env") -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / p).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def resolve_pdf(entry: dict[str, Any]) -> tuple[Path, str, str]:
    """Resolve an entry to (local_pdf_path, source_url, handle_url).

    handle_url is empty for off-IndiaCode entries.
    """
    slug = entry["slug"]
    raw_dir = ROOT / "data" / "raw" / "acts"
    raw_dir.mkdir(parents=True, exist_ok=True)
    min_size = entry.get("min_size", 30_000)

    # Pattern 1: already-cached PDF
    if "cached_pdf" in entry:
        local = ROOT / entry["cached_pdf"]
        if not local.exists():
            raise FileNotFoundError(f"{slug}: cached_pdf missing: {local}")
        sz = local.stat().st_size
        if sz < min_size:
            raise RuntimeError(f"{slug}: cached_pdf only {sz}B (need ≥{min_size}B)")
        return local, f"file://{local}", ""

    # Pattern 2: direct PDF URL override (off-IndiaCode)
    if "pdf_url" in entry:
        pdf_url = entry["pdf_url"]
        fname = Path(pdf_url.split("?")[0]).name or f"{slug}.pdf"
        local = raw_dir / f"{slug}__{fname}"
        if not local.exists() or local.stat().st_size < min_size:
            sz = fetch_bytes(pdf_url, local, min_size=min_size)
            print(f"  ↓ {slug}: {sz/1024:.0f} KB (direct URL)")
        else:
            print(f"  ✓ {slug}: cached ({local.stat().st_size/1024:.0f} KB)")
        return local, pdf_url, ""

    # Pattern 3: IndiaCode handle
    handle_id = entry["handle_id"]
    handle_url = f"https://www.indiacode.nic.in/handle/123456789/{handle_id}"
    pdf_rel = find_pdf_link(handle_id)
    if not pdf_rel:
        raise RuntimeError(f"{slug}: no PDF link at handle h={handle_id}")
    pdf_url = (pdf_rel if pdf_rel.startswith("http")
               else "https://www.indiacode.nic.in" + pdf_rel)
    pdf_name = Path(pdf_rel.split("?")[0]).name
    local = raw_dir / f"{slug}__{pdf_name}"
    if not local.exists() or local.stat().st_size < min_size:
        sz = fetch_bytes(pdf_url, local, min_size=min_size)
        print(f"  ↓ {slug}: {sz/1024:.0f} KB (h={handle_id})")
    else:
        print(f"  ✓ {slug}: cached ({local.stat().st_size/1024:.0f} KB)")
    return local, pdf_url, handle_url


async def main() -> None:
    env = load_env()
    out_jsonl = ROOT / "data" / "processed" / "acts.jsonl"

    print(f"=== P0 batch — {len(P0)} acts ===\n")

    # ---- Step 1: resolve + parse all PDFs ---------------------------
    print("Step 1: resolve + extract + redact")
    new_rows: list[dict[str, Any]] = []
    for entry in P0:
        slug = entry["slug"]
        try:
            local, src_url, handle_url = resolve_pdf(entry)
        except Exception as e:
            print(f"  ✗ {slug}: resolve failed — {e}")
            continue
        try:
            pdf_bytes = local.read_bytes()
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            n_pages = doc.page_count
            text = "\n\n".join(p.get_text("text") for p in doc)
            doc.close()
        except Exception as e:
            print(f"  ✗ {slug}: PDF parse failed — {e}")
            continue
        red = redact(text)
        new_rows.append({
            "slug": slug,
            "title": entry["title"],
            "handle_id": entry.get("handle_id", ""),
            "handle_url": handle_url,
            "pdf_url": src_url,
            "pdf_local": str(local),
            "pdf_pages": n_pages,
            "pdf_bytes": len(pdf_bytes),
            "text_chars": len(red.text),
            "text_sha256": hashlib.sha256(red.text.encode("utf-8")).hexdigest()[:16],
            "pii_hits": len([h for h in red.hits if h.confidence > 0]),
            "text": red.text,
            "subject_area_hint": entry.get("subject_area"),
            "as_at": entry.get("as_at"),
        })
        print(f"  ✓ {slug}: pages={n_pages}, chars={len(red.text):,}")
        if "handle_id" in entry:
            time.sleep(1.0)  # be polite to IndiaCode

    if not new_rows:
        print("\nNo acts could be resolved.")
        return

    # Append to acts.jsonl (idempotent: dedup on slug at the end)
    print(f"\n  appended {len(new_rows)} new rows to {out_jsonl}")
    with out_jsonl.open("a") as f:
        for r in new_rows:
            f.write(json.dumps({k: v for k, v in r.items()
                                if k != "text"}, ensure_ascii=False) + "\n")

    # ---- Step 2: chunk all texts ------------------------------------
    print("\nStep 2: chunk")
    all_chunks: list[tuple[dict, Any]] = []
    for r in new_rows:
        # Pass act_title so the chunker prepends "<Act Title>, Section <N>"
        # to every section chunk's text — fixes the 5-agent-confirmed root
        # cause where bare-act chunks lost to SC judgments at BM25, dense
        # AND rerank because chunk text alone never contained the Act's
        # name or section reference. See packages/chunking/act.py docstring.
        chunks = list(chunk_act(r["slug"], r["text"], act_title=r["title"]))
        all_chunks.extend((r, c) for c in chunks)
        print(f"  {r['slug']:42s}  {len(chunks):>4d} chunks  ({r['pdf_pages']} pages)")
    print(f"  TOTAL: {len(all_chunks)} chunks")

    # ---- Step 3: embed (dense only — sparse via backfill) ----------
    print("\nStep 3: embed (bge-m3 on MPS, dense-only)")
    t0 = time.time()
    model = SentenceTransformer("BAAI/bge-m3", device="mps")
    model.max_seq_length = 512
    print(f"  model loaded in {time.time()-t0:.1f}s")

    texts = [c.text for _, c in all_chunks]
    t0 = time.time()
    embeddings = model.encode(
        texts, batch_size=16, show_progress_bar=False,
        normalize_embeddings=True, convert_to_numpy=True,
    )
    elapsed = time.time() - t0
    print(f"  embedded {len(texts)} chunks in {elapsed:.0f}s "
          f"({len(texts)/max(elapsed,1):.1f} emb/s)")

    # ---- Step 4: insert into postgres -------------------------------
    print("\nStep 4: insert into postgres")
    conn = await asyncpg.connect(
        host="localhost", port=int(env["POSTGRES_HOST_PORT"]),
        database=env["POSTGRES_DB"], user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )

    by_slug: dict[str, tuple[dict, list]] = {}
    for r, c in all_chunks:
        by_slug.setdefault(r["slug"], (r, []))[1].append(c)

    inserted_total = 0
    skipped_total = 0
    new_docs = 0
    reused_docs = 0
    for slug, (meta, chunks) in by_slug.items():
        # Idempotency: skip if document exists AND has chunks; reuse if orphan
        existing = await conn.fetchrow(
            """SELECT d.id,
                      (SELECT COUNT(*) FROM chunks c WHERE c.document_id = d.id) AS n_chunks
               FROM documents d WHERE d.doc_id = $1""",
            slug,
        )
        if existing and existing["n_chunks"] > 0:
            print(f"  - {slug}: already has {existing['n_chunks']} chunks — skipping")
            skipped_total += len(chunks)
            continue

        # Resolve/create source
        url_for_src = meta["handle_url"] or meta["pdf_url"]
        url_hash = hashlib.sha256(url_for_src.encode()).hexdigest()
        src_id = await conn.fetchval(
            """INSERT INTO sources (source_type, origin, url,
                                    canonical_url_hash, metadata)
               VALUES ('bare_act', $1, $2, $3, $4)
               ON CONFLICT (canonical_url_hash) DO UPDATE
                 SET source_type = EXCLUDED.source_type
               RETURNING id""",
            "indiacode" if meta["handle_url"] else "direct",
            url_for_src, url_hash,
            json.dumps({"slug": slug, "handle_id": meta.get("handle_id", "")}),
        )

        # Subject area: explicit hint > inferred from text
        subject = meta.get("subject_area_hint")
        if not subject:
            subject = infer_subject_area(meta["text"], title=meta["title"])

        # Statute year (best-effort from slug suffix)
        slug_year = slug.rsplit("-", 1)[-1]
        statute_year = int(slug_year) if slug_year.isdigit() else None

        # Use entry-provided as_at, else fall back to first chunk's as_at
        as_at = meta.get("as_at")
        if as_at is None and chunks:
            as_at = chunks[0].as_at

        if existing and existing["n_chunks"] == 0:
            # Orphan: reuse the row, update title/subject in case they changed
            doc_pk = existing["id"]
            await conn.execute(
                """UPDATE documents
                   SET title = $1, statute_short = $2, statute_year = $3,
                       as_at = $4, subject_area = $5,
                       metadata = jsonb_set(metadata,
                                            '{handle_id}',
                                            to_jsonb($6::text), true)
                   WHERE id = $7""",
                meta["title"], meta["title"], statute_year,
                as_at, subject, meta.get("handle_id", ""), doc_pk,
            )
            print(f"  ⚠ {slug}: reusing orphan doc_pk={doc_pk}")
            reused_docs += 1
        else:
            doc_pk = await conn.fetchval(
                """INSERT INTO documents (source_id, doc_id, title, statute_short,
                                          statute_year, as_at, subject_area, metadata)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                   RETURNING id""",
                src_id, slug, meta["title"], meta["title"],
                statute_year, as_at, subject,
                json.dumps({"handle_id": meta.get("handle_id", "")}),
            )
            new_docs += 1

        # Find embeddings for this slug's chunks
        global_indices = [
            i for i, (rr, _) in enumerate(all_chunks) if rr["slug"] == slug
        ]
        # Build chunk→global-index map for fast lookup
        chunk_to_global: dict[int, int] = {}
        for gi in global_indices:
            chunk_to_global[id(all_chunks[gi][1])] = gi

        seen_anchors: set[str] = set()
        inserted = 0
        for c in chunks:
            if c.anchor in seen_anchors:
                continue
            seen_anchors.add(c.anchor)
            gi = chunk_to_global.get(id(c))
            if gi is None:
                continue
            emb = embeddings[gi].astype(np.float32)
            emb_str = "[" + ",".join(f"{x:.7f}" for x in emb) + "]"
            await conn.execute(
                """
                INSERT INTO chunks (document_id, source_type, subject_area,
                                    anchor, token_count, text, embedding,
                                    chunk_strategy, as_at, metadata)
                VALUES ($1, 'bare_act', $2, $3, $4, $5, $6::halfvec, $7, $8, $9)
                ON CONFLICT (document_id, anchor, as_at) DO NOTHING
                """,
                doc_pk, subject, c.anchor, c.token_count, c.text, emb_str,
                c.chunk_strategy.value, c.as_at,
                json.dumps(c.metadata),
            )
            inserted += 1
        inserted_total += inserted
        print(f"  ✓ {slug}: inserted {inserted} chunks (subject={subject})")

    await conn.close()
    print(f"\n=== Done ===")
    print(f"  new documents     : {new_docs}")
    print(f"  reused orphan docs: {reused_docs}")
    print(f"  chunks inserted   : {inserted_total}")
    print(f"  chunks skipped    : {skipped_total} (already in DB)")
    print(f"  Note: sparse vectors will populate as the backfill script runs")
    print(f"        (filters on embedding_sparse IS NULL).")


if __name__ == "__main__":
    asyncio.run(main())
