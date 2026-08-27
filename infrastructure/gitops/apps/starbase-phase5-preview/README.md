# Starbase RC4 Phase 5 synthetic preview

Status: prepared for exact-revision review; merge is the activation decision

This overlay implements Phase 5 of the authoritative Starbase Kubani deployment
plan. It builds on the accepted RC4 foundation and both completed RC4 migration
Jobs. Rendering, tests, or server-side dry-run do not authorize activation.

## Exact scope

The overlay starts only:

- one `starbase-core` pod containing the core and web containers; and
- one dedicated `starbase-preview-fixture` pod.

Both are required to schedule on `asio` or `strix`. The live GitHub and
Kubernetes connectors remain at zero replicas. Mutation and sandbox workers
remain absent. The fixture has no Kubernetes RBAC, provider credential,
provider egress, mutation authority, or sandbox authority; its only application
egress is the core API.

The fixture is an immutable, content-bound, visibly synthetic repository
snapshot. It submits four observations every 30 seconds through the same
short-lived projected identity, authenticated ingress, fencing, persistence,
reconciliation, and checkpoint path used by a live read-only GitHub connector.
The accepted expected and peak preview profile are both eight observation
submissions per minute. This is a bounded homelab preview, not a production
capacity claim.

## Immutable release and corrected identity contract

The preview retains Starbase `0.1.0-rc.4`, source
`e35ac44f5cea35b400d73bf94802b1a70e84585a`, and the images in
`../starbase/promotion-lock.json`. The exact core and web digests remain
unchanged. The fixture uses that same lock's GitHub connector image.

RC4 closes both configuration failures from the earlier RC3 preview attempts:

- `STARBASE_OIDC_REQUIRED_GROUPS` is the bounded JSON array
  `["starbase-operators"]`; and
- `STARBASE_WORKLOAD_IDENTITY_FILE` remains the sole projected-token-file
  contract at `/var/run/secrets/starbase.io/workload-issuer-identity/token`.

The obsolete `STARBASE_WORKLOAD_OIDC_TOKEN_FILE` is absent and rejected by RC4.
The environment overlay pins the authenticated discovery result exactly:

- issuer: `https://kubernetes.default.svc.cluster.local`; and
- JWKS: `https://100.92.107.71:6443/openid/v1/jwks`.

The pin was observed read-only on 2026-08-27. The JWKS contained one public
RS256 key and no private key material. NetworkPolicy permits only the cluster
service endpoint and that exact K3s node/API endpoint. Discovery drift,
redirect, TLS failure, a changed endpoint, or inability to reread the rotated
projected token keeps core unready; do not weaken the pin or egress policy.

## Resource and placement budget

Combined steady requests are 175m CPU and 224Mi memory:

- core: 100m CPU / 128Mi memory;
- web: 25m CPU / 32Mi memory; and
- fixture: 50m CPU / 64Mi memory.

Combined limits are 1.75 CPU and 896Mi memory. A core rolling surge brings
declared limits to exactly 3 CPU and 1.5Gi memory, within the existing
`starbase-system` quota and with the fixture bounded by the separate connectors
quota. Immediately before candidate validation, `asio` used 3% CPU / 31%
memory and `strix` used 4% CPU / 19% memory; all nodes were Ready and
pressure-free. Refresh these measurements before merge and stop if they are
stale or materially changed.

The same checkpoint found `asio` at 1,425m requested CPU / 830Mi requested
memory and `strix` at 1,555m / 1,144Mi. The `starbase-system` quota had zero
active CPU/memory requests or limits charged before activation, three retained
Job pods of ten allowed, and two Services of four allowed. The connectors quota
had zero active usage. Steady requests, the one-core rolling surge, fixture,
retained pods, and Services fit their independent namespace limits. This is
admission headroom, not soak evidence.

## Observation model

Prometheus and Grafana remain intentionally scaled to zero. During this
time-bounded, actively supervised homelab preview, evidence comes from:

- Flux revision and health, Kubernetes probes/events/logs/restarts, Endpoints,
  resource samples, PostgreSQL invariants, and synthetic freshness;
- the independently available Lifeboat diagnostic path; and
- the credential-free Osprey desktop observer in
  `../../../observers/starbase-preview/`.

The Osprey timer must remain disabled until the merged workload is Ready. After
the first manual successful run, it checks every five minutes and its sanitized
journal is retained at six-hour checkpoints. Al McKay accepted this
local-only, supervised exception for Phase 5. It provides no off-site dead-man
delivery and is not sufficient for production or unattended operation. Issue
[#90](https://github.com/X-McKay/kubani/issues/90) retains the production gate.

The 2026-08-27 read-only Osprey preflight found the host online under its
existing device identity, with the observer timer disabled and inactive and
the service inactive. The installed script and both systemd units are
byte-identical to this candidate:

- script: `sha256:ae288cc825a2e1fb23563c900e430019c4a12d07dd0e3eac70d6ef936cc68329`;
- service: `sha256:31bacd01e0d39b94618b27b5e9a6d12f3bea504c7fba4108b57e2983edc882b5`; and
- timer: `sha256:bc679bc32a7825132b83c2407076ad6b1678ec1b3f173b8d927a062f65b17c8f`.

`systemd-analyze verify` accepted both Starbase units; it emitted only an
unrelated existing Nomad-unit warning. `/opt/kubani` remains at its prior
reviewed observer revision and must be advanced to the exact merged Phase 5
revision before the timer starts. No observer service was run against the
intentionally inert backend.

## Pre-merge gates

Require all of the following on the exact PR head:

1. all local manifest, policy, secret, lint, evidence, and contract tests pass;
2. deterministic RC4 promotion verification remains exact;
3. Secret-free preview and Flux manifests pass server-side dry-run with no
   persistence; raw SOPS files remain excluded because Flux decrypts them;
4. both retained migration Jobs remain Complete and their checksummed database
   acceptance evidence remains exact;
5. all Flux Kustomizations align and report Ready, required services and
   storage are healthy, the current PostgreSQL backup is successful, and
   Authentik, DNS, ingress, and Certificate checks pass;
6. the discovery issuer/JWKS pair, K3s certificate boundary, and narrow egress
   addresses still match this revision;
7. every node is Ready and pressure-free, `asio`/`strix` have fresh headroom,
   and namespace quota covers steady plus rollout-surge resources;
8. Osprey is reachable, its reviewed checkout and units are valid, and its
   timer is disabled and inactive; and
9. owner review and merge of the exact immutable revision.

## Post-merge acceptance

Observe natural Flux reconciliation; do not force a reconcile without separate
authorization. Before starting the 24-hour clock:

1. require all Flux Kustomizations at the exact merge revision;
2. require exactly one Ready core pod and one Ready fixture pod on `asio` or
   `strix`, zero restarts, expected image IDs, and bounded resource use;
3. require both live connector Deployments at zero and no provider Secret,
   provider egress, mutation, or sandbox authority;
4. require public TLS/readiness, unauthenticated denial, correct Authentik
   redirect, operator login/logout, session behavior, and API/SSE reconnect;
5. verify exactly four synthetic observations become the expected durable
   Signals/Bounties and replay remains idempotent while freshness advances;
6. verify database ownership, ledgers, locks, connections, and row growth match
   the synthetic journey; and
7. enable the Osprey timer only after the application is Ready, force one
   successful credential-free run, and record the clock start.

Observe for at least 24 continuous hours. Any unexplained heartbeat/freshness
gap, duplicate durable Signal, restart, resource trend, dependency failure,
identity error, provider access, or SLO breach restarts the clock after recovery
or triggers rollback.

## Exercises and later phases

After a clean baseline, exercise one bounded failure at a time: login/logout and
stale session; API/SSE reconnect; core and fixture restart; reschedule between
`asio` and `strix`; Authentik outage/recovery; observer outage/recovery;
projection rebuild; migration restart safety; isolated backup restore; release
rollback; and Lifeboat diagnosis. Database, identity, node, and recovery
mutations retain their own explicit authorization and are not granted by this
PR.

Passing Phase 5 permits preparation of Phase 6. It does not enable live
providers. Phase 6 separately activates namespace-bounded Kubernetes
observation and one read-only, non-critical GitHub repository canary.

## Stop and rollback

Stop on revision/digest drift, identity or authorization failure, unexpected
egress, provider access, non-synthetic data, node pressure, dependency
degradation, ambiguous migration/data state, loss of observation, or failed
recovery. Preserve sanitized evidence first when safe.

Rollback is an exact Git revert to the accepted inert RC4 foundation and normal
Flux reconciliation. Verify core returns to zero, the fixture and its
ServiceAccount/ConfigMap/policies are pruned, both live connectors remain zero,
all Flux/dependency checks recover, and database state remains readable. Disable
the Osprey timer after retaining its sanitized journal. Do not delete or
down-migrate database state, imperatively scale workloads, or weaken identity,
network, resource, probe, or health gates.
