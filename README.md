# kg-fastapi-demo: Agentic Knowledge Graph Construction as a FastAPI service

This project wraps the DeepLearning.AI short course **"Agentic Knowledge Graph Construction"**
(Andreas Kollegger, Neo4j) in a FastAPI service. The course builds a multi-agent system in
notebooks using **Google ADK**, **LiteLLM**, **Neo4j** and **neo4j-graphrag**. The system:

1. agrees on a **user goal** with you (L4),
2. **suggests the input files** (L5),
3. proposes a **graph schema for the CSVs** with a proposer/critic loop (L6),
4. proposes **entity and fact types for the review text** (L7),
5. **builds the knowledge graph**: a domain graph from the CSVs, a lexical graph from the reviews,
   and entity resolution between the two (L8),
6. lets you **query it**, including the course's root-cause question: which suppliers' parts
   end up in products that customers complain about?

The service is stateless and follows the [Twelve-Factor App](https://12factor.net) methodology
(see [Twelve-Factor](#twelve-factor) below).

> **About where the code comes from.** Prompts, tool functions and Cypher are adapted from the
> course lessons and from the course's public companion repo
> [neo4j-contrib/agentic-kg](https://github.com/neo4j-contrib/agentic-kg) (MIT). Every module's
> docstring names the lesson it comes from. The course helper `neo4j_for_adk.py` lives in the
> Jupyter file browser, not in the downloaded notebooks, so it is **reimplemented** here in
> `app/graph/neo4j_client.py`. Compare the prompts in `app/agents/prompts.py` with your notebooks
> and adjust them if your version differs.

---

## Project layout

```
kg-fastapi-demo/
├── app/
│   ├── main.py                 # app factory, lifespan (startup/shutdown), request logging
│   ├── __main__.py             # `python -m app` -> uvicorn on $HOST:$PORT
│   ├── worker.py               # `python -m app.worker` -> background build worker (Redis queue)
│   ├── config.py               # pydantic-settings: ALL config from env vars
│   ├── logging_config.py       # JSON logs to stdout
│   ├── deps.py                 # FastAPI dependency injection (graph, store, runner, files, settings)
│   ├── files.py                # list/sample/search files in DATA_DIR (L5/L6 file tools)
│   ├── domain/
│   │   ├── state_keys.py       # session-state keys used by the notebooks
│   │   ├── models.py           # Pydantic request/response + plan/schema models
│   │   └── defaults.py         # known-good plan for the sample data (LLM-free demo)
│   ├── agents/
│   │   ├── prompts.py          # agent instructions from L4-L7 (+ API-MODE suffix)
│   │   ├── tools.py            # ADK function tools from L4-L7 (+ read-only Cypher tool)
│   │   ├── runner.py           # stateless ADK Runner wrapper (L2/L3) + AgentRunner interface
│   │   ├── intent.py           # L4 user intent agent
│   │   ├── file_suggestion.py  # L5 file suggestion agent
│   │   ├── schema_structured.py    # L6 LoopAgent: proposer -> critic -> CheckStatusAndEscalate
│   │   ├── schema_unstructured.py  # L7 NER agent + fact-type agent (SequentialAgent)
│   │   └── graphrag.py         # question -> Cypher agent for /query
│   ├── construction/
│   │   ├── structured.py       # L8 domain graph: constraints + LOAD CSV
│   │   ├── unstructured.py     # L8 lexical graph (SimpleKGPipeline) + entity resolution
│   │   ├── splitter.py         # L8 RegexTextSplitter("---")
│   │   └── jobs.py             # build job, progress reporting (BackgroundTasks or worker)
│   ├── graph/
│   │   ├── neo4j_client.py     # GraphDB wrapper (reimplemented neo4j_for_adk helper)
│   │   └── cypher.py           # Cypher from L8 + named queries (root cause)
│   ├── state/
│   │   ├── base.py             # StateStore interface + SessionRecord
│   │   ├── memory.py           # in-memory store (demo/tests only)
│   │   ├── redis_store.py      # Redis store + job queue (production)
│   │   └── factory.py          # chooses one based on STATE_BACKEND
│   └── routers/                # health, sessions (L4/L5), schema (L6/L7), build (L8), query
├── scripts/
│   ├── load_sample_data.py     # admin: load the sample graph (no LLM needed)
│   └── reset_graph.py          # admin: wipe graph + constraints (--yes)
├── data/                       # sample CSVs + product_reviews/*.md (see data/README.md)
├── tests/                      # pytest; LLM and Neo4j are mocked; optional real-Neo4j test
├── Dockerfile                  # separate build and run stages
├── docker-compose.yml          # neo4j (+APOC), redis, api, worker
├── requirements.txt            # pinned runtime deps
├── requirements-dev.txt        # + pytest, httpx, fakeredis
└── .env.example                # local-dev config template (no real keys)
```

## Notebook → module map

| Course notebook / lesson | What it does | Where it is here |
|---|---|---|
| L2–L3 Intro to Google ADK (agents, tools, Runner, InMemorySessionService, state) | `LiteLlm(model="openai/gpt-4o")`, `Runner.run_async`, tools mutate `tool_context.state` | `app/agents/runner.py`, `app/agents/tools.py`, `app/config.py` |
| Helper `neo4j_for_adk.py` (`graphdb.send_query`, `tool_success`/`tool_error`) | Neo4j access with ADK-friendly results | `app/graph/neo4j_client.py` (reimplemented) |
| L4 User intent agent | `set_perceived_user_goal`, `approve_perceived_user_goal` → `approved_user_goal` | `app/agents/intent.py`, `routers/sessions.py` (`/goal`) |
| L5 File suggestion agent | `list_available_files`, `sample_file`, `set_suggested_files`, `approve_suggested_files` | `app/agents/file_suggestion.py`, `app/files.py`, `routers/sessions.py` (`/files`) |
| L6 Schema proposal, structured | proposer + critic (`output_key="feedback"`) + `CheckStatusAndEscalate` in a `LoopAgent`; `propose_node_construction`, `propose_relationship_construction`, `search_file` | `app/agents/schema_structured.py`, `routers/schema.py` (`/schema/structured`) |
| L7 Schema proposal, unstructured | NER agent (`get_well_known_types`, `set_proposed_entities`) → fact-type agent (`add_proposed_fact`) | `app/agents/schema_unstructured.py`, `routers/schema.py` (`/schema/unstructured`) |
| L8 KG construction | `create_uniqueness_constraint`, `load_nodes_from_csv`, `import_relationships`, `SimpleKGPipeline` + `RegexTextSplitter`, entity resolution with `apoc.text.jaroWinklerDistance` → `CORRESPONDS_TO` | `app/construction/*`, `app/graph/cypher.py`, `routers/build.py` |
| L8 closing questions | root-cause query across the domain and lexical graphs | `NAMED_QUERIES["root_cause"]`, `app/agents/graphrag.py`, `routers/query.py` |

## Setup

### Option A: Docker Compose (recommended, matches production)

```bash
cp .env.example .env          # set OPENAI_API_KEY (and NEO4J_PASSWORD if you like)
docker compose up --build     # neo4j + redis + api + worker
open http://localhost:8000/docs     # Swagger UI
open http://localhost:7474          # Neo4j Browser (neo4j / please-change-me)
```

Compose runs `STATE_BACKEND=redis` and `JOB_RUNNER=worker`, mounts `./data` into Neo4j's import
directory (for `LOAD CSV`) and into the API/worker (for the agents' `sample_file`), and enables APOC.

### Option B: local Python (fast dev loop)

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                       # STATE_BACKEND=memory, JOB_RUNNER=inprocess
docker compose up -d neo4j                 # or any Neo4j 5.26+ with APOC, import dir = ./data
uvicorn app.main:app --reload --port 8000  # or: PORT=8000 python -m app
```

### Tests

```bash
pytest -q                                   # 24 tests, no keys/Neo4j/Redis needed
RUN_NEO4J_IT=1 NEO4J_PASSWORD=please-change-me pytest -q   # + real-Neo4j integration test
```

The tests replace the LLM with fakes: `FakeRunner` drives the real tool functions, and
`test_adk_runner.py` runs the actual ADK `Runner` with a scripted fake `BaseLlm`. Neo4j is
replaced by a `FakeGraph`, and Redis by `fakeredis`. **Real LLM calls are not covered by the
tests.** Try them by hand with a key (walkthrough below).

## Endpoint walkthrough (curl)

```bash
B=http://localhost:8000
J='content-type: application/json'

# Health: liveness (no dependencies) and readiness (Neo4j + state store)
curl $B/health
curl $B/health/ready

# 1) Create a session (the HTTP version of the notebooks' shared ADK session)
SID=$(curl -s -XPOST $B/sessions | jq -r .id)

# 2) L4: chat with the user intent agent (call it several times; history is kept)
curl -s -XPOST $B/sessions/$SID/goal -H "$J" \
  -d '{"message":"I want to find the root cause of product quality issues using my BOM and supplier data."}' | jq
curl -s -XPOST $B/sessions/$SID/goal -H "$J" -d '{"message":"Yes, that is right."}' | jq
curl -s -XPOST $B/sessions/$SID/goal/approve | jq          # human approval -> approved_user_goal
#   (no LLM? set it directly:)
# curl -XPUT $B/sessions/$SID/goal -H "$J" -d '{"kind_of_graph":"supply chain analysis","description":"..."}'

# 3) L5: file suggestions, then approve
curl -s $B/sessions/$SID/files/available | jq
curl -s -XPOST $B/sessions/$SID/files -H "$J" -d '{}' | jq .state.suggested_files
curl -s -XPOST $B/sessions/$SID/files/approve | jq
# curl -XPUT $B/sessions/$SID/files -H "$J" -d '{"files":["products.csv","assemblies.csv","components.csv","part_supplier_mapping.csv","suppliers.csv"]}'

# 4) L6: structured schema (proposer/critic loop); returns typed node/relationship rules
curl -s -XPOST $B/sessions/$SID/schema/structured -H "$J" -d '{"feedback":""}' | jq
curl -s -XPOST $B/sessions/$SID/schema/structured/approve | jq
# curl -XPUT "$B/sessions/$SID/schema/structured?use_default=true"     # known-good plan

# 5) L7: unstructured schema. "all" = NER -> auto-approve -> facts (SequentialAgent)
curl -s -XPOST $B/sessions/$SID/schema/unstructured -H "$J" -d '{"phase":"all"}' | jq
#    or step by step like the notebook:
#    {"phase":"entities"} -> POST .../unstructured/approve-entities -> {"phase":"facts"}
curl -s -XPOST $B/sessions/$SID/schema/unstructured/approve | jq
# curl -XPUT "$B/sessions/$SID/schema/unstructured?use_default=true"

# 6) L8: build in the background -> 202 + job id, then poll
JOB=$(curl -s -XPOST $B/sessions/$SID/build -H "$J" -d '{"reset_graph":true}' | jq -r .id)
watch -n2 "curl -s $B/jobs/$JOB | jq '{status,progress,steps}'"
#    structured only (no LLM needed): -d '{"include_unstructured":false}'

# 7) Query
curl -s -XPOST $B/query -H "$J" -d '{"named":"graph_summary"}' | jq
curl -s -XPOST $B/query -H "$J" -d '{"named":"root_cause","limit":10}' | jq
curl -s -XPOST $B/query -H "$J" -d '{"cypher":"MATCH (p:Product)-[:CONTAINS]->(:Assembly)<-[:IS_PART_OF]-(:Part)-[:SUPPLIED_BY]->(s:Supplier) WHERE p.product_id=$id RETURN DISTINCT s.name","params":{"id":"P-1000"}}' | jq
curl -s -XPOST $B/query -H "$J" -d '{"question":"Which suppliers provide parts for products with the most complaints?"}' | jq
```

| Method | Path | Purpose |
|---|---|---|
| GET | `/health`, `/health/ready` | liveness, readiness |
| POST | `/sessions` · GET `/sessions/{id}` | create or inspect a session (full shared state) |
| POST | `/sessions/{id}/goal` · `/goal/approve` · PUT `/goal` | L4 chat, approve, set directly |
| GET | `/sessions/{id}/files/available` | files in DATA_DIR |
| POST | `/sessions/{id}/files` · `/files/approve` · PUT `/files` | L5 suggest, approve, set directly |
| POST | `/sessions/{id}/schema/structured` · `/approve` · PUT | L6 propose (loop), approve, set or default |
| POST | `/sessions/{id}/schema/unstructured` · `/approve-entities` · `/approve` · PUT | L7 |
| POST | `/sessions/{id}/build` → 202 · GET `/jobs/{job_id}` | L8 background build + progress |
| POST | `/query` | read-only Cypher, named query (root cause), or natural-language question |

### Why each FastAPI feature is used

- **`APIRouter`**: one router per stage of the workflow, so each lesson's endpoints live together and show up grouped in `/docs`.
- **Pydantic models**: validate requests (bad input returns 422 automatically), define stable response shapes (`NodeConstruction`/`RelationshipConstruction` use a discriminated union), and generate the OpenAPI docs.
- **`Depends` / `Annotated` dependencies**: the Neo4j wrapper, state store, agent runner, file catalog and settings are injected, not global, so tests swap them through `dependency_overrides` or `app.state`. `SessionDep` resolves `{session_id}` and returns 404 in one place.
- **`lifespan`**: creates the clients once at startup and closes them on shutdown (graceful SIGTERM).
- **`BackgroundTasks`**: the build can take minutes, so the endpoint returns 202 right away and the client polls `/jobs/{id}`.
- **HTTP middleware**: one JSON access-log line per request, with an `x-request-id`.
- **`response_model`** keeps internals (such as the job payload snapshot) out of responses.

## Twelve-Factor

| Factor | How this project meets it |
|---|---|
| **I. Codebase** | One repo, one app. The same code runs as the `api` and `worker` processes and in the admin `scripts/`. |
| **II. Dependencies** | Every runtime dependency is pinned exactly in `requirements.txt` (dev extras in `requirements-dev.txt`) and installed into an isolated venv or image. Nothing relies on system packages. |
| **III. Config** | All config comes from env vars via `pydantic-settings` (`app/config.py`). Secrets are `SecretStr`. `.env` is only for local dev; `.env.example` has no real keys. |
| **IV. Backing services** | Neo4j (`NEO4J_URI`/creds), the LLM (`LLM_MODEL`, `OPENAI_API_KEY`, `LLM_API_BASE`) and Redis (`REDIS_URL`) are attached resources. Swap local containers for Aura, another LLM provider or managed Redis by changing env vars only. |
| **V. Build, release, run** | A multi-stage `Dockerfile`: the build stage compiles wheels and the run stage installs them only. Release = image plus env (compose or k8s). Run = `python -m app` / `python -m app.worker`. |
| **VI. Processes** | API processes are stateless. Sessions and jobs sit behind the `StateStore` interface: `MemoryStateStore` for the demo and `RedisStateStore` when `STATE_BACKEND=redis`. ADK sessions are rebuilt from the store on every request. |
| **VII. Port binding** | The app binds `$PORT` itself (`python -m app` runs uvicorn on `HOST:PORT`). |
| **VIII. Concurrency** | Two process types: `api` (web) and `worker` (builds). `JOB_RUNNER=inprocess` uses FastAPI `BackgroundTasks`, which is simple but shares the API's CPU and loses the job if the pod restarts. `JOB_RUNNER=worker` enqueues jobs in Redis for `python -m app.worker`; scale workers independently (`docker compose up --scale worker=3`). |
| **IX. Disposability** | Fast startup: drivers connect lazily and heavy ADK/LiteLLM/graphrag imports are deferred. Graceful shutdown: the lifespan closes the Neo4j driver and Redis pool, and the worker finishes its current job on SIGTERM before exiting. |
| **X. Dev/prod parity** | The same compose services (Neo4j 5.26 + APOC, Redis, api, worker) and the same image are used in dev and prod. Only env vars differ. |
| **XI. Logs** | Structured JSON, one event per line, to stdout only (`app/logging_config.py`). uvicorn logs are reformatted too. No log files. |
| **XII. Admin processes** | One-off tasks live in `scripts/` and run with the same code and config: `python -m scripts.load_sample_data [--with-reviews]` and `python -m scripts.reset_graph --yes` (`docker compose run --rm api python -m scripts.reset_graph --yes`). |

**Concurrency tradeoff in detail.** Running the build in-process is fine for a laptop demo. In
production, LLM extraction ties up CPU and event-loop time and can run for minutes. A pod restart
or Knative scale-to-zero would kill it mid-way. The worker model separates the two, and the API
stays fast and stateless. The included worker uses a plain Redis list (`BRPOP`). If a worker is
killed hard, that job stays `running`. For guaranteed redelivery, move to Redis Streams with
acks, or to RQ, Arq or Celery.

## Deploying to your Knative / Kind cluster (Mac mini)

You already have `kn quickstart kind` running. Here is a minimal path:

```bash
# 1) Build and load the image straight into Kind (no registry needed for dev.local/)
docker build -t dev.local/kg-api:0.1.0 .
kind load docker-image dev.local/kg-api:0.1.0 --name knative

# 2) Backing services: plain Deployments/Services (or point at Neo4j Aura / managed Redis)
kubectl create secret generic kg-secrets \
  --from-literal=OPENAI_API_KEY=sk-... --from-literal=NEO4J_PASSWORD=please-change-me
#   e.g. helm install neo4j neo4j/neo4j --set neo4j.password=please-change-me ... (enable APOC)
#   and  kubectl create deployment redis --image=redis:7-alpine && kubectl expose deployment redis --port 6379

# 3) The API as a Knative Service (Knative injects $PORT; the app already binds it)
kn service create kg-api --image dev.local/kg-api:0.1.0 \
  --env NEO4J_URI=bolt://neo4j.default.svc.cluster.local:7687 \
  --env STATE_BACKEND=redis --env REDIS_URL=redis://redis.default.svc.cluster.local:6379/0 \
  --env JOB_RUNNER=worker \
  --env-from secret:kg-secrets \
  --scale-min 0 --scale-max 5
curl http://kg-api.default.127.0.0.1.sslip.io/health

# 4) The worker as a normal Deployment (it must not scale to zero mid-job)
kubectl create deployment kg-worker --image=dev.local/kg-api:0.1.0 -- python -m app.worker
kubectl set env deployment/kg-worker --from=secret/kg-secrets \
  NEO4J_URI=bolt://neo4j.default.svc.cluster.local:7687 STATE_BACKEND=redis \
  REDIS_URL=redis://redis.default.svc.cluster.local:6379/0
```

Notes:
- With scale-to-zero, **always use `STATE_BACKEND=redis` + `JOB_RUNNER=worker`**. In-memory state and in-process builds vanish when the pod goes away.
- The CSVs must be in **Neo4j's** import directory for `LOAD CSV`. Bake them into a custom Neo4j image or mount a volume. The API image already contains `data/` for the agents.
- Point a liveness probe at `/health` and a readiness probe at `/health/ready`.
- If you ran the quickstart with `--host-port 8080`, add `:8080` to the sslip.io URL.

## Assumptions, gaps and differences from the notebooks

- **API mode.** The notebooks run the schema agents in an interactive chat. Here they run one-shot, and you approve through explicit `/approve` endpoints. The prompts get a short `API_MODE_SUFFIX` that tells the agent not to wait for approval. L4 and L5 stay conversational, and chat history is kept per session.
- **Stateless ADK.** Each request builds a fresh ADK `InMemorySessionService` session from the stored state. Earlier turns are replayed as a transcript in the prompt rather than as native ADK events.
- **The `neo4j_for_adk.py` helper was reimplemented**, based on the companion repo. `is_write_query` is stricter than the course's. `/query` also runs with READ routing; still use a read-only Neo4j user in production.
- **Sample data** comes from the companion repo (`components.csv` stands in for the course's parts file). See `data/README.md`.
- **`app/domain/defaults.py`** is a hand-written known-good plan for LLM-free demos, not a notebook output.
- **The L8 lexical graph** uses neo4j-graphrag 1.24's `schema={node_types, relationship_types, patterns}` instead of the older `entities/relations/potential_schema` arguments. Predicates are normalised to `UPPER_SNAKE` relationship types (for example `has_issue` becomes `HAS_ISSUE`). It needs an **OpenAI** key for extraction and embeddings; the ADK agents can use any LiteLLM provider.
- **Entity resolution** matches extracted `name` against the first `*name*` property of the domain node with the same label, using Jaro-Winkler distance below 0.1, as in the notebook.
- **Neo4j 5.26+ is required**, for dynamic labels `$($label)` and `CALL (row) {...} IN TRANSACTIONS`.

## License

[MIT](LICENSE). Prompts, tool functions and Cypher are adapted from the course and from
[neo4j-contrib/agentic-kg](https://github.com/neo4j-contrib/agentic-kg), which is also MIT licensed;
see that repository for its copyright notice.
