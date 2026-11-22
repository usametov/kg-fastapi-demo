"""kg-fastapi-demo: a FastAPI wrapper around the DeepLearning.AI
"Agentic Knowledge Graph Construction" course (Andreas Kollegger, Neo4j).

The course is notebook-based. Each notebook (lesson) builds one piece of a
multi-agent system with Google ADK + Neo4j:

    L2/L3  Intro to ADK (agents, tools, sessions, state)   -> app/agents/runner.py
    L4     User intent agent                               -> app/agents/intent.py
    L5     File suggestion agent                           -> app/agents/file_suggestion.py
    L6     Schema proposal (structured, loop of agents)    -> app/agents/schema_structured.py
    L7     Schema proposal (unstructured, NER + facts)     -> app/agents/schema_unstructured.py
    L8     KG construction (CSV import, lexical graph,
           entity resolution)                              -> app/construction/*

This package turns that notebook flow into a stateless HTTP API that follows
the Twelve-Factor App methodology (see README "Twelve-Factor").
"""

__version__ = "0.1.0"
