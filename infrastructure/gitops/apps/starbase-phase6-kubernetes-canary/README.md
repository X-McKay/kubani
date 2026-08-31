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
checkpoint found all nodes Ready and pressure-free, `asio` at 3% CPU / 37%
memory, and `strix` at 5% CPU / 20% memory. Refresh those values immediately
before merge and stop on pressure, degraded Flux, or materially reduced
headroom.

## Exact artifact and trust boundary

GitHub-hosted Actions cannot currently start because the account billing limit
has been reached. Under accepted ADR 0009's time-bounded owner-local
pre-production exception, the core and connector were built for `linux/amd64`
from clean Starbase main revision
`400711d9fbb3e068f6dff274e58db26bcae934e3` and preloaded into K3s containerd
on both preferred nodes. They are not production releases or a claim of signed
provenance.

Core artifact:

- OCI manifest digest:
  `sha256:b906d2d2d3e2aff743974cd829b548932101615f9f10ca2ad3c5413b84eb4809`
- OCI config / CRI image ID:
  `sha256:561a898ae546c8df9f2369dacfa458f92a0296294286ee882abf24e6baedd639`
- OCI archive SHA-256:
  `8a73d61c9b446135299602e06fc17033791c0e92ac67ff2c5c7b756c983173fb`
- Equivalent Docker archive SHA-256:
  `a11d5000e55fd3eb14c4e01d3eb76b9422da1bac551707df7500251f6151fffa`
- Trivy security evidence SHA-256:
  `03a506ccf058358a506857b9dd4fcc5f29d8d6ad2002290f5befd0e6b5074cbc`

Kubernetes connector artifact:

- OCI manifest digest:
  `sha256:70595d0171b481ae78b221e52b11f38a67aedf6768974fb77b19a875c42ae7c5`
- OCI config / CRI image ID:
  `sha256:87d4be4fae2a98a354695525e040a555890dbfdd472a38746f08afcb7830cd43`
- OCI archive SHA-256:
  `e080ff369c2ffde5c5299d4be218f0d5dda3e2cc9aefb9a37c1063ae96d5378a`
- Equivalent Docker archive SHA-256:
  `84488689147a773522dc100f4822e8fae39b8adfdde16b5eb2ec622cfc7145bb`
- Trivy security evidence SHA-256:
  `9e023c6874e2132d9f6ee967f08796e178bc030fe8639bd19d4abaf9c6ee49dc`

Pinned Trivy 0.70.0 reported zero fixed HIGH/CRITICAL vulnerabilities and zero
secret findings for both Docker archives exported from the exact local images.
OCI archives of those same images were used for preload so containerd retained
their manifest identities. CRI inspection on both nodes independently
confirmed each matching manifest digest and `linux/amd64`; image configuration
retains source revision `400711d9fbb3e068f6dff274e58db26bcae934e3` and
non-root `65532:65532`. Normally signed release successors must replace these
artifacts before the ADR 0009 exception expires or any production transition
begins.

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

1. exactly one Ready core and Kubernetes connector on `asio` or `strix`, zero
   restarts, and the exact image IDs and source annotations;
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

At `2026-08-31T23:40:56Z`, the exact candidate passed all 108 local promotion,
Phase 4A/5/6, rollback, heartbeat, backup/recovery, Authentik, and live-probe
contract tests. Every relevant Kustomize target rendered; YAML, secret,
SOPS-encryption, high-entropy, and repository diff checks passed. A
Flux-equivalent server-side dry-run admitted all 57 non-Secret candidate
resources plus the exact Flux Kustomization without persistence.

Immediately before that dry-run, all four nodes were Ready and pressure-free,
every Flux Kustomization was Ready at
`main@sha1:c018087f140ad86773a50326f1be85465b960d1b`, and every non-completed Pod
was Running and Ready. `asio` used 3% CPU / 37% memory and `strix` used 5% CPU /
20% memory. Core was 2/2 Ready, and the Kubernetes connector and synthetic
fixture were each 1/1 Ready; all three ran on `asio` with zero restarts. The live
GitHub connector remained at zero replicas, and both successor migration Jobs
remained suspended with no active, successful, or failed execution.

## Rollback and cleanup

Rollback is a reviewed forward GitOps change restoring the Flux path to
`./infrastructure/gitops/apps/starbase-phase5-session-repair`. That removes the
Kubernetes source from core's expected-source contract and returns the
Kubernetes connector to zero replicas without replaying migrations or changing
database state. Verify Phase 5 core and fixture freshness, GitHub and Kubernetes
connector replicas at zero, and full Flux readiness after rollback.

After successful rollout, remove only the transferred archives named
`/home/al/starbase-core-400711d{,-oci}.tar`,
`/home/al/starbase-kubernetes-connector-400711d{,-oci}.tar`, and the predecessor
`/home/al/starbase-kubernetes-connector-e9e431b95.tar` from `asio` and `strix`.
Retain the imported images through the acceptance and rollback window.
