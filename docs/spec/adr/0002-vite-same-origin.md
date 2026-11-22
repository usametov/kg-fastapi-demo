# ADR-0002: Vite SPA served same-origin by FastAPI

- **Status:** accepted
- **Date:** 2026-11-22
- **Deciders:** Alan Samet
- **Related:** [ADR-0001](0001-chat-ui-stack.md), [ADR-0005](0005-knative-topology.md)

## Context

The API is FastAPI and the deployment target is a single Knative Service. The UI
could be a separate Next.js app on its own host, or a static SPA built into the
same image.

## Decision

Build the UI with **Vite**, output to `ui/dist`, and serve it from FastAPI at `/`
with `StaticFiles` plus an SPA fallback. In development, Vite proxies `/sessions`,
`/jobs`, `/query`, `/health`, `/auth` to `:8000`.

## Consequences

- **No CORS in production** and no cross-site cookie problem: `SameSite=Lax`
  cookies work as-is.
- One image, one revision, one URL: rollback is a Knative revision change.
- The fallback must not shadow the API. Assets live under `/assets` (immutable,
  hashed); `index.html` is `no-store`; `/sessions`, `/jobs`, `/query`, `/health`,
  `/docs`, `/openapi.json`, `/auth` are matched before the fallback.
- UI changes require a new image; there is no CDN or instant static deploy.
  Acceptable at this scale, and it keeps the contract versioned with the server.
- CORS middleware is still added behind `UI_ORIGINS` for preview deployments and
  split-origin development.

## Alternatives rejected

| Option | Why not |
|---|---|
| **Next.js App Router** | SSR buys nothing for an authenticated tool; a second server and a proxy layer for streaming add complexity with no product benefit |
| **Separate static host + CORS API** | Two deployables, preflighted SSE, cookie scoping across origins, and two URLs to document; only worth it at CDN scale |
| **FastAPI + Jinja/HTMX** | Would avoid JS tooling but gives up AI Elements and the streaming UX the product depends on |

## References

- https://ui.shadcn.com/docs/installation/vite
- `knative/service.yaml` (single container, port 8000)
