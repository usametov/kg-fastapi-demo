"""Session + job state behind an interface (Twelve-Factor VI: stateless processes).

API processes keep *no* state in memory between requests; everything lives in a
`StateStore`. Pick the implementation with STATE_BACKEND:

    memory  -> MemoryStateStore  (demo / tests; single process only!)
    redis   -> RedisStateStore   (any number of API replicas + workers)
"""

from app.state.base import SessionRecord, StateStore
from app.state.factory import build_state_store

__all__ = ["SessionRecord", "StateStore", "build_state_store"]
