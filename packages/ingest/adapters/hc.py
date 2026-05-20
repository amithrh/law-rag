"""High Court adapter — AWS Open Data Registry mirror of ecourts.gov.in.

Source: ``s3://indian-high-court-judgments`` (Registry of Open Data on AWS),
upstream maintained by https://github.com/vanga/indian-high-court-judgments
which crawls the official judgments.ecourts.gov.in portal on a quarterly
cadence and publishes:

  * raw PDFs            data/pdf/year=YYYY/court=N_M/bench=BENCH/<basename>.pdf
  * tar archives        data/tar/year=YYYY/court=N_M/bench=BENCH/data.tar
                        data/tar/year=YYYY/court=N_M/bench=BENCH/data.index.json
  * structured metadata metadata/parquet/year=YYYY/court=N_M/bench=BENCH/metadata.parquet
  * raw metadata JSON   metadata/json/year=YYYY/court=N_M/bench=BENCH/<basename>.json

Parquet schema (verified 2025-10-23 snapshot, see ``hc_probe_v2.json``):
    court_code: str        '7~26'
    title: str             'W.P.(C)/293/2024 of CHUKNOO SECURITIES ... Vs DY ...'
    description: str       full case-list line (1.4 kB-ish on average)
    judge: str             comma-separated bench
    pdf_link: str          'court/cnrorders/dhcdb/orders/<basename>.pdf'
    cnr: str               'DLHC010003812024'  — CNR is the canonical Govt id
    date_of_registration: str   'DD-MM-YYYY'
    decision_date: timestamp[ns]
    disposal_nature: str        often empty
    court: str                  'High Court of Delhi'
    raw_html: str               original case-list row HTML (provenance)
    pdf_exists: bool            warning: in the 2024 snapshot this is False
                                across the board; rely on HEAD on the S3 key
                                instead.

License: CC-BY-4.0. Anonymous read access — no AWS credentials required.

**Provenance**: every yielded RawDoc records both the S3 URL (where we
fetched it from) and the canonical ecourts CNR (so we can always link
back to the official Govt source). The S3 mirror is upstream-of-the-
official-portal; per the project's hard constraint that provenance
ends at a Govt URL, the canonical_url we mint is constructed from the
CNR. The mirror URL is preserved as metadata.

Why not scrape ecourts directly?
    judgments.ecourts.gov.in/pdfsearch/ requires solving a Securimage
    CAPTCHA (distorted-text PNG bound to PHPSESSID, refreshed per
    session). The project budget excludes paid CAPTCHA-solving APIs.
    OSS alternatives (Tesseract on Securimage output, Whisper on the
    audio variant) are technically possible but the open-data mirror
    eliminates the need entirely — it republishes the same PDFs from
    the same Govt source, with a quarterly lag that is well below the
    weekly-rebuild cadence we target.

Why not Playwright? Same reason. This adapter is `httpx`-only.
"""
from __future__ import annotations

import hashlib
import io
import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from ingest.adapters.base import (
    AdapterQuery,
    RawDoc,
    SourceType,
    infer_subject_area,
)

logger = logging.getLogger(__name__)

S3_BUCKET = "https://indian-high-court-judgments.s3.ap-south-1.amazonaws.com"
COURT_CODES_URL = (
    "https://raw.githubusercontent.com/vanga/indian-high-court-judgments/"
    "main/court-codes.json"
)
USER_AGENT = "Mozilla/5.0 (law-rag/hc-adapter; +pro-bono Indian legal RAG)"

# Slice default: last 2 years per PLAN §1.1 (HC is much larger than SC, so
# start narrower and broaden once retrieval quality is verified).
DEFAULT_YEAR_FROM = 2024
DEFAULT_YEAR_TO = 2025

# Throttle — be a polite citizen on the AWS bucket. 0.2s between requests
# means ~5 req/s, well below S3's 5500 req/s/prefix limit and well below
# anything that could be considered abusive of a public-good bucket.
DEFAULT_THROTTLE_S = 0.2

# When the S3 bucket returns 404 for an individual PDF (the parquet listed
# it but the upstream crawler didn't archive it), we count it as a
# soft-skip rather than a hard error — the parquet inventory drifts ahead
# of the PDF archive between quarterly rebuilds. If the soft-skip rate
# exceeds this, raise — likely the bucket has shifted layout.
MAX_PDF_404_RATIO = 0.30


class CaptchaRequiredError(RuntimeError):
    """Raised when a fallback portal returns a CAPTCHA challenge.

    This should never happen on the S3 path — surfacing it loudly here
    makes sure any silent path-switch to a CAPTCHA-gated portal in the
    future fails the pipeline rather than producing empty docs.
    """


class RateLimitedError(RuntimeError):
    """Raised on HTTP 429 from the S3 bucket or any fallback portal.

    The caller (`bulk_ingest_hc.py`) is expected to surface this and exit
    non-zero — we do NOT silently retry forever.
    """


# Bench code → conventional short name. The bucket nests benches under each
# court_code; we list them at runtime so this map is just for human-readable
# logs and the `bench` field in documents.
_BENCH_NAMES = {
    "dhcdb": "Delhi HC (Principal Bench)",
    "ahcbdb": "Allahabad HC (Principal Bench)",
    "ahcldb": "Allahabad HC (Lucknow Bench)",
    "bhcdb": "Bombay HC (Principal Bench)",
    "bhcabdb": "Bombay HC (Aurangabad Bench)",
    "bhcgodb": "Bombay HC (Goa Bench)",
    "bhcnadb": "Bombay HC (Nagpur Bench)",
    "khcdb": "Karnataka HC (Bengaluru Bench)",
    "khcdhdb": "Karnataka HC (Dharwad Bench)",
    "khcgudb": "Karnataka HC (Gulbarga Bench)",
    "chcdb": "Calcutta HC (Principal Bench)",
    "mhcdb": "Madras HC (Principal Bench)",
    "mhcmdb": "Madras HC (Madurai Bench)",
    "patnahcdb": "Patna HC (Principal Bench)",
    "patnahcucisdb94": "Patna HC (Common bench listing — see bucket)",
}


class HCEcourtsAdapter:
    """Stream HC judgments from the AWS Open Data Registry mirror.

    Usage (sync iteration over the async generator):

        adapter = HCEcourtsAdapter(courts=["7_26"])  # Delhi HC
        async for doc in adapter.iter_docs(AdapterQuery(year_from=2024, limit=5)):
            ...

    Per-doc envelope (`RawDoc`):
        source_type = HC_JUDGMENT
        origin      = 's3:indian-high-court-judgments'
        url         = the S3 object URL we fetched (provenance trail)
        payload     = PDF bytes
        content_type = 'application/pdf'
        metadata    = {court_code, court_name, bench, cnr, decision_date, ...,
                       canonical_ecourts_url (constructed from CNR)}
    """

    name = "hc_ecourts_opendata"
    source_type = SourceType.HC_JUDGMENT

    def __init__(
        self,
        *,
        courts: list[str] | None = None,
        throttle_s: float = DEFAULT_THROTTLE_S,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        # courts: list of court_code strings using underscore form (the S3
        # path style). e.g. ["7_26"] for Delhi HC, ["7_26", "27_1"] for Delhi + Bombay.
        # None → just Delhi HC for the MVP.
        self.courts = courts or ["7_26"]
        self.throttle_s = throttle_s
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        self._court_names: dict[str, str] | None = None
        self._pdf_404_count = 0
        self._pdf_fetch_count = 0

    async def __aenter__(self) -> "HCEcourtsAdapter":
        return self

    async def __aexit__(self, *exc_info) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _load_court_names(self) -> dict[str, str]:
        if self._court_names is not None:
            return self._court_names
        r = await self._client.get(COURT_CODES_URL)
        r.raise_for_status()
        raw = r.json()  # keys use "~" separator (e.g. "7~26")
        self._court_names = {k.replace("~", "_"): v for k, v in raw.items()}
        return self._court_names

    async def _list_keys(self, prefix: str) -> tuple[list[tuple[str, int]], list[str]]:
        """List S3 keys under a prefix; returns (keys, common_prefixes).

        Anonymous read uses the standard S3 REST GET-Bucket-V2 API; no
        signing required. We always use `delimiter=/` so deep listings
        come back as common-prefixes the caller can recurse on.
        """
        url = (
            f"{S3_BUCKET}/?list-type=2"
            f"&prefix={prefix}&delimiter=/&max-keys=1000"
        )
        r = await self._client.get(url)
        if r.status_code == 429:
            raise RateLimitedError(
                f"S3 returned 429 listing {prefix} — back off and retry later"
            )
        r.raise_for_status()
        # Strip the default xmlns so ElementTree paths are simple
        xml = re.sub(r'xmlns="[^"]+"', "", r.text)
        root = ET.fromstring(xml)
        keys = [
            (k.findtext("Key") or "", int(k.findtext("Size") or 0))
            for k in root.findall(".//Contents")
        ]
        prefixes = [p.text or "" for p in root.findall(".//CommonPrefixes/Prefix")]
        return keys, prefixes

    async def _list_benches(self, year: int, court_code: str) -> list[str]:
        prefix = f"metadata/parquet/year={year}/court={court_code}/"
        _, prefixes = await self._list_keys(prefix)
        # Extract bench=<name> from the prefix
        out = []
        for p in prefixes:
            m = re.search(r"bench=([^/]+)/?$", p)
            if m:
                out.append(m.group(1))
        return out

    async def _fetch_parquet(self, year: int, court_code: str, bench: str) -> Any:
        try:
            import pyarrow.parquet as pq
        except ImportError as e:
            raise ImportError(
                "pyarrow required for HC adapter; install with "
                "`uv pip install pyarrow`"
            ) from e
        url = (
            f"{S3_BUCKET}/metadata/parquet/year={year}"
            f"/court={court_code}/bench={bench}/metadata.parquet"
        )
        r = await self._client.get(url, timeout=httpx.Timeout(180.0))
        if r.status_code == 429:
            raise RateLimitedError(f"S3 429 on parquet {url}")
        if r.status_code == 404:
            logger.warning("hc: no parquet for year=%d court=%s bench=%s", year, court_code, bench)
            return None
        r.raise_for_status()
        return pq.read_table(io.BytesIO(r.content))

    async def _fetch_pdf(
        self, year: int, court_code: str, bench: str, pdf_link: str
    ) -> bytes | None:
        # pdf_link in the parquet is the full ecourts path
        # (e.g. court/cnrorders/dhcdb/orders/<basename>.pdf); for the S3
        # bucket layout the file is at data/pdf/year=YYYY/court=N_M/bench=B/<basename>.
        basename = Path(pdf_link).name
        url = (
            f"{S3_BUCKET}/data/pdf/year={year}"
            f"/court={court_code}/bench={bench}/{basename}"
        )
        self._pdf_fetch_count += 1
        r = await self._client.get(url, timeout=httpx.Timeout(120.0))
        if r.status_code == 429:
            raise RateLimitedError(f"S3 429 on pdf {url}")
        if r.status_code == 404:
            self._pdf_404_count += 1
            ratio = self._pdf_404_count / max(1, self._pdf_fetch_count)
            if self._pdf_fetch_count >= 20 and ratio > MAX_PDF_404_RATIO:
                raise RuntimeError(
                    f"PDF 404 rate {ratio:.0%} exceeds {MAX_PDF_404_RATIO:.0%} "
                    f"after {self._pdf_fetch_count} fetches — bucket layout "
                    "may have changed. Last URL: " + url
                )
            return None
        r.raise_for_status()
        # Sanity — make sure we got an actual PDF, not an HTML CAPTCHA page
        ctype = r.headers.get("content-type", "").lower()
        if "html" in ctype and b"captcha" in r.content[:4096].lower():
            raise CaptchaRequiredError(
                f"Got an HTML CAPTCHA page from what should be an S3 PDF: {url}"
            )
        if not r.content.startswith(b"%PDF"):
            # Some S3 keys are 0-byte placeholders — surface but skip
            logger.warning("hc: non-PDF content at %s (first bytes: %r)", url, r.content[:16])
            return None
        return r.content

    @staticmethod
    def _make_ecourts_canonical_url(cnr: str) -> str:
        """Construct the canonical Govt source URL from a CNR.

        The eCourts case-status portal accepts the 16-char CNR via
        ``services.ecourts.gov.in/ecourtindia_v6/cnr/<CNR>`` — this is the
        stable Govt deep-link. Provenance lineage:
            our DB -> CNR field -> services.ecourts.gov.in -> judgment PDF.
        """
        return f"https://services.ecourts.gov.in/ecourtindia_v6/?p=cnr_status/searchByCNR&cino={cnr}"

    async def iter_docs(self, query: AdapterQuery) -> AsyncIterator[RawDoc]:
        """Yield judgments matching `query`.

        AdapterQuery fields honored:
          year_from / year_to  — bucket partitions to walk
          courts               — list of court codes (overrides adapter init)
          limit                — cap on yielded docs
          subject_areas        — post-filter on inferred subject area
        """
        year_from = query.year_from or DEFAULT_YEAR_FROM
        year_to = query.year_to or DEFAULT_YEAR_TO
        # courts can be passed via query.courts (interpreted as court_codes for HC)
        court_codes = query.courts or self.courts
        limit = query.limit

        court_names = await self._load_court_names()
        yielded = 0

        for year in range(year_from, year_to + 1):
            for court_code in court_codes:
                if court_code not in court_names:
                    logger.warning("hc: unknown court_code %s — skipping", court_code)
                    continue
                benches = await self._list_benches(year, court_code)
                if not benches:
                    logger.info(
                        "hc: no benches for year=%d court=%s", year, court_code
                    )
                    continue
                for bench in benches:
                    table = await self._fetch_parquet(year, court_code, bench)
                    if table is None:
                        continue
                    logger.info(
                        "hc: year=%d court=%s bench=%s rows=%d",
                        year, court_code, bench, table.num_rows,
                    )
                    async for doc in self._iter_table(
                        table, year, court_code, bench, query
                    ):
                        yield doc
                        yielded += 1
                        if limit and yielded >= limit:
                            return

    async def _iter_table(
        self,
        table: Any,
        year: int,
        court_code: str,
        bench: str,
        query: AdapterQuery,
    ) -> AsyncIterator[RawDoc]:
        # Iterate as pylist for simplicity; the row count is in the tens of
        # thousands per bench-year so memory is fine.
        court_name = (await self._load_court_names())[court_code]
        import asyncio

        for row in table.to_pylist():
            pdf_link = row.get("pdf_link") or ""
            if not pdf_link:
                continue
            cnr = row.get("cnr") or ""
            # The S3 mirror's PDF
            pdf_bytes = await self._fetch_pdf(year, court_code, bench, pdf_link)
            if pdf_bytes is None:
                continue

            mirror_url = (
                f"{S3_BUCKET}/data/pdf/year={year}"
                f"/court={court_code}/bench={bench}/{Path(pdf_link).name}"
            )
            canonical_url = self._make_ecourts_canonical_url(cnr) if cnr else mirror_url

            metadata = {
                "court_code": court_code,
                "court": court_name,
                "court_short": _court_short(court_name),
                "bench_code": bench,
                "bench": _BENCH_NAMES.get(bench, bench),
                "year": year,
                "cnr": cnr,
                "title": row.get("title"),
                "description": row.get("description"),
                "judge": row.get("judge"),
                "decision_date": _to_isodate(row.get("decision_date")),
                "date_of_registration": row.get("date_of_registration"),
                "disposal_nature": row.get("disposal_nature"),
                "pdf_link": pdf_link,
                "mirror_url": mirror_url,
                "canonical_url": canonical_url,
                "license": "CC-BY-4.0",
            }
            if query.subject_areas:
                # Post-filter: we'd need to parse the PDF to infer subject,
                # which we do downstream (in bulk_ingest_hc). Skip the filter
                # here — the script calls infer_subject_area on the extracted
                # text and applies the same SLICE rules as SC ingest.
                pass

            yield RawDoc(
                source_type=SourceType.HC_JUDGMENT,
                origin="s3:indian-high-court-judgments",
                url=mirror_url,
                payload=pdf_bytes,
                content_type="application/pdf",
                metadata=metadata,
            )
            # Polite throttle
            if self.throttle_s:
                await asyncio.sleep(self.throttle_s)


def _to_isodate(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, str):
        # Try common formats; fall through to raw string if none match
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(v, fmt).date().isoformat()
            except ValueError:
                continue
        return v
    return str(v)


# Map full court names → 3-char shorts that fit in the DB.court column
# (matches the SC use of 'SC' as the short code).
_COURT_SHORT_MAP = {
    "High Court of Delhi": "DHC",
    "Bombay High Court": "BHC",
    "Calcutta High Court": "CHC",
    "Madras High Court": "MHC",
    "Allahabad High Court": "AHC",
    "Gauhati High Court": "GHC",
    "High Court of Karnataka": "KHC",
    "High Court of Kerala": "KEHC",
    "High Court of Punjab and Haryana": "PHHC",
    "High Court of Gujarat": "GUJHC",
    "High Court of Rajasthan": "RHC",
    "High Court of Madhya Pradesh": "MPHC",
    "Patna High Court": "PHC",
    "High Court of Orissa": "OHC",
    "High Court of Chhattisgarh": "CGHC",
    "High Court of Telangana": "TGHC",
    "High Court for State of Telangana": "TGHC",
    "High Court of Andhra Pradesh": "APHC",
    "High Court of Uttarakhand": "UHC",
    "High Court of Himachal Pradesh": "HPHC",
    "High Court of Jharkhand": "JHC",
    "High Court of Jammu and Kashmir": "JKHC",
    "High Court of Sikkim": "SHC",
    "High Court of Tripura": "TRHC",
    "High Court of Manipur": "MNHC",
    "High Court of Meghalaya": "MEHC",
}


def _court_short(court_name: str) -> str:
    return _COURT_SHORT_MAP.get(court_name, "HC")


__all__ = [
    "CaptchaRequiredError",
    "DEFAULT_YEAR_FROM",
    "DEFAULT_YEAR_TO",
    "HCEcourtsAdapter",
    "RateLimitedError",
]
