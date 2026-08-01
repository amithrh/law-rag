"""asyncpg connection pool — created on app startup, closed on shutdown."""
from __future__ import annotations

import asyncpg

from apps.api.config import get_settings


class _State:
    pool: asyncpg.Pool | None = None


_state = _State()


async def get_pool() -> asyncpg.Pool:
    if _state.pool is None:
        s = get_settings()
        # If DATABASE_URL is explicitly set, trust the caller.
        # Otherwise pick the right form based on where the API is running:
        #   - inside docker network (env API_IN_DOCKER=1 set by prod compose)
        #     → use service-name URL
        #   - else (host-side dev) → localhost:host_port
        import os
        if s.database_url:
            dsn = s.database_url
        elif os.environ.get("API_IN_DOCKER") == "1":
            dsn = s.resolved_database_url
        else:
            dsn = s.resolved_database_url_host_side
        _state.pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=2,
            max_size=8,
            timeout=min(max(float(s.postgres_connect_timeout_sec), 0.1), 60.0),
        )
    return _state.pool


async def close_pool() -> None:
    if _state.pool is not None:
        await _state.pool.close()
        _state.pool = None
