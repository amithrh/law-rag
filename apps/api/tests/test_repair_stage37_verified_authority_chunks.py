from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.repair_stage37_verified_authority_chunks as repair


def _spec(document_id: str, section_no: str):
    return next(
        spec
        for spec in repair.SPECS
        if spec.document_id == document_id and spec.section_no == section_no
    )


def test_msmed_promotion_specs_are_pinned_to_local_india_code_artifact():
    specs = [
        spec
        for spec in repair.SPECS
        if spec.document_id == "msmed-2006"
    ]

    assert [spec.section_no for spec in specs] == ["15", "16", "18"]
    assert all(spec.source_id == 342 for spec in specs)
    assert all(spec.local_artifact_path and spec.local_artifact_path.endswith(
        "data/raw/acts/msmed-2006__A2006-27.pdf"
    ) for spec in specs)
    assert all(len(spec.source_sha256) == 64 and spec.source_bytes == 242312 for spec in specs)
    assert all(len(spec.expected_text_sha256 or "") == 64 for spec in specs)


def test_sale_of_goods_promotion_specs_are_pinned_to_local_india_code_artifact():
    specs = [
        spec
        for spec in repair.SPECS
        if spec.document_id == "sale-of-goods-1930"
    ]

    assert [spec.section_no for spec in specs] == ["31", "32", "55", "56"]
    assert all(spec.source_id == 366 for spec in specs)
    assert all(spec.local_artifact_path and spec.local_artifact_path.endswith(
        "data/raw/acts/sale-of-goods-1930__193003.pdf"
    ) for spec in specs)
    assert all(len(spec.source_sha256) == 64 and spec.source_bytes == 377988 for spec in specs)
    assert all(len(spec.expected_text_sha256 or "") == 64 for spec in specs)


def test_high_value_specs_resolve_by_document_identity_and_pin_local_artifacts():
    expected_counts = {
        "aadhaar-2016": 1,
        "senior-citizens-2007": 4,
        "gratuity-1972": 3,
        "epf-1952": 4,
        "esi-1948": 4,
        "social-security-code-2020": 4,
        "bocw-1996": 5,
        "employees-compensation-1923": 3,
        "consumer-protection-2019": 2,
        "rfctlarr-2013": 3,
        "sarfaesi-2002": 2,
    }
    specs = [spec for spec in repair.SPECS if spec in repair._HIGH_VALUE_SPECS]

    assert len(specs) == sum(expected_counts.values())
    assert {spec.document_id for spec in specs} == set(expected_counts)
    for document_id, count in expected_counts.items():
        assert sum(spec.document_id == document_id for spec in specs) == count
    for spec in specs:
        assert spec.source_id is None
        assert spec.accepted_source_urls or spec.source_url.startswith(
            "https://www.indiacode.nic.in/bitstream/"
        )
        assert spec.local_artifact_path and spec.local_artifact_path.startswith(
            str(repair.ROOT / "data/raw/acts")
        )
        assert len(spec.source_sha256) == 64
        assert spec.source_bytes > 0
        assert len(spec.expected_text_sha256 or "") == 64
        assert spec.kind == "generic_act_section"


def test_every_projection_has_an_exact_text_hash():
    assert all(len(spec.expected_text_sha256 or "") == 64 for spec in repair.SPECS)


def test_projection_metadata_persists_exact_text_fingerprint():
    for spec in repair.SPECS:
        metadata = repair._projection_metadata(spec)
        assert metadata["canonical_artifact_sha256"] == spec.source_sha256
        assert metadata["canonical_text_sha256"] == spec.expected_text_sha256


class _CanonicalTargetConnection:
    def __init__(self, target):
        self.target = target
        self.executed = []

    async def fetch(self, _query, *_args):
        return [self.target]

    async def execute(self, _query, *args):
        self.executed.append(args)
        self.target["raw_bytes_size"] = args[0]
        self.target["metadata"].update(json.loads(args[1]))
        return "UPDATE 1"


@pytest.mark.asyncio
async def test_canonical_alias_reuse_backfills_null_size_even_with_matching_transition_metadata():
    spec = _spec("senior-citizens-2007", "4")
    predecessor = 74
    target = {
        "id": 298,
        "source_type": "bare_act",
        "origin": "indiacode",
        "url": spec.source_url,
        "canonical_url_hash": hashlib.sha256(spec.source_url.encode()).hexdigest(),
        "raw_sha256": spec.source_sha256,
        "raw_bytes_size": None,
        "provenance_tier": "canonical",
        "metadata": {
            "replaces_unverified_source_id": predecessor,
            "replaces_unverified_source_urls": list(spec.accepted_source_urls),
            "predecessor_content_verified": False,
            "source_transition": "independent_first_party_artifact_replacement",
        },
    }
    connection = _CanonicalTargetConnection(target)

    result = await repair._ensure_canonical_source(
        connection,
        spec,
        predecessor_source_id=predecessor,
    )
    target["metadata"].pop("reused_predecessor_source_ids")
    await repair._ensure_canonical_source(
        connection,
        spec,
        predecessor_source_id=298,
    )

    assert result == 298
    assert target["raw_bytes_size"] == spec.source_bytes
    assert target["metadata"]["reused_predecessor_source_id"] == predecessor
    assert target["metadata"]["reused_predecessor_source_ids"] == [74, 298]
    assert connection.executed


def test_high_value_manifest_titles_match_extracted_act_headings():
    for spec in repair._HIGH_VALUE_SPECS:
        pdf = Path(spec.local_artifact_path).read_bytes()
        text, _pages = repair.extract_pdf_text(pdf)
        matches = [
            chunk
            for chunk in repair.chunk_act(spec.document_id, text, act_title=spec.title)
            if str(chunk.metadata.get("section_no") or "") == spec.section_no
            and str(chunk.anchor).split("@")[0] == spec.anchor.split("@")[0]
        ]
        assert len(matches) == 1
        assert matches[0].metadata.get("section_title") == spec.section_title


def test_local_pinned_artifact_loader_rejects_hash_drift(tmp_path):
    source = tmp_path / "msmed.pdf"
    source.write_bytes(b"not-the-act")
    spec = _spec("msmed-2006", "15")
    spec = replace(spec, local_artifact_path=str(source))

    with pytest.raises(RuntimeError, match="local artifact hash/size mismatch"):
        repair._fetch_pinned_pdf(spec)


class _RunTransaction:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        self.connection.transaction_started = True
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.connection.transaction_rolled_back = exc is not None
        return False


class _RunConnection:
    def __init__(self):
        self.transaction_started = False
        self.transaction_rolled_back = False
        self.closed = False

    def transaction(self):
        return _RunTransaction(self)

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_high_value_run_scope_is_explicit_and_rolls_back_as_one_batch(monkeypatch):
    connection = _RunConnection()
    monkeypatch.setattr(
        repair,
        "get_settings",
        lambda: SimpleNamespace(resolved_database_url_host_side="dsn"),
    )

    async def connect(_dsn):
        return connection

    monkeypatch.setattr(repair.asyncpg, "connect", connect)
    calls = []

    async def fake_repair_spec(_conn, spec, *, dry_run):
        calls.append((spec.document_id, dry_run))
        if len(calls) == 2:
            raise RuntimeError("fixture later-spec failure")
        return {"document_id": spec.document_id}

    monkeypatch.setattr(repair, "repair_spec", fake_repair_spec)

    with pytest.raises(RuntimeError, match="fixture later-spec failure"):
        await repair.run(high_value_only=True)

    assert len(calls) == 2
    assert all(dry_run is False for _document_id, dry_run in calls)
    assert connection.transaction_started is True
    assert connection.transaction_rolled_back is True
    assert connection.closed is True


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("LAW_RAG_REAL_DB_TESTS"),
    reason="set LAW_RAG_REAL_DB_TESTS=1 for the local Postgres transaction contract",
)
async def test_high_value_run_rolls_back_later_spec_in_real_postgres(monkeypatch):
    import asyncpg

    settings = repair.get_settings()
    connection = await asyncpg.connect(settings.resolved_database_url_host_side)
    try:
        await connection.execute(
            "CREATE TEMP TABLE stage37_transaction_fixture (value text) ON COMMIT PRESERVE ROWS"
        )
        monkeypatch.setattr(
            repair,
            "get_settings",
            lambda: SimpleNamespace(resolved_database_url_host_side=settings.resolved_database_url_host_side),
        )

        class _KeepOpenConnection:
            def __init__(self, inner):
                self.inner = inner

            def transaction(self):
                return self.inner.transaction()

            async def execute(self, *args):
                return await self.inner.execute(*args)

            async def fetchval(self, *args):
                return await self.inner.fetchval(*args)

            async def close(self):
                return None

        wrapped = _KeepOpenConnection(connection)

        async def connect(_dsn):
            return wrapped

        monkeypatch.setattr(repair.asyncpg, "connect", connect)
        calls = 0

        async def fake_repair_spec(conn, _spec, *, dry_run):
            nonlocal calls
            assert dry_run is False
            calls += 1
            await conn.execute(
                "INSERT INTO stage37_transaction_fixture (value) VALUES ($1)",
                str(calls),
            )
            if calls == 2:
                raise RuntimeError("fixture later-spec failure")
            return {"action": "fixture"}

        monkeypatch.setattr(repair, "repair_spec", fake_repair_spec)

        with pytest.raises(RuntimeError, match="fixture later-spec failure"):
            await repair.run(high_value_only=True)

        assert calls == 2
        assert await connection.fetchval(
            "SELECT count(*) FROM stage37_transaction_fixture"
        ) == 0
    finally:
        await connection.close()


def test_court_fees_repair_selects_only_the_operating_section_start(monkeypatch):
    spec = _spec("court-fees-1870", "7")
    good = SimpleNamespace(
        metadata={"section_no": "7"},
        anchor="court-fees-1870/sec-7-a@2026-07-08",
        text=(
            "The Court-Fees Act, 1870, Section 7\n\n"
            "7. Computation of fees payable in certain suits. --The amount of fee payable"
        ),
    )
    misleading = SimpleNamespace(
        metadata={"section_no": "7"},
        anchor="court-fees-1870/sec-7__2@2026-07-08",
        text="The Court-Fees Act, 1870, Section 7\n\n7. Copy of a decree",
    )
    monkeypatch.setattr(repair, "extract_pdf_text", lambda _pdf: ("ignored", []))
    monkeypatch.setattr(repair, "chunk_act", lambda *_args, **_kwargs: [misleading, good])

    assert repair._court_fees_text(spec, b"pdf") == good.text


def test_court_fees_repair_refuses_ambiguous_operating_starts(monkeypatch):
    spec = _spec("court-fees-1870", "7")
    good = SimpleNamespace(
        metadata={"section_no": "7"},
        anchor="court-fees-1870/sec-7-a@2026-07-08",
        text=(
            "The Court-Fees Act, 1870, Section 7\n\n"
            "7. Computation of fees payable in certain suits. --The amount of fee payable"
        ),
    )
    monkeypatch.setattr(repair, "extract_pdf_text", lambda _pdf: ("ignored", []))
    monkeypatch.setattr(repair, "chunk_act", lambda *_args, **_kwargs: [good, good])

    with pytest.raises(RuntimeError, match="expected one operative Section 7 start"):
        repair._court_fees_text(spec, b"pdf")


def test_drugs_section_27_repair_requires_one_bounded_body(monkeypatch):
    spec = _spec("drugs-cosmetics-1940", "27")
    text = (
        "5[27.\nPenalty\nfor\nmanufacture,\nsale,\netc.,\nof\ndrugs\n"
        "in\ncontravention\nof\nthis Chapter.—Whoever, himself or by any other person "
        "on his behalf, manufactures for sale.\n27A. Penalty for cosmetics."
    )
    monkeypatch.setattr(repair, "extract_pdf_text", lambda _pdf: (text, []))

    extracted = repair._drugs_act_section_27_text(spec, b"pdf")

    assert "Section 27" in extracted
    assert "Whoever, himself" in extracted


def test_drugs_act_section_repair_requires_heading_at_text_start(monkeypatch):
    spec = _spec("drugs-cosmetics-1940", "18")
    misleading = SimpleNamespace(
        metadata={"section_no": "18"},
        anchor="drugs-cosmetics-1940/sec-18-a",
        text="Preamble mentions Prohibition of manufacture and sale of certain drugs and cosmetics later.",
    )
    monkeypatch.setattr(repair, "extract_pdf_text", lambda _pdf: ("ignored", []))
    monkeypatch.setattr(repair, "chunk_act", lambda *_args, **_kwargs: [misleading])

    with pytest.raises(RuntimeError, match="expected one operative section start"):
        repair._drugs_act_section_text(spec, b"pdf")


def test_crpc_section_154_repair_extracts_the_refusal_escalation_clause(monkeypatch):
    spec = _spec("crpc-1973", "154")
    text = (
        "154. Information in cognizable cases.—(1) Every information relating to the commission "
        "of a cognizable offence, if given orally to an officer in charge of a police station, "
        "shall be reduced to writing. (2) A copy shall be given free of cost. (3) Any person "
        "aggrieved by a refusal on the part of an officer in charge may send the substance in "
        "writing to the Superintendent of Police.\n"
        "STATE AMENDMENT\n"
        "Chhattisgarh\n"
    )
    monkeypatch.setattr(repair, "extract_pdf_text", lambda _pdf: (text, []))

    extracted = repair._crpc_section_154_text(spec, b"pdf")

    assert extracted.startswith("Code of Criminal Procedure 1973, Section 154")
    assert "Superintendent of Police" in extracted


def test_crpc_section_154_repair_refuses_a_table_of_contents_only(monkeypatch):
    spec = _spec("crpc-1973", "154")
    text = (
        "154. Information in cognizable cases.\n"
        "155. Information as to non-cognizable cases.\n"
        "STATE AMENDMENT\n"
    )
    monkeypatch.setattr(repair, "extract_pdf_text", lambda _pdf: (text, []))

    with pytest.raises(RuntimeError, match="expected one operative official match"):
        repair._crpc_section_154_text(spec, b"pdf")


def test_bnss_repair_extracts_full_section_and_removes_page_column(monkeypatch):
    spec = _spec("bnss-2023", "173-a")
    text = (
        "173. (1) Every information relating to the commission of a cognizable offence,\n"
        "irrespective of the area where the offence is committed, may be given orally or by electronic\n"
        "communication to an officer in charge of a police station, and if given—\n"
        "(ii) by electronic communication, it shall be taken on record by him on being\n"
        "signed within three days by the person giving it,\n"
        "Local inquiry.\nPolice to prevent cognizable offences.\n"
        "52\nTHE GAZETTE OF INDIA EXTRAORDINARY\n"
        "and the substance thereof shall be entered in a book to be kept by such officer:\n"
        "(4) Any person aggrieved by a refusal on the part of an officer in charge of a police station\n"
        "may send the substance in writing and by post, to the Superintendent of Police concerned,\n"
        "who may investigate or direct an investigation and the aggrieved person may apply to the Magistrate.\n"
        "174. Persons bound to conform to lawful directions of police."
    )
    monkeypatch.setattr(repair, "extract_pdf_text", lambda _pdf: (text, []))

    extracted = repair._bnss_chunk_text(spec, b"pdf")
    assert extracted.startswith("Bharatiya Nagarik Suraksha Sanhita 2023, Section 173")
    assert "Local inquiry." not in extracted
    assert "electronic communication" in extracted
    assert "Superintendent of Police" in extracted


def test_bnss_repair_extracts_paragraph_173_4_as_its_legal_identity(monkeypatch):
    spec = _spec("bnss-2023", "173-c")
    text = (
        "173. (1) Every information relating to the commission of a cognizable offence,\n"
        "may be given orally or by electronic communication to an officer in charge.\n"
        "(4) Any person aggrieved by a refusal on the part of an officer in charge of a police\n"
        "station to record the information referred to in sub-section (1), may send the substance\n"
        "of such information, in writing and by post, to the Superintendent of Police concerned\n"
        "who may direct an investigation, failing which such aggrieved person may make an\n"
        "application to the Magistrate.\n"
        "174. Persons bound to conform to lawful directions of police."
    )
    monkeypatch.setattr(repair, "extract_pdf_text", lambda _pdf: (text, []))

    extracted = repair._bnss_chunk_text(spec, b"pdf")
    assert extracted.startswith("Bharatiya Nagarik Suraksha Sanhita 2023, Section 173(4)")
    assert extracted.startswith("Bharatiya Nagarik Suraksha Sanhita 2023, Section 173(4)\n\n(4)")
    assert "Superintendent of Police" in extracted


def test_bnss_repair_refuses_a_chunk_without_operational_phrases(monkeypatch):
    spec = _spec("bnss-2023", "175")
    text = (
        "175. (1) Police officer power to investigate cognizable case.\n"
        "176. Procedure for investigation."
    )
    monkeypatch.setattr(repair, "extract_pdf_text", lambda _pdf: (text, []))

    with pytest.raises(RuntimeError, match="lacks required operative phrases"):
        repair._bnss_chunk_text(spec, b"pdf")


def test_generic_act_repair_matches_section_anchor_without_snapshot_date(monkeypatch):
    good = SimpleNamespace(
        metadata={"section_no": "303", "section_title": "Theft"},
        anchor="bns-2023/sec-303-a@2025-10-06",
        text="Bharatiya Nyaya Sanhita 2023, Section 303\n\n303. Theft.",
    )
    spec = replace(
        _spec("bns-2023", "303"),
        expected_text_sha256=hashlib.sha256(good.text.encode()).hexdigest(),
    )
    misleading = SimpleNamespace(
        metadata={"section_no": "303"},
        anchor="bns-2023/sec-303-b@2025-10-06",
        text="Bharatiya Nyaya Sanhita 2023, Section 303\n\n303. Illustration.",
    )
    monkeypatch.setattr(repair, "extract_pdf_text", lambda _pdf: ("ignored", []))
    monkeypatch.setattr(repair, "chunk_act", lambda *_args, **_kwargs: [misleading, good])

    assert repair._generic_act_section_text(spec, b"pdf") == good.text


def test_generic_act_repair_rejects_same_anchor_with_wrong_body(monkeypatch):
    good_text = "Bharatiya Nyaya Sanhita 2023, Section 303\n\n303. Theft."
    spec = replace(
        _spec("bns-2023", "303"),
        expected_text_sha256=hashlib.sha256(good_text.encode()).hexdigest(),
    )
    wrong_body = SimpleNamespace(
        metadata={"section_no": "303", "section_title": "Theft"},
        anchor="bns-2023/sec-303-a@2025-10-06",
        text="Bharatiya Nyaya Sanhita 2023, Section 303\n\n303. Unrelated provision.",
    )
    monkeypatch.setattr(repair, "extract_pdf_text", lambda _pdf: ("ignored", []))
    monkeypatch.setattr(repair, "chunk_act", lambda *_args, **_kwargs: [wrong_body])

    with pytest.raises(RuntimeError, match="extracted text hash changed"):
        repair._generic_act_section_text(spec, b"pdf")


def test_generic_act_repair_refuses_duplicate_exact_section_chunks(monkeypatch):
    spec = _spec("bns-2023", "303")
    duplicate = SimpleNamespace(
        metadata={"section_no": "303"},
        anchor="bns-2023/sec-303-a@2025-10-06",
        text="Bharatiya Nyaya Sanhita 2023, Section 303\n\n303. Theft.",
    )
    monkeypatch.setattr(repair, "extract_pdf_text", lambda _pdf: ("ignored", []))
    monkeypatch.setattr(repair, "chunk_act", lambda *_args, **_kwargs: [duplicate, duplicate])

    with pytest.raises(RuntimeError, match="expected one exact section chunk"):
        repair._generic_act_section_text(spec, b"pdf")


def test_ipc_378_repair_removes_pdf_layout_artifacts_and_requires_boundary(monkeypatch):
    spec = _spec("ipc-1860", "378")
    text = (
        "378. Theft.--Whoever, intending to take dishonestly any movable\n"
        "property out of the possession of any person without that person's consent,\n"
        "moves that property in order to such taking, is said to commit theft.\n"
        "----------------------------------------------------------------------\n"
        "188\n"
        "Illustrations (a) A cuts down a tree.\n"
        "379. Punishment for theft.--Whoever commits theft shall be punished.\n"
    )
    monkeypatch.setattr(repair, "extract_pdf_text", lambda _pdf: (text, []))

    extracted = repair._ipc_section_378_text(spec, b"pdf")

    assert extracted.startswith("Indian Penal Code 1860, Section 378")
    assert "----------------------------------------------------------------------" not in extracted
    assert " 188 " not in f" {extracted} "
    assert "without that person's consent" in extracted


def test_ipc_378_repair_refuses_unbounded_or_incomplete_text(monkeypatch):
    spec = _spec("ipc-1860", "378")
    text = "378. Theft.--A short table of contents entry.\n379. Punishment for theft.--next"
    monkeypatch.setattr(repair, "extract_pdf_text", lambda _pdf: (text, []))

    with pytest.raises(RuntimeError, match="lacks required operative phrases"):
        repair._ipc_section_378_text(spec, b"pdf")


def test_idempotency_metadata_accepts_jsonb_string_without_dropping_extra_fields():
    row = {"metadata": '{"section_no":"46","unrelated":"preserved"}'}

    assert repair._expected_metadata_matches(row, {"section_no": "46"})
    assert not repair._expected_metadata_matches(row, {"section_no": "47"})
    assert repair._metadata_json(row["metadata"]) == row["metadata"]
