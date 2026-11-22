"""Run the *real* AdkAgentRunner + ADK Runner with a scripted fake LLM.

This verifies the notebook pattern (Runner + InMemorySessionService + tools
mutating tool_context.state) and our state hydration/persistence, without any
API key: FakeLlm returns a tool call first, then a text answer.
"""

import asyncio
from typing import AsyncGenerator

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from app.agents.runner import AdkAgentRunner
from app.files import FileCatalog


class FakeLlm(BaseLlm):
    model: str = "fake"
    script: list = []

    async def generate_content_async(self, llm_request, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        part = self.script.pop(0)
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


def test_user_intent_agent_with_fake_llm(settings, fake_graph):
    runner = AdkAgentRunner(settings, FileCatalog(settings.data_dir), fake_graph)
    runner._model = FakeLlm(script=[
        types.Part(function_call=types.FunctionCall(
            name="set_perceived_user_goal",
            args={"kind_of_graph": "supply chain analysis", "graph_description": "Trace issues to suppliers."},
        )),
        types.Part(text="I recorded your goal. Shall I approve it?"),
    ])
    result = asyncio.run(runner.run("user_intent", "I need root-cause analysis", {"preexisting": 1}))
    assert result.reply == "I recorded your goal. Shall I approve it?"
    assert result.state["perceived_user_goal"]["kind_of_graph"] == "supply chain analysis"
    assert result.state["preexisting"] == 1  # hydrated state survives the run
