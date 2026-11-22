"""L4 - User intent agent.

Notebook: "Understanding user intent". A conversational ADK `Agent` that
helps the user name a kind_of_graph + description, records it with
`set_perceived_user_goal`, and on the user's explicit OK calls
`approve_perceived_user_goal` -> state['approved_user_goal'].

API mapping: POST /sessions/{id}/goal  (one chat turn per request)
             POST /sessions/{id}/goal/approve  (human approval without the LLM)
"""

from app.agents.prompts import USER_INTENT_INSTRUCTION

AGENT_NAME = "user_intent_agent_v1"


def build(model, tools):
    from google.adk.agents import Agent

    return Agent(
        name=AGENT_NAME,
        model=model,
        description="Helps the user ideate on a knowledge graph use case.",
        instruction=USER_INTENT_INSTRUCTION,
        tools=[tools.set_perceived_user_goal, tools.approve_perceived_user_goal],
    )
