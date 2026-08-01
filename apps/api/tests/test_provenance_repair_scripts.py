from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

from scripts import quarantine_misanchored_act_chunks as quarantine_script
from scripts import repair_canonical_act_chunks as repair_script
from scripts.quarantine_misanchored_act_chunks import TARGETS
from scripts.repair_canonical_act_chunks import ACT_SPECS, _canonical_chunks


@pytest.mark.needs_eval_data
def test_canonical_act_repair_targets_are_pinned_and_complete() -> None:
    spec = ACT_SPECS["indian-succession-1925"]
    assert spec["pdf"].is_file()
    assert spec["raw_bytes_size"] == 1_144_648
    assert set(spec["expected_old_sha256"]) == set(spec["sections"])

    chunks = _canonical_chunks("indian-succession-1925")
    assert set(chunks) == {"50", "51", "54"}
    for section, replacement in chunks.items():
        assert replacement["metadata"]["canonical_repair"] is True
        assert replacement["metadata"]["canonical_artifact_sha256"] == spec["pdf_sha256"]
        assert f"Section {section}" in replacement["text"]


def test_quarantine_target_has_exact_identity_and_text_fingerprint() -> None:
    target = TARGETS["registration-1908/sec-3__3-d"]
    assert target["document_id"] == "registration-1908"
    assert target["source_url"].endswith("/A1908-16.pdf")
    assert len(target["expected_text_sha256"]) == hashlib.sha256(b"x").digest_size * 2


class _Transaction:
    def __init__(self, owner):
        self.owner = owner
        self.snapshot = None

    async def __aenter__(self):
        self.owner.transaction_started = True
        if hasattr(self.owner, "snapshot"):
            self.snapshot = self.owner.snapshot()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.owner.transaction_rolled_back = exc is not None
        if exc is not None and self.snapshot is not None:
            self.owner.restore(self.snapshot)
        return False


class _RepairConnection:
    def __init__(self, *, fail_chunk_update: bool = False, fail_document_update: bool = False):
        self.fail_chunk_update = fail_chunk_update
        self.fail_document_update = fail_document_update
        self.executed: list[tuple[str, tuple]] = []
        self.transaction_started = False
        self.transaction_rolled_back = False
        self.chunk_text: dict[str, str] = {}

    def snapshot(self):
        return dict(self.chunk_text)

    def restore(self, snapshot):
        self.chunk_text = snapshot

    def transaction(self):
        return _Transaction(self)

    async def fetch(self, query, *args):
        if "FROM sources" in query:
            return [{
                "id": 11,
                "url": "fixture-source",
                "canonical_url_hash": hashlib.sha256(b"fixture-source").hexdigest(),
                "raw_sha256": "fixture-pdf-sha",
                "raw_bytes_size": 4,
                "source_type": "bare_act",
            }]
        if "FROM documents" in query:
            return [{"id": 22, "title": "Fixture Act 2020"}]
        anchor = args[1]
        section = anchor.rsplit("-", 1)[-1]
        text = self.chunk_text.setdefault(anchor, f"old-{section}")
        return [{
            "id": int(section),
            "anchor": anchor,
            "text": text,
            "quarantined": False,
        }]

    async def execute(self, query, *args):
        self.executed.append((query, args))
        if "UPDATE chunks" in query:
            if self.fail_chunk_update:
                return "UPDATE 0"
            anchor = args[7]
            if self.chunk_text.get(anchor) != args[8]:
                return "UPDATE 0"
            self.chunk_text[anchor] = args[0]
            return "UPDATE 1"
        if self.fail_document_update:
            return "UPDATE 0"
        return "UPDATE 1"

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_repair_updates_each_exact_section_and_uses_compare_and_swap(monkeypatch):
    old = {section: f"old-{section}" for section in ("50", "51", "54")}
    fixture_spec = {
        "title": "Fixture Act 2020",
        "pdf": SimpleNamespace(),
        "pdf_sha256": "fixture-pdf-sha",
        "raw_bytes_size": 4,
        "source_url": "fixture-source",
        "sections": ("50", "51", "54"),
        "expected_old_sha256": {
            section: hashlib.sha256(text.encode()).hexdigest()
            for section, text in old.items()
        },
    }
    connection = _RepairConnection()
    monkeypatch.setattr(repair_script, "ACT_SPECS", {"fixture": fixture_spec})
    monkeypatch.setattr(
        repair_script,
        "_canonical_chunks",
        lambda _slug: {
            section: {"text": f"new-{section}", "token_count": 1, "metadata": {}}
            for section in fixture_spec["sections"]
        },
    )
    monkeypatch.setattr(
        repair_script,
        "get_settings",
        lambda: SimpleNamespace(resolved_database_url_host_side="dsn"),
    )
    async def connect(_dsn):
        return connection
    monkeypatch.setattr(repair_script.asyncpg, "connect", connect)
    monkeypatch.setattr(
        repair_script,
        "get_embedder",
        lambda: SimpleNamespace(encode_with_sparse=lambda texts: ([[0.1]], [{}])),
    )
    monkeypatch.setattr(repair_script, "embedding_to_halfvec_literal", lambda _value: "[0.1]")
    monkeypatch.setattr(repair_script, "sparse_to_jsonb", lambda _value: "{}")

    rows = await repair_script.repair("fixture")

    assert [row["action"] for row in rows] == ["repair", "repair", "repair"]
    chunk_updates = [args for query, args in connection.executed if "UPDATE chunks" in query]
    assert [args[7] for args in chunk_updates] == [
        "fixture/sec-50", "fixture/sec-51", "fixture/sec-54"
    ]
    assert all("AND text=$9" in query for query, _args in connection.executed if "UPDATE chunks" in query)
    assert connection.transaction_rolled_back is False
    assert connection.chunk_text == {
        "fixture/sec-50": "new-50",
        "fixture/sec-51": "new-51",
        "fixture/sec-54": "new-54",
    }

    no_op_rows = await repair_script.repair("fixture")
    assert [row["action"] for row in no_op_rows] == ["no_op", "no_op", "no_op"]
    assert len([1 for query, _args in connection.executed if "UPDATE chunks" in query]) == 3


@pytest.mark.asyncio
async def test_repair_rolls_back_when_compare_and_swap_fails(monkeypatch):
    section = "50"
    old = "old-50"
    fixture_spec = {
        "title": "Fixture Act 2020",
        "pdf": SimpleNamespace(),
        "pdf_sha256": "fixture-pdf-sha",
        "raw_bytes_size": 4,
        "source_url": "fixture-source",
        "sections": (section,),
        "expected_old_sha256": {section: hashlib.sha256(old.encode()).hexdigest()},
    }
    connection = _RepairConnection(fail_chunk_update=True)
    monkeypatch.setattr(repair_script, "ACT_SPECS", {"fixture": fixture_spec})
    monkeypatch.setattr(
        repair_script,
        "_canonical_chunks",
        lambda _slug: {section: {"text": "new-50", "token_count": 1, "metadata": {}}},
    )
    monkeypatch.setattr(
        repair_script,
        "get_settings",
        lambda: SimpleNamespace(resolved_database_url_host_side="dsn"),
    )
    async def connect(_dsn):
        return connection
    monkeypatch.setattr(repair_script.asyncpg, "connect", connect)
    monkeypatch.setattr(
        repair_script,
        "get_embedder",
        lambda: SimpleNamespace(encode_with_sparse=lambda texts: ([[0.1]], [{}])),
    )
    monkeypatch.setattr(repair_script, "embedding_to_halfvec_literal", lambda _value: "[0.1]")
    monkeypatch.setattr(repair_script, "sparse_to_jsonb", lambda _value: "{}")

    with pytest.raises(RuntimeError, match="changed during transaction"):
        await repair_script.repair("fixture")
    assert connection.transaction_rolled_back is True


@pytest.mark.asyncio
async def test_repair_rolls_back_chunk_state_when_document_update_fails(monkeypatch):
    section = "50"
    old = "old-50"
    fixture_spec = {
        "title": "Fixture Act 2020",
        "pdf": SimpleNamespace(),
        "pdf_sha256": "fixture-pdf-sha",
        "raw_bytes_size": 4,
        "source_url": "fixture-source",
        "sections": (section,),
        "expected_old_sha256": {section: hashlib.sha256(old.encode()).hexdigest()},
    }
    connection = _RepairConnection(fail_document_update=True)
    monkeypatch.setattr(repair_script, "ACT_SPECS", {"fixture": fixture_spec})
    monkeypatch.setattr(
        repair_script,
        "_canonical_chunks",
        lambda _slug: {section: {"text": "new-50", "token_count": 1, "metadata": {}}},
    )
    monkeypatch.setattr(
        repair_script,
        "get_settings",
        lambda: SimpleNamespace(resolved_database_url_host_side="dsn"),
    )
    async def connect(_dsn):
        return connection
    monkeypatch.setattr(repair_script.asyncpg, "connect", connect)
    monkeypatch.setattr(
        repair_script,
        "get_embedder",
        lambda: SimpleNamespace(encode_with_sparse=lambda texts: ([[0.1]], [{}])),
    )
    monkeypatch.setattr(repair_script, "embedding_to_halfvec_literal", lambda _value: "[0.1]")
    monkeypatch.setattr(repair_script, "sparse_to_jsonb", lambda _value: "{}")

    with pytest.raises(RuntimeError, match="document state update failed"):
        await repair_script.repair("fixture")
    assert connection.transaction_rolled_back is True
    assert connection.chunk_text == {"fixture/sec-50": "old-50"}


class _QuarantineConnection:
    def __init__(self, *, fail_update: bool = False):
        self.fail_update = fail_update
        self.transaction_rolled_back = False
        self.executed: list[tuple[str, tuple]] = []
        self.quarantined = False

    def snapshot(self):
        return self.quarantined

    def restore(self, snapshot):
        self.quarantined = snapshot

    def transaction(self):
        return _Transaction(self)

    async def fetch(self, _query, *_args):
        return [{
            "id": 99,
            "document_id": 88,
            "anchor": "fixture/sec-3",
            "text": "fixture text",
            "quarantined": self.quarantined,
        }]

    async def execute(self, query, *args):
        self.executed.append((query, args))
        if self.fail_update:
            return "UPDATE 0"
        if "UPDATE chunks" in query:
            self.quarantined = True
        return "UPDATE 1"

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_quarantine_rolls_back_when_exact_target_changes(monkeypatch):
    anchor = "fixture/sec-3"
    target = {
        "document_id": "fixture-doc",
        "source_url": "fixture-source",
        "expected_text_sha256": hashlib.sha256(b"fixture text").hexdigest(),
        "reason": "fixture quarantine",
    }
    connection = _QuarantineConnection(fail_update=True)
    monkeypatch.setattr(quarantine_script, "TARGETS", {anchor: target})
    monkeypatch.setattr(
        quarantine_script,
        "get_settings",
        lambda: SimpleNamespace(resolved_database_url_host_side="dsn"),
    )
    async def connect(_dsn):
        return connection
    monkeypatch.setattr(quarantine_script.asyncpg, "connect", connect)

    with pytest.raises(RuntimeError, match="changed during transaction"):
        await quarantine_script.quarantine(anchor)
    assert connection.transaction_rolled_back is True


@pytest.mark.asyncio
async def test_quarantine_is_exact_and_repeat_is_no_op(monkeypatch):
    anchor = "fixture/sec-3"
    target = {
        "document_id": "fixture-doc",
        "source_url": "fixture-source",
        "expected_text_sha256": hashlib.sha256(b"fixture text").hexdigest(),
        "reason": "fixture quarantine",
    }
    connection = _QuarantineConnection()
    monkeypatch.setattr(quarantine_script, "TARGETS", {anchor: target})
    monkeypatch.setattr(
        quarantine_script,
        "get_settings",
        lambda: SimpleNamespace(resolved_database_url_host_side="dsn"),
    )
    async def connect(_dsn):
        return connection
    monkeypatch.setattr(quarantine_script.asyncpg, "connect", connect)

    result = await quarantine_script.quarantine(anchor)
    assert result["action"] == "quarantine"
    assert connection.quarantined is True
    update_query, update_args = connection.executed[0]
    assert "AND document_id=$3" in update_query
    assert "AND anchor=$4" in update_query
    assert "AND text=$5" in update_query
    assert update_args[2:] == (88, anchor, "fixture text")

    no_op = await quarantine_script.quarantine(anchor)
    assert no_op["action"] == "no_op"
    assert len(connection.executed) == 2
