"""Schema proposal endpoints: structured (L6) and unstructured (L7).

These agents run one-shot (API-MODE) and return *typed* proposals as Pydantic
models (NodeConstruction / RelationshipConstruction / FactType), so clients get
a stable JSON contract and /docs shows the exact shape.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Query

from app.agents.tools import APPROVED_UNSTRUCTURED_FILES
from app.deps import FilesDep, RunnerDep, SessionDep, StoreDep
from app.domain import defaults
from app.domain import state_keys as K
from app.domain.models import (
    ConstructionPlan,
    FactType,
    SchemaRequest,
    StructuredSchemaResponse,
    UnstructuredSchema,
    UnstructuredSchemaRequest,
    UnstructuredSchemaResponse,
)
from app.routers._common import run_agent_turn

router = APIRouter(prefix="/sessions/{session_id}/schema", tags=["schema"])


def _structured_view(session, approved: bool = False) -> StructuredSchemaResponse:
    key = K.APPROVED_CONSTRUCTION_PLAN if approved else K.PROPOSED_CONSTRUCTION_PLAN
    plan = ConstructionPlan.from_state(session.state.get(key))
    return StructuredSchemaResponse(session_id=session.id, critic_feedback=session.state.get(K.FEEDBACK) or None,
                                    proposed=plan.rules, approved=approved)


# ---------------------------------------------------------- L6 structured
@router.post("/structured", response_model=StructuredSchemaResponse)
async def propose_structured(session: SessionDep, runner: RunnerDep, store: StoreDep,
                             body: SchemaRequest = Body(default_factory=SchemaRequest)) -> StructuredSchemaResponse:
    """Run the L6 proposer -> critic LoopAgent over the approved CSV files."""
    for key in (K.APPROVED_USER_GOAL, K.APPROVED_FILES):
        if key not in session.state:
            raise HTTPException(409, f"{key} missing; complete the earlier steps first")
    session.state[K.FEEDBACK] = body.feedback  # fills {feedback} in the proposer prompt
    await run_agent_turn(session, "schema_structured", "How can these files be imported?", runner, store, keep_history=False)
    return _structured_view(session)


@router.post("/structured/approve", response_model=StructuredSchemaResponse)
async def approve_structured(session: SessionDep, store: StoreDep) -> StructuredSchemaResponse:
    plan = session.state.get(K.PROPOSED_CONSTRUCTION_PLAN)
    if not plan:
        raise HTTPException(409, "nothing proposed yet")
    session.state[K.APPROVED_CONSTRUCTION_PLAN] = plan
    await store.save_session(session)
    return _structured_view(session, approved=True)


@router.put("/structured", response_model=StructuredSchemaResponse)
async def put_structured(session: SessionDep, store: StoreDep,
                         plan: ConstructionPlan | None = Body(None),
                         use_default: bool = Query(False, description="Use the known-good plan for the sample BOM data.")) -> StructuredSchemaResponse:
    """Set + approve a construction plan directly (or the sample default)."""
    if use_default:
        plan = defaults.DEFAULT_PLAN
    if plan is None or not plan.rules:
        raise HTTPException(422, "send a plan body or ?use_default=true")
    session.state[K.PROPOSED_CONSTRUCTION_PLAN] = session.state[K.APPROVED_CONSTRUCTION_PLAN] = plan.to_state()
    await store.save_session(session)
    return _structured_view(session, approved=True)


# -------------------------------------------------------- L7 unstructured
def _facts(raw) -> list[FactType]:
    values = raw.values() if isinstance(raw, dict) else (raw or [])
    return [FactType(**f) for f in values]


def _unstructured_view(session, reply: str = "") -> UnstructuredSchemaResponse:
    s = session.state
    approved = None
    if s.get(K.APPROVED_ENTITIES) and s.get(K.APPROVED_FACTS):
        approved = UnstructuredSchema(entity_types=s[K.APPROVED_ENTITIES], fact_types=_facts(s[K.APPROVED_FACTS]))
    return UnstructuredSchemaResponse(
        session_id=session.id,
        proposed=UnstructuredSchema(entity_types=s.get(K.PROPOSED_ENTITIES, []), fact_types=_facts(s.get(K.PROPOSED_FACTS))),
        approved=approved,
        agent_reply=reply,
    )


@router.post("/unstructured", response_model=UnstructuredSchemaResponse)
async def propose_unstructured(session: SessionDep, runner: RunnerDep, store: StoreDep, files: FilesDep,
                               body: UnstructuredSchemaRequest = Body(default_factory=UnstructuredSchemaRequest),
                               review_files: list[str] | None = Query(None, description="Markdown files; default = all *.md in DATA_DIR")) -> UnstructuredSchemaResponse:
    """Run the L7 NER agent and/or fact-type agent over the review markdown."""
    if K.APPROVED_USER_GOAL not in session.state:
        raise HTTPException(409, "approved_user_goal missing")
    md = [f for f in files.list_files().get("files", []) if f.endswith(".md")]
    chosen = review_files or md
    unknown = [f for f in chosen if f not in md]
    if unknown:
        raise HTTPException(422, f"unknown review files: {unknown}")
    session.state[APPROVED_UNSTRUCTURED_FILES] = chosen
    if body.phase == "facts" and not session.state.get(K.APPROVED_ENTITIES):
        raise HTTPException(409, "approve entity types first (POST .../unstructured/approve-entities)")
    agent = {"entities": "schema_unstructured_entities", "facts": "schema_unstructured_facts", "all": "schema_unstructured_all"}[body.phase]
    message = "Propose a schema for these files." + (f"\nFeedback: {body.feedback}" if body.feedback else "")
    reply = await run_agent_turn(session, agent, message, runner, store, keep_history=False)
    return _unstructured_view(session, reply)


@router.post("/unstructured/approve-entities", response_model=UnstructuredSchemaResponse)
async def approve_entities(session: SessionDep, store: StoreDep) -> UnstructuredSchemaResponse:
    """Notebook's human step between NER and fact extraction."""
    if not session.state.get(K.PROPOSED_ENTITIES):
        raise HTTPException(409, "no proposed entity types yet")
    session.state[K.APPROVED_ENTITIES] = session.state[K.PROPOSED_ENTITIES]
    await store.save_session(session)
    return _unstructured_view(session)


@router.post("/unstructured/approve", response_model=UnstructuredSchemaResponse)
async def approve_unstructured(session: SessionDep, store: StoreDep) -> UnstructuredSchemaResponse:
    s = session.state
    if not (s.get(K.PROPOSED_ENTITIES) and s.get(K.PROPOSED_FACTS)):
        raise HTTPException(409, "need proposed entity and fact types")
    s[K.APPROVED_ENTITIES] = s[K.PROPOSED_ENTITIES]
    s[K.APPROVED_FACTS] = s[K.PROPOSED_FACTS]
    await store.save_session(session)
    return _unstructured_view(session)


@router.put("/unstructured", response_model=UnstructuredSchemaResponse)
async def put_unstructured(session: SessionDep, store: StoreDep, files: FilesDep,
                           schema: UnstructuredSchema | None = Body(None),
                           use_default: bool = Query(False),
                           review_files: list[str] | None = Query(None)) -> UnstructuredSchemaResponse:
    """Set + approve entity/fact types directly (or the sample default)."""
    if use_default:
        schema = defaults.DEFAULT_UNSTRUCTURED
        review_files = review_files or defaults.DEFAULT_REVIEW_FILES
    if schema is None or not schema.entity_types:
        raise HTTPException(422, "send a schema body or ?use_default=true")
    md = [f for f in files.list_files().get("files", []) if f.endswith(".md")]
    s = session.state
    s[APPROVED_UNSTRUCTURED_FILES] = review_files or md
    s[K.PROPOSED_ENTITIES] = s[K.APPROVED_ENTITIES] = schema.entity_types
    facts = {f.predicate_label: f.model_dump() for f in schema.fact_types}
    s[K.PROPOSED_FACTS] = s[K.APPROVED_FACTS] = facts
    await store.save_session(session)
    return _unstructured_view(session)
