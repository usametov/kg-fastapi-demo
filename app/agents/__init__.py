"""Google ADK agents borrowed from the course notebooks.

Import-light on purpose: `google.adk` is only imported when an agent actually
runs (app/agents/runner.py), so API startup stays fast (Factor IX) and the
test-suite can swap in a fake runner without touching ADK or an LLM.
"""
