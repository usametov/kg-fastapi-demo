"""Sessions, user goal (L4) and file selection (L5).

A *session* is the HTTP equivalent of the notebooks' shared ADK session: each
stage reads what the previous stage approved from `session.state`.

Approval pattern used everywhere: the agent PROPOSES (perceived_user_goal,
suggested_files, proposed_construction_plan ...), a human APPROVES via an
explicit endpoint, which copies proposed -> approved. A PUT variant lets you
set the approved value directly (scripted demos, no LLM).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.deps import FilesDep, RunnerDep, SessionDep, StoreDep
from app.domain import state_keys as K
from app.domain.models import ChatRequest, ChatResponse, FilesBody, FileSuggestionRequest, SessionView, UserGoal
from app.routers._common import pick, run_agent_turn

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionView, status_code=status.HTTP_201_CREATED)
async def create_session(store: StoreDep) -> SessionView:
    """Start a new KG-construction session (empty shared state)."""
    s = await store.create_session()
    return SessionView(**s.model_dump())


@router.get("/{session_id}", response_model=SessionView)
async def get_session(session: SessionDep) -> SessionView:
    """Inspect the whole shared state - handy for debugging the flow."""
    return SessionView(**session.model_dump())


# ------------------------------------------------------------ L4: goal
@router.post("/{session_id}/goal", response_model=ChatResponse)
async def chat_goal(body: ChatRequest, session: SessionDep, runner: RunnerDep, store: StoreDep) -> ChatResponse:
    """One chat turn with the L4 user intent agent.

    Multi-turn: send several messages; the agent records `perceived_user_goal`
    and, if you say e.g. "yes, approve it", calls approve_perceived_user_goal.
    """
    reply = await run_agent_turn(session, "user_intent", body.message, runner, store)
    return ChatResponse(session_id=session.id, agent="user_intent", reply=reply,
                        state=pick(session.state, K.PERCEIVED_USER_GOAL, K.APPROVED_USER_GOAL))


@router.post("/{session_id}/goal/approve", response_model=UserGoal)
async def approve_goal(session: SessionDep, store: StoreDep) -> UserGoal:
    """Human approval: perceived_user_goal -> approved_user_goal (no LLM call)."""
    goal = session.state.get(K.PERCEIVED_USER_GOAL)
    if not goal:
        raise HTTPException(409, "no perceived_user_goal yet; chat with POST /goal first")
    session.state[K.APPROVED_USER_GOAL] = goal
    await store.save_session(session)
    return UserGoal(**goal)


@router.put("/{session_id}/goal", response_model=UserGoal)
async def put_goal(goal: UserGoal, session: SessionDep, store: StoreDep) -> UserGoal:
    """Set (and approve) the goal directly, skipping the agent."""
    session.state[K.PERCEIVED_USER_GOAL] = session.state[K.APPROVED_USER_GOAL] = goal.model_dump()
    await store.save_session(session)
    return goal


# ------------------------------------------------------------ L5: files
@router.get("/{session_id}/files/available")
async def available_files(session: SessionDep, files: FilesDep) -> dict:
    """What's in DATA_DIR (the notebook's Neo4j import dir)."""
    return files.list_files()


@router.post("/{session_id}/files", response_model=ChatResponse)
async def suggest_files(body: FileSuggestionRequest, session: SessionDep, runner: RunnerDep, store: StoreDep) -> ChatResponse:
    """Run the L5 file suggestion agent; it records `suggested_files`."""
    if K.APPROVED_USER_GOAL not in session.state:
        raise HTTPException(409, "approve a user goal first")
    reply = await run_agent_turn(session, "file_suggestion", body.message, runner, store)
    return ChatResponse(session_id=session.id, agent="file_suggestion", reply=reply,
                        state=pick(session.state, K.SUGGESTED_FILES, K.APPROVED_FILES))


@router.post("/{session_id}/files/approve", response_model=FilesBody)
async def approve_files(session: SessionDep, store: StoreDep) -> FilesBody:
    """Human approval: suggested_files -> approved_files."""
    suggested = session.state.get(K.SUGGESTED_FILES)
    if not suggested:
        raise HTTPException(409, "no suggested_files yet; call POST /files first")
    session.state[K.APPROVED_FILES] = suggested
    await store.save_session(session)
    return FilesBody(files=suggested)


@router.put("/{session_id}/files", response_model=FilesBody)
async def put_files(body: FilesBody, session: SessionDep, store: StoreDep, files: FilesDep) -> FilesBody:
    """Set approved files directly (validated against DATA_DIR)."""
    available = set(files.list_files().get("files", []))
    missing = [f for f in body.files if f not in available]
    if missing:
        raise HTTPException(422, f"unknown files: {missing}")
    session.state[K.SUGGESTED_FILES] = session.state[K.APPROVED_FILES] = body.files
    await store.save_session(session)
    return body
