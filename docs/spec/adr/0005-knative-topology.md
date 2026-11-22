# ADR-0005: Knative topology — one Service, a worker Deployment, self-managed Neo4j

- **Status:** accepted
- **Date:** 2026-11-22
- **Deciders:** Alan Samet
- **Related:** [knative/README.md](../../../knative/README.md), [technical design §6](../technical-design.md#6-concurrency-and-statelessness)

## Context

The service must run on Knative with scale-to-zero, within a 300 s request
ceiling and concurrency-based autoscaling. Two properties conflict with naive
Knative usage: sessions live in process memory by default, and a graph build takes
minutes.

Separately, the structured build uses `LOAD CSV … "file:///…"`, which reads
Neo4j's own import directory. Neo4j Aura does not support `file:///`.

## Decision

1. **One Knative Service** (`kg-fastapi-demo`) serves the API and, later, the
   static SPA — same origin.
2. **The worker is a plain `Deployment`**, never a Knative Service: it consumes a
   Redis queue and must not scale to zero mid-build.
3. **`STATE_BACKEND=redis` and `JOB_RUNNER=worker` are mandatory** in the cluster.
4. **Neo4j is self-managed** (StatefulSet or external with an import dir) until
   the loader speaks `https://`; Aura is viable only after that change.
5. Probes: `/health` for startup + liveness (dependency-free), `/health/ready`
   for readiness (Neo4j + state store).

## Consequences

- Scale-to-zero is safe for sessions and jobs because neither lives in the pod.
- Autoscaling is concurrency-based, and an open SSE stream holds a slot:
  `containerConcurrency: 10` × `maxScale: 5` is the real concurrency budget.
- Builds survive API restarts; the API only enqueues.
- Cold start (2–5 s) is a product concern: `minScale: 1` for live demos, and the
  UI shows a waking state.
- Someone must own the Neo4j volume and its `/import` contents; this is
  documented rather than automated.

## Alternatives rejected

| Option | Why not |
|---|---|
| **Worker as a Knative Service** | Needs HTTP traffic; scale-to-zero would strand queued jobs |
| **`JOB_RUNNER=inprocess` on Knative** | A scale-down kills a multi-minute build mid-flight |
| **`STATE_BACKEND=memory`** | Sessions vanish between replicas and after scale-to-zero |
| **Neo4j Aura + current loader** | `file:///` is unsupported; the CSV build fails |
| **In-cluster Neo4j inside the same pod** | Couples graph durability to a scale-to-zero workload |

## References

- `knative/service.yaml`, `knative/worker.yaml`, `knative/configmap.yaml`
- `app/worker.py` (exits unless `STATE_BACKEND=redis`)
