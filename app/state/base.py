"""The StateStore interface.

Why an abstract interface instead of a module-level dict?
  * Factor VI: with STATE_BACKEND=redis, a request can hit any replica and a
    build job can run in another process (the worker) and still see the session.
  * Tests inject a MemoryStateStore through FastAPI dependency overrides.

ADK note: the notebooks keep state in an ADK `InMemorySessionService`. Here
the *durable* copy of that state lives in a StateStore; for each agent turn
we hydrate a throwaway ADK session from it and write the result back
(see app/agents/runner.py).
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.models import ChatTurn, Job, utcnow


class SessionRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    # Same shape as the ADK session.state in the notebooks.
    state: dict[str, Any] = {}
    # Per-agent conversation history, so multi-turn chat survives across
    # stateless requests (agent name -> list of turns).
    history: dict[str, list[ChatTurn]] = {}


class StateStore(ABC):
    """Async CRUD for sessions and jobs, plus a tiny job queue."""

    # sessions -----------------------------------------------------------
    @abstractmethod
    async def save_session(self, session: SessionRecord) -> None: ...

    @abstractmethod
    async def get_session(self, session_id: str) -> SessionRecord | None: ...

    async def create_session(self) -> SessionRecord:
        session = SessionRecord()
        await self.save_session(session)
        return session

    # jobs ---------------------------------------------------------------
    @abstractmethod
    async def save_job(self, job: Job) -> None: ...

    @abstractmethod
    async def get_job(self, job_id: str) -> Job | None: ...

    # queue (used when JOB_RUNNER=worker) ---------------------------------
    @abstractmethod
    async def enqueue_job(self, job_id: str) -> None: ...

    @abstractmethod
    async def dequeue_job(self, timeout: float = 5.0) -> str | None: ...

    # lifecycle ------------------------------------------------------------
    @abstractmethod
    async def ping(self) -> bool: ...

    async def close(self) -> None:  # pragma: no cover - default no-op
        return None
