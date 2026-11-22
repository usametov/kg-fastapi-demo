"""L6 - Schema proposal for structured data (CSV) as a refinement loop.

Notebook: "Schema proposal (structured data)". Three agents inside an ADK
`LoopAgent`:
    1. schema_proposal_agent  - proposes node/relationship constructions
    2. schema_critic_agent    - output_key='feedback'; replies 'valid' or 'retry' + bullets
    3. CheckStatusAndEscalate - custom BaseAgent; escalates (stops the loop)
                                when feedback == 'valid'
The proposer's prompt contains `{feedback}`, which ADK fills from state, so
each iteration sees the critic's last review. max_iterations bounds cost.

API mapping: POST /sessions/{id}/schema/structured, .../approve, PUT (manual).
"""

from app.agents.prompts import API_MODE_SUFFIX, SCHEMA_CRITIC_INSTRUCTION, SCHEMA_PROPOSAL_INSTRUCTION
from app.domain import state_keys as K

AGENT_NAME = "schema_refinement_loop"


def build(model, tools, max_iterations: int = 2):
    from google.adk.agents import BaseAgent, LlmAgent, LoopAgent
    from google.adk.events import Event, EventActions

    class CheckStatusAndEscalate(BaseAgent):
        """Borrowed from L6: stop the loop once the critic says 'valid'."""

        async def _run_async_impl(self, ctx):
            feedback = str(ctx.session.state.get(K.FEEDBACK, "")).strip().lower()
            yield Event(author=self.name, actions=EventActions(escalate=feedback.startswith("valid")))

    proposer = LlmAgent(
        name="schema_proposal_agent_v1",
        model=model,
        description="Proposes a knowledge graph schema based on the user goal and approved file list",
        instruction=SCHEMA_PROPOSAL_INSTRUCTION + API_MODE_SUFFIX,
        tools=[
            tools.get_approved_user_goal, tools.get_approved_files, tools.get_proposed_construction_plan,
            tools.sample_file, tools.search_file,
            tools.propose_node_construction, tools.propose_relationship_construction,
            tools.remove_node_construction, tools.remove_relationship_construction,
        ],
    )
    critic = LlmAgent(
        name="schema_critic_agent_v1",
        model=model,
        description="Criticizes the proposed schema for relevance to the user goal and approved files.",
        instruction=SCHEMA_CRITIC_INSTRUCTION,
        tools=[
            tools.get_approved_user_goal, tools.get_approved_files, tools.get_proposed_construction_plan,
            tools.sample_file, tools.search_file,
        ],
        output_key=K.FEEDBACK,  # critic's final text lands in state['feedback']
    )
    return LoopAgent(
        name=AGENT_NAME,
        description="Analyzes approved files to propose a schema based on user intent and feedback",
        max_iterations=max_iterations,
        sub_agents=[proposer, critic, CheckStatusAndEscalate(name="StopChecker")],
    )
