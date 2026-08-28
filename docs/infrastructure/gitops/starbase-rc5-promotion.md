# Starbase RC5 runtime and Authentik-session promotion

Date: 2026-08-27

Status: prepared for review; dependent on Starbase PR #31

## Objective and authority boundary

Promote the signed Starbase `0.1.0-rc.5` release into the existing Phase 5
synthetic preview so the reviewed Authentik session-reuse behavior can be
verified live. The change upgrades the digest-pinned core, web, and synthetic
fixture images through Kubani's content-bound bundle. The live GitHub and
Kubernetes connectors remain at zero replicas. Mutation, sandbox, and agent
execution workloads remain absent.

Merge is the GitOps activation decision for this exact release and target. It
does not authorize provider mutation, schema changes, migration replay,
production claims, a persistent test account, or later cohort expansion.

## Immutable inputs

| Input | Accepted value |
|---|---|
| Release | `0.1.0-rc.5` |
| Starbase source revision | `96c920472c29fcf7b536591fed4e363c34be36ff` |
| Starbase evidence revision | `dac7bbd6b9739233e9141b7839e72cb57b278817` |
| Evidence PR | [Starbase #31](https://github.com/X-McKay/Starbase/pull/31) |
| Release workflow | [33132580125](https://github.com/X-McKay/Starbase/actions/runs/33132580125) |
| Source CI | [33130244579](https://github.com/X-McKay/Starbase/actions/runs/33130244579) |
| Release manifest checksum | `sha256:1c70f2c3412cee88c4790348fa6a5322881286c988b97132f6a5d0a617237265` |
| Target platform | `linux/amd64` |

The release workflow passed all six image publication gates and aggregate
assembly. Independent verification accepted the checksums, twelve Trivy
reports, six Cosign signatures, tag equality, OCI index structure, SPDX
attestations, and SLSA provenance. Kubani stayed healthy and unchanged before
and after publication.

## Exact image set

| Image | Immutable digest |
|---|---|
| core | `sha256:ca90ed140c23bd630f5ce5e6d1b6c90d29c8096da3e5481abc8ca5ef234d7dad` |
| web | `sha256:cc366db29258b16ed593ac7ab7a2d35987905a9346e505dbc0b1afc015ad282d` |
| github-connector | `sha256:8b51d4dedd2bedbf9ffc8b87395a0484784f3674b807d9411dbcc7a1f0519883` |
| kubernetes-connector | `sha256:e7e7fe83ec2299cfe578296e74f5f62dc104d19c493960d1674042eb0193255d` |
| core-migrator | `sha256:983ed5ea6c6cf5820c42f171429eea7716633d5b0dee5347f5a7182c07d88462` |
| gateway-migrator | `sha256:b4ab2e9e07726f855b9eea91c112291350cdef2e3f316253b03167860bab4b8a` |

All desired state uses these digests rather than tags.

## No-migration promotion

The release configuration digest and all three ordered SQL migration digests
are byte-identical to RC4. There is no schema, backfill, repair, or data
transformation in this promotion. The RC4 core and gateway migrations have
already completed and have checksummed retained evidence.

The bundle generator correctly creates new execution identities because the
migrator image digests changed:

- `starbase-core-migrate-0da307f3148a`; and
- `starbase-gateway-migrate-f2fa2f551602`.

Both successor Jobs are explicitly `suspend: true`, carry a blocked
unchanged-schema annotation, and are absent from Flux health checks. The
completed RC4 Job objects may be pruned after their retained evidence is
rechecked. Rebuilding a migrator is not authority to rerun production SQL.
Any future unsuspension requires a separate reviewed migration decision,
preflight, backup/recovery evidence, and exact health gate.

## Runtime and placement

The live topology remains one core pod with core and web containers plus one
synthetic preview fixture. Both remain restricted to `asio` or `strix`. The
steady request budget remains 175m CPU and 224Mi memory; the core rolling surge
fits the existing `starbase-system` quota. No new replica, Service, persistent
volume, RBAC grant, Secret, provider credential, or egress destination is
introduced.

The release preflight at `2026-08-28T01:20:16Z` observed all four nodes Ready,
zero unhealthy workloads, all Flux Kustomizations Ready at
`main@sha1:60a0c7267a3e28141fc469cecf18686f2e1a7a63`, `asio` at 3% CPU / 33%
memory, and `strix` at 4% CPU / 19% memory. These measurements must be refreshed
immediately before merge and rollout.

## Pre-merge verification

Require all of the following on the exact PR head:

1. Starbase PR #31 is merged or its exact evidence commit is otherwise accepted
   without content drift.
2. Deterministic generation and verification pass from clean distinct evidence
   and source checkouts.
3. Kubani focused promotion, Phase 4A, and Phase 5 tests pass.
4. The complete local validation suite and committed-bundle consistency checks
   pass.
5. The rendered Phase 5 overlay has exactly one core and one fixture replica;
   both live providers remain zero.
6. Both RC5 migration Jobs render suspended and neither appears in Flux health
   checks.
7. Rendered RBAC, ServiceAccounts, NetworkPolicies, pod security, resource
   limits, image digests, Ingress, TLS, and secret references remain bounded.
8. A Flux-equivalent server-side dry-run admits the non-secret resources
   without persistence; encrypted Secret source files remain validated through
   the dedicated SOPS gate.
9. Fresh Kubani, Flux, Authentik, PostgreSQL, certificate, storage, Osprey,
   Lifeboat, and `asio`/`strix` capacity checks pass.
10. Owner review accepts the exact immutable revision and rollback plan.

Do not merge if evidence, source, target, toolchain, render, or live health has
drifted.

## Preparation evidence

At `2026-08-27T18:47:41-07:00`, immediately before opening the promotion PR:

- deterministic generation and verification passed from distinct clean Starbase
  evidence and product checkouts;
- all 95 promotion, Phase 4A, Phase 5, heartbeat, backup/recovery, Authentik,
  and live-probe contract tests passed;
- `validate-local` passed inventory, SOPS and plaintext-Secret checks, all
  Kustomize builds, the contract suite, and hook installation policy;
- the complete full-tree pre-commit suite passed, including Gitleaks,
  detect-secrets, private-key detection, SOPS checks, YAML, and Ansible lint;
- the cluster validator passed 44 of 44 checks with zero warnings, and every
  required independent live-service probe passed; only the documented
  authenticated-registry and intentionally inactive embeddings probes skipped;
- every node was Ready and pressure-free, with `asio` at 3% CPU / 32% memory
  and `strix` at 5% CPU / 19% memory; no non-completed pod was unhealthy;
- all Flux objects were Ready and aligned at
  `main@sha1:60a0c7267a3e28141fc469cecf18686f2e1a7a63`;
- Authentik server and worker, PostgreSQL, the RC4 Starbase core, and the
  synthetic fixture were Ready with zero restarts on `asio` or `strix`; and
- a Flux-equivalent server-side dry-run admitted all 57 non-Secret preview
  resources plus the exact Flux Kustomization without persistence. The seven
  encrypted Secret source documents passed their dedicated repository gates.

The post-dry-run check confirmed the live RC4 images and three completed RC4
Jobs remained unchanged; neither suspended RC5 successor Job existed or ran.
These results are pre-PR evidence, not permission to skip the fresh exact-head
and immediate pre-merge checks above.

### Review-remediation evidence

At `2026-08-28T05:17:53Z`, after addressing the exact-head review findings:

- deterministic regeneration and verification passed against Starbase evidence
  revision `97779a13b0395e4d66cec32a3fa8b52bb5588f9c` and unchanged product
  revision `96c920472c29fcf7b536591fed4e363c34be36ff`;
- all 101 promotion, Phase 4A, Phase 5, heartbeat, rollback,
  backup/recovery, Authentik, and live-probe contract tests passed;
- `validate-local` and the complete full-tree pre-commit suite passed;
- the cluster validator passed 44 of 44 checks with zero warnings, all five
  Flux Kustomizations remained Ready at
  `main@sha1:60a0c7267a3e28141fc469cecf18686f2e1a7a63`, and required independent
  service probes passed;
- every node was Ready and pressure-free; `asio` used 3% CPU / 32% memory and
  `strix` used 4% CPU / 19% memory; and
- Flux-equivalent server-side dry-runs admitted all 57 non-Secret preview
  resources, all 57 non-Secret rollback resources, and the exact Flux
  Kustomization without persistence.

The post-dry-run check confirmed the live Flux path and revision, exact RC4
images, three completed RC4 Jobs, zero unhealthy workloads, and node-pressure
state remained unchanged. Neither suspended RC5 successor Job existed or ran.

## Rollout and live verification

After merge, allow natural Flux reconciliation; do not force it merely to make
the rollout faster. Observe continuously from an external path.

1. Require every Flux Kustomization to reach the exact merged revision.
2. Require the rolling core replacement to keep the Service available and the
   new pod to land on `asio` or `strix` with the exact RC5 image IDs.
3. Require the fixture to replace cleanly with its exact RC5 image, remain
   synthetic, and resume freshness without duplicate durable Signals.
4. Confirm both RC5 successor migration Jobs are suspended and neither ran.
5. Confirm the RC4 migration evidence remains checksummed and database schema
   versions and invariants are unchanged.
6. Confirm unauthenticated readiness succeeds while snapshot, SSE, and command
   surfaces remain fail closed.
7. Perform one Authentik login from a fresh Starbase session. An existing
   Authentik session must reach the callback without a second Authentik prompt.
8. Verify authenticated session state, snapshot, SSE connection/reconnect, and
   logout invalidation. Mutation controls remain unavailable.
9. After RC5 is accepted as Ready, update Osprey's `/opt/kubani` checkout to
   the exact merged Kubani revision before its first forced run or timer start.
   The RC5 observer intentionally rejects RC4's outgoing `prompt=login` and
   `max_age=0` redirect contract, so do not update or run it early.
10. If automation still requires a credential, create only an ephemeral
   Authentik user in `starbase-operators`, use a random temporary password held
   outside logs, and delete or disable the identity immediately after the test.
   Do not grant Authentik administration or Kubernetes RBAC.
11. Repeat cluster, Flux, Authentik, PostgreSQL, error, restart, capacity, and
    external-observer checks before starting or resuming the Phase 5 clock.

## Stop conditions

Stop and preserve evidence on any digest/revision mismatch, unexpected
migration start, authentication loop, callback error, group-boundary failure,
session that survives logout, provider access, non-synthetic observation,
duplicate durable state, restart loop, readiness failure, Flux drift, node
pressure, stale external observation, database anomaly, or unexplained error
increase.

An automation-client refusal to display an OAuth callback is not by itself an
application failure. Distinguish client policy from server response using
sanitized server evidence and, when needed, a normal user-controlled browser.

## Rollback and recovery

Rollback is a separately reviewed GitOps commit changing only the Starbase Flux
`spec.path` to
`./infrastructure/gitops/apps/starbase-phase5-rc4-runtime-rollback`. The
prepared, inactive overlay inherits RC5 and replaces only the active core,
web, and fixture images with the exact accepted RC4 digests plus rollback
annotations. It preserves the RC5 content-named migration Jobs byte-for-byte,
suspended and blocked. The older pruned RC4 Job identities remain absent.

Do not exact-revert this promotion: that can recreate runnable, previously
pruned migration Jobs. Do not use `kubectl rollout undo`, run SQL,
imperatively scale, or modify managed fields as the normal path. Before the
rollback path change is reviewed, render and policy-test the overlay, perform
a Secret-free server-side dry-run, and confirm the live Flux path is still the
RC5 preview.

Before rollback, preserve new pod events, redacted logs, image IDs, Flux state,
Auth/HTTP results, and database invariants. RC5 applies no schema change, so the
RC4 application remains schema-compatible. Keep the successor migration Jobs
suspended during rollback. Verify RC4 core/web/fixture image IDs, the absence
of old RC4 migration Job names, public
readiness, fail-closed authentication, synthetic freshness, zero provider
replicas, zero unexpected migration executions, database integrity, and
external observation after reconciliation.

If the failure indicates credential exposure or authorization bypass, disable
the temporary test identity first, retain redacted evidence, and enter the
security incident path before ordinary rollback.

## Deferred production gates

This supervised homelab preview retains the accepted ADR 0009 trusted-renderer
deferral and local Osprey observer exception. Tailscale federation, independent
off-site heartbeat, production SLO/on-call policy, and a persistent automated
browser-test identity remain deferred. This promotion does not weaken their
documented triggers or deadlines.
