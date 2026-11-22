# ADR-0001: React chat stack — AI SDK UI plus AI Elements

- **Status:** accepted
- **Date:** 2026-11-22
- **Deciders:** Alan Samet
- **Related:** [ADR-0002](0002-vite-same-origin.md), [technical design §2](../technical-design.md#2-architecture)

## Context

The UI needs a conversational surface over a stage-gated workflow whose outputs
are structured artifacts (schema rules, job progress, query records), not prose.
Candidates were evaluated on 2026-11-22: `ai@7.0.179` + `@ai-sdk/react@4.0.183`
(note the independent majors), `@assistant-ui/react@0.15.37`, OpenAI ChatKit
(`@openai/chatkit-react@1.6.1`, `openai-chatkit@1.6.5`), and AG-UI
(`ag-ui-adk@0.14.0`, `@ag-ui/client@1.0.5`, CopilotKit).

## Decision

Use AI SDK UI for the chat spine (`useChat` + `DefaultChatTransport`) and AI
Elements from the **shadcn registry** for components. Carry workflow state as
typed `data-*` parts; approvals stay REST calls that patch a card by id.

## Consequences

- The UI Message Stream protocol is the integration contract; a Python backend
  can emit it directly, and the AI SDK documents FastAPI as a supported backend.
- Components are vendored into the repo (`npx shadcn@latest add @ai-elements/…`),
  so there is no runtime dependency on Vercel and styling is ours.
- The standalone `elements.ai-sdk.dev` project is deprecated end of November
  2026; the shadcn registry is the maintained path.
- `ai` and `@ai-sdk/react` majors move independently — both are pinned together
  and the lockfile is committed.
- We own more layout/state code than assistant-ui would impose, in exchange for
  artifact rendering that matches this domain.

## Alternatives rejected

| Option | Why not |
|---|---|
| **OpenAI ChatKit** | One web component with its own thread protocol, `ChatKitServer`/`Store`/`FileStore`, and an OpenAI-centric agent path; poor fit for FastAPI + ADK and for bespoke artifact cards |
| **assistant-ui** | Strong batteries (threads, editing, voice) but a more opinionated layout; revisit if thread management becomes a burden |
| **AG-UI + CopilotKit** | Good protocol, real ADK middleware, but heavier and duplicative once AI SDK UI is chosen |
| **Hand-rolled** | +1 week for streaming, parts, abort, retry — no differentiation |

## References

- https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol
- https://ui.shadcn.com/docs/ai-elements
- https://developers.openai.com/api/docs/guides/custom-chatkit
