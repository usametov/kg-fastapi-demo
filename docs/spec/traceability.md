# Traceability

- **Status:** living document — update in the same commit as behavior changes
- **Rule:** an FR ships only with a green test; an NFR is verified at the
  milestone that claims it. IDs are permanent — never renumber.

## Intent → requirements

| Intent | Requirements |
|---|---|
| **INT-1** ready in < 5 min | FR-15, NFR-12 |
| **INT-2** works without an LLM key | FR-6, FR-15 |
| **INT-3** root-cause question | FR-7 |
| **INT-4** drivable from the browser | FR-1, FR-8, FR-9, FR-12, FR-14 |
| **INT-5** safe to expose | FR-10, FR-11, FR-13, NFR-5, NFR-8, NFR-9 |
| **INT-6** usable docs | plan gate, `AGENTS.md`, this table |

## Functional requirements

| ID | Requirement | Acceptance (§FD) | Test | M | Status |
|---|---|---|---|---|---|
| FR-2 | Multi-turn goal chat + approval | §1 | `tests/test_flow.py::test_full_agentic_flow`, `tests/test_adk_runner.py::test_user_intent_agent_with_fake_llm` | — | done |
| FR-1 | Stage gating with 409 + hint | §1 | `tests/test_flow.py::test_preconditions_enforced` | M1 | done (backend), UI hint planned |
| FR-3 | File suggestion, approval, validation | §1 | `tests/test_tools_and_files.py::test_file_catalog`, `tests/test_flow.py::test_full_agentic_flow` | — | done |
| FR-4 | Structured schema + defaults | §1 | `tests/test_flow.py::test_manual_defaults_path`, `tests/test_tools_and_files.py::test_node_construction_checks_column` | — | done |
| FR-5 | Unstructured schema, two-stage approval | §1 | `tests/test_tools_and_files.py::test_fact_requires_approved_entities` | — | done |
| FR-6 | Background build with progress | §1 | `tests/test_state_and_jobs.py::test_build_job_full`, `::test_worker_mode_enqueues` | — | done |
| FR-7 | Named / Cypher / question query | §3 | `tests/test_query.py` (5 tests) | — | done |
| FR-9 | Inline artifacts, reconcile by id | §5 | `ui/src/components/kg/*.test.tsx` | M2 | planned |
| FR-8 | SSE chat stream per protocol | §4 | `tests/test_chat_stream.py` + golden `.sse` | M1 | planned |
| FR-12 | Reload restores transcript | §2 | `e2e/resume.spec.ts` | M1 | planned |
| FR-11 | Session list, rename, delete, ownership | §8 | `tests/test_sessions_api.py` | M1 | planned |
| FR-13 | Auth on session + query routes | §6 | `tests/test_auth.py` | M1 | planned |
| FR-14 | SPA served same-origin without shadowing API | §3 | `tests/test_static.py` | M2 | planned |
| FR-15 | No-LLM demo path end-to-end | §1 | `e2e/no-llm.spec.ts` | M2 | planned |
| FR-10 | Cypher console: params, history, refusal | §7 | `e2e/cypher-console.spec.ts`, `tests/test_query.py::test_write_cypher_rejected` | M3 | backend done, UI planned |

## Non-functional requirements

| ID | Requirement | Verified by | M | Status |
|---|---|---|---|---|
| NFR-1 | Scale-to-zero keeps sessions/jobs | `knative/README.md` smoke test on the cluster | M4 | planned |
| NFR-2 | Turn fits 300 s ceiling | `knative/service.yaml` + contract test timing | M1 | partial (config) |
| NFR-3 | Cold start ≤ 5 s p50 | Manual measurement, recorded in `plan.md` | M4 | planned |
| NFR-4 | ≤ 1 Gi/pod | `service.yaml` limits + soak run | M4 | planned |
| NFR-5 | No secrets in git | Plan gate + review checklist + secret scan | — | manual |
| NFR-6 | First byte ≤ 2 s; ping ≤ 15 s | `tests/test_chat_stream.py::test_keepalive` | M1 | planned |
| NFR-7 | No serious axe violations | `axe` in Playwright | M4 | planned |
| NFR-8 | Rate limits + daily budget | `tests/test_auth.py::test_rate_limit` | M1 | planned |
| NFR-9 | Read-only Cypher guarantee | `tests/test_query.py::test_write_cypher_rejected` | — | done |
| NFR-10 | No prompt/Cypher text in logs | Log assertions in `tests/test_chat_stream.py` | M1 | planned |
| NFR-11 | Page-sized session listing | `tests/test_sessions_api.py::test_pagination` | M1 | planned |
| NFR-12 | Reproducible builds | `requirements.txt` pins + `ui/pnpm-lock.yaml` | M0 | partial |

## Gaps

- No test asserts the **UI never auto-runs** a query from a template; covered by
  manual review until FR-10's e2e lands.
- NFR-5 has no automated scan yet; the plan gate is not a secret scanner.
- FR-1's UI half (disabled actions, inline hint) has no test until M1.
