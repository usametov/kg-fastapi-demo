"""HTTP routers, one module per stage of the notebook workflow.

`APIRouter` keeps each lesson's endpoints self-contained (prefix, tags shown in
/docs) and lets main.py assemble the app with `include_router`.
"""
