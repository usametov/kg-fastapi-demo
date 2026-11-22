# ADR-0004: Multi-session history with per-owner isolation

- **Status:** accepted
- **Date:** 2026-11-22
- **Deciders:** Alan Samet
- **Related:** [functional design §8](../functional-design.md#8-multi-session-history), [technical design §3](../technical-design.md#3-data-model)

## Context

Sessions are anonymous and discoverable only by id. A UI with history needs to
list them, name them, reopen them and delete them. Once sessions are listable,
"who owns this session" becomes a security question: a public Knative URL with a
session list is an IDOR waiting to happen, and the raw Cypher console (ADR-0003)
raises the stakes.

## Decision

Add `owner_id` and `title` to `SessionRecord`, expose
`GET/PATCH/DELETE /sessions` and `GET /sessions/{id}/messages`, and filter every
session route by owner. A session owned by someone else returns **404, not 403**.
`owner_id` is `sha256(subject)[:16]` — never an email or a raw provider id.

Listing is cursor-paginated (50/page) over a Redis ZSET scored by `updated_at`;
titles derive from the approved `kind_of_graph`, else the first user message
(≤ 80 chars), else the user's rename.

## Consequences

- Authentication moves into M1: history without ownership is a data-leak feature.
- `StateStore` grows `list_sessions` and `delete_session`; the Redis layout gains
  an owner index. Listing must stay O(page) — no `SCAN`.
- 404 for foreign ids avoids an enumeration oracle but makes debugging slightly
  less obvious in logs; the request id disambiguates.
- Titles are user content and must be rendered as text, never HTML.
- Deletion is immediate and irreversible in the demo (no soft delete).

## Alternatives rejected

| Option | Why not |
|---|---|
| **Remember session ids in `localStorage` only** | No cross-device history, no shared links, and it hides the ownership problem rather than solving it |
| **Single global session list** | Trivially enumerable; unacceptable on a public URL |
| **403 for foreign ids** | Confirms existence — an oracle for guessing ids |
| **Soft delete / archive** | Extra states and retention rules for a demo; can be added later without breaking the API |

## References

- OWASP: Insecure Direct Object Reference
- `app/state/base.py` (`SessionRecord`, `StateStore`)
