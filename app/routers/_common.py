"""Shared helpers for routers that run an agent turn against a session."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.agents.runner import AgentName, AgentRunner
from app.domain.models import ChatTurn
from app.state.base import SessionRecord, StateStore


async def run_agent_turn(
    session: SessionRecord, agent: AgentName, message: str, runner: AgentRunner, store: StateStore, *, keep_history: bool = True
) -> str:
    """Hydrate state -> run agent -> persist state + history. Returns the reply.

    LLM/provider failures become 502 (bad gateway): the *attached resource*
    failed, not our API.
    """
    history = session.history.get(agent, []) if keep_history else []
    try:
        result = await runner.run(agent, message, session.state, history)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"agent '{agent}' failed: {type(exc).__name__}: {exc}") from exc
    session.state = result.state
    if keep_history:
        session.history[agent] = [*history, ChatTurn(role="user", text=message), ChatTurn(role="agent", text=result.reply)]
    await store.save_session(session)
    return result.reply


def pick(state: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {k: state[k] for k in keys if k in state}
