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

Verification state is document-scoped. A source may back multiple documents,
so an audit can only change the documents whose chunks were actually compared.

Two modes:
  --full        verify every source (slow; can take an hour)
  --sample N    sample N sources per tier (default 20 per tier)
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

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
OFFICIAL_PDF_ORIGINS = {
    "indiacode",
    "rbi",
    "mha_gazette",
    "legislative_department",
    "tihar_prisons_delhi",
    "socialjustice.gov.in",
}


def local_official_pdf_path(url: str) -> Path | None:
    """Allow only repository-owned cached official PDFs for local audits."""
    if not url.startswith("file://"):
        return None
    path = Path(unquote(url.removeprefix("file://"))).resolve()
    allowed_root = (ROOT / "data" / "raw" / "acts").resolve()
    try:
        path.relative_to(allowed_root)
    except ValueError:
        return None
    return path if path.is_file() and path.suffix.lower() == ".pdf" else None


def is_verifiable_official_source(source_row: dict) -> bool:
    return (
        source_row["origin"] in OFFICIAL_PDF_ORIGINS
        or local_official_pdf_path(source_row["url"]) is not None
    )


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


def audit_persistence_rows(audit_rows: list[dict]) -> list[tuple]:
    rows: list[tuple] = []
    for row in audit_rows:
        target_verdicts = row.get("target_verdicts") or [
            {
                "document_id": document_id,
                "chunk_id": chunk_id,
                "text_match": row["text_match"],
                "text_similarity": row["text_similarity"],
                "verification_pass": row.get("verification_pass"),
            }
            for document_id, chunk_id in (
                row.get("audit_targets") or [(None, None)]
            )
        ]
        for verdict in target_verdicts:
            rows.append((
                row["source_id"], row["source_url"], verdict["document_id"],
                verdict["chunk_id"], row["sha_match"], verdict["text_match"],
                verdict["text_similarity"], row["refetch_status"],
                row["refetch_size"], row["refetch_pages"], row["refetch_hash"],
                row["notes"],
            ))
    return rows


def verification_scope_updates(
    audit_rows: list[dict],
) -> tuple[list[int], list[int], list[int], list[int]]:
    def ids(scope: str, passed: bool, position: int) -> list[int]:
        matched: set[int] = set()
        for row in audit_rows:
            if row.get("scope", "document") != scope:
                continue
            target_verdicts = row.get("target_verdicts")
            if target_verdicts:
                key = "document_id" if position == 0 else "chunk_id"
                matched.update(
                    verdict[key]
                    for verdict in target_verdicts
                    if verdict.get("verification_pass") == passed
                    and verdict.get(key) is not None
                )
                continue
            if row.get("verification_pass") == passed:
                matched.update(
                    target[position]
                    for target in row.get("audit_targets", [])
                    if target[position] is not None
                )
        return sorted(matched)

    return (
        ids("document", True, 0),
        ids("document", False, 0),
        ids("chunk", True, 1),
        ids("chunk", False, 1),
    )


async def apply_verification_updates(conn, audit_rows: list[dict]) -> None:
    """Apply only the document/chunk scopes actually compared by the audit.

    A legacy Act is audited at document scope by comparing the complete set of
    its non-quarantined chunks with the selected official artifact. Retrieval,
    however, gates on ``chunks.provenance_verified``. Propagating a passed
    document verdict to those same chunks is therefore part of the document
    promotion contract. A failed document clears every non-quarantined chunk
    so an earlier promotion cannot survive a later drift finding.

    Registry-mapped authorities remain chunk-scoped and are updated only by
    their per-chunk verdicts from ``verification_scope_updates``.
    """
    (
        passed_document_ids,
        failed_document_ids,
        passed_chunk_ids,
        failed_chunk_ids,
    ) = verification_scope_updates(audit_rows)
    # A document and its chunks are one promotion unit. Keep every update in
    # one transaction so a failed chunk update cannot leave a stale document
    # or chunk marked as production-eligible.
    async with conn.transaction():
        if passed_document_ids:
            await conn.execute("""
                UPDATE documents
                SET provenance_verified = true, provenance_verified_at = now()
                WHERE id = ANY($1::bigint[])
            """, passed_document_ids)
            await conn.execute("""
                UPDATE chunks
                SET provenance_verified = true, provenance_verified_at = now()
                WHERE document_id = ANY($1::bigint[])
                  AND NOT quarantined
                  AND NOT EXISTS (
                      SELECT 1 FROM document_authorities da
                      WHERE da.chunk_id = chunks.id
                  )
            """, passed_document_ids)
        if failed_document_ids:
            await conn.execute("""
                UPDATE documents
                SET provenance_verified = false, provenance_verified_at = NULL
                WHERE id = ANY($1::bigint[])
            """, failed_document_ids)
            await conn.execute("""
                UPDATE chunks
                SET provenance_verified = false, provenance_verified_at = NULL
                WHERE document_id = ANY($1::bigint[])
                  AND NOT EXISTS (
                      SELECT 1 FROM document_authorities da
                      WHERE da.chunk_id = chunks.id
                  )
            """, failed_document_ids)
        if passed_chunk_ids:
            await conn.execute("""
                UPDATE chunks
                SET provenance_verified = true, provenance_verified_at = now()
                WHERE id = ANY($1::bigint[]) AND NOT quarantined
            """, passed_chunk_ids)
        if failed_chunk_ids:
            await conn.execute("""
                UPDATE chunks
                SET provenance_verified = false, provenance_verified_at = NULL
                WHERE id = ANY($1::bigint[])
            """, failed_chunk_ids)


# --- Re-fetch helpers ------------------------------------------------------

def india_code_pdf_links(html: str) -> list[str]:
    """Return distinct PDF bitstream links from an India Code handle page.

    India Code pages are not consistently formatted: some have whitespace
    after the opening quote and some use single quotes. Keep discovery
    tolerant, but restrict it to the India Code bitstream path so an
    unrelated link cannot become an authority artifact.
    """
    links = re.findall(
        r"href\s*=\s*[\"']\s*(/bitstream/\d+/\d+/\d+/[^\"']+?\.pdf)",
        html,
        flags=re.IGNORECASE,
    )
    out: list[str] = []
    seen: set[str] = set()
    for link in links:
        link = link.strip()
        if link not in seen:
            seen.add(link)
            out.append(link)
    return out


def _download_pdf(url: str) -> tuple[bytes, str, int] | tuple[None, str, int]:
    """Download one PDF URL and reject missing/non-PDF-sized responses."""
    with tempfile.NamedTemporaryFile(
        prefix="law-rag-verify-", suffix=".pdf", delete=False
    ) as temp:
        out_path = Path(temp.name)
    try:
        try:
            r = subprocess.run(
                ["curl", "-sS", "-L", "--compressed", "--max-time", "60",
                 "-o", str(out_path), "-w", "%{http_code}",
                 *CURL_HEADERS, url],
                capture_output=True, text=True, timeout=70,
            )
        except subprocess.TimeoutExpired:
            return None, "timeout", 0
        http_code = (r.stdout or "").strip()
        if not out_path.exists() or out_path.stat().st_size < 1000:
            return None, f"http_{http_code}", int(http_code) if http_code.isdigit() else 0
        data = out_path.read_bytes()
        return data, "ok", int(http_code) if http_code.isdigit() else 200
    finally:
        out_path.unlink(missing_ok=True)


def refetch_act_pdfs(
    url: str,
) -> list[tuple[bytes, str, int, str]]:
    """Re-download all candidate act PDFs and retain their resolved URLs.

    A handle page can contain English and Hindi artifacts, or an obsolete
    duplicate. Returning all candidates lets the audit layer choose by the
    stored hash/text rather than trusting page order.
    """
    candidate_urls = [url]
    if "/handle/" in url:
        links: list[str] = []
        discovered: list[str] = []
        # India Code occasionally serves an incomplete handle page during a
        # rate-limited request. Retry discovery and accumulate candidates;
        # artifact downloads stay bounded and fail closed after three misses.
        for attempt in range(3):
            try:
                r = subprocess.run(
                    ["curl", "-sS", "-L", "--compressed", "--max-time", "20", *CURL_HEADERS, url],
                    capture_output=True, text=True, timeout=30,
                )
            except subprocess.TimeoutExpired:
                r = None
            links = india_code_pdf_links(r.stdout) if r is not None else []
            for link in links:
                if link not in discovered:
                    discovered.append(link)
            if attempt < 2:
                time.sleep(0.5)
        if not discovered:
            return []
        candidate_urls = [
            "https://www.indiacode.nic.in" + link for link in discovered
        ]

    results = []
    for candidate_url in candidate_urls:
        for attempt in range(3):
            data, status, http_code = _download_pdf(candidate_url)
            if data is not None:
                results.append((data, status, http_code, candidate_url))
                break
            if attempt < 2:
                time.sleep(0.5)
    return results


def refetch_act_pdf(url: str) -> tuple[bytes, str, int] | tuple[None, str, int]:
    """Backward-compatible single-artifact fetch helper.

    New audits use :func:`refetch_act_pdfs` so handle-page candidates can be
    scored against the stored authority text.
    """
    results = refetch_act_pdfs(url)
    if not results:
        return None, "no_pdf_link" if "/handle/" in url else "download_failed", 0
    data, status, http_code, _ = results[0]
    return data, status, http_code


HF_CACHE_ROOT = Path.home() / ".cache" / "huggingface" / "hub"
RAHUL_DATASET_CACHE = (
    HF_CACHE_ROOT / "datasets--Rahul1872--Indian-Supreme-Court-Judgments" / "snapshots"
)


def refetch_sc_year_tar(year: int) -> Path | None:
    """Resolve the local HF cache path for a year's SC tar. Returns None
    if the dataset isn't cached locally (script never ran before)."""
    if not RAHUL_DATASET_CACHE.exists():
        return None
    for snapshot_dir in RAHUL_DATASET_CACHE.iterdir():
        tar = snapshot_dir / "data" / "tar" / f"year={year}" / "english" / "english.tar"
        if tar.exists():
            return tar
    return None


def extract_sc_pdf_from_tar(tar_path: Path, judgment_filename: str) -> tuple[bytes, str] | tuple[None, str]:
    """Open the year tar and extract a specific PDF by filename. The Rahul1872
    dataset names files like `2024_10_108_125_EN.pdf` which matches the eSCR
    URL pattern (year_volume_startpage_endpage_lang.pdf).
    """
    import tarfile
    if not tar_path.exists():
        return None, "tar_missing"
    try:
        with tarfile.open(tar_path, "r") as tar:
            for m in tar:
                if m.name == judgment_filename or m.name.endswith(f"/{judgment_filename}"):
                    f = tar.extractfile(m)
                    if f:
                        return f.read(), "ok"
        return None, "filename_not_in_tar"
    except Exception as e:
        return None, f"tar_error: {e}"


def refetch_sc_canonical_spot(case_id: str) -> tuple[bytes, str, int] | tuple[None, str, int]:
    """Best-effort canonical check via scr.sci.gov.in or judgments.ecourts.gov.in.

    Both portals are reachable from outside India (unlike digiscr.sci.gov.in
    which is geo-fenced). They have CAPTCHA on the search form, so direct
    URL-based fetch is rate-limited and brittle. We return a stub for now;
    full canonical verification needs Playwright + CAPTCHA solving OR an
    India-region machine where direct eSCR access works.
    """
    return None, "canonical_spot_needs_playwright", 0


_INGESTED_SECTION_PREFIX_RE = re.compile(
    r"^\s*(?P<title>[^.\n]{2,200}),\s+Section\s+[0-9A-Za-z()/-]+\s*(?:\n+|$)",
    flags=re.IGNORECASE,
)


def _strip_ingested_section_prefix(
    text: str,
    *,
    expected_title: str | None = None,
) -> str:
    """Remove only the exact document title prefix added by the chunker."""
    match = _INGESTED_SECTION_PREFIX_RE.match(text)
    if not match or not expected_title:
        return text
    prefix_title = match.group("title").strip()

    def normalize_title(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    if normalize_title(prefix_title) != normalize_title(expected_title):
        return text
    return text[match.end():]


def text_similarity(
    stored: str,
    refetched: str,
    *,
    expected_title: str | None = None,
) -> float:
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

    s, r = ngrams(
        _strip_ingested_section_prefix(stored, expected_title=expected_title)
    ), ngrams(refetched)
    if not s:
        return 0.0
    overlap = len(s & r)
    return overlap / len(s)


def document_scope_verdict(
    document_chunks: list[dict],
    refetched_text: str,
    hash_pass: bool,
    *,
    threshold: float = 0.90,
    expected_title: str | None = None,
) -> dict:
    """Require every stored live chunk to match the official artifact.

    Document-level promotion is convenient for legacy Acts, but a single
    corrupted chunk must not be hidden by aggregate document similarity.
    """
    similarities = [
        text_similarity(
            chunk["text"],
            refetched_text,
            expected_title=expected_title,
        )
        for chunk in document_chunks
    ]
    text_match = bool(similarities) and all(
        similarity >= threshold for similarity in similarities
    )
    return {
        "text_similarity": min(similarities, default=0.0),
        "text_match": text_match,
        "verification_pass": bool(text_match and hash_pass),
        "chunk_similarities": similarities,
    }


def exact_sha_match(expected: str | None, actual: str) -> bool:
    """Only a pinned source hash can satisfy the artifact identity gate."""
    return bool(expected) and expected == actual


def select_act_candidate(candidates: list[dict], expected_sha: str | None) -> dict:
    """Choose an artifact deterministically, preferring a pinned exact hash."""
    exact_hashes = [
        candidate for candidate in candidates
        if exact_sha_match(expected_sha, candidate["sha"])
    ]
    return max(exact_hashes or candidates, key=lambda candidate: candidate["score"])


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
        "audit_targets": [],
        "scope": "document",
        "verification_pass": None,
        "target_verdicts": [],
    }
    tier = source_row["provenance_tier"]
    origin = source_row["origin"]

    # Registry-mapped authorities are audited at the exact document/chunk
    # projection. Legacy sources are audited per document over the complete
    # non-quarantined chunk set; a concatenated sample must never allow one
    # document to mask another.
    doc_chunks: dict[int, list] = {}
    mapped_targets = await conn.fetch("""
        SELECT da.document_id, da.chunk_id
        FROM document_authorities da
        WHERE da.source_id = $1
        ORDER BY da.document_id, da.chunk_id
    """, source_row["id"])
    if mapped_targets:
        out["scope"] = "chunk"
        chunks = await conn.fetch("""
            SELECT c.id AS chunk_id, c.text, c.document_id, d.title AS document_title
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.id = ANY($1::bigint[]) AND NOT c.quarantined
            ORDER BY c.id
        """, [target["chunk_id"] for target in mapped_targets])
    else:
        chunks = await conn.fetch("""
            SELECT c.id AS chunk_id, c.text, c.document_id, d.title AS document_title
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE d.source_id = $1 AND NOT c.quarantined
            ORDER BY c.id
        """, source_row["id"])
        for chunk in chunks:
            doc_chunks.setdefault(chunk["document_id"], []).append(chunk)
    if not chunks:
        out["refetch_status"] = "no_chunks_stored"
        return out
    if mapped_targets:
        out["audit_targets"] = [
            (chunk["document_id"], chunk["chunk_id"])
            for chunk in chunks
        ]
        stored_text = " ".join(c["text"] for c in chunks)
    else:
        out["audit_targets"] = [
            (document_id, None)
            for document_id in sorted(doc_chunks)
        ]
        stored_text = ""

    # Re-fetch
    if is_verifiable_official_source(source_row) and refetch_acts:
        candidates = refetch_act_pdfs(source_row["url"])
        out["refetch_status"] = "ok" if candidates else (
            "no_pdf_link" if "/handle/" in source_row["url"] else "download_failed"
        )
        if not candidates:
            return out

        # Select the artifact after extraction. Handle pages may publish
        # multiple language/duplicate PDFs, so page order is not evidence.
        candidate_scores = []
        for data, status, http_code, candidate_url in candidates:
            text, pages = extract_pdf_text(data)
            if text is None:
                continue
            sha = hashlib.sha256(data).hexdigest()
            if mapped_targets:
                score = min(
                    (
                        text_similarity(
                            chunk["text"],
                            text,
                            expected_title=chunk["document_title"],
                        )
                        for chunk in chunks
                    ),
                    default=0.0,
                )
            else:
                score = min(
                    (
                        document_scope_verdict(
                            document_chunks,
                            text,
                            True,
                            expected_title=document_chunks[0]["document_title"],
                        )["text_similarity"]
                        for document_chunks in doc_chunks.values()
                    ),
                    default=0.0,
                )
            candidate_scores.append({
                "data": data,
                "text": text,
                "pages": pages,
                "sha": sha,
                "url": candidate_url,
                "score": score,
                "sha_match": exact_sha_match(source_row.get("raw_sha256"), sha),
            })
        if not candidate_scores:
            out["refetch_status"] = "parse_failed"
            return out

        selected = select_act_candidate(
            candidate_scores, source_row.get("raw_sha256")
        )
        data = selected["data"]
        text = selected["text"]
        out["refetch_size"] = len(data)
        out["refetch_hash"] = selected["sha"]
        out["sha_match"] = selected["sha_match"] is True
        out["refetch_pages"] = selected["pages"]
        # A text match proves extraction consistency, not artifact identity.
        # Missing a pinned source hash is diagnostic-only and can never
        # promote a document or registry chunk into production retrieval.
        hash_pass = out["sha_match"] is True
        if mapped_targets:
            out["target_verdicts"] = []
            for chunk in chunks:
                sim = text_similarity(
                    chunk["text"],
                    text,
                    expected_title=chunk["document_title"],
                )
                text_match = sim >= 0.90
                out["target_verdicts"].append({
                    "document_id": chunk["document_id"],
                    "chunk_id": chunk["chunk_id"],
                    "text_similarity": sim,
                    "text_match": text_match,
                    "verification_pass": bool(text_match and hash_pass),
                })
            similarities = [
                verdict["text_similarity"]
                for verdict in out["target_verdicts"]
            ]
            out["text_similarity"] = min(similarities)
            out["text_match"] = all(
                verdict["text_match"]
                for verdict in out["target_verdicts"]
            )
            out["verification_pass"] = all(
                verdict["verification_pass"]
                for verdict in out["target_verdicts"]
            )
            out["notes"] = (
                f"per_chunk_similarities={similarities}; "
                f"stored_chunks={len(chunks)}"
            )
        else:
            out["target_verdicts"] = []
            for document_id, document_chunks in sorted(doc_chunks.items()):
                document_verdict = document_scope_verdict(
                    document_chunks,
                    text,
                    hash_pass,
                    expected_title=document_chunks[0]["document_title"],
                )
                out["target_verdicts"].append({
                    "document_id": document_id,
                    "chunk_id": None,
                    "text_similarity": document_verdict["text_similarity"],
                    "text_match": document_verdict["text_match"],
                    "verification_pass": document_verdict["verification_pass"],
                })
            similarities = [
                verdict["text_similarity"]
                for verdict in out["target_verdicts"]
            ]
            out["text_similarity"] = min(similarities, default=0.0)
            out["text_match"] = all(
                verdict["text_match"]
                for verdict in out["target_verdicts"]
            )
            out["verification_pass"] = all(
                verdict["verification_pass"]
                for verdict in out["target_verdicts"]
            )
            out["notes"] = (
                f"per_document_similarities={similarities}; "
                f"stored_documents={len(doc_chunks)}; "
                f"stored_chunks={len(chunks)}"
            )
        out["notes"] = (
            f"{out['notes']}; candidates={len(candidate_scores)}; "
            f"selected={selected['url']} score={selected['score']:.3f}"
        )
    elif origin.startswith("hf:") and "Rahul1872" in origin:
        # SC via HF Rahul1872. Extraction-consistency check: re-extract the
        # original PDF from the local HF tar cache and compare against the
        # stored chunks. This proves the whole pipeline (PDF → PyMuPDF →
        # redact → chunk → DB) is deterministic and the DB hasn't drifted
        # from the source file we ingested.
        #
        # True upstream verification against digiscr.sci.gov.in (the
        # canonical Govt source) is geo-fenced and needs an India-region
        # runner (PLAN §13.4 productization).
        #
        # The filename → case_id mapping isn't in documents.metadata; we
        # bridge via the year's JSONL file (which carries `filename` +
        # `case_id` in every row).
        year_match = re.search(r"year=(\d{4})", source_row["url"])
        if not year_match:
            out["refetch_status"] = "no_year_in_url"
            return out
        year = int(year_match.group(1))
        tar_path = refetch_sc_year_tar(year)
        if tar_path is None:
            out["refetch_status"] = "hf_cache_missing"
            out["notes"] = f"no local cache for year={year}; pull tar first"
            return out

        # Build filename ↔ case_id mapping from the JSONL we wrote at ingest
        jsonl_path = ROOT / "data" / "processed" / "sc" / f"year={year}.jsonl"
        if not jsonl_path.exists():
            out["refetch_status"] = "jsonl_missing"
            out["notes"] = f"no {jsonl_path.name} on disk; can't map filenames"
            return out
        caseid_to_filename: dict[str, str] = {}
        with jsonl_path.open() as f:
            for line in f:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                cid = (row.get("case_id") or "").strip()
                fn = row.get("filename")
                if cid and fn:
                    caseid_to_filename[cid] = fn

        # Sample 5 random judgments from this source's chunks. Larger n
        # smooths out transient I/O issues (e.g. tar being concurrently
        # written by background ingest).
        sample_docs = await conn.fetch("""
            SELECT d.id, d.metadata, d.title
            FROM documents d
            WHERE d.source_id = $1
            ORDER BY random()
            LIMIT 5
        """, source_row["id"])
        out["audit_targets"] = [(doc["id"], None) for doc in sample_docs]
        out["scope"] = "document"
        per_doc_results: list[dict] = []
        for doc in sample_docs:
            meta = doc["metadata"] if isinstance(doc["metadata"], dict) else (
                json.loads(doc["metadata"]) if doc["metadata"] else {}
            )
            case_id = (meta.get("case_id") or "").strip()
            filename = caseid_to_filename.get(case_id)
            if not filename:
                per_doc_results.append({
                    "document_id": doc["id"],
                    "text_similarity": 0.0,
                    "text_match": False,
                    "verification_pass": False,
                    "status": f"no_filename_for_case_id={case_id!r}",
                })
                continue
            pdf_bytes, status = extract_sc_pdf_from_tar(tar_path, filename)
            if pdf_bytes is None:
                per_doc_results.append({
                    "document_id": doc["id"],
                    "text_similarity": 0.0,
                    "text_match": False,
                    "verification_pass": False,
                    "status": status,
                })
                continue
            text, _ = extract_pdf_text(pdf_bytes)
            if text is None:
                per_doc_results.append({
                    "document_id": doc["id"],
                    "text_similarity": 0.0,
                    "text_match": False,
                    "verification_pass": False,
                    "status": "extract_failed",
                })
                continue
            # Compare every live chunk in this sampled judgment independently;
            # aggregate document similarity must not hide one corrupted chunk.
            doc_chunks = await conn.fetch(
                "SELECT text FROM chunks WHERE document_id=$1 AND NOT quarantined ORDER BY id",
                doc["id"],
            )
            verdict = document_scope_verdict(
                list(doc_chunks),
                text,
                False,
                threshold=0.85,
                expected_title=doc["title"],
            )
            per_doc_results.append({
                "document_id": doc["id"],
                "text_similarity": verdict["text_similarity"],
                "text_match": verdict["text_match"],
                "verification_pass": verdict["verification_pass"],
                "chunk_count": len(doc_chunks),
                "chunk_similarities": verdict["chunk_similarities"],
                "status": "ok",
            })

        if per_doc_results and any(item["status"] == "ok" for item in per_doc_results):
            out["target_verdicts"] = [
                {
                    "document_id": item["document_id"],
                    "chunk_id": None,
                    "text_similarity": item["text_similarity"],
                    "text_match": item["text_match"],
                    "verification_pass": item["verification_pass"],
                }
                for item in per_doc_results
            ]
            out["text_similarity"] = min(
                item["text_similarity"] for item in per_doc_results
            )
            out["text_match"] = all(
                item["text_match"] for item in per_doc_results
            )
            # HF extraction consistency is diagnostic only: without a
            # canonical publisher artifact/hash it cannot promote production
            # provenance, even when every sampled chunk matches the cache.
            out["verification_pass"] = False
            out["refetch_status"] = "ok"
            out["notes"] = (
                f"extraction-consistency over {len(per_doc_results)} sampled "
                "documents with per-live-chunk matching; "
                f"per-doc: {per_doc_results}"
            )
        else:
            out["refetch_status"] = "no_docs_extractable"
            out["notes"] = f"per-doc: {per_doc_results}"
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
    parser.add_argument("--source-id", type=int,
                        help="audit one exact source id")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit nonzero unless every requested source passes verification",
    )
    args = parser.parse_args()

    env = load_env()
    conn = await asyncpg.connect(
        host="localhost", port=int(env["POSTGRES_HOST_PORT"]),
        database=env["POSTGRES_DB"], user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )

    log("=== verify_provenance starting ===")

    # Pick sources to audit
    if args.source_id is not None:
        sources = await conn.fetch("""
            SELECT id, source_type, origin, url, raw_sha256, provenance_tier
            FROM sources WHERE id = $1
        """, args.source_id)
        if not sources:
            raise SystemExit(f"unknown source id: {args.source_id}")
    elif args.full:
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
    verified_count = 0
    text_match_only_count = 0
    failed_count = 0
    deferred_count = 0
    audit_rows = []
    for i, src in enumerate(sources, 1):
        log(f"[{i}/{len(sources)}] {src['origin']} {src['url'][:60]}…  tier={src['provenance_tier']}")
        verdict = await audit_source(conn, dict(src), refetch_acts=refetch_acts)
        audit_rows.append(verdict)
        # A text match alone is useful diagnostic evidence, but it is not a
        # provenance verification pass when the official file has drifted.
        if verdict.get("verification_pass") is True:
            verified_count += 1
        elif verdict["text_match"] is True:
            text_match_only_count += 1
        elif verdict["text_match"] is False:
            failed_count += 1
        else:
            deferred_count += 1
        if i % 5 == 0:
            log(
                "  progress: "
                f"verified={verified_count} text_only={text_match_only_count} "
                f"failed={failed_count} deferred={deferred_count}"
            )
        if refetch_acts and is_verifiable_official_source(dict(src)):
            time.sleep(1.5)  # polite rate-limit

    # Persist audit rows
    if audit_rows:
        persistence_rows = audit_persistence_rows(audit_rows)
        await conn.executemany("""
            INSERT INTO provenance_audit (
                source_id, source_url, document_id, chunk_id,
                sha_match, text_match, text_similarity,
                refetch_status, refetch_size, refetch_pages, refetch_hash, notes
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        """, persistence_rows)
        log(f"persisted {len(persistence_rows)} document-scoped audit rows")

    # Verification is document-scoped. A source-level verdict must never mark
    # every document attached to a shared source as verified. A passed legacy
    # document also promotes its compared non-quarantined chunks because the
    # production retrieval gate is chunk-scoped.
    (
        passed_document_ids,
        failed_document_ids,
        passed_chunk_ids,
        failed_chunk_ids,
    ) = verification_scope_updates(audit_rows)
    await apply_verification_updates(conn, audit_rows)
    if passed_document_ids:
        log(f"marked {len(passed_document_ids)} audited documents as verified")
    if failed_document_ids:
        log(f"cleared verification on {len(failed_document_ids)} drifted documents")
    if passed_document_ids:
        log(
            f"marked non-quarantined chunks for {len(passed_document_ids)} "
            "verified documents"
        )
    if failed_document_ids:
        log(
            f"cleared non-quarantined chunks for {len(failed_document_ids)} "
            "drifted documents"
        )
    if passed_chunk_ids:
        log(f"marked {len(passed_chunk_ids)} audited authority chunks as verified")
    if failed_chunk_ids:
        log(f"cleared verification on {len(failed_chunk_ids)} drifted authority chunks")

    log(f"\n=== Summary ===")
    log(f"  verified: {verified_count}")
    log(f"  text only:{text_match_only_count}  (hash or another verification gate failed)")
    log(f"  failed:   {failed_count}")
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
    if args.strict and (
        verified_count != len(sources)
        or text_match_only_count
        or failed_count
        or deferred_count
    ):
        raise SystemExit(2)


if __name__ == "__main__":
    asyncio.run(main())
