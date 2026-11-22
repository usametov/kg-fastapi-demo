"""Pick the StateStore implementation from settings (STATE_BACKEND)."""

from __future__ import annotations

from app.config import Settings
from app.state.base import StateStore


def build_state_store(settings: Settings) -> StateStore:
    if settings.state_backend == "redis":
        from app.state.redis_store import RedisStateStore

        return RedisStateStore.from_url(settings.redis_url, settings.state_ttl_seconds)
    from app.state.memory import MemoryStateStore

    return MemoryStateStore()
