"""Concurrency and admission-control contracts for the streamed answer API."""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse


def _request(path: str = "/search", headers: list[tuple[str, str]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [
                (name.lower().encode(), value.encode())
                for name, value in (headers or [])
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 8056),
            "scheme": "http",
        }
    )


@pytest.mark.asyncio
async def test_admission_queues_a_short_burst_until_stream_finishes(monkeypatch):
    import apps.api.config as cfg
    import apps.api.main as main

    settings = cfg.get_settings()
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "answer_api_key", "")
    monkeypatch.setattr(settings, "answer_max_concurrent", 1)
    monkeypatch.setattr(settings, "answer_max_waiters", 2)
    monkeypatch.setattr(settings, "answer_admission_wait_ms", 250)
    monkeypatch.setattr(settings, "answer_rate_limit_per_minute", 100)
    monkeypatch.setattr(main, "_answer_admission_controller", None)

    release_first = asyncio.Event()
    calls = 0

    async def first_body():
        await release_first.wait()
        yield b"first"

    async def call_next(_request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return StreamingResponse(first_body())
        return Response("second")

    first = await main.answer_admission_control(_request(), call_next)
    second_task = asyncio.create_task(
        main.answer_admission_control(_request(), call_next)
    )
    await asyncio.sleep(0.03)
    assert not second_task.done(), "the second request should wait, not fail immediately"

    async def consume_first():
        return [chunk async for chunk in first.body_iterator]

    consume_task = asyncio.create_task(consume_first())
    await asyncio.sleep(0.03)
    release_first.set()
    assert await consume_task == [b"first"]

    second = await asyncio.wait_for(second_task, timeout=0.5)
    assert second.status_code == 200
    assert calls == 2


@pytest.mark.asyncio
async def test_admission_returns_bounded_busy_response_after_wait_budget(monkeypatch):
    import apps.api.config as cfg
    import apps.api.main as main

    settings = cfg.get_settings()
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "answer_api_key", "")
    monkeypatch.setattr(settings, "answer_max_concurrent", 1)
    monkeypatch.setattr(settings, "answer_max_waiters", 0)
    monkeypatch.setattr(settings, "answer_admission_wait_ms", 5)
    monkeypatch.setattr(settings, "answer_rate_limit_per_minute", 100)
    monkeypatch.setattr(main, "_answer_admission_controller", None)

    release_first = asyncio.Event()
    calls = 0

    async def first_body():
        await release_first.wait()
        yield b"first"

    async def call_next(_request):
        nonlocal calls
        calls += 1
        return StreamingResponse(first_body()) if calls == 1 else Response("second")

    first = await main.answer_admission_control(_request(), call_next)
    second = await main.answer_admission_control(_request(), call_next)
    assert second.status_code == 429
    assert second.headers["retry-after"] == "1"
    assert calls == 1

    release_first.set()
    _ = [chunk async for chunk in first.body_iterator]


@pytest.mark.asyncio
async def test_admission_rejects_only_after_waiter_cap_is_reached(monkeypatch):
    import apps.api.config as cfg
    import apps.api.main as main

    settings = cfg.get_settings()
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "answer_api_key", "")
    monkeypatch.setattr(settings, "answer_max_concurrent", 1)
    monkeypatch.setattr(settings, "answer_max_waiters", 1)
    monkeypatch.setattr(settings, "answer_admission_wait_ms", 250)
    monkeypatch.setattr(settings, "answer_rate_limit_per_minute", 100)
    monkeypatch.setattr(main, "_answer_admission_controller", None)

    release_first = asyncio.Event()
    calls = 0

    async def first_body():
        await release_first.wait()
        yield b"first"

    async def call_next(_request):
        nonlocal calls
        calls += 1
        return StreamingResponse(first_body()) if calls == 1 else Response("ok")

    first = await main.answer_admission_control(_request(), call_next)
    queued = asyncio.create_task(main.answer_admission_control(_request(), call_next))
    for _ in range(20):
        if main._answer_admission_controller._waiting >= 1:
            break
        await asyncio.sleep(0.005)
    third = await main.answer_admission_control(_request(), call_next)
    assert third.status_code == 429
    assert calls == 1

    async def consume_first():
        return [chunk async for chunk in first.body_iterator]

    consume_task = asyncio.create_task(consume_first())
    release_first.set()
    assert await consume_task == [b"first"]
    assert (await asyncio.wait_for(queued, timeout=0.5)).status_code == 200


def test_admission_defaults_are_bounded_and_burst_tolerant():
    from apps.api.config import Settings

    settings = Settings()
    assert settings.answer_max_concurrent == 4
    assert settings.answer_max_waiters == 32
    assert settings.answer_admission_wait_ms == 60_000
    assert settings.answer_admission_wait_ms <= 300_000


@pytest.mark.asyncio
async def test_distributed_admission_uses_redis_lease_and_releases_it(monkeypatch):
    import redis.asyncio as redis

    from apps.api.admission import AdmissionController
    from apps.api.config import Settings

    class FakeRedis:
        def __init__(self):
            self.eval_calls = 0
            self.released = []
            self.closed = False

        async def ping(self):
            return True

        async def eval(self, *_args):
            self.eval_calls += 1
            return 1

        async def zadd(self, *_args):
            return 1

        async def pexpire(self, *_args):
            return True

        async def zrem(self, _key, token):
            self.released.append(token)
            return 1

        async def aclose(self):
            self.closed = True

    fake = FakeRedis()
    monkeypatch.setattr(redis, "from_url", lambda *args, **kwargs: fake)
    settings = Settings(
        database_url="postgresql://x",
        answer_distributed_admission=True,
        answer_admission_wait_ms=100,
    )
    controller = AdmissionController(settings)
    await controller.start()
    decision = await controller.acquire(
        "session:test",
        max_concurrent=1,
        max_waiters=1,
        wait_ms=100,
        rate_limit_per_minute=10,
        lease_seconds=30,
    )
    assert decision.lease is not None
    assert fake.eval_calls == 2
    await decision.lease.release()
    assert len(fake.released) == 2  # waiting-set cleanup plus active lease release
    assert fake.released[0] == fake.released[1]
    await controller.close()
    assert fake.closed is True


@pytest.mark.asyncio
async def test_distributed_admission_fails_closed_when_redis_is_unavailable(monkeypatch):
    import redis.asyncio as redis

    from apps.api.admission import AdmissionController, AdmissionUnavailable
    from apps.api.config import Settings

    class BrokenRedis:
        async def ping(self):
            raise OSError("redis is down")

        async def aclose(self):
            return None

    monkeypatch.setattr(redis, "from_url", lambda *args, **kwargs: BrokenRedis())
    controller = AdmissionController(
        Settings(database_url="postgresql://x", answer_distributed_admission=True)
    )
    with pytest.raises(AdmissionUnavailable):
        await controller.start()


@pytest.mark.skipif(
    os.environ.get("LAW_RAG_REAL_REDIS_TESTS") != "1",
    reason="set LAW_RAG_REAL_REDIS_TESTS=1 for a live Redis contract",
)
@pytest.mark.asyncio
async def test_live_redis_admission_queues_and_releases():
    from apps.api.admission import AdmissionController
    from apps.api.config import Settings

    prefix = f"law-rag:test-admission:{uuid.uuid4().hex}"
    settings = Settings(
        database_url="postgresql://x",
        answer_distributed_admission=True,
        answer_admission_redis_prefix=prefix,
    )
    controller = AdmissionController(settings)
    await controller.start()
    first = await controller.acquire(
        "live-client",
        max_concurrent=1,
        max_waiters=1,
        wait_ms=1000,
        rate_limit_per_minute=100,
        lease_seconds=30,
    )
    assert first.lease is not None
    second_task = asyncio.create_task(
        controller.acquire(
            "live-client-2",
            max_concurrent=1,
            max_waiters=1,
            wait_ms=1000,
            rate_limit_per_minute=100,
            lease_seconds=30,
        )
    )
    await asyncio.sleep(0.05)
    assert not second_task.done()
    await first.lease.release()
    second = await second_task
    assert second.lease is not None
    await second.lease.release()
    await controller.close()


def test_client_identity_requires_a_signed_proxy_session_or_trusted_ip():
    import hashlib
    import hmac

    from apps.api.admission import request_client_key, request_client_keys
    from apps.api.config import Settings

    secret = "test-secret"
    client_id = "client-1234567890"
    signature = hmac.new(secret.encode(), client_id.encode(), hashlib.sha256).hexdigest()
    settings = Settings(
        database_url="postgresql://x",
        answer_api_key=secret,
        answer_trusted_proxy_ips="10.0.0.2",
    )

    signed = _request(
        headers=[("X-Answer-Client", f"{client_id}.{signature}")]
    )
    assert request_client_key(signed, settings) == f"session:{client_id}"
    assert request_client_keys(signed, settings) == (
        f"session:{client_id}",
        "ip:127.0.0.1",
    )

    forged = _request(headers=[("X-Answer-Client", f"{client_id}.bad")])
    assert request_client_key(forged, settings) == "ip:127.0.0.1"

    forwarded = Request(
        {
            **_request().scope,
            "client": ("10.0.0.2", 12345),
            "headers": [(b"x-forwarded-for", b"203.0.113.7, 10.0.0.2")],
        }
    )
    assert request_client_key(forwarded, settings) == "ip:203.0.113.7"
