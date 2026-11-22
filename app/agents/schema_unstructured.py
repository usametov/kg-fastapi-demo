"""L7 - Schema proposal for unstructured data (product review markdown).

Notebook: "Schema proposal (unstructured data)". Two LLM agents:
    1. ner_schema_agent        - proposes entity *types* (well-known labels
                                 from the L6 plan + discovered ones like Issue)
    2. fact_type_extraction    - proposes (subject, predicate, object) fact types
                                 over the *approved* entity types
In the notebook the human approves entities between the two. For phase='all'
we chain them in an ADK `SequentialAgent` with a tiny `AutoApproveEntities`
agent in the middle (state_delta copies proposed -> approved), and the human
reviews/approves the final result through the API instead.
"""

from app.agents.prompts import API_MODE_SUFFIX, FACT_TYPE_INSTRUCTION, NER_INSTRUCTION
from app.domain import state_keys as K


def build_ner(model, tools):
    from google.adk.agents import LlmAgent

    return LlmAgent(
        name="ner_schema_agent_v1",
        model=model,
        description="Proposes the kind of named entities that could be extracted from text files.",
        instruction=NER_INSTRUCTION + API_MODE_SUFFIX,
        tools=[
            tools.get_approved_user_goal, tools.get_approved_unstructured_files, tools.sample_file,
            tools.get_well_known_types, tools.set_proposed_entities, tools.get_proposed_entities,
        ],
    )


def build_facts(model, tools):
    from google.adk.agents import LlmAgent

    return LlmAgent(
        name="fact_type_extraction_agent_v1",
        model=model,
        description="Proposes the kind of relevant facts that could be extracted from text files.",
        instruction=FACT_TYPE_INSTRUCTION + API_MODE_SUFFIX,
        tools=[
            tools.get_approved_user_goal, tools.get_approved_unstructured_files, tools.sample_file,
            tools.get_approved_entities, tools.add_proposed_fact, tools.get_proposed_facts,
        ],
    )


def build_all(model, tools):
    from google.adk.agents import BaseAgent, SequentialAgent
    from google.adk.events import Event, EventActions

    class AutoApproveEntities(BaseAgent):
        """API-MODE stand-in for the human 'approve entities' step of L7."""

        async def _run_async_impl(self, ctx):
            proposed = ctx.session.state.get(K.PROPOSED_ENTITIES, [])
            yield Event(author=self.name, actions=EventActions(state_delta={K.APPROVED_ENTITIES: proposed}))

    return SequentialAgent(
        name="unstructured_schema_pipeline",
        description="NER agent, then fact type extraction agent.",
        sub_agents=[build_ner(model, tools), AutoApproveEntities(name="AutoApproveEntities"), build_facts(model, tools)],
    )
