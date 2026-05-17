#!/usr/bin/env python3
"""Background data-gathering: archive raw PDFs to MinIO + pull older SC years +
hunt missing Central Acts from alternative sources.

Designed to run alongside the foreground API + retrieval work without
contending for MPS (no embedding here — just fetch / extract / redact / archive).

Priorities (executed in order, each phase resumable):
  Phase 1: Archive existing raw PDFs / tars to MinIO `raw` bucket
  Phase 2: Pull older SC years from Rahul1872 (2018, 2019, then 2010-2017)
  Phase 3: Retry missing Central Acts (Indian Contract 1872, IPC, CrPC,
           Indian Evidence Act 1872) via alternative sources

Output:
  data/processed/sc/year=YYYY.jsonl   (new years, ready for bulk_ingest_sc.py)
  data/processed/acts.jsonl           (appended rows for newly-resolved acts)
  data/raw/sc/year=YYYY.tar           (mirrored from HF cache)
  minio:raw/sc/, minio:raw/acts/      (durable archive)
  data/processed/gather.log           (structured progress log)

Idempotent: skips work already done. Safe to ctrl-C and re-run.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
import sys
import tarfile
import time
from datetime import datetime
from pathlib import Path

import pymupdf
from bs4 import BeautifulSoup
from huggingface_hub import hf_hub_download
from minio import Minio
from minio.error import S3Error

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "packages"))
from ingest.adapters.base import infer_subject_area  # noqa: E402
from ingest.normalize.redact import redact, sanitize_for_db  # noqa: E402

LOG_PATH = ROOT / "data" / "processed" / "gather.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# Configuration ---------------------------------------------------------------

# SC: Rahul1872 covers 1950-2025; we already have 2020-2024. Pull recent
# upstream years first (constitutional-bench landmarks live mostly 2010+).
SC_YEAR_PRIORITY = [2019, 2018, 2017, 2016, 2015, 2014, 2013, 2012, 2011, 2010,
                    2009, 2008, 2007, 2006, 2005, 2004, 2003, 2002, 2001, 2000]

# Missing Central Acts — these failed via IndiaCode in earlier attempts.
# Try multiple sources / handles per act. Sources documented per attempt.
MISSING_ACTS = [
    {
        "slug": "indian-contract-1872",
        "title": "The Indian Contract Act, 1872",
        "search_terms": ["Indian Contract Act, 1872", "Contract Act 1872"],
        # Known to lack a PDF at IndiaCode handle 12845. Try fresh searches
        # + fall back to legislative.gov.in / archive.org if needed.
    },
    {
        "slug": "ipc-1860",
        "title": "The Indian Penal Code, 1860",
        "search_terms": ["Indian Penal Code, 1860", "IPC 1860"],
    },
    {
        "slug": "crpc-1973",
        "title": "The Code of Criminal Procedure, 1973",
        "search_terms": ["Code of Criminal Procedure, 1973", "CrPC 1973"],
    },
    {
        "slug": "indian-evidence-act-1872",
        "title": "The Indian Evidence Act, 1872",
        "search_terms": ["Indian Evidence Act, 1872", "Evidence Act 1872"],
    },
]

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
CURL_HEADERS = [
    "-A", UA,
    "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "-H", "Accept-Language: en-US,en;q=0.5",
    "-H", "Accept-Encoding: gzip, deflate, br",
]
CENTRAL_COLLECTION = "123456789/1362"
RAHUL_DATASET = "Rahul1872/Indian-Supreme-Court-Judgments"


# Logging ---------------------------------------------------------------------

def log(msg: str, *, phase: str = "") -> None:
    stamp = datetime.utcnow().strftime("%H:%M:%S")
    prefix = f"[{stamp}]" + (f" [{phase}]" if phase else "")
    line = f"{prefix} {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a") as f:
        f.write(line + "\n")


# Env -------------------------------------------------------------------------

def load_env(p: str = ".env") -> dict:
    out = {}
    for line in (ROOT / p).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


# MinIO client ----------------------------------------------------------------

def minio_client(env: dict) -> Minio:
    endpoint = f"localhost:{env['MINIO_HOST_PORT']}"
    return Minio(
        endpoint,
        access_key=env["MINIO_ROOT_USER"],
        secret_key=env["MINIO_ROOT_PASSWORD"],
        secure=False,
    )


def minio_put_idempotent(client: Minio, bucket: str, key: str, local_path: Path) -> bool:
    """PUT a local file to MinIO unless object already exists with same size + etag.

    Returns True if uploaded, False if skipped (already present).
    """
    try:
        stat = client.stat_object(bucket, key)
        if stat.size == local_path.stat().st_size:
            return False
    except S3Error:
        pass  # object doesn't exist; upload
    client.fput_object(bucket, key, str(local_path))
    return True


# Phase 1: archive existing raw to MinIO --------------------------------------

def phase_1_archive(client: Minio, bucket: str) -> None:
    """Mirror local raw PDFs and SC tars into the MinIO `raw` bucket."""
    log("phase 1: archive raw PDFs / tars to MinIO", phase="archive")
    uploaded = 0
    skipped = 0

    # Acts
    acts_dir = ROOT / "data" / "raw" / "acts"
    if acts_dir.exists():
        for pdf in sorted(acts_dir.glob("*.pdf")):
            key = f"acts/{pdf.name}"
            if minio_put_idempotent(client, bucket, key, pdf):
                log(f"  ↑ {key} ({pdf.stat().st_size/1024:.0f} KB)", phase="archive")
                uploaded += 1
            else:
                skipped += 1

    # SC tars from HF cache. Walk the snapshots dir.
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub" / "datasets--Rahul1872--Indian-Supreme-Court-Judgments"
    if hf_cache.exists():
        for tar in hf_cache.rglob("english.tar"):
            year_match = re.search(r"year=(\d{4})", str(tar))
            if not year_match:
                continue
            year = year_match.group(1)
            key = f"sc/year={year}/english.tar"
            try:
                size_mb = tar.stat().st_size / 1024 / 1024
                if minio_put_idempotent(client, bucket, key, tar):
                    log(f"  ↑ {key} ({size_mb:.1f} MB)", phase="archive")
                    uploaded += 1
                else:
                    skipped += 1
            except FileNotFoundError:
                continue

    log(f"phase 1 done: {uploaded} uploaded, {skipped} already present", phase="archive")


# Phase 2: pull older SC years ------------------------------------------------

def phase_2_older_sc(client: Minio, bucket: str) -> None:
    """For each priority year not already on disk, download tar + metadata,
    extract PDFs, run redactor, and write a JSONL identical in shape to the
    existing data/processed/sc/year=YYYY.jsonl files."""
    log("phase 2: pull older SC years from Rahul1872", phase="sc")

    sc_dir = ROOT / "data" / "processed" / "sc"
    sc_dir.mkdir(parents=True, exist_ok=True)

    import pyarrow.parquet as pq

    for year in SC_YEAR_PRIORITY:
        out_path = sc_dir / f"year={year}.jsonl"
        if out_path.exists() and out_path.stat().st_size > 1000:
            log(f"  {year}: already on disk ({out_path.stat().st_size/1024/1024:.1f} MB), skipping", phase="sc")
            continue

        log(f"  {year}: downloading...", phase="sc")
        try:
            tar_path = hf_hub_download(
                RAHUL_DATASET, f"data/tar/year={year}/english/english.tar", repo_type="dataset",
            )
            parquet_path = hf_hub_download(
                RAHUL_DATASET, f"metadata/parquet/year={year}/metadata.parquet", repo_type="dataset",
            )
        except Exception as e:
            log(f"  {year}: download failed ({e})", phase="sc")
            continue

        # Archive the tar to MinIO
        try:
            key = f"sc/year={year}/english.tar"
            if minio_put_idempotent(client, bucket, key, Path(tar_path)):
                log(f"    ↑ archived to minio:{bucket}/{key}", phase="sc")
        except Exception as e:
            log(f"    warn: minio archive failed ({e})", phase="sc")

        # Load metadata
        try:
            meta_rows = pq.ParquetFile(parquet_path).read_row_group(0).to_pylist()
            meta_by_path = {r["path"]: r for r in meta_rows if r.get("path")}
        except Exception as e:
            log(f"  {year}: metadata read failed ({e})", phase="sc")
            continue

        # Walk tar → JSONL
        t0 = time.time()
        counts = {"ok": 0, "empty_text": 0, "pdf_error": 0}
        subject_dist: dict[str, int] = {}
        with tarfile.open(tar_path, "r") as tar, out_path.open("w") as fh:
            for m in tar:
                if not m.isfile() or not m.name.endswith(".pdf"):
                    continue
                stem = m.name.removesuffix("_EN.pdf").removesuffix(".pdf")
                meta = meta_by_path.get(stem, {})
                f = tar.extractfile(m)
                if f is None:
                    counts["pdf_error"] += 1
                    continue
                pdf_bytes = f.read()
                try:
                    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
                    n_pages = doc.page_count
                    text = "\n\n".join(p.get_text("text") for p in doc)
                    doc.close()
                except Exception:
                    counts["pdf_error"] += 1
                    continue
                if not text.strip():
                    counts["empty_text"] += 1
                    continue

                # Sanitize then redact
                text = sanitize_for_db(text)
                red = redact(text)
                # infer_subject_area now spans slice + 8 "other" categories so
                # almost no judgment is left without a tag. Real "(unknown)"
                # signals a parse problem or extreme edge case worth surfacing.
                subj = infer_subject_area(red.text)
                subject_dist[subj or "(unknown)"] = subject_dist.get(subj or "(unknown)", 0) + 1

                row = {
                    "filename": m.name, "path_stem": stem,
                    "title": meta.get("title", ""), "petitioner": meta.get("petitioner", ""),
                    "respondent": meta.get("respondent", ""), "citation": meta.get("citation", ""),
                    "case_id": meta.get("case_id", ""), "cnr": meta.get("cnr", ""),
                    "decision_date": meta.get("decision_date", ""), "judge": meta.get("judge", ""),
                    "nc_display": meta.get("nc_display", ""), "court": "SC", "year": year,
                    "subject_area": subj, "case_type": red.case_type.value,
                    "pii_hits": len([h for h in red.hits if h.confidence > 0]),
                    "pii_suspicious": red.suspicious,
                    "pdf_pages": n_pages, "pdf_bytes": len(pdf_bytes),
                    "text_chars": len(red.text),
                    "text_sha256": hashlib.sha256(red.text.encode("utf-8")).hexdigest()[:16],
                    "text": red.text,
                }
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                counts["ok"] += 1

        elapsed = time.time() - t0
        top_subj = sorted(subject_dist.items(), key=lambda x: -x[1])[:5]
        log(
            f"  {year}: {counts['ok']} judgments processed in {elapsed:.0f}s "
            f"(errors: pdf={counts['pdf_error']}, empty={counts['empty_text']}); "
            f"top subjects: {top_subj}",
            phase="sc",
        )

    log("phase 2 done", phase="sc")


# Phase 3: missing Central Acts ----------------------------------------------

def search_indiacode(query: str) -> list[dict]:
    """Return all handle candidates for a query."""
    url = f"https://www.indiacode.nic.in/simple-search?query={query.replace(' ', '+')}&searchTypes=metadata_name&Search=Search"
    r = subprocess.run(
        ["curl", "-sS", "-L", "--compressed", "--max-time", "25", *CURL_HEADERS, url],
        capture_output=True, text=True, timeout=35,
    )
    soup = BeautifulSoup(r.stdout, "html.parser")
    out = []
    for tr in soup.select("table.table tr, table.miscTable tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        a = tr.find("a", href=re.compile(r"/handle/\d+/\d+"))
        if a and len(cells) >= 3:
            href = a["href"]
            hid = href.split("?")[0].rsplit("/", 1)[-1]
            m = re.search(r"col=(\d+/\d+)", href)
            col = m.group(1) if m else ""
            out.append({"handle_id": hid, "collection": col,
                        "date": cells[0], "act_no": cells[1] if len(cells) > 1 else "",
                        "title": cells[2] if len(cells) > 2 else ""})
    return out


def fetch_pdf_link(handle_id: str) -> str | None:
    handle_url = f"https://www.indiacode.nic.in/handle/123456789/{handle_id}"
    r = subprocess.run(
        ["curl", "-sS", "-L", "--compressed", "--max-time", "25", *CURL_HEADERS, handle_url],
        capture_output=True, text=True, timeout=35,
    )
    soup = BeautifulSoup(r.stdout, "html.parser")
    for a in soup.find_all("a", href=re.compile(r"/bitstream/.*\.pdf$", re.I)):
        href = a["href"]
        text = a.get_text(strip=True)
        if any(x in text.lower() for x in ("hindi", "bengali", "tamil", "gujarati", "marathi", "kannada", "telugu")):
            continue
        return href
    return None


def download_pdf(url: str, out_path: Path) -> int | None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["curl", "-sS", "-L", "--compressed", "--max-time", "60", *CURL_HEADERS, "-o", str(out_path), url],
        capture_output=True, timeout=70,
    )
    if not out_path.exists() or out_path.stat().st_size < 5000:
        out_path.unlink(missing_ok=True)
        return None
    return out_path.stat().st_size


def is_meaningful_act_text(text: str, *, expected_title: str | None = None) -> bool:
    """Cheap sanity gate for downloaded act PDFs.

    Requirements:
      1. Length ≥ 2000 chars (rule out empty / nearly-empty PDFs).
      2. Contains an Indian-Act front-matter marker.
      3. ASCII letter ratio in the first 3000 chars ≥ 0.95 (rule out OCR-garbled
         PDFs and Hindi/Bengali scans — those drop to ~0.75 or lower).
      4. If `expected_title` is given, the document's actual short title
         (the first occurrence of "THE <title>") must match. This catches
         IndiaCode handles that link to *adjacent* acts with similar names
         (e.g. "Commercial Documents Evidence Act" returned for "Indian
         Evidence Act" query).
    """
    if len(text) < 2000:
        return False
    head = text[:5000]
    if not any(marker in head for marker in (
        "ARRANGEMENT OF SECTIONS", "ACT NO.", "Short title", "extends to",
    )):
        return False

    # Reject garbled OCR (Hindi/Bengali mixed with English). We measure
    # the fraction of *letter* characters (excluding whitespace and digits)
    # that are ASCII — pure English text scores 1.0; OCR'd Hindi/Bengali
    # interleaved with English drops well below 0.90.
    sample = text[:3000]
    letters = [c for c in sample if c.isalpha()]
    if letters:
        ascii_ratio = sum(1 for c in letters if c.isascii()) / len(letters)
        if ascii_ratio < 0.90:
            return False

    # Reject Bills outright — we want enacted Acts, not bills under
    # consideration. IndiaCode does sometimes return bill PDFs.
    if re.search(r"\bBILL,?\s*\d{4}\b", head, re.IGNORECASE):
        return False

    # Title check: the PDF's own "THE <title> ACT, <year>" line must overlap
    # with the expected query
    if expected_title:
        m = re.search(r"THE\s+([A-Z][A-Z ,\-&/()]+ACT(?:\s*,?\s*\d{4})?)", head)
        if not m:
            # No "THE … ACT" header at all → suspicious. Reject when we have
            # an expected title to compare against.
            return False
        actual = m.group(1).upper()
        # Take significant words from expected (strip stop words)
        expected_tokens = {
            w.upper() for w in re.findall(r"[A-Za-z]+", expected_title)
            if w.upper() not in {"THE", "OF", "AND", "ACT", "FOR", "TO", "IN", "A"}
        }
        if expected_tokens:
            actual_tokens = set(re.findall(r"[A-Z]+", actual))
            overlap = expected_tokens & actual_tokens
            # Require ≥ 60% of expected meaningful tokens in the actual
            # title. Loose enough for "Code of Criminal Procedure" vs the
            # abbreviated "CrPC"; strict enough to catch "Commercial
            # Documents Evidence Act 1939" returned for "Indian Evidence
            # Act 1872" query.
            if len(overlap) / len(expected_tokens) < 0.6:
                return False
    return True


def phase_3_missing_acts(client: Minio, bucket: str, env: dict) -> None:
    """For each missing act, try multiple IndiaCode handles. If they all fail,
    log the gap so the user can supply an alternative source later."""
    log("phase 3: missing Central Acts", phase="acts")

    existing_slugs: set[str] = set()
    jsonl_path = ROOT / "data" / "processed" / "acts.jsonl"
    if jsonl_path.exists():
        with jsonl_path.open() as f:
            for line in f:
                try:
                    existing_slugs.add(json.loads(line)["slug"])
                except Exception:
                    continue

    new_rows = []
    for act in MISSING_ACTS:
        slug = act["slug"]
        if slug in existing_slugs:
            log(f"  {slug}: already in acts.jsonl, skipping", phase="acts")
            continue

        log(f"  {slug}: searching {len(act['search_terms'])} term(s)...", phase="acts")
        candidates: list[dict] = []
        for term in act["search_terms"]:
            candidates.extend(search_indiacode(term))
            time.sleep(1.5)
        # Prefer Central Acts collection; then by oldest date (the original act)
        central = [c for c in candidates if c["collection"] == CENTRAL_COLLECTION]
        ordered = central or candidates

        chosen = None
        for cand in ordered:
            pdf_link = fetch_pdf_link(cand["handle_id"])
            if not pdf_link:
                continue
            pdf_url = "https://www.indiacode.nic.in" + pdf_link
            local = ROOT / "data" / "raw" / "acts" / f"{slug}__h{cand['handle_id']}.pdf"
            sz = download_pdf(pdf_url, local)
            if not sz:
                continue
            # Quality check
            try:
                doc = pymupdf.open(str(local))
                text = "\n".join(p.get_text("text") for p in doc)
                doc.close()
            except Exception:
                local.unlink(missing_ok=True)
                continue
            text = sanitize_for_db(text)
            if not is_meaningful_act_text(text, expected_title=act["title"]):
                log(f"    handle {cand['handle_id']}: PDF rejected (failed title/quality "
                    f"check for {act['title']!r}), trying next", phase="acts")
                continue

            # Got a good one
            chosen = {"cand": cand, "pdf": local, "text": text}
            log(f"  ✓ {slug}: handle={cand['handle_id']} col={cand['collection']} {sz/1024:.0f} KB", phase="acts")
            break
            time.sleep(1)

        if not chosen:
            log(f"  ✗ {slug}: no working IndiaCode source found. "
                f"NEEDS: alternative source (legislative.gov.in / archive.org / manual)", phase="acts")
            continue

        red = redact(chosen["text"])
        new_rows.append({
            "slug": slug,
            "handle_id": chosen["cand"]["handle_id"],
            "handle_url": f"https://www.indiacode.nic.in/handle/123456789/{chosen['cand']['handle_id']}",
            "pdf_url": chosen["cand"].get("pdf_url", ""),
            "title": act["title"],
            "act_no": chosen["cand"].get("act_no", ""),
            "enactment_date": chosen["cand"].get("date", ""),
            "pdf_local": str(chosen["pdf"]),
            "pdf_pages": pymupdf.open(str(chosen["pdf"])).page_count,
            "pdf_bytes": chosen["pdf"].stat().st_size,
            "text_chars": len(red.text),
            "text_sha256": hashlib.sha256(red.text.encode("utf-8")).hexdigest()[:16],
            "pii_hits": len([h for h in red.hits if h.confidence > 0]),
            "text": red.text,
        })

        # Archive raw to MinIO
        try:
            minio_put_idempotent(client, bucket, f"acts/{chosen['pdf'].name}", chosen["pdf"])
        except Exception as e:
            log(f"    warn: minio archive failed ({e})", phase="acts")

    if new_rows:
        with jsonl_path.open("a") as f:
            for r in new_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        log(f"appended {len(new_rows)} new acts to {jsonl_path.name}", phase="acts")
        log("→ run scripts/reingest_acts.py to load these into postgres", phase="acts")
    else:
        log("phase 3: no new acts added (all sources failed or already present)", phase="acts")


# Main ------------------------------------------------------------------------

def main():
    env = load_env()
    bucket = env.get("MINIO_BUCKET_RAW", "raw")

    LOG_PATH.write_text("")  # truncate
    log("=== gather_more_data starting ===")
    log(f"  MinIO endpoint: localhost:{env['MINIO_HOST_PORT']} bucket={bucket}")

    client = minio_client(env)
    try:
        # Ensure bucket exists (it should, from minio-init in compose)
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            log(f"  created bucket {bucket}")
    except Exception as e:
        log(f"  warn: bucket setup failed ({e}); MinIO uploads will fail")

    t0 = time.time()
    phase_1_archive(client, bucket)
    phase_2_older_sc(client, bucket)
    phase_3_missing_acts(client, bucket, env)

    log(f"=== gather_more_data done in {time.time()-t0:.0f}s ===")


if __name__ == "__main__":
    main()
