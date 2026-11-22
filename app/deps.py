"""FastAPI dependency providers (dependency injection).

Why DI instead of importing globals (the notebooks' `from neo4j_for_adk import graphdb`)?
  * Routers declare what they need: `graph: GraphDB = Depends(get_graph)`.
  * Long-lived resources (Neo4j driver, Redis client, agent runner) are
    created once in the lifespan, stored on `app.state`, and handed out here.
  * Tests replace any of them with `app.dependency_overrides[...]` - no
    monkey-patching, no real Neo4j/LLM needed.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.agents.runner import AgentRunner
from app.config import Settings, get_settings
from app.files import FileCatalog
from app.graph.neo4j_client import GraphDB
from app.state.base import SessionRecord, StateStore


def get_graph(request: Request) -> GraphDB:
    return request.app.state.graph


def get_store(request: Request) -> StateStore:
    return request.app.state.store


def get_runner(request: Request) -> AgentRunner:
    return request.app.state.runner


def get_files(request: Request) -> FileCatalog:
    return request.app.state.files


SettingsDep = Annotated[Settings, Depends(get_settings)]
GraphDep = Annotated[GraphDB, Depends(get_graph)]
StoreDep = Annotated[StateStore, Depends(get_store)]
RunnerDep = Annotated[AgentRunner, Depends(get_runner)]
FilesDep = Annotated[FileCatalog, Depends(get_files)]


async def get_session_or_404(session_id: str, store: StoreDep) -> SessionRecord:
    """Path-param dependency: resolves {session_id} or raises 404 in one place."""
    session = await store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    return session


SessionDep = Annotated[SessionRecord, Depends(get_session_or_404)]
