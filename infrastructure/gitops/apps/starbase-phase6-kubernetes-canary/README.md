# Starbase Phase 6 Kubernetes observation canary

Date: 2026-08-31
Owner and approving authority: Al McKay
Status: prepared under the bounded Starbase pre-production acceleration cycle

## Scope

This overlay inherits the accepted Phase 5 native Observatory deployment and
adds one read-only Kubernetes connector. It observes only Pods, Deployments,
StatefulSets, and DaemonSets in `starbase-connectors`, `starbase-execution`, and
`starbase-system`. It cannot read Secrets, ConfigMaps, Nodes, logs, or
cluster-scoped resources. It has no mutation verbs. The live GitHub connector
remains at zero replicas, both migrator Jobs remain suspended, and the
synthetic preview fixture remains active so its known observations continue to
exercise the same durable ingestion path.

The connector is required to run on `asio` or `strix`. Its declared request is
50m CPU and 64Mi memory, with a 500m CPU and 256Mi limit. The pre-activation
checkpoint found all nodes Ready and pressure-free, `asio` at 3% CPU / 36%
memory, and `strix` at 4% CPU / 20% memory. Refresh those values immediately
before merge and stop on pressure, degraded Flux, or materially reduced
headroom.

## Exact artifact and trust boundary

GitHub-hosted Actions cannot currently start because the account billing limit
has been reached. Under accepted ADR 0009's time-bounded owner-local
pre-production exception, the connector was built for `linux/amd64` from clean
Starbase main revision `e9e431b95e3d375f2ed5da8cad4084977578228d` and
preloaded into K3s containerd on both preferred nodes. It is not a production
release or a claim of signed provenance.

- Workload image digest:
  `sha256:1942252813483c551bf7992b13344f262d13db18f20758f2b8be1e7446339c26`
- OCI config / CRI image ID:
  `sha256:ae624a049a73e8088ff32a3157e2767f5adf8e087d64f208171bdeea439f4d79`
- Docker archive SHA-256:
  `50e4439aa37634927a344eb69130bd7b8edf19bb94f63ac8e7831c6494dbb19d`
- Trivy security evidence SHA-256:
  `811de4e73ecc57ca579baf5064ad5d7a831bba7bd70996c727b93269b15565b0`

Pinned Trivy 0.70.0 reported zero fixed HIGH/CRITICAL vulnerabilities and zero
secret findings. CRI inspection on both nodes independently confirmed the
exact source revision, `linux/amd64`, and non-root `65532:65532` runtime. A
normally signed release successor must replace this artifact before the ADR
0009 exception expires or any production transition begins.

The workload uses a ten-minute projected Kubernetes API token and a separate
ten-minute `starbase-core` audience token. NetworkPolicy permits DNS, the exact
Kubernetes API endpoints, and core port 8081 only. Core admits this Service
Account identity only for `kubernetes` observations. The configured scope sets
`include_nodes` to false and has an empty Flux namespace list.

## Activation and acceptance

Merge is the activation decision. Let Flux reconcile naturally; do not force
it. Before merge, require healthy nodes and Flux, fresh capacity, exact image
resolution on both preferred nodes, the three namespace-scoped list-only Role
bindings, denied Secrets and Nodes, zero GitHub replicas, and suspended
migrations.

After reconciliation require:

1. exactly one Ready Kubernetes connector on `asio` or `strix`, zero restarts,
   and the exact image ID and source annotation;
2. successful bounded collection for all three namespaces without RBAC or
   network errors;
3. the `kubernetes:kubani:starbase-namespaces-v1` source becomes fresh in core,
   while the synthetic GitHub source remains fresh;
4. an independent Kubernetes API comparison agrees with the resulting
   workload observations;
5. the live GitHub connector remains at zero, migrations remain suspended,
   unauthenticated API requests remain denied, and all Flux dependencies remain
   Ready; and
6. node health and capacity remain stable after rollout.

Any unexpected permission, Secret or cluster-scoped access, digest drift,
migration execution, identity failure, stale source, restart loop, node
pressure, or Flux degradation stops the canary.

## Exact pre-merge evidence

At `2026-08-31T23:09:58Z`, the exact candidate passed all 108 local promotion,
Phase 4A/5/6, rollback, heartbeat, backup/recovery, Authentik, and live-probe
contract tests. Every relevant Kustomize target rendered; YAML, secret,
SOPS-encryption, high-entropy, and repository diff checks passed. A
Flux-equivalent server-side dry-run admitted all 57 non-Secret candidate
resources plus the exact Flux Kustomization without persistence.

Immediately before that dry-run, all four nodes were Ready and pressure-free,
every Flux Kustomization was Ready at
`main@sha1:c4e4cabfb1d628e550dfff354e17e9c23b4e3eba`, and every non-completed Pod
was Running and Ready. `asio` used 4% CPU / 36% memory and `strix` used 5% CPU /
20% memory. Core was 2/2 Ready on `strix`; the synthetic fixture was 1/1 Ready
on `asio`; both had zero restarts. Both live provider connectors were at zero
replicas, and both successor migration Jobs remained suspended with no active,
successful, or failed execution.

## Rollback and cleanup

Rollback is a reviewed forward GitOps change restoring the Flux path to
`./infrastructure/gitops/apps/starbase-phase5-session-repair`. That removes the
Kubernetes source from core's expected-source contract and returns the
Kubernetes connector to zero replicas without replaying migrations or changing
database state. Verify Phase 5 core and fixture freshness, GitHub and Kubernetes
connector replicas at zero, and full Flux readiness after rollback.

After successful rollout, remove only the transferred Docker archives from
`/home/al/starbase-kubernetes-connector-e9e431b95.tar` on `asio` and `strix`.
Retain the imported image through the acceptance and rollback window.
