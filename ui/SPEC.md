# UI spec has moved

The chat UI specification is now split across the documents under
[`docs/spec/`](../docs/spec/spec.md), because each part has a different reader:

| Was in this file | Now |
|---|---|
| Personas, journey, IA, UX states, a11y, brand | [`docs/spec/product-design.md`](../docs/spec/product-design.md) |
| Stage machine, API surface, streaming contract, artifacts, errors, FRs | [`docs/spec/functional-design.md`](../docs/spec/functional-design.md) |
| Stack, architecture, data model, security, NFRs, test strategy | [`docs/spec/technical-design.md`](../docs/spec/technical-design.md) |
| Locked decisions (stack, Vite, Cypher, sessions, Knative) | [`docs/spec/adr/`](../docs/spec/adr/) |
| Milestones and open questions | [`plan.md`](../plan.md), [`docs/spec/spec.md#open-questions`](../docs/spec/spec.md#open-questions) |
| Coverage status | [`docs/spec/traceability.md`](../docs/spec/traceability.md) |

This file is kept only as a pointer so old links do not break. The full previous
content is in git history (`git log -- ui/SPEC.md`); do not add new content here.
