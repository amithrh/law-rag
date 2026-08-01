from __future__ import annotations

import hashlib
from dataclasses import replace
from types import SimpleNamespace

import pytest

import scripts.promote_source_pack_sections as promote


def _spec(document_id: str):
    return next(spec for spec in promote.SPECS if spec.document_id == document_id)


def _partial_constitution_section_21_spec():
    base_spec = _spec("constitution-india")
    text = "Constitution of India, Article 21\n21. Liberty."
    return replace(
        base_spec,
        sections=("21",),
        section_text_sha256={"21": hashlib.sha256(text.encode("utf-8")).hexdigest()},
    )


def test_source_pack_promotion_specs_are_pinned_and_section_scoped():
    assert {spec.document_id for spec in promote.SPECS} == {
        "motor-vehicles-1988",
        "rti-2005",
        "rpwd-2016",
        "street-vendors-2014",
        "constitution-india",
        "crpc-1973",
        "jj-2015",
        "income-tax-1961",
        "prisons-1894",
        "sc-st-poa-1989",
        "legal-services-authorities-1987",
        "domestic-violence-2005",
        "it-2000",
        "itpa-1956",
        "mgnrega-2005",
        "hindu-succession-1956",
        "ibc-2016",
        "copyright-1957",
        "family-courts-1984",
        "national-food-security-2013",
        "industrial-disputes-1947",
    }
    for spec in promote.SPECS:
        assert len(spec.source_sha256) == 64
        assert spec.source_bytes > 0
        assert spec.sections
        assert set(dict(spec.section_text_sha256)) == set(spec.sections)
        assert all(
            promote._target_anchor(spec, section).endswith(f"sec-{section}-official")
            for section in spec.sections
        )
    assert _spec("constitution-india").expected_origin == "legislative_department"
    pwdva = _spec("domestic-violence-2005")
    assert pwdva.sections == ("2", "3", "12", "17", "18", "19", "20", "27", "29")
    assert pwdva.supplement_document_id == "domestic-violence-2005-official"
    assert pwdva.source_sha256 == "17ea6d7cb89fcae52825ec4b15f61e5573285ae9d6eca6937665161afcdad9b1"
    assert set(dict(pwdva.section_text_sha256)) == set(pwdva.sections)
    assert pwdva.local_artifact_path.endswith("domestic-violence-2005__A2005-43.pdf")


def test_high_risk_criminal_source_specs_are_exact_and_replace_only_handle_predecessors():
    crpc = _spec("crpc-1973")
    jj = _spec("jj-2015")
    lsa = _spec("legal-services-authorities-1987")

    assert crpc.sections == ("167", "482")
    assert dict(crpc.section_text_sha256).keys() == {"167", "482"}
    assert crpc.promote_to_new_source is False
    assert jj.sections == ("9", "10", "12", "56", "57", "58", "59", "62", "63", "94")
    assert set(dict(jj.section_text_sha256)) == {
        "9", "10", "12", "56", "57", "58", "59", "62", "63", "94",
    }
    assert jj.promote_to_new_source is True
    assert jj.accepted_source_urls == ("https://www.indiacode.nic.in/handle/123456789/17101",)
    assert jj.local_artifact_path
    assert lsa.sections == ("9", "12", "19", "20", "21")
    assert set(dict(lsa.section_text_sha256)) == {"9", "12", "19", "20", "21"}
    assert lsa.promote_to_new_source is True
    assert lsa.allow_unpinned_predecessor is True
    assert lsa.requires_dated_as_at is True
    assert lsa.accepted_source_urls == ("https://www.indiacode.nic.in/handle/123456789/12883",)
    assert lsa.local_artifact_path.endswith("legal-services-authorities-1987__198739.pdf")
    it_act = _spec("it-2000")
    assert it_act.sections == ("66C", "66D", "66E", "67", "67A", "67B", "69", "69A", "79", "90")
    assert it_act.promote_to_new_source is False
    assert set(dict(it_act.section_text_sha256)) == set(it_act.sections)
    assert it_act.local_artifact_path.endswith("it-2000__it_act_2000_updated.pdf")
    itpa = _spec("itpa-1956")
    assert itpa.promote_to_new_source is True
    assert itpa.allow_unpinned_predecessor is True
    assert set(dict(itpa.section_text_sha256)) == set(itpa.sections)
    mgnrega = _spec("mgnrega-2005")
    assert mgnrega.promote_to_new_source is True
    assert mgnrega.allow_unpinned_predecessor is False
    assert {"3", "6", "7", "15", "17", "19", "23", "27", "35"} <= set(mgnrega.sections)
    assert set(dict(mgnrega.section_text_sha256)) == set(mgnrega.sections)
    hsa = _spec("hindu-succession-1956")
    assert hsa.promote_to_new_source is True
    assert hsa.allow_unpinned_predecessor is True
    assert hsa.allow_hash_only_predecessor is True
    assert set(dict(hsa.section_text_sha256)) == set(hsa.sections)
    income_tax = _spec("income-tax-1961")
    assert income_tax.sections == ("139AA",)
    assert set(dict(income_tax.section_text_sha256)) == {"139AA"}
    assert income_tax.promote_to_new_source is True
    assert income_tax.local_artifact_path
    assert income_tax.supplement_document_id == "income-tax-1961-official"
    prisons = _spec("prisons-1894")
    assert prisons.sections == ("13", "14", "37", "38", "39")
    assert set(dict(prisons.section_text_sha256)) == {"13", "14", "37", "38", "39"}
    assert prisons.allow_unpinned_predecessor is True
    assert prisons.supplement_document_id == "prisons-1894-official"
    scst = _spec("sc-st-poa-1989")
    assert scst.sections == ("3", "4", "14", "15", "15A", "18", "18A")
    assert set(dict(scst.section_text_sha256)) == {"3", "4", "14", "15", "15A", "18", "18A"}
    assert scst.accepted_predecessor_origins == ("direct",)
    assert scst.supplement_document_id == "sc-st-poa-1989-official"


def test_stage38_national_source_batch_uses_current_pinned_artifacts():
    ibc = _spec("ibc-2016")
    copyright_act = _spec("copyright-1957")
    family = _spec("family-courts-1984")
    nfsa = _spec("national-food-security-2013")
    industrial = _spec("industrial-disputes-1947")

    assert ibc.sections == ("7", "8", "9", "54A", "61")
    assert ibc.source_sha256 == "d13ef44426184e496133029f601b63412dea188bc36a23f90b0b719c16c5f000"
    assert ibc.allow_unpinned_predecessor is True
    assert ibc.local_artifact_path is None

    assert copyright_act.sections == ("51", "52", "55", "63")
    assert copyright_act.source_sha256 == "da4144b68419cf81bbf10979183ed1cf3fbe3795188995d1efc85fd7d65713bd"
    assert copyright_act.local_artifact_path is None

    assert family.sections == ("7", "8", "9")
    assert family.source_url.endswith("the_family_courts_act_1984_no._66_of_1984_dt._14-09-1984.pdf")

    assert nfsa.expected_origin == "direct"
    assert nfsa.source_url == "https://dfpd.gov.in/WriteReadData/Other/nfsa_1.pdf"
    assert nfsa.sections == ("3", "12", "13", "14", "15", "24")

    assert industrial.expected_origin == "indiacode"
    assert industrial.accepted_predecessor_origins == ("direct",)
    assert industrial.sections == ("2A", "10", "12", "25F", "25G", "25H")
    for spec in (ibc, copyright_act, family, nfsa, industrial):
        assert spec.source_id is None


def test_pinned_local_artifact_is_verified_before_promotion(tmp_path, monkeypatch):
    data = b"official-income-tax-pdf"
    artifact = tmp_path / "income-tax.pdf"
    artifact.write_bytes(data)
    monkeypatch.setattr(promote, "refetch_act_pdfs", lambda _url: (_ for _ in ()).throw(AssertionError("network should not be used")))

    assert promote._fetch_pinned_pdf(
        "https://www.indiacode.nic.in/example.pdf",
        hashlib.sha256(data).hexdigest(),
        len(data),
        str(artifact),
    ) == data


@pytest.mark.asyncio
async def test_supplement_dry_run_preserves_the_predecessor_document(monkeypatch):
    mock_text = "Income-tax Act 1961, Section 139AA\n139AA. Quoting of Aadhaar number."
    spec = replace(
        _spec("income-tax-1961"),
        section_text_sha256=(("139AA", hashlib.sha256(mock_text.encode()).hexdigest()),),
    )
    document = {"id": 16214, "title": spec.title, "source_id": spec.source_id}
    connection = _PromotionConnection(_source_for_spec(spec), document)
    monkeypatch.setattr(promote, "_fetch_pinned_pdf", lambda *_args: b"pdf")
    monkeypatch.setattr(
        promote,
        "_canonical_section_text",
        lambda *_args: mock_text,
    )

    rows = await promote.promote_spec(connection, spec, dry_run=True)

    assert rows == [{
        "section": "139AA",
        "anchor": "income-tax-1961-official/sec-139AA-official",
        "action": "would_promote_supplement",
    }]
    assert connection.executed == []


@pytest.mark.asyncio
async def test_supplement_inserts_only_its_verified_section(monkeypatch):
    mock_text = "Income-tax Act 1961, Section 139AA\n139AA. Quoting of Aadhaar number."
    spec = replace(
        _spec("income-tax-1961"),
        section_text_sha256=(("139AA", hashlib.sha256(mock_text.encode()).hexdigest()),),
    )
    document = {"id": 16214, "title": spec.title, "source_id": spec.source_id}
    connection = _PromotionConnection(_source_for_spec(spec), document)
    monkeypatch.setattr(promote, "_fetch_pinned_pdf", lambda *_args: b"pdf")
    monkeypatch.setattr(
        promote,
        "_canonical_section_text",
        lambda *_args: mock_text,
    )
    async def ensure_canonical_source(*_args, **_kwargs):
        return 9002

    async def ensure_supplement_document(*_args, **_kwargs):
        return {"id": 9003, "title": spec.title, "source_id": 9002}

    monkeypatch.setattr(promote, "_ensure_canonical_source", ensure_canonical_source)
    monkeypatch.setattr(promote, "_ensure_supplement_document", ensure_supplement_document)
    monkeypatch.setattr(
        promote,
        "get_embedder",
        lambda: SimpleNamespace(encode_with_sparse=lambda texts: ([[0.1] for _ in texts], [{} for _ in texts])),
    )
    monkeypatch.setattr(promote, "embedding_to_halfvec_literal", lambda _value: "[0.1]")
    monkeypatch.setattr(promote, "sparse_to_jsonb", lambda _value: "{}")

    rows = await promote.promote_spec(connection, spec, dry_run=False)

    assert rows[0]["action"] == "inserted"
    assert rows[0]["anchor"] == "income-tax-1961-official/sec-139AA-official"
    assert sum("UPDATE documents SET provenance_verified=false" in query for query in connection.executed) == 2
    assert sum("UPDATE chunks SET provenance_verified=false" in query for query in connection.executed) == 2
    assert any("anchor = ANY($2::text[])" in query for query in connection.executed)


def test_canonical_section_text_prefers_exact_section_start_over_split_fragment(monkeypatch):
    spec = _spec("motor-vehicles-1988")
    split = SimpleNamespace(
        metadata={"section_no": "74"},
        anchor="motor-vehicles-1988/sec-74-b@2025-05-21",
        text="Motor Vehicles Act 1988, Section 74\n74. Later fragment.",
    )
    duplicate = SimpleNamespace(
        metadata={"section_no": "74"},
        anchor="motor-vehicles-1988/sec-74__2@2025-05-21",
        text="Motor Vehicles Act 1988, Section 74\n74. Duplicate schedule fragment.",
    )
    start = SimpleNamespace(
        metadata={"section_no": "74"},
        anchor="motor-vehicles-1988/sec-74-a@2025-05-21",
        text="Motor Vehicles Act 1988, Section 74\n74. Grant of permits.",
    )
    monkeypatch.setattr(promote, "extract_pdf_text", lambda _pdf: ("ignored", 1))
    monkeypatch.setattr(promote, "chunk_act", lambda *_args, **_kwargs: [duplicate, split, start])

    assert promote._canonical_section_text(spec, "74", b"pdf") == start.text


def test_constitution_article_text_uses_substantive_heading_not_toc(monkeypatch):
    spec = _spec("constitution-india")
    raw = (
        "21.\nProtection of life and personal liberty.\n"
        "2[21A.\nRight to education.\n"
        "21. Protection of life and personal liberty.—No person shall be deprived\n"
        "of his life or personal liberty except according to procedure established by law.\n"
        "2[21A. Right to education.—The State shall provide free and compulsory education.\n"
    )
    monkeypatch.setattr(promote, "extract_pdf_text", lambda _pdf: (raw, 1))

    text = promote._canonical_section_text(spec, "21", b"pdf")

    assert text.startswith("Constitution of India, Article 21")
    assert "No person shall be deprived" in text
    assert text.count("Protection of life and personal liberty") == 1


def test_constitution_article_text_fails_closed_without_boundary(monkeypatch):
    spec = _spec("constitution-india")
    raw = (
        "21. Protection of life and personal liberty.—No person shall be deprived\n"
        "of his life or personal liberty except according to procedure established by law.\n"
    )
    monkeypatch.setattr(promote, "extract_pdf_text", lambda _pdf: (raw, 1))

    with pytest.raises(RuntimeError, match="no exact article start"):
        promote._canonical_section_text(spec, "21", b"pdf")


def test_constitution_article_text_rejects_ambiguous_duplicate_candidates(monkeypatch):
    spec = _spec("constitution-india")
    candidate = (
        "21. Protection of life and personal liberty.—No person shall be deprived "
        "of his life or personal liberty except according to procedure established by law.\n"
        "21A. Right to education.—The State shall provide free and compulsory education.\n"
    )
    raw = candidate + "APPENDIX\n" + candidate
    monkeypatch.setattr(promote, "extract_pdf_text", lambda _pdf: (raw, 1))

    with pytest.raises(RuntimeError, match="ambiguous exact article start"):
        promote._canonical_section_text(spec, "21", b"pdf")


def test_canonical_section_text_does_not_promote_schedule_duplicate(monkeypatch):
    spec = _spec("motor-vehicles-1988")
    duplicate = SimpleNamespace(
        metadata={"section_no": "74"},
        anchor="motor-vehicles-1988/sec-74__2@2025-05-21",
        text="Motor Vehicles Act 1988, Section 74\n74. Duplicate schedule fragment.",
    )
    monkeypatch.setattr(promote, "extract_pdf_text", lambda _pdf: ("ignored", 1))
    monkeypatch.setattr(promote, "chunk_act", lambda *_args, **_kwargs: [duplicate])

    with pytest.raises(RuntimeError, match="no exact section start"):
        promote._canonical_section_text(spec, "74", b"pdf")


def test_canonical_section_text_rejects_missing_exact_section(monkeypatch):
    spec = _spec("rti-2005")
    misleading = SimpleNamespace(
        metadata={"section_no": "60"},
        anchor="rti-2005/sec-60@2025-11-18",
        text="Right to Information Act 2005, Section 60",
    )
    monkeypatch.setattr(promote, "extract_pdf_text", lambda _pdf: ("ignored", 1))
    monkeypatch.setattr(promote, "chunk_act", lambda *_args, **_kwargs: [misleading])

    try:
        promote._canonical_section_text(spec, "6", b"pdf")
    except RuntimeError as exc:
        assert "no exact section start" in str(exc)
    else:
        raise AssertionError("missing section was accepted")


def test_canonical_section_text_rejects_ambiguous_exact_section_starts(monkeypatch):
    spec = _spec("crpc-1973")
    first = SimpleNamespace(
        metadata={"section_no": "482"},
        anchor="crpc-1973/sec-482",
        text="Code of Criminal Procedure 1973, Section 482\n482. First candidate.",
    )
    second = SimpleNamespace(
        metadata={"section_no": "482"},
        anchor="crpc-1973/sec-482@1974-04-01",
        text="Code of Criminal Procedure 1973, Section 482\n482. Second candidate.",
    )
    monkeypatch.setattr(promote, "extract_pdf_text", lambda _pdf: ("ignored", 1))
    monkeypatch.setattr(promote, "chunk_act", lambda *_args, **_kwargs: [first, second])

    with pytest.raises(RuntimeError, match="ambiguous exact section start"):
        promote._canonical_section_text(spec, "482", b"pdf")


@pytest.mark.asyncio
async def test_promotion_rejects_normalized_section_text_hash_drift(monkeypatch):
    spec = replace(
        _spec("crpc-1973"),
        sections=("482",),
        section_text_sha256=(("482", "0" * 64),),
    )
    source = _source_for_spec(spec)
    document = {"id": 26280, "title": spec.title, "source_id": spec.source_id}
    connection = _PromotionConnection(source, document)
    monkeypatch.setattr(promote, "_fetch_pinned_pdf", lambda *_args: b"pdf")
    monkeypatch.setattr(
        promote,
        "_canonical_section_text",
        lambda *_args: "Code of Criminal Procedure 1973, Section 482\n482. Saving of inherent powers.",
    )

    with pytest.raises(RuntimeError, match="normalized text hash mismatch"):
        await promote.promote_spec(connection, spec, dry_run=True)


def test_local_official_artifact_is_hash_pinned():
    spec = _spec("street-vendors-2014")
    data = promote._fetch_pinned_pdf(
        promote._STREET_VENDOR_LOCAL_URL,
        spec.source_sha256,
        spec.source_bytes,
    )
    assert len(data) == spec.source_bytes


def test_unpinned_predecessor_is_only_allowed_for_an_explicit_supplement():
    prisons = _spec("prisons-1894")
    unpinned_handle = {
        **_source_for_spec(prisons),
        "url": prisons.accepted_source_urls[0],
        "raw_sha256": None,
        "raw_bytes_size": None,
    }
    assert promote._predecessor_content_matches(prisons, unpinned_handle)

    constitution = _spec("constitution-india")
    unpinned_constitution = {
        **_source_for_spec(constitution),
        "raw_sha256": None,
        "raw_bytes_size": None,
    }
    assert not promote._predecessor_content_matches(constitution, unpinned_constitution)

    hash_only_hsa = {
        **_source_for_spec(_spec("hindu-succession-1956")),
        "url": _spec("hindu-succession-1956").accepted_source_urls[0],
        "raw_bytes_size": None,
    }
    assert promote._predecessor_content_matches(_spec("hindu-succession-1956"), hash_only_hsa)


def test_section_text_hash_is_carried_into_chunk_metadata():
    spec = _spec("crpc-1973")
    metadata = promote._metadata(spec, "482")
    assert metadata["canonical_text_sha256"] == dict(spec.section_text_sha256)["482"]


def test_empty_section_text_hash_is_rejected():
    spec = replace(_spec("crpc-1973"), sections=("482",), section_text_sha256=(("482", ""),))
    with pytest.raises(RuntimeError, match="invalid section text hash pin"):
        promote._validate_section_text_hashes(spec, {"482": "482. Saving of inherent powers."})


@pytest.mark.asyncio
async def test_existing_unverified_canonical_url_is_upgraded_only_without_siblings():
    spec = _spec("hindu-succession-1956")
    row = {
        "id": 590,
        "source_type": "bare_act",
        "origin": spec.expected_origin,
        "url": spec.source_url,
        "canonical_url_hash": hashlib.sha256(spec.source_url.encode()).hexdigest(),
        "raw_sha256": None,
        "raw_bytes_size": None,
        "provenance_tier": "unverified",
        "metadata": {"manual_section_backfill": True},
    }

    class _ExistingUnverifiedSourceConnection:
        def __init__(self, sibling_count=0, metadata=None):
            self.sibling_count = sibling_count
            self.metadata = metadata or row["metadata"]
            self.executed = []

        async def fetch(self, *_args):
            return [{**row, "metadata": self.metadata}]

        async def fetchval(self, query, *_args):
            assert "count(*) FROM documents" in query
            return self.sibling_count

        async def execute(self, query, *_args):
            self.executed.append(query)
            return "UPDATE 1"

    connection = _ExistingUnverifiedSourceConnection()
    assert await promote._ensure_canonical_source(connection, spec, predecessor_source_id=81) == 590
    assert any("UPDATE sources SET raw_sha256" in query for query in connection.executed)

    sibling_connection = _ExistingUnverifiedSourceConnection(sibling_count=1)
    with pytest.raises(RuntimeError, match="sibling documents"):
        await promote._ensure_canonical_source(sibling_connection, spec, predecessor_source_id=81)

    conflict_connection = _ExistingUnverifiedSourceConnection(
        metadata={"canonical_pdf_url": "https://example.invalid/wrong.pdf"},
    )
    with pytest.raises(RuntimeError, match="metadata conflicts"):
        await promote._ensure_canonical_source(conflict_connection, spec, predecessor_source_id=81)


@pytest.mark.asyncio
async def test_dated_source_requires_a_dedicated_promoter():
    spec = _spec("legal-services-authorities-1987")

    class _SourceOnlyConnection:
        async def fetchrow(self, *_args):
            return _source_for_spec(spec)

    with pytest.raises(RuntimeError, match="dated as_at provenance"):
        await promote.promote_spec(_SourceOnlyConnection(), spec, dry_run=True)


def test_direct_predecessor_requires_an_explicit_origin_and_exact_artifact():
    scst = _spec("sc-st-poa-1989")
    local_source = {
        **_source_for_spec(scst),
        "url": scst.accepted_source_urls[0],
        "origin": "direct",
    }
    assert promote._predecessor_content_matches(scst, local_source)
    local_source["origin"] = "untrusted_import"
    assert not promote._predecessor_content_matches(scst, local_source)


class _PromotionConnection:
    def __init__(
        self,
        source,
        document,
        *,
        changed_source=False,
        fail_document_update=False,
        fail_chunk_insert=False,
    ):
        self.source = source
        self.document = document
        self.changed_source = changed_source
        self.fail_document_update = fail_document_update
        self.fail_chunk_insert = fail_chunk_insert
        self.document_provenance_verified = True
        self.inserted_chunks: list[str] = []
        self.executed: list[str] = []

    class _Transaction:
        def __init__(self, owner):
            self.owner = owner
            self.snapshot = None

        async def __aenter__(self):
            self.snapshot = (
                self.owner.document_provenance_verified,
                list(self.owner.inserted_chunks),
            )
            return self

        async def __aexit__(self, exc_type, _exc, _tb):
            if exc_type is not None:
                self.owner.document_provenance_verified, chunks = self.snapshot
                self.owner.inserted_chunks = chunks
            return False

    def transaction(self):
        return self._Transaction(self)

    async def fetchrow(self, query, *_args):
        if "FROM sources" in query:
            if self.changed_source and "FOR UPDATE" in query:
                changed = dict(self.source)
                changed["raw_sha256"] = "f" * 64
                return changed
            return self.source
        if "FROM documents" in query:
            return self.document
        raise AssertionError(query)

    async def fetch(self, query, *_args):
        if "FROM chunks" in query:
            return []
        raise AssertionError(query)

    async def fetchval(self, query, *_args):
        if "advisory_xact_lock" in query:
            return None
        if "INSERT INTO chunks" in query:
            if self.fail_chunk_insert:
                raise RuntimeError("simulated chunk insert failure")
            self.inserted_chunks.append(query)
        return 9001

    async def execute(self, query, *_args):
        self.executed.append(query)
        if self.fail_document_update and "UPDATE documents SET source_id" in query:
            return "UPDATE 0"
        if "UPDATE documents SET provenance_verified=false" in query:
            self.document_provenance_verified = False
        return "UPDATE 1"


def _source_for_spec(spec):
    return {
        "id": spec.source_id,
        "url": spec.source_url,
        "canonical_url_hash": hashlib.sha256(spec.source_url.encode()).hexdigest(),
        "origin": spec.expected_origin,
        "raw_sha256": spec.source_sha256,
        "raw_bytes_size": spec.source_bytes,
        "source_type": "bare_act",
        "provenance_tier": "canonical",
    }


def test_pinned_target_source_is_accepted_for_idempotent_repair():
    spec = _spec("street-vendors-2014")
    source = _source_for_spec(spec)
    source["metadata"] = {
        "canonical_pdf_hash_pinned": True,
        "canonical_pdf_url": spec.source_url,
        "replaces_unverified_source_id": 123,
        "source_transition": "independent_first_party_artifact_replacement",
    }

    assert promote._is_pinned_target_source(spec, source)

    source["raw_sha256"] = "f" * 64
    assert not promote._is_pinned_target_source(spec, source)


@pytest.mark.asyncio
async def test_new_source_promotion_does_not_recreate_an_existing_canonical_source(monkeypatch):
    mock_text = "Street Vendors Act 2014, Section 3\n3. Survey."
    base_spec = _spec("street-vendors-2014")
    spec = replace(
        base_spec,
        sections=("3",),
        section_text_sha256=(("3", hashlib.sha256(mock_text.encode()).hexdigest()),),
    )
    source = _source_for_spec(spec)
    source["id"] = 9002
    source["metadata"] = {
        "canonical_pdf_hash_pinned": True,
        "canonical_pdf_url": spec.source_url,
        "replaces_unverified_source_id": 123,
        "source_transition": "independent_first_party_artifact_replacement",
    }
    document = {"id": 16221, "title": spec.title, "source_id": 9002}
    connection = _PromotionConnection(source, document)

    async def should_not_recreate(*_args, **_kwargs):
        raise AssertionError("canonical source should be reused")

    monkeypatch.setattr(promote, "_ensure_canonical_source", should_not_recreate)
    monkeypatch.setattr(promote, "_fetch_pinned_pdf", lambda *_args: b"pdf")
    monkeypatch.setattr(promote, "_canonical_section_text", lambda *_args: mock_text)
    monkeypatch.setattr(
        promote,
        "get_embedder",
        lambda: SimpleNamespace(encode_with_sparse=lambda texts: ([[0.1] for _ in texts], [{} for _ in texts])),
    )
    monkeypatch.setattr(promote, "embedding_to_halfvec_literal", lambda _value: "[0.1]")
    monkeypatch.setattr(promote, "sparse_to_jsonb", lambda _value: "{}")

    rows = await promote.promote_spec(connection, spec, dry_run=False)

    assert rows[0]["action"] == "inserted"
    assert not any("UPDATE documents SET source_id" in query for query in connection.executed)


@pytest.mark.asyncio
async def test_partial_promotion_clears_document_level_eligibility(monkeypatch):
    base_spec = _spec("constitution-india")
    spec = replace(
        base_spec,
        sections=("21",),
        section_text_sha256={
            "21": hashlib.sha256(
                "Constitution of India, Article 21\n21. Liberty.".encode("utf-8")
            ).hexdigest(),
        },
    )
    source = _source_for_spec(spec)
    document = {"id": 16220, "title": spec.title, "source_id": spec.source_id}
    connection = _PromotionConnection(source, document)
    monkeypatch.setattr(promote, "_fetch_pinned_pdf", lambda *_args: b"pdf")
    monkeypatch.setattr(promote, "_canonical_section_text", lambda *_args: "Constitution of India, Article 21\n21. Liberty.")
    monkeypatch.setattr(
        promote,
        "get_embedder",
        lambda: SimpleNamespace(encode_with_sparse=lambda texts: ([[0.1] for _ in texts], [{} for _ in texts])),
    )
    monkeypatch.setattr(promote, "embedding_to_halfvec_literal", lambda _value: "[0.1]")
    monkeypatch.setattr(promote, "sparse_to_jsonb", lambda _value: "{}")

    rows = await promote.promote_spec(connection, spec, dry_run=False)

    assert rows[0]["action"] == "inserted"
    assert any("UPDATE documents SET provenance_verified=false" in query for query in connection.executed)
    chunk_resets = [
        query for query in connection.executed
        if "UPDATE chunks SET provenance_verified=false" in query
    ]
    assert chunk_resets == [
        "UPDATE chunks SET provenance_verified=false, provenance_verified_at=NULL "
        "WHERE document_id=$1 AND NOT ("
        "COALESCE(metadata->>'registry_projection','')='chunk' "
        "AND metadata ? 'authority_record_sha256' "
        "AND COALESCE((metadata->>'text_is_verbatim')::boolean,false)"
        ")"
    ]


@pytest.mark.asyncio
async def test_promotion_rejects_source_changed_after_preflight(monkeypatch):
    spec = _partial_constitution_section_21_spec()
    document = {"id": 16220, "title": spec.title, "source_id": spec.source_id}
    connection = _PromotionConnection(
        _source_for_spec(spec),
        document,
        changed_source=True,
    )
    monkeypatch.setattr(promote, "_fetch_pinned_pdf", lambda *_args: b"pdf")
    monkeypatch.setattr(
        promote,
        "_canonical_section_text",
        lambda *_args: "Constitution of India, Article 21\n21. Liberty.",
    )
    monkeypatch.setattr(
        promote,
        "get_embedder",
        lambda: SimpleNamespace(encode_with_sparse=lambda texts: ([[0.1] for _ in texts], [{} for _ in texts])),
    )
    monkeypatch.setattr(promote, "embedding_to_halfvec_literal", lambda _value: "[0.1]")
    monkeypatch.setattr(promote, "sparse_to_jsonb", lambda _value: "{}")

    with pytest.raises(RuntimeError, match="source changed during promotion"):
        await promote.promote_spec(connection, spec, dry_run=False)

    assert not any("UPDATE documents" in query for query in connection.executed)


@pytest.mark.asyncio
async def test_nonreplacement_rejects_wrong_expected_source_origin():
    spec = _partial_constitution_section_21_spec()
    source = _source_for_spec(spec)
    source["origin"] = "indiacode"
    document = {"id": 16220, "title": spec.title, "source_id": spec.source_id}
    connection = _PromotionConnection(source, document)

    with pytest.raises(RuntimeError, match="source identity mismatch"):
        await promote.promote_spec(connection, spec, dry_run=True)


@pytest.mark.asyncio
async def test_new_source_promotion_rejects_failed_document_source_cas(monkeypatch):
    mock_text = "Street Vendors Act 2014, Section 3\n3. Survey."
    spec = replace(
        _spec("street-vendors-2014"),
        sections=("3",),
        section_text_sha256=(("3", hashlib.sha256(mock_text.encode()).hexdigest()),),
    )
    document = {"id": 16221, "title": spec.title, "source_id": spec.source_id}
    connection = _PromotionConnection(
        _source_for_spec(spec),
        document,
        fail_document_update=True,
    )
    async def ensure_canonical_source(*_args, **_kwargs):
        return 9002

    monkeypatch.setattr(promote, "_ensure_canonical_source", ensure_canonical_source)
    monkeypatch.setattr(promote, "_fetch_pinned_pdf", lambda *_args: b"pdf")
    monkeypatch.setattr(
        promote,
        "_canonical_section_text",
        lambda *_args: mock_text,
    )
    monkeypatch.setattr(
        promote,
        "get_embedder",
        lambda: SimpleNamespace(encode_with_sparse=lambda texts: ([[0.1] for _ in texts], [{} for _ in texts])),
    )
    monkeypatch.setattr(promote, "embedding_to_halfvec_literal", lambda _value: "[0.1]")
    monkeypatch.setattr(promote, "sparse_to_jsonb", lambda _value: "{}")

    with pytest.raises(RuntimeError, match="source CAS failed"):
        await promote.promote_spec(connection, spec, dry_run=False)

    assert not any("UPDATE documents SET provenance_verified=false" in query for query in connection.executed)


@pytest.mark.asyncio
async def test_partial_promotion_rolls_back_document_clear_on_chunk_failure(monkeypatch):
    spec = _partial_constitution_section_21_spec()
    document = {"id": 16222, "title": spec.title, "source_id": spec.source_id}
    connection = _PromotionConnection(
        _source_for_spec(spec),
        document,
        fail_chunk_insert=True,
    )
    monkeypatch.setattr(promote, "_fetch_pinned_pdf", lambda *_args: b"pdf")
    monkeypatch.setattr(promote, "_canonical_section_text", lambda *_args: "Constitution of India, Article 21\n21. Liberty.")
    monkeypatch.setattr(
        promote,
        "get_embedder",
        lambda: SimpleNamespace(encode_with_sparse=lambda texts: ([[0.1] for _ in texts], [{} for _ in texts])),
    )
    monkeypatch.setattr(promote, "embedding_to_halfvec_literal", lambda _value: "[0.1]")
    monkeypatch.setattr(promote, "sparse_to_jsonb", lambda _value: "{}")

    with pytest.raises(RuntimeError, match="simulated chunk insert failure"):
        await promote.promote_spec(connection, spec, dry_run=False)

    assert connection.document_provenance_verified is True
    assert connection.inserted_chunks == []
