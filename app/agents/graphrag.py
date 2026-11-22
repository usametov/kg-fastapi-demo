"""Question answering over the finished graph (text-to-Cypher).

Used by POST /query when a natural-language `question` is sent. Adapted from
the companion repo's graphrag_agent and the course's final "ask the graph"
step. Tools are read-only (write Cypher is rejected).
"""

from app.agents.prompts import GRAPHRAG_INSTRUCTION

AGENT_NAME = "graphrag_agent_v1"


def build(model, tools):
    from google.adk.agents import Agent

    return Agent(
        name=AGENT_NAME,
        model=model,
        description="Answers questions using the knowledge graph.",
        instruction=GRAPHRAG_INSTRUCTION,
        tools=[tools.get_physical_schema, tools.read_neo4j_cypher],
    )
