"""Supreme Court adapter — Rahul1872/Indian-Supreme-Court-Judgments on HF.

This is the primary SC corpus source for the slice. The dataset is CC-BY-4.0
and covers 1950–2025, year-partitioned, with English text in tar archives plus
per-year parquet metadata.

File layout in the HF dataset:
    metadata/parquet/year=YYYY/metadata.parquet
    metadata/zip/year=YYYY/metadata.zip          (alt JSONL packaging)
    data/tar/year=YYYY/english/english.tar       (raw judgment text files)
    data/tar/year=YYYY/english/english.index.json
    data/tar/year=YYYY/regional/regional.tar     (Hindi/regional translations)

Provenance status: **unverified** — must pass §10.1 50-doc sample inspection
before any non-localhost deployment. Sample inspection happens via
`make pii-eval` once the eval set is built.

Note on subject-area filtering: the upstream dataset has no subject tagging.
This adapter uses `infer_subject_area` (in adapters/base.py) on the parsed
text to populate `documents.subject_area`. Coverage is imperfect; the eval
set must include both well-tagged and ambiguous queries.
"""
from __future__ import annotations

import io
import json
import logging
import tarfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from ingest.adapters.base import (
    Adapter,
    AdapterQuery,
    RawDoc,
    SourceType,
    infer_subject_area,
)

logger = logging.getLogger(__name__)

# Slice cutoff: last 5 years per PLAN §1.1.
DEFAULT_YEAR_FROM = 2019
DEFAULT_YEAR_TO = 2025


class SCRahul1872Adapter:
    """Stream SC judgments from the Rahul1872/Indian-Supreme-Court-Judgments
    Hugging Face dataset.

    Usage:
        adapter = SCRahul1872Adapter()
        async for doc in adapter.iter_docs(AdapterQuery(year_from=2020, year_to=2024, limit=100)):
            ...

    Imports `datasets` lazily so this module is importable even in
    environments where the HF stack isn't installed (e.g., the test runner
    that only exercises the PII redactor).
    """

    name = "sc_hf_rahul1872"
    source_type = SourceType.SC_JUDGMENT
    dataset_id = "Rahul1872/Indian-Supreme-Court-Judgments"

    def __init__(self, *, cache_dir: str | Path | None = None) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else None

    async def iter_docs(self, query: AdapterQuery) -> AsyncIterator[RawDoc]:
        year_from = query.year_from or DEFAULT_YEAR_FROM
        year_to = query.year_to or DEFAULT_YEAR_TO
        limit = query.limit

        yielded = 0
        # Defer HF imports so this file is importable without the heavy ML stack.
        try:
            from huggingface_hub import hf_hub_download
        except ImportError as e:
            raise ImportError(
                "`huggingface_hub` is required for the SC HF adapter. "
                "Install with: `uv pip install huggingface_hub pyarrow`"
            ) from e

        for year in range(year_from, year_to + 1):
            logger.info("sc_hf: fetching year=%d", year)
            metadata = self._fetch_year_metadata(year, hf_hub_download)
            if not metadata:
                logger.warning("sc_hf: no metadata for year=%d", year)
                continue
            tar_path = self._fetch_year_tar(year, hf_hub_download)
            if tar_path is None:
                logger.warning("sc_hf: no tar for year=%d", year)
                continue

            async for doc in self._iter_year_docs(year, metadata, tar_path, query):
                yield doc
                yielded += 1
                if limit and yielded >= limit:
                    return

    def _fetch_year_metadata(self, year: int, hf_hub_download: Any) -> list[dict]:
        """Download per-year metadata parquet and return rows as dicts.

        Returns [] if the year is missing from the dataset (some early years
        may have no English judgments).
        """
        try:
            local = hf_hub_download(
                repo_id=self.dataset_id,
                filename=f"metadata/parquet/year={year}/metadata.parquet",
                repo_type="dataset",
                cache_dir=str(self.cache_dir) if self.cache_dir else None,
            )
        except Exception as e:
            logger.warning("sc_hf: could not fetch metadata parquet for year=%d: %s", year, e)
            return []

        try:
            import pyarrow.parquet as pq
        except ImportError as e:
            raise ImportError("`pyarrow` required for parquet parsing") from e

        table = pq.read_table(local)
        return table.to_pylist()

    def _fetch_year_tar(self, year: int, hf_hub_download: Any) -> Path | None:
        try:
            local = hf_hub_download(
                repo_id=self.dataset_id,
                filename=f"data/tar/year={year}/english/english.tar",
                repo_type="dataset",
                cache_dir=str(self.cache_dir) if self.cache_dir else None,
            )
            return Path(local)
        except Exception as e:
            logger.warning("sc_hf: could not fetch tar for year=%d: %s", year, e)
            return None

    async def _iter_year_docs(
        self,
        year: int,
        metadata: list[dict],
        tar_path: Path,
        query: AdapterQuery,
    ) -> AsyncIterator[RawDoc]:
        """Walk the year's tar archive, joining text with metadata rows."""
        metadata_by_key = {row.get("filename") or row.get("file_name") or row.get("id"): row
                           for row in metadata}

        with tarfile.open(tar_path, "r") as tar:
            for member in tar:
                if not member.isfile():
                    continue
                f = tar.extractfile(member)
                if f is None:
                    continue
                raw_bytes = f.read()
                try:
                    text = raw_bytes.decode("utf-8", errors="replace")
                except Exception:
                    continue

                # Pull metadata row first so the subject classifier has access
                # to the title (it's the strongest single signal — see
                # adapters/base.py infer_subject_area).
                key = Path(member.name).stem
                meta = metadata_by_key.get(key) or metadata_by_key.get(member.name) or {}

                # Subject-area filter (PLAN §1, §2.4 — slice covers common-public
                # acts only). Skip docs that don't match any subject area unless
                # the caller explicitly asked for everything.
                title_hint = (meta.get("title") or meta.get("case_name") or "")
                subject = infer_subject_area(text, title=title_hint)
                if query.subject_areas and subject not in (query.subject_areas or []):
                    continue

                # Synthesize canonical URL — this dataset doesn't always carry
                # an eSCR judgment_url, so we mint a stable one from year + filename.
                # Adapters that DO have the real URL should overwrite this.
                url = (meta.get("judgment_url") or meta.get("url")
                       or f"hf:{self.dataset_id}/year={year}/{member.name}")

                yield RawDoc(
                    source_type=SourceType.SC_JUDGMENT,
                    origin=f"hf:{self.dataset_id}",
                    url=url,
                    payload=raw_bytes,
                    content_type="text/plain",
                    metadata={
                        "year": year,
                        "subject_area": subject,
                        "filename": member.name,
                        "court": "SC",
                        **{k: v for k, v in meta.items() if v is not None},
                    },
                )


__all__ = ["DEFAULT_YEAR_FROM", "DEFAULT_YEAR_TO", "SCRahul1872Adapter"]
