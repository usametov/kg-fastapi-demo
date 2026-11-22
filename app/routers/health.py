"""Health endpoints.

GET /health        liveness: process is up (no dependency calls; cheap, used
                   by Docker/Kubernetes livenessProbe and Knative).
GET /health/ready  readiness: Neo4j and the state store are reachable.
"""

from __future__ import annotations

import anyio
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import __version__
from app.deps import GraphDep, SettingsDep, StoreDep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(settings: SettingsDep) -> dict:
    return {"status": "ok", "version": __version__, "env": settings.environment}


@router.get("/health/ready")
async def ready(graph: GraphDep, store: StoreDep, settings: SettingsDep):
    neo4j_ok = await anyio.to_thread.run_sync(graph.verify)  # sync driver -> thread
    store_ok = await store.ping()
    body = {
        "neo4j": neo4j_ok,
        "state_store": store_ok,
        "state_backend": settings.state_backend,
        "llm_configured": bool(settings.openai_key()) or not settings.llm_model.startswith("openai/"),
    }
    return JSONResponse(body, status_code=200 if neo4j_ok and store_ok else 503)
