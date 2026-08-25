# Starbase Phase 4A dependency preflight

Date: 2026-08-24

Status: Stage 1 backup passed; isolated restore and fail-closed foundation
pending reviewed GitOps merge

Scope: Kubani-owned dependencies and bindings for the inactive Starbase
`0.1.0-rc.2` Phase 3 bundle

## Decision and authority boundary

Al McKay authorized Phase 4A cluster resources and deployment provided node
health and capacity are actively monitored and considered. The initial change
created the reviewable GitOps contract without adding Starbase to Flux. The
current Stage 2 tranche authorizes only the exact isolated restore verifier and
an inert foundation behind that verifier's Flux health gate. It still does not
provision secrets, modify Authentik's active blueprint mount, execute database
bootstrap or migrations, create DNS, issue a certificate, expose ingress, or
start a Starbase Deployment.

Those mutations remain later, exact-revision activation steps. Repository
changes may be grouped when automatic fail-closed dependencies preserve the
operational sequence; passing and observing each live gate is still mandatory.
Current execution evidence is retained in
[`starbase-phase4a-activation-evidence.md`](starbase-phase4a-activation-evidence.md).

## Fresh cluster baseline

Read-only observations were taken around `2026-08-24T21:58Z` through
`2026-08-24T22:01Z` using the existing protected administrative recovery
identity. No credential value was read or retained.

- Kubernetes API and etcd readiness passed.
- `asio`, `strix`, `rig0`, and `sparky` were Ready and schedulable. `sparky`
  retains its GPU taint and is not a preferred Starbase target.
- No active pod was observed outside Running/Succeeded state.
- All Flux sources and Kustomizations were Ready at
  `main@sha1:fb5a4595aef108f1af7a547e2e224d1629c98ef2`.
- Starbase namespaces and workloads were absent.
- Grafana and Prometheus remained intentionally scaled to zero.
- Authentik, its server and worker, its certificate, and PostgreSQL were Ready.
- PostgreSQL was one replica on `strix`, backed by a 20 GiB Longhorn PVC, with
  `max_connections=200` and a 250m CPU / 256 MiB memory request.
- The latest daily PostgreSQL backup Job succeeded, but its 1 GiB `local-path`
  target shares the database node failure domain and no isolated restore
  evidence was available. This is a hard activation blocker, not a warning.

Point-in-time node evidence:

| Node | Allocatable | Observed use | Allocated requests | Assessment |
|---|---|---|---|---|
| `asio` | 8 CPU, 15,777,944 KiB | 4% CPU, 29% memory | 1,425m CPU (17%), 830 MiB (5%) | preferred; ample first-release headroom |
| `strix` | 7 CPU, 13,703,748 KiB | 4% CPU, 21% memory | 1,555m CPU (22%), 1,144 MiB (8%) | preferred; database locality but avoid unnecessary concentration |

The inactive first-release workload with GitHub disabled requests approximately
175m CPU and 224 MiB memory in steady state. Each migration requests 25m CPU
and 32 MiB memory and will run sequentially. These requests fit either preferred
node with substantial headroom. This is admission evidence only; it is not a
representative load test or permission to ignore a fresh activation check.

## Contract implemented

### PostgreSQL ownership

Two databases prevent accidental cross-service ownership:

| Database | Migration owner | Runtime role | Owned schema |
|---|---|---|---|
| `starbase_core` | `starbase_core_migrator` | `starbase_core_runtime` | `starbase_core` |
| `starbase_gateway` | `starbase_gateway_migrator` | `starbase_gateway_runtime` | `experience_gateway` |

All four roles are login roles with `NOSUPERUSER`, `NOCREATEDB`,
`NOCREATEROLE`, `NOINHERIT`, and `NOREPLICATION`. Runtime roles receive only
connect, schema usage, table DML, and sequence access. Public database and
schema-create privileges are revoked. Migration roles own their database and
schema. The bootstrap is idempotent, validates generated credential shape,
does not intentionally emit credentials, uses the existing digest-pinned
PostgreSQL image, has bounded retry/deadline/retention, and is suspended.

Role credentials are passed from the shell environment into `psql` with
`\getenv`, rather than as command-line arguments, and the role-creation session
sets `log_statement` to `none` before password-bearing DDL is generated. This
removes the ordinary process-argument and PostgreSQL statement-log paths. It
does not protect a credential from a database superuser, node root, process
instrumentation, or an extension that captures statement text independently of
`log_statement`. Immediately before unsuspending the bootstrap, the operator
must inspect PostgreSQL logging and preload/extension configuration without
printing credentials; unexpected statement capture is a stop condition.

### Authentik and operator authorization

The blueprint contract creates:

- a non-superuser `starbase-operators` group with no automatic member;
- a public `starbase-kubani` OAuth client;
- Authorization Code only, with the exact callback
  `https://starbase.almckay.io/api/v1/auth/callback`;
- strict redirect matching, RS256 signing, and no client secret;
- an Authentik application access policy bound directly to
  `starbase-operators`; and
- a bounded groups claim that Starbase independently checks for
  `starbase-operators`.

Both authorization layers deny a non-member. The public client relies on
Starbase to generate, bind, and verify PKCE for every authorization flow; this
blueprint does not claim provider-side PKCE enforcement that has not been
verified for the installed Authentik version.

The active Authentik HelmRelease currently mounts only the platform-owned
`authentik-blueprints` ConfigMap. The new ConfigMap is intentionally inert.
Activation must merge this data into the Authentik-owned blueprint resource (or
add the additional ConfigMap to that same owner's Helm values) rather than let
two Flux resources own one HelmRelease.

### Secret and network boundaries

No Secret object exists in the overlay. Five named Secret contracts separate
bootstrap, core runtime, gateway runtime, core migration, and gateway migration
authority. The runtime never receives a migration credential; the database
bootstrap never runs in a Starbase namespace.

The existing default-deny policies remain. Additions allow only:

- selected Starbase core/migration pods to PostgreSQL TCP 5432;
- the suspended bootstrap pod to same-namespace PostgreSQL TCP 5432;
- core to Traefik TCP 8443 for the external Authentik issuer;
- core to the Kubernetes discovery service `10.43.0.1/32:443` and its currently
  advertised JWKS endpoint `100.92.107.71/32:6443`; and
- only the Kubernetes connector to those same exact Kubernetes API service and
  endpoint paths; and
- Traefik to the web sidecar on TCP 8080.

The Kubernetes service and issuer endpoint were discovered from the live
`default/kubernetes` Service, EndpointSlice, and service-account issuer metadata
and are time-bound evidence. They must be rediscovered immediately before
activation and tested from a policy-equivalent disposable pod. If either has
changed, update and review the exact `/32`; do not substitute catch-all egress.
The public Authentik issuer route must likewise be proven from a policy-equivalent
pod because ingress hairpin behavior can differ by CNI implementation.

The Ingress exposes only `starbase-core` port 80 (the web same-origin proxy).
The connector-only `starbase-core-api` Service is never an Ingress backend.
The GitHub connector remains at zero replicas and receives neither a credential
nor GitHub egress. Core and the Kubernetes connector also render at zero
replicas; annotations are retained for operator visibility but are not relied
upon as a scheduling control.

## Repository and API validation evidence

The implementation began with a failing contract test because the Phase 4A
overlay did not exist. After implementation:

- all 20 existing promotion tests and 8 Phase 4A tests passed;
- the full repository `validate-local` path passed: inventory, encrypted-secret
  and plaintext-secret scans, all five Kustomize builds, tests, and CI hook
  policy;
- the changed-file pre-commit suite passed, including YAML, Gitleaks,
  detect-secrets, private-key, merge-conflict, and plaintext-Secret checks;
- Actionlint and `git diff --check` passed;
- Kubeconform strict Kubernetes 1.34 validation found 48 resources, with 47
  valid built-in resources and the cert-manager `Certificate` correctly skipped
  because its CRD schema was not supplied;
- strict kubectl client dry-run accepted all 48 resources against live API
  discovery; and
- server-side dry-run accepted cluster-scoped and existing-namespace objects,
  then correctly could not validate objects in the three absent Starbase
  namespaces because dry-run namespace creation is not visible to subsequent
  requests. No namespace or other object was persisted.

Trivy's embedded checks reported one HIGH heuristic on the bootstrap ConfigMap
because the stored shell code contains PostgreSQL password-handling syntax. The
ConfigMap contains variable names and SQL, not a credential value; independent
Gitleaks, detect-secrets, plaintext Kubernetes Secret, and exact object tests
passed. This is retained as a documented false positive. The online Trivy
checks bundle was unavailable in the sandbox, so embedded checks were used.

A final read-only checkpoint at `2026-08-24T22:14:53Z` reproduced the healthy
API, node, workload, Flux, Authentik, PostgreSQL, PVC, and current backup state.
`asio` remained at 1,425m requested CPU / 830 MiB requested memory and `strix`
at 1,555m / 1,144 MiB; both measured 4% CPU with 29% and 21% memory use. Live
Traefik labels and port 8443 matched the proposed policy. The Kubernetes Service
was `10.43.0.1:443` with EndpointSlice `100.92.107.71:6443`. No Starbase
namespace or workload existed after validation.

## Activation gates and sign-off

Every gate is fail-closed. Record the command, timestamp, exact Git revision,
and result in the activation evidence.

1. **Revision and CI:** Phase 4A PR merged; CI green; exact immutable Starbase
   release and rendered lock reverified.
2. **Recovery:** an off-node PostgreSQL backup is current, checksum-verified,
   and restored into an isolated target; core and gateway databases/roles can
   be excluded or removed cleanly after a failed bootstrap. The off-node copy
   passed; isolated restore remains pending. The bounded implementation and
   exercise procedure are
   defined in
   [`postgresql-backup-recovery.md`](../operations/postgresql-backup-recovery.md).
3. **Health:** API/etcd, nodes, active pods, Flux, Authentik, PostgreSQL,
   certificate, storage, and backup checks pass immediately before mutation.
4. **Capacity:** current `kubectl top nodes`, allocatable resources, requests,
   limits, taints, disk pressure, and PVC health still leave the accepted
   headroom on `asio` or `strix`. Stop if either preferred node is NotReady,
   under pressure, or the workload would rely on `sparky`.
5. **Secrets:** encrypted files pass SOPS and plaintext-secret scans; secret
   keys and consumers exactly match the contract; no value appears in Git,
   logs, shell history, PR text, or retained evidence.
6. **Identity:** blueprint dry-run/schema validation passes; the operator is
   deliberately added to `starbase-operators`; PKCE, issuer, audience, callback,
   groups, logout, expiry, Authentik application-policy denial, and Starbase
   denied non-member behavior are exercised independently.
7. **Network:** policy-equivalent probes prove PostgreSQL, Authentik discovery,
   and Kubernetes API/JWKS reachability from both core and the Kubernetes
   connector, while arbitrary internet, GitHub, Secret read, internal core
   ingress, and cross-namespace database paths remain denied.
8. **Migration:** bootstrap and both migrations are reviewed, run one at a
   time, complete once, retain logs without secrets, and leave expected schema
   ownership. No product Deployment starts before both migrations succeed.
9. **External observation:** an observer outside Starbase can detect rollout
   failure; Lifeboat diagnostics remain available.
10. **Human go/no-go:** Al McKay signs the exact activation revision and current
    evidence after all prior gates pass. Development-mode sign-off needs no
    additional ceremonial approval text.

## Staged activation sequence

Each operational step has a fresh health/capacity check before and after it.
Related repository changes may share a PR only when explicit dependency and
health gates prevent a later operation from starting early.

1. Close the recovery gate. The fail-closed Starbase foundation may reconcile
   only after the exact restore Job passes; verify that it starts no pod.
2. Generate and review SOPS-encrypted credentials; do not activate workloads.
3. Recheck cluster identity, Flux health, nodes, requests, pressure, PostgreSQL,
   Authentik, and backup freshness.
4. Apply only quotas, LimitRanges, ServiceAccounts, ConfigMaps, Secrets, and
   NetworkPolicies through their single owning Flux path. Verify no pod starts.
5. Merge/mount the Authentik blueprint through the existing Authentik owner;
   verify blueprint reconciliation, group, provider, discovery, and JWKS.
6. Unsuspend the content-named database bootstrap Job. Wait for success and
   verify exact databases, owners, grants, and absence of leaked credentials.
   Before unsuspending it, verify PostgreSQL statement logging and loaded
   extensions do not add an unreviewed password-bearing statement capture path.
7. Unsuspend the core migration Job; verify its schema and fencing. Then, and
   only then, unsuspend the gateway migration Job and verify it independently.
8. Apply Certificate and Ingress while the Deployment remains blocked; verify
   TLS and expected unavailable/readiness behavior without exposing core API.
9. Add and review an activation patch that changes only the core Deployment to
   one replica, preferring the healthier of `asio` and `strix`; keep both
   connectors at zero. Verify health, login, denial at both identity layers,
   session behavior, database state, node impact, events, restarts, and logs.
10. Add and review a second activation patch that changes only the read-only
    Kubernetes connector to one replica. Verify projected identity, bounded
    RBAC and API egress, Signal ingestion, freshness, UI truthfulness, and
    resource impact. GitHub and all mutation remain disabled.

## Stop conditions

Stop and do not proceed when any of these occurs:

- API/etcd or any preferred node becomes unhealthy or pressured;
- Flux ceases to reconcile cleanly or unrelated workloads degrade;
- PostgreSQL, Authentik, certificates, storage, or backup freshness degrades;
- scheduling lands unexpectedly on `rig0` or `sparky` without a reviewed reason;
- a Job retries unexpectedly, exceeds its deadline, or has ambiguous ownership;
- any credential appears outside its intended Secret/consumer;
- a required exact network path fails or an expected-denied path succeeds;
- migration output or database ownership differs from the reviewed contract;
- external observation is unavailable; or
- rollback target, authority, or blast radius becomes uncertain.

## Rollback and recovery

Before database bootstrap, rollback is a Git revert/removal of the inactive
resources and deletion of newly delivered Secrets. There is no application data.

After bootstrap but before migration, suspend the Job and application, verify no
connections, then remove only the four Starbase roles/databases using a reviewed
cleanup script. Never use a broad PostgreSQL restore for this case.

After migration but before workload traffic, keep the Deployment at zero and
either retain the empty compatible schemas for retry or remove only Starbase
databases/roles. Migration rollback is not down-migration.

After the first workload starts, revert to the prior Git revision, scale
Starbase to zero, preserve database evidence, revoke sessions and workload
access as needed, and diagnose before retry. Do not reverse schemas or restore
the shared PostgreSQL instance unless corruption is proven and the separately
approved recovery plan requires it.

Authentik rollback removes the Starbase application/provider/scope mapping only
after Starbase is at zero; the dedicated group is removed only after verifying
it has no other use. Certificate/Ingress rollback removes the Starbase route and
certificate without altering Authentik's own route.

Every rollback ends with the same API, node, workload, Flux, Authentik,
PostgreSQL, storage, backup, and capacity checks used at entry.
