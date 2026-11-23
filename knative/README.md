# Deploying on Knative

This is the cluster deployment guide. For the local loop, use
[`docker compose`](../docker-compose.yml) from the repo root — it starts Neo4j,
Redis, the API and the worker with the same environment variables.

The application is already shaped for this: configuration is entirely
environment-driven via `pydantic-settings` ([`app/config.py`](../app/config.py)),
the image is a single artifact for both process types, and state lives in Redis
rather than in the process. Nothing in `app/` needs to change to deploy here.

---

## 1. What is in this folder

| File | Apply? | Purpose |
|---|---|---|
| `configmap.yaml` | yes (via kustomize) | Non-sensitive settings: Neo4j URI, Redis URL, model names, state backend |
| `service.yaml` | yes (via kustomize) | Knative **Service** for the API: image, port 8000, probes, autoscaling |
| `worker.yaml` | yes (via kustomize) | Plain **Deployment** for `python -m app.worker` |
| `kustomization.yaml` | — | Lists the three above and pins the namespace; excludes the Secret template |
| `secret.example.yaml` | **no — reference only** | Shows which keys exist. Never fill it in or keep a real Secret in this folder; create it with `kubectl` (§4.3) |

Apply everything with:

```bash
kubectl apply -k knative/
```

Do **not** run `kubectl apply -f knative/`. `-f` treats every YAML in the
directory as a Kubernetes resource: it will try to apply `secret.example.yaml`
(placeholders that would replace your real Secret) *and* `kustomization.yaml`
itself, which is a build config rather than a resource. The command therefore
either errors or does the wrong thing. `-k` reads an explicit allowlist instead.

### 1.1 Why `kustomization.yaml`?

Kubernetes does not require it; three explicit files would also work:

```bash
kubectl apply -f knative/configmap.yaml \
              -f knative/service.yaml \
              -f knative/worker.yaml
```

The kustomization earns its place for four reasons:

1. **An allowlist instead of a directory scan.** Only the listed resources are
   applied, so a template, a scratch manifest, or a future `secret.yaml` can sit
   in the folder without any chance of being applied by the deploy command.
2. **One namespace.** `namespace: kg-demo` is stamped onto every namespaced
   resource, so the manifests stay namespace-free (portable, copy-pasteable) and
   there is exactly one place to change the target. Running
   `kubectl apply -f knative/service.yaml` directly would silently deploy to
   `default`.
3. **A stable command.** `kubectl apply -k knative/` does not change when files
   are added, renamed or split. A `-f` list must be maintained by hand and is
   easy to run in an incomplete form.
4. **A home for transformations.** Pinning the image tag once
   (`images:`), shared labels, or a generated ConfigMap go here later without
   editing `service.yaml` and `worker.yaml` separately.

What it does **not** do:

- **It does not create the namespace.** Run `kubectl create namespace kg-demo`
  first, or `apply -k` fails.
- **It does not order applies or wait for readiness.** The Secret must already
  exist (§4.3) because `envFrom` is read when the container starts.
- **It does not template.** There is no `${VAR}` substitution from your shell or
  environment: values live in `configmap.yaml`, and real secrets in a
  `kubectl`-created Secret (§4.3). This is the most common Helm expectation it
  does not meet.
- **It does not manage the Secret.** `secret.example.yaml` is documentation, and
  is deliberately absent from the `resources:` list.

Preview what it will do:

```bash
kubectl kustomize knative/     # render the final YAML; no cluster needed
kubectl diff -k knative/       # what would change on the cluster
```

`kustomize` is built into `kubectl` (since 1.14), so there is no extra binary to
install. Helm would add templating and release state that a three-manifest
deployment does not need; a bare `-f` list would lose the allowlist.

## 2. Prerequisites

- A Kubernetes cluster with **Knative Serving** installed and working
  (`kubectl get ksvc` succeeds). The quickstart is the fastest path:
  `kn quickstart kind` or `kn quickstart minikube`.
- Knative networking configured with a domain — `sslip.io` is fine for a
  cluster without DNS (the README's Mac mini setup uses it).
- `kubectl`, `kn` (Knative CLI) and `docker` (or `podman`) locally.
- A container registry you can push to (GHCR, Docker Hub, a local registry, or
  `kind load` — see §3).
- A reachable **Neo4j 5.26+** (APOC enabled) and **Redis**. See §6; the CSV
  build path has one hard requirement that rules out some managed services.
- If your Knative quickstart was created with `--host-port 8080`, append
  `:8080` to generated `sslip.io` URLs.

```bash
kubectl create namespace kg-demo
```

`kustomization.yaml` targets `kg-demo`; `kubectl apply -k` does not create
namespaces, so this step is required.

## 3. Build and push the image

The image contains the API *and* the worker; the entrypoint decides which
process runs. `ui/` is not built into the image yet — when the SPA lands, the
Dockerfile gains a `node` stage and `UI_DIST_DIR=/app/ui/dist` is added here.

```bash
# Multi-arch: the Mac mini cluster is arm64, CI or a laptop may be amd64.
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t ghcr.io/usametov/kg-fastapi-demo:latest \
  --push .
```

Single-arch on the cluster's own architecture is enough for a demo:

```bash
docker build -t ghcr.io/usametov/kg-fastapi-demo:latest .
docker push ghcr.io/usametov/kg-fastapi-demo:latest
```

Then update `image:` in **both** `service.yaml` and `worker.yaml` (or override
it with `kustomize`'s `images:` field). With `kind`, no registry is needed:

```bash
kind load docker-image ghcr.io/usametov/kg-fastapi-demo:latest
```

`imagePullPolicy: IfNotPresent` in the manifests makes the loaded image win.

## 4. Configuration

### 4.1 Every variable the app reads

All of these come from `Settings` in `app/config.py`. Defaults are shown for
reference; the ConfigMap or Secret is the source of truth in the cluster.

| Variable | Default in code | Set in | Notes |
|---|---|---|---|
| `APP_NAME` | `kg-fastapi-demo` | ConfigMap | Used as the ADK app name |
| `ENVIRONMENT` | `dev` | ConfigMap → `prod` | Literal: `dev` \| `test` \| `prod` only |
| `HOST` | `0.0.0.0` | — | Correct for containers already |
| `PORT` | `8000` | **Knative** | Knative injects `PORT` from `containerPort`; don't put it in the ConfigMap |
| `LOG_LEVEL` | `INFO` | ConfigMap | JSON logs to stdout |
| `NEO4J_URI` | `bolt://localhost:7687` | ConfigMap | `bolt://neo4j:7687`, `neo4j+s://…` for Aura |
| `NEO4J_USERNAME` | `neo4j` | ConfigMap | |
| `NEO4J_PASSWORD` | `please-change-me` | **Secret** | Neo4j rejects the default unless you set it |
| `NEO4J_DATABASE` | `neo4j` | ConfigMap | |
| `LLM_MODEL` | `openai/gpt-4o` | ConfigMap | Any LiteLLM model string |
| `LLM_API_BASE` | unset | ConfigMap (commented) | For Ollama/vLLM/OpenAI-compatible gateways |
| `OPENAI_API_KEY` | unset | **Secret** | Needed when `LLM_MODEL` starts with `openai/` |
| `EXTRACTION_MODEL` | `gpt-4o` | ConfigMap | L8 lexical graph (neo4j-graphrag) talks to OpenAI directly |
| `EMBEDDING_MODEL` | `text-embedding-3-large` | ConfigMap | Same |
| `DATA_DIR` | `data` | ConfigMap → `/app/data` | Baked into the image |
| `STATE_BACKEND` | `memory` | ConfigMap → `redis` | **Required**: memory state dies with the pod |
| `REDIS_URL` | `redis://localhost:6379/0` | ConfigMap | Move to the Secret if it contains a password |
| `STATE_TTL_SECONDS` | `86400` | ConfigMap | Session/job expiry |
| `JOB_RUNNER` | `inprocess` | ConfigMap → `worker` | **Required**: in-process builds die on scale-down |
| `SCHEMA_LOOP_MAX_ITERATIONS` | `2` | ConfigMap | L6 proposer/critic loop |
| `REVIEW_CHUNK_SEPARATOR` | `---` | ConfigMap | L8 markdown splitter |
| `ENTITY_SIMILARITY_THRESHOLD` | `0.1` | ConfigMap | L8 Jaro-Winkler |

`ConfigMap` values are strings; pydantic coerces them to `int`/`float`/`Path`
as declared in `config.py`. Unknown variables are ignored (`extra="ignore"`),
so a stray key will not crash startup — but it also will not do anything.

### 4.2 ConfigMap vs Secret

Rule of thumb: anything that grants access goes in the Secret.

- **ConfigMap:** endpoints, model names, log level, feature knobs.
- **Secret:** `OPENAI_API_KEY`, `NEO4J_PASSWORD`, and `REDIS_URL` *only if* it
  carries a password.

Both are consumed with `envFrom`, so every key becomes an environment variable.
An explicit `env:` entry would override `envFrom`; this stack deliberately does
not set either, so there is exactly one source per key.

### 4.3 Create the Secret — you never need a `secret.yaml` here

`secret.example.yaml` is a **reference for which keys exist**, not a step. Do not
fill it in and keep it in `knative/`: the directory is one `git add -A` away from
publishing a live key, and `kubectl apply -f knative/` would apply it (which is
exactly why `kustomization.yaml` excludes it).

All three options below create the same `kg-fastapi-demo-secrets` object. Pick one.

**Option A — no file (recommended).** The key is prompted for, so it never reaches
your shell history:

```bash
read -rsp "OpenAI API key: " OPENAI_API_KEY; echo
kubectl -n kg-demo create secret generic kg-fastapi-demo-secrets \
  --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY" \
  --from-literal=NEO4J_PASSWORD="$(openssl rand -hex 24)"
unset OPENAI_API_KEY
```

**Option B — an env file outside the repo.** Convenient when you rotate often:

```bash
printf 'OPENAI_API_KEY=\nNEO4J_PASSWORD=%s\n' "$(openssl rand -hex 24)" \
  > ~/kg-secrets.env
chmod 600 ~/kg-secrets.env
$EDITOR ~/kg-secrets.env      # paste the key here; it stays out of shell history
kubectl -n kg-demo create secret generic kg-fastapi-demo-secrets \
  --from-env-file="$HOME/kg-secrets.env"
```

Keep it outside the repository. If it must live inside, add its exact name to
`.gitignore` *before* creating it — the existing `.env` pattern does not cover
`kg-secrets.env`.

**Option C — a manifest file outside the repo.** Copy the template to a scratch
location, fill it, and apply that path explicitly:

```bash
cp knative/secret.example.yaml ~/kg-secrets.yaml
$EDITOR ~/kg-secrets.yaml
kubectl apply -f ~/kg-secrets.yaml
```

Never `cp` the filled-in file into `knative/`.

**Re-running / updating.** `create` fails when the Secret already exists:

```bash
kubectl -n kg-demo create secret generic kg-fastapi-demo-secrets \
  --from-literal=OPENAI_API_KEY=... --dry-run=client -o yaml | kubectl apply -f -
```

**Verify without printing values.** `-o yaml` shows base64, which is plaintext
with extra steps:

```bash
kubectl -n kg-demo get secret kg-fastapi-demo-secrets
kubectl -n kg-demo get secret kg-fastapi-demo-secrets -o jsonpath='{.data}' | jq -r 'keys[]'
```

**After changing a value, restart the consumers.** `envFrom` is read at container
start, so an edited Secret does not propagate:

```bash
kubectl -n kg-demo rollout restart deploy/kg-fastapi-demo-worker
kubectl -n kg-demo delete pod -l serving.knative.dev/service=kg-fastapi-demo
```

If the Secret is missing entirely, the revision fails with
`CreateContainerConfigError` — the `secretRef` is not optional.

### 4.4 Volume mounts (not supported today)

The app reads plain environment variables only. It does **not** implement the
`*_FILE` convention, so mounting a Secret as a file will not configure
anything. Use `envFrom` (as the manifests do). Supporting volume-mounted
secrets would be a small `pydantic-settings` change — a reasonable follow-up,
not a requirement for this deployment.

## 5. Deploy and verify

Three steps, in this order — the Secret is read when the container starts, so it
must exist before the revision is created:

```bash
kubectl create namespace kg-demo          # 1. namespace (kustomize won't create it)
# 2. the Secret, §4.3 — e.g. the Option A one-liner
kubectl apply -k knative/                 # 3. ConfigMap + Service + worker

kubectl -n kg-demo get ksvc,deploy,pods
kn service list -n kg-demo
kn service describe kg-fastapi-demo -n kg-demo
```

Get the URL and hit the health endpoints:

```bash
BASE=$(kn service describe kg-fastapi-demo -n kg-demo -o url)
curl -s "$BASE/health" | jq        # {"status":"ok","version":"...","env":"prod"}
curl -s "$BASE/health/ready" | jq  # neo4j + state_store true, llm_configured true
```

`/health/ready` returning `503` means Neo4j or Redis is unreachable — check
`kubectl -n kg-demo logs deploy/kg-fastapi-demo-worker` and the API revision
logs. The OpenAPI UI is at `$BASE/docs`.

### 5.1 End-to-end smoke test

This path deliberately avoids the LLM: it uses the known-good plan from
`app/domain/defaults.py` and builds only the structured (CSV) graph. It needs
Neo4j reachable and the CSVs in Neo4j's import directory (§6.1).

```bash
J='content-type: application/json'

SID=$(curl -s -XPOST "$BASE/sessions" | jq -r .id)

curl -s -XPUT "$BASE/sessions/$SID/goal" -H "$J" -d '{
  "kind_of_graph":"supply chain analysis",
  "description":"Find the root cause of product issues by tracing products to parts and suppliers."
}' | jq

curl -s -XPUT "$BASE/sessions/$SID/files" -H "$J" -d '{
  "files":["products.csv","assemblies.csv","components.csv","part_supplier_mapping.csv","suppliers.csv"]
}' | jq

curl -s -XPUT "$BASE/sessions/$SID/schema/structured?use_default=true" | jq

JOB=$(curl -s -XPOST "$BASE/sessions/$SID/build" -H "$J" \
  -d '{"reset_graph":true,"include_unstructured":false}' | jq -r .id)

# 202 above; poll until succeeded (the work runs in the worker Deployment)
watch -n2 "curl -s $BASE/jobs/$JOB | jq '{status,progress,steps}'"

curl -s -XPOST "$BASE/query" -H "$J" -d '{"named":"graph_summary"}' | jq
```

A `202` followed by a job that stays `queued` means the worker is not running
or not consuming: check `JOB_RUNNER=worker`, `STATE_BACKEND=redis`, and the
worker logs.

## 6. Dependencies

The API and worker only hold connection strings; Neo4j and Redis are attached
resources (Twelve-Factor IV). They are not part of `kubectl apply -k knative/`.

### 6.1 Neo4j — the import directory matters

The structured build uses `LOAD CSV ... FROM "file:///" + $source_file`
([`app/graph/cypher.py`](../app/graph/cypher.py)), which reads from **Neo4j's
own import directory**, not from the API container. So:

- The five CSVs must be present in Neo4j's `import/` dir (default
  `NEO4J_server_directories_import=/import`).
- **Neo4j Aura does not support `file:///` imports.** Aura works for querying
  an existing graph, but the CSV build step will fail with a file-not-found
  error. Use a self-managed Neo4j for the full workflow, or change the loader
  to `https://` URLs first.
- APOC is required for entity resolution:
  `NEO4J_PLUGINS='["apoc"]'` and
  `NEO4J_dbms_security_procedures_unrestricted=apoc.*`.

Appendix A has a working single-node example that mounts the repo's `data/`
into `/import`.

### 6.2 Redis

Any Redis 7 works. `REDIS_URL=redis://redis:6379/0` in the ConfigMap assumes
no auth and an in-cluster Service named `redis`. With AUTH, put the full URL in
the Secret and remove it from the ConfigMap.

Both the API and the worker must use the **same** Redis database — that queue
is the only thing connecting them.

## 7. The worker

`worker.yaml` is a `Deployment`, not a Knative Service, for three reasons:

1. Knative Services need HTTP traffic; this is a Redis queue consumer.
2. Knative can scale a Service to zero. A worker at zero means queued builds
   never run.
3. A build takes minutes. Knative's `timeoutSeconds` ceiling applies to
   requests, and there is no request here at all.

Operationally:

```bash
kubectl -n kg-demo logs deploy/kg-fastapi-demo-worker -f
kubectl -n kg-demo scale deploy/kg-fastapi-demo-worker --replicas=3   # more builds in parallel
```

- The worker traps SIGTERM, finishes the current job, then exits
  (`terminationGracePeriodSeconds: 60`). A SIGKILL leaves the job stuck
  `running` — the code comments note that a reliable queue (RQ/Arq/Redis
  Streams with ack) would be the production fix.
- It calls `raise SystemExit` at start if `STATE_BACKEND != redis`. That is
  intentional: in-memory state is per-process, so a worker could never see the
  API's session.
- There is no probe because there is no listener. A hung LLM call looks
  healthy; watch the job status instead.

## 8. Scale-to-zero and streaming

These are the Knative settings that matter, and why:

| Setting | Value | Why |
|---|---|---|
| `timeoutSeconds` | `300` | Hard ceiling for a request *including a streaming response*. One agent turn must finish inside it; builds already use the job path |
| `containerConcurrency` | `10` | Each in-flight turn holds a slot, so this is your per-pod LLM concurrency |
| `max-scale` | `5` | Caps replicas and therefore LLM spend |
| `min-scale` | `0` | Cheapest. For a live demo use `1`: Python + ADK + LiteLLM import costs 2–5 s |
| `startupProbe` | `/health`, 60 s budget | Covers cold-start imports without failing the revision |
| `livenessProbe` | `/health` | Dependency-free, so a Neo4j outage does not restart pods |
| `readinessProbe` | `/health/ready` | 503 while Neo4j/Redis are down, so traffic drains instead of erroring |

Consequences to plan for:

- **Sessions survive scale-down only because they live in Redis.** With
  `STATE_BACKEND=memory` they would vanish with the pod.
- **The first request after zero has a cold start.** A future chat UI will show
  a "waking the service" state; until then it is a 2–5 s delay on `curl`.
- **A streaming response keeps a slot open** for its whole life. If you expect
  many simultaneous chat users, raise `containerConcurrency` and `max-scale`
  together and budget for the tokens.
- Knative injects `K_SERVICE`, `K_REVISION`, `K_CONFIGURATION` and `PORT`.
  The app already reads `PORT`; the `K_*` vars are handy for log correlation.

## 9. Local vs cluster

`docker compose` stays the fast inner loop. Knative is for the cluster.

| Concern | `docker compose up` | Knative |
|---|---|---|
| Build | `build: .` on every change (cached) | Image push + new revision |
| State | `STATE_BACKEND=redis`, Redis container | Redis Service (required) |
| Jobs | `JOB_RUNNER=worker`, worker container | `worker.yaml` Deployment |
| Neo4j | Compose service, `./data` mounted at `/import` | Self-managed StatefulSet (§6.1) or external |
| Scale to zero | No | Yes (configurable) |
| Cold start | None | 2–5 s |
| Secrets | `.env` file (git-ignored) | Kubernetes Secret |
| URL | `localhost:8000` | `$BASE` from `kn service describe` |

The environment variable names are identical in both, which is the point:
the same image and the same config run in both places.

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `RevisionMissing` / `RevisionFailed` | Bad image reference or a failing probe | `kubectl -n kg-demo describe revision <rev>`; check `Ready` reason |
| `ImagePullBackOff` | Private registry without a pull secret | Create `ghcr-pull-secret` and uncomment `imagePullSecrets` |
| `503` on every request | No ready revision (probes failing) or activator cold start | `curl $BASE/health`; check `/health/ready` and revision status |
| Readiness flaps | Neo4j or Redis unreachable from the pod | `kubectl -n kg-demo exec deploy/… -- python -c "…"`; check `NEO4J_URI` / `REDIS_URL` DNS names |
| Pod `OOMKilled` during schema turns | 1Gi limit too low for ADK + LiteLLM | Raise `memory` limit in `service.yaml` |
| Build job stuck `queued` | Worker not running, or `JOB_RUNNER`/`STATE_BACKEND` wrong | `kubectl get deploy`; worker logs; confirm ConfigMap values |
| Worker exits immediately | `STATE_BACKEND != redis` | Set `STATE_BACKEND=redis` (ConfigMap already does) |
| `LOAD CSV` file-not-found | CSVs not in **Neo4j's** `/import` | Mount `data/` at `/import` (§6.1, Appendix A) |
| `Unknown function 'apoc…'` | APOC not installed | `NEO4J_PLUGINS='["apoc"]'`, restart Neo4j |
| Request times out around 5 min | `timeoutSeconds` (300) hit on a long turn | Ship long work through `/build`; or raise `timeoutSeconds` (cluster max is usually 600) |
| `CreateContainerConfigError` | Secret or ConfigMap name mismatch | `kubectl -n kg-demo get secret,configmap` |
| App listens on the wrong port | `PORT` set in the ConfigMap overriding Knative's injection | Remove `PORT` from the ConfigMap |

## 11. Cleanup

```bash
kubectl delete -k knative/
kubectl -n kg-demo delete secret kg-fastapi-demo-secrets
kubectl delete namespace kg-demo
```

---

## Appendix A — minimal in-cluster Neo4j (optional)

Single node, good for a demo cluster. It mounts the repo's `data/` directory
into Neo4j's import dir so `LOAD CSV "file:///…"` works, and wires the password
from the Secret created in §4.3.

```bash
# 1) The CSVs, as a ConfigMap (the sample data is well under the 1 MiB limit)
kubectl -n kg-demo create configmap kg-sample-data --from-file=data/
```

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: neo4j
  labels: { app: neo4j }
spec:
  serviceName: neo4j
  replicas: 1
  selector:
    matchLabels: { app: neo4j }
  template:
    metadata:
      labels: { app: neo4j }
    spec:
      containers:
        - name: neo4j
          image: neo4j:5.26-community
          ports:
            - { name: bolt, containerPort: 7687 }
            - { name: http, containerPort: 7474 }
          env:
            - name: NEO4J_PASSWORD
              valueFrom:
                secretKeyRef: { name: kg-fastapi-demo-secrets, key: NEO4J_PASSWORD }
            - name: NEO4J_AUTH
              value: neo4j/$(NEO4J_PASSWORD)
            - { name: NEO4J_PLUGINS, value: '["apoc"]' }
            - { name: NEO4J_server_directories_import, value: /import }
            - { name: NEO4J_dbms_security_procedures_unrestricted, value: "apoc.*" }
          volumeMounts:
            - { name: data, mountPath: /data }
            - { name: import, mountPath: /import, readOnly: true }
      volumes:
        - name: import
          configMap:
            name: kg-sample-data
  volumeClaimTemplates:
    - metadata: { name: data }
      spec:
        accessModes: ["ReadWriteOnce"]
        resources: { requests: { storage: 5Gi } }
---
apiVersion: v1
kind: Service
metadata:
  name: neo4j
spec:
  selector: { app: neo4j }
  ports:
    - { name: bolt, port: 7687 }
    - { name: http, port: 7474 }
```

Notes:

- `$(NEO4J_PASSWORD)` expansion requires the variable to be declared *before*
  `NEO4J_AUTH` in the same `env` list — that is why the order matters.
- Change the password if you ever expose Bolt outside the cluster; the
  StatefulSet has no Ingress and the Service is `ClusterIP`.
- Bump the image to `neo4j:5.26` or newer — dynamic labels `$($label)` and
  `CALL (row) { … } IN TRANSACTIONS` need 5.26+.
- With Aura, skip this appendix and change the loader to `https://` CSV URLs
  instead (`file:///` is not supported by Aura).
