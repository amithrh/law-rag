import asyncio
import hashlib
import os
from pathlib import Path
import uuid

import pytest

from scripts.verify_provenance import (
    OFFICIAL_PDF_ORIGINS,
    audit_persistence_rows,
    apply_verification_updates,
    document_scope_verdict,
    exact_sha_match,
    india_code_pdf_links,
    is_verifiable_official_source,
    local_official_pdf_path,
    select_act_candidate,
    verification_scope_updates,
)


class _RecordingConn:
    def __init__(self) -> None:
        self.calls = []
        self.transaction_events = []
        self.state = {"documents": {}, "chunks": {}}

    async def execute(self, query, values):
        self.calls.append((query, values))
        entity = "documents" if "UPDATE documents" in query else "chunks"
        verified = "provenance_verified = true" in query
        for value in values:
            self.state[entity][value] = verified

    def transaction(self):
        return _RecordingTransaction(self)


class _RecordingTransaction:
    def __init__(self, conn):
        self.conn = conn
        self.snapshot = None

    async def __aenter__(self):
        self.conn.transaction_events.append("begin")
        self.snapshot = {
            entity: values.copy()
            for entity, values in self.conn.state.items()
        }
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        if exc:
            self.conn.state = self.snapshot
        self.conn.transaction_events.append("rollback" if exc else "commit")


def _audit(*, matched, targets, scope="document", hash_match=True):
    return {
        "source_id": 1,
        "source_url": "https://example.gov.in/law.pdf",
        "sha_match": hash_match,
        "text_match": matched,
        "verification_pass": bool(matched and hash_match) if matched is not None else None,
        "scope": scope,
        "text_similarity": 1.0 if matched else 0.2,
        "refetch_status": "ok",
        "refetch_size": 100,
        "refetch_pages": 1,
        "refetch_hash": "a" * 64,
        "notes": "test",
        "audit_targets": targets,
    }


def test_audit_rows_are_expanded_to_exact_documents_and_chunks():
    rows = audit_persistence_rows(
        [
            _audit(matched=True, targets=[(10, 100), (11, 110)]),
        ]
    )
    assert [(row[2], row[3]) for row in rows] == [(10, 100), (11, 110)]


def test_verification_updates_only_compared_documents_and_clears_drift():
    passed_docs, failed_docs, passed_chunks, failed_chunks = verification_scope_updates(
        [
            _audit(matched=True, targets=[(10, 100)]),
            _audit(matched=False, targets=[(11, 110)]),
            _audit(matched=None, targets=[(12, 120)]),
            _audit(matched=True, targets=[(13, 130)], scope="chunk"),
            _audit(matched=False, targets=[(14, 140)], scope="chunk"),
        ]
    )
    assert passed_docs == [10]
    assert failed_docs == [11]
    assert passed_chunks == [130]
    assert failed_chunks == [140]


def test_document_scope_updates_propagate_to_all_live_chunks():
    conn = _RecordingConn()

    asyncio.run(
        apply_verification_updates(
            conn,
            [
                _audit(matched=True, targets=[(10, None)]),
                _audit(matched=False, targets=[(11, None)]),
            ],
        )
    )

    assert len(conn.calls) == 4
    assert conn.calls[0][1] == [10]
    assert "UPDATE documents" in conn.calls[0][0]
    assert conn.calls[1][1] == [10]
    assert "UPDATE chunks" in conn.calls[1][0]
    assert "document_id = ANY" in conn.calls[1][0]
    assert "NOT quarantined" in conn.calls[1][0]
    assert "NOT EXISTS" in conn.calls[1][0]
    assert conn.calls[2][1] == [11]
    assert conn.calls[3][1] == [11]
    assert "provenance_verified = false" in conn.calls[3][0]
    assert "NOT EXISTS" in conn.calls[3][0]
    assert conn.transaction_events == ["begin", "commit"]


def test_registry_chunk_pass_update_excludes_quarantined_chunks():
    conn = _RecordingConn()

    asyncio.run(
        apply_verification_updates(
            conn,
            [_audit(matched=True, targets=[(10, 100)], scope="chunk")],
        )
    )

    assert len(conn.calls) == 1
    assert "WHERE id = ANY" in conn.calls[0][0]
    assert "AND NOT quarantined" in conn.calls[0][0]
    assert conn.transaction_events == ["begin", "commit"]


def test_document_scope_update_rolls_back_if_chunk_update_fails():
    class FailingConn(_RecordingConn):
        async def execute(self, query, values):
            if len(self.calls) == 1:
                raise RuntimeError("simulated chunk update failure")
            await super().execute(query, values)

    conn = FailingConn()

    with pytest.raises(RuntimeError, match="simulated chunk update failure"):
        asyncio.run(
            apply_verification_updates(
                conn,
                [_audit(matched=True, targets=[(10, None)])],
            )
        )
    assert conn.transaction_events == ["begin", "rollback"]
    assert conn.state == {"documents": {}, "chunks": {}}


def test_one_corrupted_chunk_blocks_document_promotion():
    verdict = document_scope_verdict(
        [
            {"text": "section 138 cheque dishonour complaint notice"},
            {"text": "unrelated injected text that is not in the official act"},
        ],
        "section 138 cheque dishonour complaint notice official act text",
        True,
    )
    assert verdict["text_similarity"] < 0.90
    assert verdict["text_match"] is False
    assert verdict["verification_pass"] is False


def test_similarity_ignores_only_the_generated_section_prefix():
    from scripts.verify_provenance import text_similarity

    stored = (
        "Negotiable Instruments Act 1881, Section 63\n"
        "63. Drawee's time for deliberation. The holder must allow forty-eight hours."
    )
    official = (
        "63. Drawee's time for deliberation. The holder must allow forty-eight hours."
    )
    assert text_similarity(
        stored,
        official,
        expected_title="Negotiable Instruments Act 1881",
    ) == 1.0


def test_similarity_does_not_strip_a_different_title_prefix():
    from scripts.verify_provenance import text_similarity

    stored = (
        "Fake Act 2020, Section 63\n"
        "63. Drawee's time for deliberation. The holder must allow forty-eight hours."
    )
    official = (
        "63. Drawee's time for deliberation. The holder must allow forty-eight hours."
    )
    assert text_similarity(
        stored,
        official,
        expected_title="Negotiable Instruments Act 1881",
    ) < 1.0


def test_hash_mismatch_cannot_promote_registry_chunk():
    passed_docs, failed_docs, passed_chunks, failed_chunks = verification_scope_updates(
        [
            _audit(
                matched=True,
                hash_match=False,
                targets=[(13, 130)],
                scope="chunk",
            ),
        ]
    )
    assert passed_docs == []
    assert failed_docs == []
    assert passed_chunks == []
    assert failed_chunks == [130]


def test_registry_chunks_keep_independent_verification_verdicts():
    row = _audit(
        matched=False,
        targets=[(13, 130), (13, 131)],
        scope="chunk",
    )
    row["target_verdicts"] = [
        {
            "document_id": 13,
            "chunk_id": 130,
            "text_similarity": 0.99,
            "text_match": True,
            "verification_pass": True,
        },
        {
            "document_id": 13,
            "chunk_id": 131,
            "text_similarity": 0.10,
            "text_match": False,
            "verification_pass": False,
        },
    ]

    persistence = audit_persistence_rows([row])
    assert [(item[3], item[5], item[6]) for item in persistence] == [
        (130, True, 0.99),
        (131, False, 0.10),
    ]
    _, _, passed_chunks, failed_chunks = verification_scope_updates([row])
    assert passed_chunks == [130]
    assert failed_chunks == [131]


def test_official_pdf_verifier_accepts_custody_registry_publishers():
    assert {"mha_gazette", "legislative_department"} <= OFFICIAL_PDF_ORIGINS


def test_india_code_handle_parser_accepts_whitespace_single_quotes_and_deduplicates():
    html = """
    <a href=\" /bitstream/123/456/3/act-en.pdf\" download>English</a>
    <a href=' /bitstream/123/456/4/act-hi.pdf '>Hindi</a>
    <a href=\"/bitstream/123/456/3/act-en.pdf\">duplicate</a>
    <a href=\"https://example.invalid/other.pdf\">unrelated</a>
    """
    assert india_code_pdf_links(html) == [
        "/bitstream/123/456/3/act-en.pdf",
        "/bitstream/123/456/4/act-hi.pdf",
    ]


def test_india_code_handle_parser_rejects_pages_without_bitstream_pdf():
    assert india_code_pdf_links('<a href="/handle/123/456">record</a>') == []


def test_missing_source_hash_can_never_pass_artifact_identity_gate():
    assert exact_sha_match(None, "a" * 64) is False
    assert exact_sha_match("", "a" * 64) is False
    assert exact_sha_match("b" * 64, "a" * 64) is False
    assert exact_sha_match("a" * 64, "a" * 64) is True


def test_candidate_selection_prefers_exact_hash_over_higher_text_score():
    expected = "a" * 64
    candidates = [
        {"sha": "b" * 64, "score": 0.99},
        {"sha": expected, "score": 0.91},
    ]
    assert select_act_candidate(candidates, expected) is candidates[1]


def test_candidate_selection_is_diagnostic_only_without_a_pinned_hash():
    candidates = [
        {"sha": "a" * 64, "score": 0.91},
        {"sha": "b" * 64, "score": 0.99},
    ]
    selected = select_act_candidate(candidates, None)
    assert selected is candidates[1]
    assert exact_sha_match(None, selected["sha"]) is False


def test_local_provenance_allowlist_rejects_arbitrary_file_urls():
    assert local_official_pdf_path("file:///tmp/not-an-authority.pdf") is None
    assert is_verifiable_official_source({
        "origin": "direct",
        "url": "file:///tmp/not-an-authority.pdf",
    }) is False


@pytest.mark.skipif(
    os.getenv("LAW_RAG_REAL_DB_TESTS") != "1",
    reason="set LAW_RAG_REAL_DB_TESTS=1 to exercise the local Postgres contract",
)
def test_document_scope_updates_against_real_postgres_without_persisting_rows():
    async def run() -> None:
        import asyncpg

        class RollbackFixture(Exception):
            pass

        class FailingConnection:
            def __init__(self, inner):
                self.inner = inner
                self.calls = 0

            def transaction(self):
                return self.inner.transaction()

            async def execute(self, query, values):
                self.calls += 1
                result = await self.inner.execute(query, values)
                if self.calls == 2:
                    raise RuntimeError("real chunk update failure")
                return result

        root = Path(__file__).resolve().parents[3]
        env = {}
        for line in (root / ".env").read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key] = value.strip().strip("\"'")
        conn = await asyncpg.connect(
            host="127.0.0.1",
            port=int(env.get("POSTGRES_HOST_PORT", "5433")),
            database=env["POSTGRES_DB"],
            user=env["POSTGRES_USER"],
            password=env["POSTGRES_PASSWORD"],
        )
        token = uuid.uuid4().hex
        try:
            try:
                async with conn.transaction():
                    migration_id = await conn.fetchval(
                    "SELECT migration_id FROM authority_ingest_migrations "
                    "ORDER BY migration_id LIMIT 1"
                )
                    if not migration_id:
                        pytest.fail("authority registry migration table has no rows")
                    source_id = await conn.fetchval(
                    """
                    INSERT INTO sources
                        (source_type, origin, url, canonical_url_hash, provenance_tier)
                    VALUES ('bare_act', 'direct', $1, $2, 'unverified')
                    RETURNING id
                    """,
                    f"file:///tmp/provenance-{token}.pdf",
                    hashlib.sha256(token.encode()).hexdigest(),
                )
                    document_id = await conn.fetchval(
                    """
                    INSERT INTO documents (source_id, doc_id, title)
                    VALUES ($1, $2, 'provenance integration fixture')
                    RETURNING id
                    """,
                    source_id,
                    f"provenance-integration-{token}",
                )

                    async def add_chunk(anchor, *, quarantined=False):
                        return await conn.fetchval(
                        """
                        INSERT INTO chunks
                            (document_id, source_type, anchor, text, token_count,
                             quarantined, provenance_verified)
                        VALUES ($1, 'bare_act', $2, 'fixture legal text', 3, $3, false)
                        RETURNING id
                        """,
                        document_id,
                        anchor,
                        quarantined,
                    )

                    live_chunk_id = await add_chunk("fixture/sec-1")
                    registry_chunk_id = await add_chunk("fixture/sec-2")
                    quarantined_chunk_id = await add_chunk(
                        "fixture/sec-3", quarantined=True
                    )
                    await conn.execute(
                    """
                    INSERT INTO document_authorities
                        (source_id, document_id, chunk_id, authority_id, canonical_key,
                         migration_id, record_sha256, canonical_anchor)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, '/sec-2')
                    """,
                    source_id,
                    document_id,
                    registry_chunk_id,
                    f"authority_integration_{token}",
                    f"integration_{token}",
                    migration_id,
                    hashlib.sha256(f"record-{token}".encode()).hexdigest(),
                )

                    failing_conn = FailingConnection(conn)
                    with pytest.raises(RuntimeError, match="real chunk update failure"):
                        await apply_verification_updates(
                            failing_conn,
                            [_audit(matched=True, targets=[(document_id, None)])],
                        )
                    rolled_back_state = await conn.fetch(
                        "SELECT id, provenance_verified FROM chunks "
                        "WHERE id = ANY($1::bigint[]) ORDER BY id",
                        [live_chunk_id, registry_chunk_id, quarantined_chunk_id],
                    )
                    assert all(not row["provenance_verified"] for row in rolled_back_state)
                    assert await conn.fetchval(
                        "SELECT provenance_verified FROM documents WHERE id = $1",
                        document_id,
                    ) is False

                    await apply_verification_updates(
                        conn,
                        [_audit(matched=True, targets=[(document_id, None)])],
                    )
                    state = await conn.fetch(
                    "SELECT id, provenance_verified FROM chunks "
                    "WHERE id = ANY($1::bigint[]) ORDER BY id",
                    [live_chunk_id, registry_chunk_id, quarantined_chunk_id],
                )
                    assert [(row["id"], row["provenance_verified"]) for row in state] == [
                        (live_chunk_id, True),
                        (registry_chunk_id, False),
                        (quarantined_chunk_id, False),
                    ]

                    await conn.execute(
                    "UPDATE chunks SET provenance_verified = true "
                    "WHERE id = ANY($1::bigint[])",
                    [live_chunk_id, registry_chunk_id, quarantined_chunk_id],
                )
                    await apply_verification_updates(
                        conn,
                        [_audit(matched=False, targets=[(document_id, None)])],
                    )
                    state = await conn.fetch(
                    "SELECT id, provenance_verified FROM chunks "
                    "WHERE id = ANY($1::bigint[]) ORDER BY id",
                    [live_chunk_id, registry_chunk_id, quarantined_chunk_id],
                )
                    assert [(row["id"], row["provenance_verified"]) for row in state] == [
                        (live_chunk_id, False),
                        (registry_chunk_id, True),
                        (quarantined_chunk_id, False),
                    ]
                    raise RollbackFixture
            except RollbackFixture:
                pass
            assert await conn.fetchval(
                "SELECT COUNT(*) FROM documents WHERE doc_id = $1",
                f"provenance-integration-{token}",
            ) == 0
        finally:
            await conn.close()

    asyncio.run(run())
