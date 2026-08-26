# Starbase Phase 5 synthetic preview

This overlay is the reviewable implementation candidate for Phase 5 of the
[authoritative Starbase Kubani deployment plan](https://github.com/X-McKay/Starbase/blob/main/docs/kubani-deployment-plan.md#phase-5--isolated-kubani-preview).
It is built on the accepted Phase 4 edge foundation and is not live or
authorized merely because it renders successfully. The Phase 4 probe, TLS,
DNS, expected zero-backend HTTPS, Flux, capacity, and zero-replica acceptance
evidence passed at `main@sha1:0e5f5667` and is retained in the activation
ledger.

## Exact preview scope

The overlay starts one Starbase core pod and one dedicated fixture-connector
pod. The fixture is an immutable, content-bound, visibly synthetic repository
snapshot. The connector submits four observations every 30 seconds through the
same projected-workload-identity, fencing, ingestion, persistence,
reconciliation, and checkpoint contract used by a live read-only GitHub
connector.

For this initial one-repository homelab release, the accepted proposed expected
and peak profile are intentionally the same constant profile: eight observation
submissions per minute. That is ten times the submission rate of a
four-observation live reconciliation every five minutes and is simpler and more
conservative than a separate load shaper. This proposal becomes accepted only through review
of the exact preview revision; no production capacity claim is made before the
24-hour measurement window completes.

The live GitHub and Kubernetes connectors remain at zero replicas. The fixture
identity has no Kubernetes RBAC, provider credential, provider egress, mutation
authority, or sandbox authority. Its only application egress is the core API;
the namespace's existing DNS policy supports service discovery.

Core receives a separate ten-minute Kubernetes API-audience projected identity
only for authenticated issuer discovery and JWKS retrieval. The locked
Starbase `0.1.0-rc.3` core reloads this file for every issuer request. The
promotion lock is bound to retained Starbase evidence revision
`878cc5a4e8e4356e0d18c818738c8a0f198a122b`, release source
`c4d107991a5a7cbbb4ad373c563d4422cdbb1ec2`, and rendered manifest digest
`sha256:dec2e9c31df9b939e44e71d0b8d41b4af16d8501454d50cd3ac07ef14af25a6b`.

The release narrows Kubernetes observation from one cluster-wide binding to
three exact namespace-local `Role` and `RoleBinding` pairs. They permit only
`list` on Pods and the three controller kinds in `starbase-system`,
`starbase-connectors`, and `starbase-execution`. The Kubernetes connector
remains at zero replicas during this phase, so that dormant authority is not
used by the synthetic preview.

The release also adds the content-addressed core migration Job
`starbase-core-migrate-3a3b6224525f`. It creates only the constrained
`starbase_core.connector_fence_high_water` table and does not backfill or
delete data. The already completed gateway migration has no new SQL. Its
original `0.1.0-rc.2` image and release labels remain deliberately retained so
Kubernetes is never asked to mutate, force-replace, or rerun its immutable
historical Job.

The core and fixture are required to schedule on `asio` or `strix`. Combined
requests are 175m CPU and 224Mi memory:

- core: 100m CPU / 128Mi memory;
- web sidecar: 25m CPU / 32Mi memory; and
- fixture connector: 50m CPU / 64Mi memory.

Their combined limits are 1.75 CPU and 896Mi memory. Existing namespace quotas
remain the upper bound. These values are declared budgets, not measured usage.

## Prior failed activation

The first Phase 5 activation at Kubani revision `d62ba4e4` failed closed on
2026-08-26. The core received `STARBASE_OIDC_REQUIRED_GROUPS` as the scalar
`starbase-operators`, while the locked `0.1.0-rc.3` core requires a bounded
JSON array. The core therefore rejected startup with `OIDC required groups
must be a bounded JSON array`; the fixture could not become Ready, the public
route returned `503`, and the 24-hour observation clock never started. Both
live provider connectors remained at zero replicas and no provider authority
was activated.

The owner reverted the activation through GitOps at revision `438a7836`. Flux
returned every Kustomization to Ready, pruned the preview-only resources, and
restored core and both live connectors to zero replicas. The additive database
migration had completed before rollback and remains in the migration ledger;
rollback deliberately did not delete its table or data. The corrected
candidate encodes the group requirement as `["starbase-operators"]` and has
regression coverage for both the foundation and preview render paths.

## Independent heartbeat

The separate Osprey Linux desktop is the Phase 5 external observer. A hardened
systemd timer runs the repository-owned
`infrastructure/scripts/starbase_preview_heartbeat.py` every five minutes
through Osprey's existing Tailscale device identity. Osprey is not a Kubani
node and the observer has no Kubernetes, GitHub, provider, Starbase, or
Tailscale provisioning credential and no mutation authority.

The observer verifies HTTPS readiness through each of the four reviewed Kubani
Tailscale node addresses with the production hostname retained for TLS SNI.
This prevents DNS ordering from hiding a partially unreachable ingress path.
It rejects DNS results outside those addresses and then verifies:

- public TLS and `/health/ready`;
- the anonymous session reports OIDC mode and remains unauthenticated; and
- login redirects only to the expected Authentik authorization endpoint.

The redirect check binds the exact HTTPS host and authorization path, Starbase
client ID and callback, Authorization Code response type, `openid groups`
scopes, PKCE S256 method, login/max-age controls, and non-empty one-time state,
nonce, and challenge values. It does not log those generated values. Only after
every check passes does it send an empty success ping to an independent
dead-man receiver. The opaque receiver URL is stored only as a root-readable
systemd credential on Osprey. A missing ping alerts the owner without exposing
Kubani response data.

The exact installation, receiver exercise, manual Osprey desktop journey, and
removal procedure are in the
[Osprey observer runbook](../../../observers/starbase-preview/README.md).
The observer does not replace in-cluster resource, dependency, data-integrity,
or user-journey evidence. Prometheus and Grafana remain intentionally scaled to
zero; missing metrics are not described as healthy.

GitHub/Tailscale workload federation is deliberately deferred for this
pre-production homelab phase. It would add a tailnet trust credential, tag/ACL,
GitHub OIDC permissions, and recurring Actions cost without improving the
current Osprey path enough to justify that complexity. Reconsider it before
production or unattended operation, or if Osprey can no longer provide a
separate reliable observation boundary. It remains an alternative, not an
accepted or partially configured dependency. Al McKay owns that decision in
[issue #90](https://github.com/X-McKay/kubani/issues/90).

## Pre-merge evidence

Before accepting the exact revision, require:

1. all local manifest, policy, secret, lint, and unit checks pass;
   CI intentionally includes the existing live-service probe contract tests
   because preview activation removes the core's zero-replica exemption;
2. the complete overlay and Flux Kustomization pass server-side dry-run without
   persistence (raw SOPS Secret objects are excluded because Flux decrypts and
   removes SOPS metadata before admission);
3. Phase 4's exact network probe, Certificate, DNS, HTTPS, Flux, node, and
   zero-replica acceptance evidence has passed;
4. all immutable image and fixture digests match the reviewed revision;
   specifically, the core must be the locked `0.1.0-rc.3` image containing
   authenticated issuer/JWKS retrieval and the fixture connector must equal
   that release lock's GitHub connector image;
5. `asio` and `strix` remain Ready, pressure-free, and within accepted
   headroom; and
6. Osprey remains online, separate from Kubani, and able to reach all four
   reviewed node ingress addresses; its exact repository revision and hardened
   inactive systemd units have been verified;
7. the independent dead-man receiver has a five-minute period, two-minute
   grace, and owner notification; one isolated success and one missed-period
   alert have been proven without exposing its opaque URL; and
8. the owner explicitly accepts the exact load profile, observation window,
   stop conditions, and rollback.

## Live activation and checks

Merge is the only activation mechanism. Do not manually apply this directory or
manually reconcile Flux without separate authorization. After merge:

1. Confirm all nodes and dependencies remain healthy, then confirm every Flux
   Kustomization reports `Ready=True` at the exact merge revision.
2. Confirm exactly one core pod and one preview-fixture pod are Ready on `asio`
   or `strix`; both live connector Deployments must still desire zero replicas.
3. Confirm the core and fixture have zero restarts, the expected images, bounded
   resources, projected identity, network policy, and no provider Secret.
4. From Osprey's desktop, confirm DNS, certificate, HTTPS readiness,
   unauthenticated denial, Authentik login/logout, stale-session behavior, and
   the truthful synthetic UI labels.
5. Confirm the synthetic source creates the four expected Signals/Bounties once,
   subsequent reconciliations remain idempotent, and freshness advances. Record
   that `snapshot.mode` is truthfully `live`, while source scope
   `github:starbase-preview/synthetic-observation` and every fixture-derived
   item title carry the synthetic identity. The owner must explicitly accept
   that string-level labeling as unmistakable for this window; otherwise stop
   and require a source-level synthetic field before retrying.
6. Enable the Osprey timer, force one service run, and verify its dead-man
   receiver recorded success before starting the 24-hour clock. A failed or
   missed run is an observation gap, not success.
7. Record five-minute resource, restart, readiness, dependency, database,
   heartbeat, freshness, and data-integrity samples for at least 24 continuous
   hours.

The clock restarts after any unexplained alert, heartbeat gap, freshness gap,
data loss, duplicate durable Signal, restart loop, unbounded resource trend, or
SLO breach.

## Required exercises

During the preview window, exercise one bounded fault at a time and restore a
clean baseline between exercises:

- login/logout, unauthenticated access, and stale session;
- API/SSE reconnect;
- core restart and fixture restart;
- reschedule between `asio` and `strix` without changing placement policy;
- PostgreSQL restart after a fresh backup and explicit database authorization;
- Authentik outage and recovery;
- external-heartbeat outage and recovery;
- migration restart safety, projection rebuild, isolated backup restore,
  release rollback, and Lifeboat diagnosis.

Database, identity, node, and recovery mutations retain their own explicit
authorization. This runbook does not grant it. Never combine faults during the
first exercise pass.

## Stop and rollback

Stop immediately on node pressure, dependency degradation, unexpected provider
or Internet access, authorization bypass, non-synthetic data, unexplained data
or freshness differences, migration ambiguity, failed recovery, or loss of an
independent observation path.

Rollback by reverting the exact Phase 5 commit and allowing Flux to reconcile
back to `starbase-phase4a-foundation`. Verify the core and fixture return to zero
or absence, the preview ServiceAccount/ConfigMap/policies are pruned, the live
connectors remain at zero, Flux and dependencies are Ready, and database state
is readable by the prior candidate. Do not delete database state during
rollback. Disable the Osprey heartbeat timer after retaining sanitized failure
evidence; an active heartbeat must never report an intentionally inert service
as healthy. Preserve failure logs and samples before pruning when safe.

## Evidence and sign-off

Retain the exact source and applied revisions, rendered digest, image and fixture
digests, CI links, Flux state, pod placement, resource samples, heartbeat runs,
synthetic journey results, fault-exercise results, database checks, rollback
evidence, anomalies, and owner decisions. Keep credentials, cookies, tokens,
kubeconfigs, and private raw infrastructure output out of Git.

Corrected-candidate validation: deterministic regeneration and verification,
85 local contract tests, and the complete `validate-local` path passed on
2026-08-26. Kubernetes server-side dry-run accepted the complete Secret-free
overlay and Flux Kustomization without persistence; raw SOPS Secret objects
were excluded because Flux decrypts them and removes SOPS metadata before
admission. The first activation failed and was rolled back as recorded above;
there has not yet been a successful live Phase 5 exercise. Independent review
and owner acceptance of the exact corrected revision remain required before
merge. Osprey installation, receiver-notification proof, exact-head validation,
and a final fresh cluster checkpoint remain pre-merge gates; none is represented
as complete by the repository-only implementation.
