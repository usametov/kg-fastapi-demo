# ADR-0003: Expose the raw Cypher console to end users

- **Status:** accepted
- **Date:** 2026-11-22
- **Deciders:** Alan Samet
- **Related:** [functional design §7](../functional-design.md#7-cypher-console), NFR-9

## Context

`POST /query` accepts raw Cypher and executes it read-only. Exposing an editor to
end users is unusual for a public demo: it widens the attack surface (data
enumeration) and the support surface (syntax errors, slow queries). Hiding it
behind "advanced mode" would also hide the most instructive part of the product —
the Cypher that answers the course's root-cause question.

## Decision

Expose it, with controls that live **server-side**:

- `is_write_query()` rejects any write clause with 400; queries run with READ
  routing. This is the guarantee, not the UI's disabled button.
- Requires authentication and is rate-limited per owner (M1).
- Row `limit` (1–1000, default 25) and short-lived read transactions.
- The UI never auto-runs: templates insert into the editor, and the user presses
  Run. History is per-session `localStorage`, text only.
- Logs record a query **hash** and row count, never the text or params.

## Consequences

- The demo is substantially more convincing: users can inspect and modify the
  Cypher behind an answer, which is the teaching goal.
- The public deployment must have auth enabled; `AUTH_MODE=none` is dev-only.
  This is why authentication moved into M1.
- A read-only user in Neo4j is still recommended in production, so the server
  guarantee has defence in depth.
- Cypher results can be large; the grid virtualizes and the server caps rows.

## Alternatives rejected

| Option | Why not |
|---|---|
| **Named queries only** | Safe, but hides the graph model and the course's most useful output |
| **Admin-only console** | Loses the primary audience (learners) and requires an RBAC model we do not have |
| **Client-side "safety" toggle** | Not a control; anyone can bypass the UI and call `/query` |
| **Read-only Neo4j user only** | Necessary but not sufficient: it still allows full read enumeration and slow queries without rate limits |

## References

- `app/graph/neo4j_client.py` (`is_write_query`), `app/routers/query.py`
- `tests/test_query.py::test_write_cypher_rejected`
