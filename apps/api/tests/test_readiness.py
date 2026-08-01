from types import SimpleNamespace

import pytest
from starlette.responses import JSONResponse

from apps.api import main as api_main


class _Acquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Pool:
    def __init__(self, chunks: int, documents: int):
        self.queries: list[str] = []

        async def fetchval(sql: str):
            self.queries.append(sql)
            return chunks if len(self.queries) == 1 else documents

        self.connection = SimpleNamespace(fetchval=fetchval)

    def acquire(self):
        return _Acquire(self.connection)


async def _ready_pool(chunks: int, documents: int):
    return _Pool(chunks, documents)


@pytest.mark.asyncio
async def test_readyz_returns_ready_for_non_empty_corpus(monkeypatch):
    monkeypatch.setattr(api_main, "get_pool", lambda: _ready_pool(12, 3))

    body = await api_main.readyz()

    assert body["status"] == "ready"
    assert body["chunks"] == 12
    assert body["documents"] == 3
    assert body["build_fingerprint"]


@pytest.mark.asyncio
async def test_readiness_queries_only_production_eligible_corpus(monkeypatch):
    # The readiness contract must not be satisfied by the unverified CI seed
    # or by a merely live, non-quarantined chunk.
    observed = _Pool(12, 3)

    async def observed_pool():
        return observed

    monkeypatch.setattr(api_main, "get_pool", observed_pool)
    await api_main.readyz()
    assert len(observed.queries) == 2
    assert all("provenance_verified = true" in query for query in observed.queries)
    assert all("NOT c.quarantined" in query for query in observed.queries)


@pytest.mark.asyncio
async def test_readyz_rejects_empty_corpus(monkeypatch):
    monkeypatch.setattr(api_main, "get_pool", lambda: _ready_pool(0, 3))

    response = await api_main.readyz()

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    assert response.body == b'{"status":"not_ready","dependency":"corpus","reason":"corpus_empty","chunks":0,"documents":3}'


@pytest.mark.asyncio
async def test_deep_readyz_rejects_unavailable_model(monkeypatch):
    monkeypatch.setattr(api_main, "get_pool", lambda: _ready_pool(12, 3))

    async def unavailable(_model=None):
        return {"ok": False}

    monkeypatch.setattr(api_main, "check_model_available", unavailable)
    monkeypatch.setattr(
        api_main,
        "get_model_warmup_state",
        lambda: {"enabled": False, "ready": False},
    )

    response = await api_main.readyz(deep=True)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    assert response.body == b'{"status":"not_ready","dependency":"llm","reason":"model_unavailable"}'


@pytest.mark.asyncio
async def test_deep_readyz_rejects_model_warmup(monkeypatch):
    monkeypatch.setattr(api_main, "get_pool", lambda: _ready_pool(12, 3))

    async def available(_model=None):
        return {"ok": True}

    monkeypatch.setattr(api_main, "check_model_available", available)
    monkeypatch.setattr(
        api_main,
        "get_model_warmup_state",
        lambda: {"enabled": True, "ready": False},
    )

    response = await api_main.readyz(deep=True)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    assert response.body == b'{"status":"not_ready","dependency":"llm","reason":"model_warming"}'


@pytest.mark.asyncio
async def test_readyz_hides_database_failure(monkeypatch):
    async def unavailable():
        raise TimeoutError("secret DSN must not escape")

    monkeypatch.setattr(api_main, "get_pool", unavailable)

    response = await api_main.readyz()

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    assert response.body == b'{"status":"not_ready","dependency":"postgres","reason":"database_unavailable"}'


@pytest.mark.asyncio
async def test_healthz_hides_database_failure(monkeypatch):
    async def unavailable():
        raise TimeoutError("secret DSN must not escape")

    monkeypatch.setattr(api_main, "get_pool", unavailable)

    response = await api_main.healthz()

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    assert response.body == b'{"status":"degraded","dependency":"postgres","reason":"database_unavailable"}'


@pytest.mark.asyncio
async def test_healthz_deep_redacts_model_and_warmup_diagnostics(monkeypatch):
    from apps.api import main as api_main

    async def counts():
        return 12, 3

    async def model(_model=None):
        return {
            "ok": False,
            "model": "private-model-name",
            "available_models": ["private-model-name", "another-private-model"],
            "error": "secret provider URL and token",
            "message": "raw warmup exception",
        }

    monkeypatch.setattr(api_main, "_corpus_counts", counts)
    monkeypatch.setattr(api_main, "check_model_available", model)
    monkeypatch.setattr(
        api_main,
        "get_model_warmup_state",
        lambda: {
            "enabled": True,
            "ready": False,
            "error": "secret warmup traceback",
            "model": "private-model-name",
        },
    )

    body = await api_main.healthz(deep=True)

    assert body["status"] == "degraded"
    assert body["llm"] == {"status": "unavailable"}
    assert body["model_warmup"] == {
        "enabled": True,
        "ready": False,
        "status": "pending",
    }
    rendered = str(body)
    assert "private-model-name" not in rendered
    assert "secret" not in rendered
    assert "traceback" not in rendered


@pytest.mark.asyncio
async def test_lifespan_closes_pool_when_model_prewarm_fails(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        api_main.cfg,
        "get_settings",
        lambda: SimpleNamespace(environment="development", answer_api_key=""),
    )

    async def fake_get_pool():
        calls.append("get_pool")

    async def failed_prewarm(_settings):
        calls.append("prewarm")
        raise RuntimeError("model unavailable")

    async def fake_close_pool():
        calls.append("close_pool")

    monkeypatch.setattr(api_main, "get_pool", fake_get_pool)
    monkeypatch.setattr(api_main, "prewarm_models", failed_prewarm)
    monkeypatch.setattr(api_main, "close_pool", fake_close_pool)

    with pytest.raises(RuntimeError, match="model unavailable"):
        async with api_main.lifespan(None):
            raise AssertionError("startup should not yield")

    assert calls == ["get_pool", "prewarm", "close_pool"]
