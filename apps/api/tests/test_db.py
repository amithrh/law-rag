from types import SimpleNamespace

import pytest

from apps.api import db


@pytest.mark.asyncio
async def test_get_pool_passes_configured_connect_timeout(monkeypatch):
    calls: list[dict[str, object]] = []
    sentinel = object()

    async def fake_create_pool(**kwargs):
        calls.append(kwargs)
        return sentinel

    monkeypatch.setattr(db.asyncpg, "create_pool", fake_create_pool)
    monkeypatch.setattr(
        db,
        "get_settings",
        lambda: SimpleNamespace(
            database_url="postgresql://lawrag:pw@localhost:5432/lawrag",
            postgres_connect_timeout_sec=2.5,
            resolved_database_url="postgresql://unused",
            resolved_database_url_host_side="postgresql://unused",
        ),
    )
    db._state.pool = None

    try:
        assert await db.get_pool() is sentinel
        assert calls == [{
            "dsn": "postgresql://lawrag:pw@localhost:5432/lawrag",
            "min_size": 2,
            "max_size": 8,
            "timeout": 2.5,
        }]
    finally:
        db._state.pool = None
