"""Redis-backed StateStore (STATE_BACKEND=redis, REDIS_URL=redis://...).

Layout:
    kg:session:<id>   JSON SessionRecord, with TTL (STATE_TTL_SECONDS)
    kg:job:<id>       JSON Job, with TTL
    kg:jobs:queue     LIST of job ids; API LPUSHes, worker BRPOPs

Redis is an attached resource (Factor IV): point REDIS_URL at a local
container, ElastiCache, Upstash... without code changes.
"""

from __future__ import annotations

import redis.asyncio as redis

from app.domain.models import Job, utcnow
from app.state.base import SessionRecord, StateStore

QUEUE_KEY = "kg:jobs:queue"


class RedisStateStore(StateStore):
    def __init__(self, client: redis.Redis, ttl_seconds: int = 86400) -> None:
        self.r = client
        self.ttl = ttl_seconds

    @classmethod
    def from_url(cls, url: str, ttl_seconds: int = 86400) -> "RedisStateStore":
        # from_url does not connect yet -> fast startup (Factor IX).
        return cls(redis.from_url(url, decode_responses=True), ttl_seconds)

    async def save_session(self, session: SessionRecord) -> None:
        session.updated_at = utcnow()
        await self.r.set(f"kg:session:{session.id}", session.model_dump_json(), ex=self.ttl)

    async def get_session(self, session_id: str) -> SessionRecord | None:
        raw = await self.r.get(f"kg:session:{session_id}")
        return SessionRecord.model_validate_json(raw) if raw else None

    async def save_job(self, job: Job) -> None:
        job.updated_at = utcnow()
        await self.r.set(f"kg:job:{job.id}", job.model_dump_json(), ex=self.ttl)

    async def get_job(self, job_id: str) -> Job | None:
        raw = await self.r.get(f"kg:job:{job_id}")
        return Job.model_validate_json(raw) if raw else None

    async def enqueue_job(self, job_id: str) -> None:
        await self.r.lpush(QUEUE_KEY, job_id)

    async def dequeue_job(self, timeout: float = 5.0) -> str | None:
        item = await self.r.brpop([QUEUE_KEY], timeout=int(max(1, timeout)))
        return item[1] if item else None

    async def ping(self) -> bool:
        try:
            return bool(await self.r.ping())
        except Exception:
            return False

    async def close(self) -> None:
        await self.r.aclose()
