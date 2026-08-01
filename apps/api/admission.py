"""Bounded admission control for expensive streamed answer requests.

Development uses an in-process controller so the local browser stays simple.
Production uses Redis leases so multiple API workers/replicas share the same
concurrency and rate-limit budget instead of silently multiplying it.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


_RATE_SCRIPT = """
local key = KEYS[1]
local cutoff = tonumber(ARGV[1])
local now = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
if redis.call('ZCARD', key) >= limit then
  return 0
end
redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, 61000)
return 1
"""

_LEASE_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local expiry = tonumber(ARGV[3])
local member = ARGV[4]
local waiting_key = KEYS[2]
local head = redis.call('ZRANGE', waiting_key, 0, 0)[1]
if head and head ~= member then
  return 0
end
redis.call('ZREMRANGEBYSCORE', key, '-inf', now)
if redis.call('ZCARD', key) >= limit then
  return 0
end
redis.call('ZADD', key, expiry, member)
redis.call('PEXPIRE', key, math.max(1000, expiry - now))
return 1
"""

_REFRESH_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local expiry = tonumber(ARGV[2])
local member = ARGV[3]
local current = redis.call('ZSCORE', key, member)
if not current or tonumber(current) <= now then
  return 0
end
redis.call('ZADD', key, expiry, member)
redis.call('PEXPIRE', key, math.max(1000, expiry - now))
return 1
"""

_WAIT_REGISTER_SCRIPT = """
local key = KEYS[1]
local cutoff = tonumber(ARGV[1])
local now = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
local ttl = tonumber(ARGV[5])
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
if redis.call('ZCARD', key) >= limit then
  return 0
end
redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, ttl)
return 1
"""


class AdmissionUnavailable(RuntimeError):
    """The configured distributed admission backend cannot be reached."""


@dataclass
class AdmissionLease:
    _release_callback: Callable[[], Awaitable[None]]
    _released: bool = False
    _release_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    async def release(self) -> None:
        async with self._release_lock:
            if self._released:
                return
            await self._release_callback()
            self._released = True


@dataclass(frozen=True)
class AdmissionDecision:
    lease: AdmissionLease | None
    status_code: int | None = None
    reason: str | None = None


class AdmissionController:
    def __init__(self, settings: Any):
        self.settings = settings
        self._condition = asyncio.Condition()
        self._active = 0
        self._waiting = 0
        self._rate_lock = asyncio.Lock()
        self._rate_windows: dict[str, deque[float]] = defaultdict(deque)
        self._redis: Any | None = None
        self._started = False

    @property
    def distributed(self) -> bool:
        return self._redis is not None

    async def start(self) -> None:
        if self._started:
            return
        if getattr(self.settings, "answer_distributed_admission", False):
            try:
                import redis.asyncio as redis

                self._redis = redis.from_url(
                    self.settings.resolved_redis_url,
                    db=self.settings.redis_db,
                    decode_responses=False,
                    socket_connect_timeout=self.settings.redis_connect_timeout_sec,
                    socket_timeout=self.settings.redis_connect_timeout_sec,
                )
                await self._redis.ping()
            except Exception as exc:  # pragma: no cover - exercised in prod
                await self.close()
                raise AdmissionUnavailable(
                    "distributed answer admission backend is unavailable"
                ) from exc
        self._started = True

    async def close(self) -> None:
        redis_client = self._redis
        self._redis = None
        self._started = False
        if redis_client is not None:
            close = getattr(redis_client, "aclose", None)
            if close is None:
                close = getattr(redis_client, "close", None)
            if close is not None:
                result = close()
                if result is not None:
                    await result

    async def acquire(
        self,
        client_key: str | tuple[str, ...],
        *,
        max_concurrent: int,
        max_waiters: int,
        wait_ms: int,
        rate_limit_per_minute: int,
        lease_seconds: int,
        network_rate_limit_per_minute: int | None = None,
    ) -> AdmissionDecision:
        rate_keys = (client_key,) if isinstance(client_key, str) else client_key
        rate_limits = [rate_limit_per_minute] * len(rate_keys)
        if network_rate_limit_per_minute is not None and len(rate_keys) > 1:
            rate_limits[-1] = network_rate_limit_per_minute
        if self._redis is not None:
            try:
                for key, limit in zip(rate_keys, rate_limits):
                    if not await self._allow_redis_rate(key, limit):
                        return AdmissionDecision(None, 429, "rate_limit")
                return await self._acquire_redis_lease(
                    max_concurrent=max_concurrent,
                    max_waiters=max_waiters,
                    wait_ms=wait_ms,
                    lease_seconds=lease_seconds,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise AdmissionUnavailable(
                    "distributed answer admission backend is unavailable"
                ) from exc

        for key, limit in zip(rate_keys, rate_limits):
            if not await self._allow_local_rate(key, limit):
                return AdmissionDecision(None, 429, "rate_limit")
        return await self._acquire_local_lease(
            max_concurrent=max_concurrent,
            max_waiters=max_waiters,
            wait_ms=wait_ms,
        )

    async def _allow_local_rate(self, client_key: str, limit: int) -> bool:
        now = time.monotonic()
        async with self._rate_lock:
            window = self._rate_windows[client_key]
            cutoff = now - 60.0
            while window and window[0] <= cutoff:
                window.popleft()
            if not window:
                self._rate_windows.pop(client_key, None)
                window = self._rate_windows[client_key]
            if len(window) >= limit:
                return False
            window.append(now)
            # Opportunistically evict inactive identities once the map is
            # large. This keeps local development bounded without scanning on
            # every request.
            if len(self._rate_windows) > 1024:
                for key, candidate in list(self._rate_windows.items()):
                    while candidate and candidate[0] <= cutoff:
                        candidate.popleft()
                    if not candidate:
                        self._rate_windows.pop(key, None)
            return True

    async def _acquire_local_lease(
        self, *, max_concurrent: int, max_waiters: int, wait_ms: int
    ) -> AdmissionDecision:
        async with self._condition:
            if self._active < max_concurrent:
                self._active += 1
            else:
                if self._waiting >= max_waiters:
                    return AdmissionDecision(None, 429, "busy")
                self._waiting += 1
                try:
                    await asyncio.wait_for(
                        self._condition.wait_for(
                            lambda: self._active < max_concurrent
                        ),
                        timeout=max(wait_ms, 1) / 1000,
                    )
                    self._active += 1
                except TimeoutError:
                    return AdmissionDecision(None, 429, "busy")
                finally:
                    self._waiting -= 1

        return AdmissionDecision(AdmissionLease(self._release_local))

    async def _release_local(self) -> None:
        async with self._condition:
            if self._active > 0:
                self._active -= 1
            self._condition.notify(1)

    def _redis_key(self, suffix: str) -> str:
        return f"{self.settings.answer_admission_redis_prefix}:{suffix}"

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    async def _allow_redis_rate(self, client_key: str, limit: int) -> bool:
        now_ms = int(time.time() * 1000)
        token = uuid.uuid4().hex
        result = await self._redis.eval(
            _RATE_SCRIPT,
            1,
            self._redis_key(f"rate:{self._digest(client_key)}"),
            now_ms - 60_000,
            now_ms,
            limit,
            token,
        )
        return int(result) == 1

    async def _acquire_redis_lease(
        self,
        *,
        max_concurrent: int,
        max_waiters: int,
        wait_ms: int,
        lease_seconds: int,
    ) -> AdmissionDecision:
        token = uuid.uuid4().hex
        key = self._redis_key("active")
        waiting_key = self._redis_key("waiting")
        deadline = time.monotonic() + max(wait_ms, 1) / 1000
        local_registered = False
        try:
            # Take an immediately available slot without consuming a waiter.
            if await self._try_redis_lease(
                key, waiting_key, token, max_concurrent, lease_seconds
            ):
                return await self._make_redis_decision(key, token, lease_seconds)

            async with self._condition:
                if self._waiting >= max_waiters:
                    return AdmissionDecision(None, 429, "busy")
                self._waiting += 1
                local_registered = True
            now_ms = int(time.time() * 1000)
            registered = await self._redis.eval(
                _WAIT_REGISTER_SCRIPT,
                1,
                waiting_key,
                now_ms - max(wait_ms, 1000) - 1000,
                now_ms,
                max_waiters,
                token,
                max(wait_ms, 1000) + 1000,
            )
            if int(registered) != 1:
                return AdmissionDecision(None, 429, "busy")

            while True:
                if await self._try_redis_lease(
                    key, waiting_key, token, max_concurrent, lease_seconds
                ):
                    return await self._make_redis_decision(key, token, lease_seconds)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return AdmissionDecision(None, 429, "busy")
                await asyncio.sleep(min(0.25, remaining))
        finally:
            cancellation: asyncio.CancelledError | None = None
            cleanup = asyncio.create_task(
                self._remove_waiting_token(waiting_key, token)
            )
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError as exc:
                # Let the Redis cleanup finish independently, but never skip
                # the local waiter decrement or swallow request cancellation.
                cancellation = exc
            finally:
                if local_registered:
                    async with self._condition:
                        self._waiting -= 1
            if cancellation is not None:
                raise cancellation

    async def _remove_waiting_token(self, waiting_key: str, token: str) -> None:
        try:
            await self._redis.zrem(waiting_key, token)
        except Exception:
            return

    async def _try_redis_lease(
        self,
        key: str,
        waiting_key: str,
        token: str,
        max_concurrent: int,
        lease_seconds: int,
    ) -> bool:
        now_ms = int(time.time() * 1000)
        expiry_ms = now_ms + lease_seconds * 1000
        result = await self._redis.eval(
            _LEASE_SCRIPT,
            2,
            key,
            waiting_key,
            now_ms,
            max_concurrent,
            expiry_ms,
            token,
        )
        return int(result) == 1

    async def _make_redis_decision(
        self, key: str, token: str, lease_seconds: int
    ) -> AdmissionDecision:
        redis_client = self._redis
        heartbeat = asyncio.create_task(
            self._refresh_redis_lease(
                redis_client, key, token, lease_seconds, asyncio.current_task()
            )
        )
        return AdmissionDecision(
            AdmissionLease(
                lambda: self._release_redis_lease(
                    redis_client, key, token, heartbeat
                )
            )
        )

    async def _refresh_redis_lease(
        self,
        redis_client: Any,
        key: str,
        token: str,
        lease_seconds: int,
        owner_task: asyncio.Task | None,
    ) -> None:
        interval = max(1.0, lease_seconds / 3)
        try:
            while True:
                await asyncio.sleep(interval)
                now_ms = int(time.time() * 1000)
                refreshed = await redis_client.eval(
                    _REFRESH_SCRIPT,
                    1,
                    key,
                    now_ms,
                    now_ms + lease_seconds * 1000,
                    token,
                )
                if int(refreshed) != 1:
                    if owner_task is not None and not owner_task.done():
                        owner_task.cancel()
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            # Continuing after lease loss would allow another replica to run
            # the same slot concurrently. Cancel the owner so its SSE finally
            # block releases the lease and the user receives a safe stream
            # failure instead of unbounded work.
            if owner_task is not None and not owner_task.done():
                owner_task.cancel()
            return

    async def _release_redis_lease(
        self, redis_client: Any, key: str, token: str, heartbeat: asyncio.Task
    ) -> None:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)
        try:
            await redis_client.zrem(key, token)
        except Exception:
            # Expiry is the recovery path if shutdown races the release.
            return


def _network_client_key(request: Any, settings: Any) -> str:
    host = request.client.host if request.client else "unknown"
    trusted = {
        item.strip()
        for item in settings.answer_trusted_proxy_ips.split(",")
        if item.strip()
    }
    if host in trusted:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            first_hop = forwarded.split(",", 1)[0].strip()
            return f"ip:{first_hop}"
        real_ip = request.headers.get("x-real-ip", "").strip()
        if real_ip:
            return f"ip:{real_ip}"
    return f"ip:{host}"


def request_client_keys(request: Any, settings: Any) -> tuple[str, ...]:
    """Return session plus network keys for layered abuse protection."""
    network_key = _network_client_key(request, settings)
    if settings.answer_api_key:
        client_header = request.headers.get(settings.answer_client_id_header, "")
        if client_header:
            client_id, separator, signature = client_header.partition(".")
            expected = hmac.new(
                settings.answer_api_key.encode("utf-8"),
                client_id.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            if (
                separator
                and 16 <= len(client_id) <= 64
                and hmac.compare_digest(signature, expected)
            ):
                return (f"session:{client_id}", network_key)
    return (network_key,)


def request_client_key(request: Any, settings: Any) -> str:
    """Backward-compatible single-key helper for callers outside admission."""
    return request_client_keys(request, settings)[0]
