"""In-memory StateStore for the demo and tests.

WARNING: state lives in this process only. It is lost on restart and is not
shared between uvicorn workers, replicas or the background worker. Use it for
`uvicorn --reload` dev loops and pytest; set STATE_BACKEND=redis in production.
"""

from __future__ import annotations

import asyncio

from app.domain.models import Job, utcnow
from app.state.base import SessionRecord, StateStore


class MemoryStateStore(StateStore):
    def __init__(self) -> None:
        self._sessions: dict[str, str] = {}  # store JSON so callers can't mutate shared objects
        self._jobs: dict[str, str] = {}
        self._queue: asyncio.Queue[str] | None = None

    async def save_session(self, session: SessionRecord) -> None:
        session.updated_at = utcnow()
        self._sessions[session.id] = session.model_dump_json()

    async def get_session(self, session_id: str) -> SessionRecord | None:
        raw = self._sessions.get(session_id)
        return SessionRecord.model_validate_json(raw) if raw else None

    async def save_job(self, job: Job) -> None:
        job.updated_at = utcnow()
        self._jobs[job.id] = job.model_dump_json()

    async def get_job(self, job_id: str) -> Job | None:
        raw = self._jobs.get(job_id)
        return Job.model_validate_json(raw) if raw else None

    def _q(self) -> asyncio.Queue[str]:
        # Created lazily so it binds to the running event loop.
        if self._queue is None:
            self._queue = asyncio.Queue()
        return self._queue

    async def enqueue_job(self, job_id: str) -> None:
        await self._q().put(job_id)

    async def dequeue_job(self, timeout: float = 5.0) -> str | None:
        try:
            return await asyncio.wait_for(self._q().get(), timeout)
        except asyncio.TimeoutError:
            return None

    async def ping(self) -> bool:
        return True
