"""Test fixtures: the real FastAPI app with fake Neo4j + fake LLM runner.

Nothing here needs network access, an API key, Neo4j or Redis:
  * FakeGraph records Cypher and returns canned rows;
  * FakeRunner stands in for AdkAgentRunner and drives the *real* tool
    functions (app/agents/tools.py) the way the LLM would, so tool logic and
    state hand-offs between stages are exercised;
  * MemoryStateStore (or fakeredis) for state.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATA_DIR", str(ROOT / "data"))
os.environ.setdefault("LOG_LEVEL", "WARNING")

from app.agents.runner import AgentResult, AgentRunner  # noqa: E402
from app.agents.tools import make_tools  # noqa: E402
from app.config import Settings  # noqa: E402
from app.files import FileCatalog  # noqa: E402
from app.main import create_app  # noqa: E402
from app.state.memory import MemoryStateStore  # noqa: E402


class FakeGraph:
    """Duck-typed GraphDB."""

    def __init__(self) -> None:
        self.queries: list[tuple[str, dict]] = []
        self.rows: list[dict[str, Any]] = [{"label": "Product", "count": 10}]
        self.database = "neo4j"
        self.driver = None

    def send_query(self, cypher, parameters=None, *, read_only=False):
        self.queries.append((cypher, parameters or {}))
        return {"status": "success", "query_result": self.rows}

    def run_write(self, cypher, parameters=None):
        self.queries.append((cypher, parameters or {}))
        return {"status": "success", "query_result": []}

    def verify(self) -> bool:
        return True

    def close(self) -> None:
        pass


class FakeRunner(AgentRunner):
    """Plays the LLM: calls the same tools the real agent would call."""

    def __init__(self, files: FileCatalog, graph: FakeGraph) -> None:
        self.files, self.graph = files, graph
        self.calls: list[str] = []

    async def run(self, agent, message, state, history=None):
        self.calls.append(agent)
        state = dict(state)
        ctx = SimpleNamespace(state=state)
        t = make_tools(self.files, self.graph)
        if agent == "user_intent":
            t.set_perceived_user_goal("supply chain analysis", "Trace product issues to suppliers.", ctx)
            if "approve" in message.lower():
                t.approve_perceived_user_goal(ctx)
            return AgentResult(reply="Recorded goal: supply chain analysis", state=state)
        if agent == "file_suggestion":
            assert t.get_approved_user_goal(ctx)["status"] == "success"
            listed = t.list_available_files(ctx)["files"]
            t.set_suggested_files([f for f in listed if f.endswith(".csv")], ctx)
            return AgentResult(reply="Suggested all CSV files", state=state)
        if agent == "schema_structured":
            r1 = t.propose_node_construction("products.csv", "Product", "product_id", ["product_name"], ctx)
            r2 = t.propose_node_construction("suppliers.csv", "Supplier", "supplier_id", ["name"], ctx)
            assert r1["status"] == r2["status"] == "success"
            state["feedback"] = "valid"
            return AgentResult(reply="valid", state=state)
        if agent in ("schema_unstructured_entities", "schema_unstructured_all"):
            t.set_proposed_entities(["Product", "Issue"], ctx)
            if agent == "schema_unstructured_all":
                state["approved_entity_types"] = state["proposed_entity_types"]
                t.add_proposed_fact("Product", "has_issue", "Issue", ctx)
            return AgentResult(reply="proposed", state=state)
        if agent == "schema_unstructured_facts":
            t.add_proposed_fact("Product", "has_issue", "Issue", ctx)
            return AgentResult(reply="facts", state=state)
        if agent == "graphrag":
            t.read_neo4j_cypher("MATCH (p:Product) RETURN count(p) AS n", ctx)
            return AgentResult(reply="There are 10 products.", state=state)
        raise AssertionError(agent)


@pytest.fixture
def settings() -> Settings:
    return Settings(environment="test", data_dir=ROOT / "data", state_backend="memory", job_runner="inprocess")


@pytest.fixture
def fake_graph() -> FakeGraph:
    return FakeGraph()


@pytest.fixture
def client(settings, fake_graph):
    """TestClient with the lifespan run, then resources swapped for fakes."""
    app = create_app(settings)
    with TestClient(app) as c:
        app.state.graph.close()  # close the real (never-connected) driver
        app.state.graph = fake_graph
        app.state.store = MemoryStateStore()
        app.state.files = FileCatalog(settings.data_dir)
        app.state.runner = FakeRunner(app.state.files, fake_graph)
        from app.config import get_settings

        app.dependency_overrides[get_settings] = lambda: settings
        yield c
