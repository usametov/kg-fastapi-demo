"""Pydantic models: request/response bodies and typed views of session state.

Why Pydantic models everywhere?
  * FastAPI validates request bodies and returns 422 with details on bad input.
  * The same models generate the OpenAPI schema you see at /docs.
  * `response_model=` filters/serialises responses, so internals never leak.

The construction-plan shapes mirror the dicts that the L6 tools
`propose_node_construction` / `propose_relationship_construction` store in
state, and the L7 entity/fact shapes mirror `set_proposed_entities` /
`add_proposed_fact`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- L4: goal
class UserGoal(BaseModel):
    """The user goal from L4: 'kind_of_graph' (<= 3 words) + 'description'."""

    kind_of_graph: str = Field(..., examples=["supply chain analysis"])
    description: str = Field(
        ..., examples=["Find the root cause of product issues by tracing products to parts and suppliers."]
    )


# ------------------------------------------------- L6: construction plan
class NodeConstruction(BaseModel):
    construction_type: Literal["node"] = "node"
    source_file: str
    label: str
    unique_column_name: str
    properties: list[str] = []


class RelationshipConstruction(BaseModel):
    construction_type: Literal["relationship"] = "relationship"
    source_file: str
    relationship_type: str
    from_node_label: str
    from_node_column: str
    to_node_label: str
    to_node_column: str
    properties: list[str] = []


# Discriminated union: Pydantic picks the right model from construction_type.
Construction = Annotated[Union[NodeConstruction, RelationshipConstruction], Field(discriminator="construction_type")]


class ConstructionPlan(BaseModel):
    """Keyed by label / relationship type, exactly like the notebook's dict."""

    rules: dict[str, Construction] = {}

    @property
    def nodes(self) -> list[NodeConstruction]:
        return [r for r in self.rules.values() if isinstance(r, NodeConstruction)]

    @property
    def relationships(self) -> list[RelationshipConstruction]:
        return [r for r in self.rules.values() if isinstance(r, RelationshipConstruction)]

    @classmethod
    def from_state(cls, raw: dict[str, Any] | None) -> "ConstructionPlan":
        return cls(rules=raw or {})

    def to_state(self) -> dict[str, Any]:
        return {k: v.model_dump() for k, v in self.rules.items()}


# --------------------------------------------- L7: unstructured schema
class FactType(BaseModel):
    """A (subject, predicate, object) *type*, e.g. (Product, has_issue, Issue)."""

    subject_label: str
    predicate_label: str
    object_label: str


class UnstructuredSchema(BaseModel):
    entity_types: list[str] = []
    fact_types: list[FactType] = []


# --------------------------------------------------------- API bodies
class ChatRequest(BaseModel):
    message: str = Field(..., examples=["I want to find root causes of product quality issues."])


class ChatTurn(BaseModel):
    role: Literal["user", "agent"]
    text: str


class ChatResponse(BaseModel):
    session_id: str
    agent: str
    reply: str
    state: dict[str, Any] = Field(description="Relevant slice of session state after the turn.")


class FilesBody(BaseModel):
    files: list[str] = Field(..., examples=[["products.csv", "suppliers.csv"]])


class FileSuggestionRequest(BaseModel):
    message: str = Field(
        "Suggest files relevant to my approved goal.", description="Optional feedback for the agent."
    )


class SchemaRequest(BaseModel):
    feedback: str = Field("", description="Optional human feedback fed into the {feedback} slot of the prompt.")


class UnstructuredSchemaRequest(SchemaRequest):
    phase: Literal["entities", "facts", "all"] = Field(
        "all",
        description=(
            "'entities' runs only the NER agent, 'facts' only the fact-type agent (needs approved "
            "entities), 'all' runs both as an ADK SequentialAgent with entities auto-approved in between."
        ),
    )


class StructuredSchemaResponse(BaseModel):
    session_id: str
    critic_feedback: str | None = None
    proposed: dict[str, Construction]
    approved: bool = False


class UnstructuredSchemaResponse(BaseModel):
    session_id: str
    proposed: UnstructuredSchema
    approved: UnstructuredSchema | None = None
    agent_reply: str = ""


class SessionView(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    state: dict[str, Any]


# ------------------------------------------------------------- jobs
class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class BuildRequest(BaseModel):
    include_structured: bool = True
    include_unstructured: bool = Field(
        True, description="Chunk the review markdown + LLM extraction (needs approved entity/fact types)."
    )
    reset_graph: bool = Field(False, description="DETACH DELETE everything first (demo convenience).")


class Job(BaseModel):
    id: str
    session_id: str
    status: JobStatus = JobStatus.queued
    progress: float = 0.0
    steps: list[str] = []
    payload: dict[str, Any] = {}
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class JobView(BaseModel):
    id: str
    session_id: str
    status: JobStatus
    progress: float
    steps: list[str]
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------- query
class QueryRequest(BaseModel):
    """Exactly one of cypher / named / question should be set."""

    cypher: str | None = Field(None, examples=["MATCH (p:Product) RETURN p.product_name AS name LIMIT 5"])
    params: dict[str, Any] = {}
    named: Literal["graph_summary", "root_cause", "products_with_issues"] | None = None
    question: str | None = Field(None, examples=["Which suppliers provide parts for products with complaints?"])
    limit: int = Field(25, ge=1, le=1000)


class QueryResponse(BaseModel):
    mode: Literal["cypher", "named", "question"]
    cypher: str | None = None
    records: list[dict[str, Any]] = []
    answer: str | None = None
