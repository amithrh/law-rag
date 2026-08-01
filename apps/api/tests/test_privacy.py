from __future__ import annotations

import asyncio

from apps.api import config as config_module
from apps.api import query_expand
from apps.api.privacy import query_fingerprint


def test_query_fingerprint_is_stable_without_exposing_query_text():
    secret = "my Aadhaar 999988887777 and private medical history"
    fingerprint = query_fingerprint(secret)

    assert len(fingerprint) == 16
    assert secret not in fingerprint
    assert query_fingerprint("  my   Aadhaar 999988887777 and private medical history ") == fingerprint


def test_query_expansion_logs_only_fingerprint(monkeypatch, caplog):
    secret = "my bank account 998877665544 is frozen and my medical records are private"
    settings = config_module.get_settings()
    monkeypatch.setattr(settings, "query_expansion_llm_enabled", True)
    monkeypatch.setattr(query_expand, "_route_variants", lambda *args, **kwargs: [])

    async def fake_chat_once(*args, **kwargs):
        return "bank account freeze complaint"

    monkeypatch.setattr(query_expand, "chat_once", fake_chat_once)
    caplog.set_level("INFO", logger="apps.api.query_expand")

    asyncio.run(query_expand.expand_query(secret, max_variants=1))

    assert secret not in caplog.text
    assert "query_hash=" in caplog.text
