"""Session-state keys, copied verbatim from the notebooks.

In the course every agent shares one ADK session; tools read/write
`tool_context.state[...]` with these keys, and the *next* agent picks up what
the previous one approved. We keep the exact same keys so the borrowed prompts
(which mention e.g. 'approved_user_goal') stay valid.
"""

# L4 user intent agent
PERCEIVED_USER_GOAL = "perceived_user_goal"
APPROVED_USER_GOAL = "approved_user_goal"

# L5 file suggestion agent
SUGGESTED_FILES = "suggested_files"
APPROVED_FILES = "approved_files"

# L6 structured schema proposal (loop: proposer -> critic -> check)
PROPOSED_CONSTRUCTION_PLAN = "proposed_construction_plan"
APPROVED_CONSTRUCTION_PLAN = "approved_construction_plan"
FEEDBACK = "feedback"  # critic's output_key; "valid" stops the loop

# L7 unstructured schema proposal (NER agent -> fact type agent)
PROPOSED_ENTITIES = "proposed_entity_types"
APPROVED_ENTITIES = "approved_entity_types"
PROPOSED_FACTS = "proposed_fact_types"
APPROVED_FACTS = "approved_fact_types"
