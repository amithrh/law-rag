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
        # API runs on the host (outside docker), so always connect to localhost
        # at the mapped host port. Inside docker we'd use s.postgres_host.
        _state.pool = await asyncpg.create_pool(
            host="localhost",
            port=s.postgres_host_port,
            database=s.postgres_db,
            user=s.postgres_user,
            password=s.postgres_password,
            min_size=2,
            max_size=8,
        )
    return _state.pool


async def close_pool() -> None:
    if _state.pool is not None:
        await _state.pool.close()
        _state.pool = None
