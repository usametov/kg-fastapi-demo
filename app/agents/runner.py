"""Running ADK agents statelessly behind HTTP (from L2/L3 "Intro to ADK").

The notebooks wrap agents in a small helper:

    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)
    session = await session_service.create_session(app_name=..., user_id=..., state=initial_state)
    async for event in runner.run_async(user_id=..., session_id=..., new_message=content):
        if event.is_final_response(): final = event.content.parts[0].text

`AdkAgentRunner.run()` does exactly that per request, but:
  * the initial state is *hydrated from our StateStore* (Redis or memory) and
    the final state is returned so the router can persist it -> the process
    holds no state between requests (Factor VI);
  * earlier chat turns are replayed as a short transcript in the prompt, because
    the throwaway ADK session has no memory of previous HTTP requests.

`AgentRunner` is an abstract interface so tests inject a fake (no LLM, no key).
"""

from __future__ import annotations

import copy
import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel

from app.config import Settings
from app.domain.models import ChatTurn
from app.files import FileCatalog
from app.graph.neo4j_client import GraphDB

logger = logging.getLogger(__name__)

AgentName = Literal[
    "user_intent", "file_suggestion", "schema_structured",
    "schema_unstructured_entities", "schema_unstructured_facts", "schema_unstructured_all",
    "graphrag",
]


class AgentResult(BaseModel):
    reply: str
    state: dict[str, Any]


class AgentRunner(ABC):
    @abstractmethod
    async def run(self, agent: AgentName, message: str, state: dict[str, Any], history: list[ChatTurn] | None = None) -> AgentResult:
        """Run one agent turn and return its reply + the updated session state."""


def build_agent(name: AgentName, model, tools, settings: Settings):
    """Registry: agent name -> ADK agent, built fresh per run (cheap)."""
    from app.agents import file_suggestion, graphrag, intent, schema_structured, schema_unstructured

    if name == "user_intent":
        return intent.build(model, tools)
    if name == "file_suggestion":
        return file_suggestion.build(model, tools)
    if name == "schema_structured":
        return schema_structured.build(model, tools, settings.schema_loop_max_iterations)
    if name == "schema_unstructured_entities":
        return schema_unstructured.build_ner(model, tools)
    if name == "schema_unstructured_facts":
        return schema_unstructured.build_facts(model, tools)
    if name == "schema_unstructured_all":
        return schema_unstructured.build_all(model, tools)
    if name == "graphrag":
        return graphrag.build(model, tools)
    raise ValueError(f"unknown agent {name}")


def make_model(settings: Settings):
    """LiteLlm model, as in the notebooks: LiteLlm(model="openai/gpt-4o")."""
    from google.adk.models.lite_llm import LiteLlm

    kwargs: dict[str, Any] = {}
    if settings.openai_key():
        kwargs["api_key"] = settings.openai_key()
    if settings.llm_api_base:
        kwargs["api_base"] = settings.llm_api_base
    return LiteLlm(model=settings.llm_model, **kwargs)


def _with_history(message: str, history: list[ChatTurn] | None, max_turns: int = 20) -> str:
    if not history:
        return message
    transcript = "\n".join(f"{t.role.upper()}: {t.text}" for t in history[-max_turns:])
    return f"Conversation so far:\n{transcript}\n\nUSER: {message}"


class AdkAgentRunner(AgentRunner):
    def __init__(self, settings: Settings, files: FileCatalog, graph: GraphDB | None) -> None:
        self.settings = settings
        self.files = files
        self.graph = graph
        self._model = None  # created lazily: importing ADK/LiteLLM takes ~1-2s

    async def run(self, agent: AgentName, message: str, state: dict[str, Any], history: list[ChatTurn] | None = None) -> AgentResult:
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        from app.agents.tools import make_tools

        if self._model is None:
            self._model = make_model(self.settings)
        tools = make_tools(self.files, self.graph)
        root = build_agent(agent, self._model, tools, self.settings)

        app_name, user_id, session_id = self.settings.app_name, "api", uuid.uuid4().hex
        service = InMemorySessionService()
        initial = copy.deepcopy(state)
        initial.setdefault("feedback", "")  # L6 prompt has a {feedback} template slot
        await service.create_session(app_name=app_name, user_id=user_id, session_id=session_id, state=initial)
        runner = Runner(agent=root, app_name=app_name, session_service=service)

        content = types.Content(role="user", parts=[types.Part(text=_with_history(message, history))])
        reply = ""
        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
            if event.content and event.content.parts:
                text = "".join(p.text or "" for p in event.content.parts if getattr(p, "text", None))
                if text:
                    reply = text  # keep the last textual response (final for loops/sequences)
            if event.get_function_calls():
                logger.info("tool call", extra={"agent": agent, "tools": [c.name for c in event.get_function_calls()]})
        session = await service.get_session(app_name=app_name, user_id=user_id, session_id=session_id)
        return AgentResult(reply=reply, state=dict(session.state))
