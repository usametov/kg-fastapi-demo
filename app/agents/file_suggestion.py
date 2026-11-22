"""L5 - File suggestion agent.

Notebook: "File suggestion agent". Reads the approved goal, lists files in
the import dir, samples the unclear ones and records `suggested_files`; on
approval copies them to `approved_files`.

API mapping: POST /sessions/{id}/files (agent turn), POST .../files/approve,
             PUT .../files (manual override, no LLM).
"""

from app.agents.prompts import FILE_SUGGESTION_INSTRUCTION

AGENT_NAME = "file_suggestion_agent_v1"


def build(model, tools):
    from google.adk.agents import Agent

    return Agent(
        name=AGENT_NAME,
        model=model,
        description="Helps the user select files to import.",
        instruction=FILE_SUGGESTION_INSTRUCTION,
        tools=[
            tools.get_approved_user_goal, tools.list_available_files, tools.sample_file,
            tools.set_suggested_files, tools.get_suggested_files, tools.approve_suggested_files,
        ],
    )
