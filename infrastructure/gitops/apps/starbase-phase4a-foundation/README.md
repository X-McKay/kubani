# Starbase Phase 4A fail-closed foundation

This is the first active Starbase layer in Kubani desired state. Its dedicated
`starbase-foundation` Flux Kustomization depends on `databases`. A matching
activation-wave label and dependency readiness expression require the new
databases generation—which unsuspends the exact content-named isolated restore
verifier—to have reconciled. The foundation then applies its inert resources
and performs the exact restore-Job health check with a 25-minute timeout. A
failed or incomplete restore keeps this Kustomization NotReady and prevents
every later Starbase activation stage without blocking reconciliation of
unrelated applications.

The foundation creates namespaces, service accounts, immutable release
configuration, Services, RBAC, quotas, LimitRanges, NetworkPolicies,
workload-scoped SOPS-encrypted Secrets, namespace-local GHCR pull Secrets, one
retained completed database-bootstrap Job, two suspended RC4 migration Jobs,
one authorized content-bound network/RBAC probe, a browser-only Ingress, its
Certificate, and zero-replica Deployments.
Five Secrets separate bootstrap, core runtime, gateway runtime, core migration,
and gateway migration authority; two additional Secrets grant package-read-only
GHCR pulls to the exact Starbase ServiceAccounts. The Flux health contract now
requires the isolated restore, content-bound network/RBAC probe, and exact
Starbase Certificate to succeed before this layer reports Ready. The suspended
successor migrations are deliberately excluded until a separate activation
adds each exact execution identity to the health gate. No Job has provider
authority.

The internal PostgreSQL HelmRelease does not enable TLS. Database URLs therefore
state `sslmode=disable` explicitly and rely on the existing default-deny and
exact PostgreSQL NetworkPolicies for the current homelab boundary. Enabling
PostgreSQL TLS requires separately reviewed certificate and URL rotation.

The foundation deliberately excludes:

- every plaintext credential and shared all-purpose Starbase Secret;
- the Authentik blueprint;
- an imperatively managed DNS record (ExternalDNS owns it from the Ingress);
- any authorized RC4 product migration; and
- any non-zero Starbase Deployment.

The broader sibling `starbase-phase4a` overlay remains review-only and renders
the complete dependency contract. Do not add it to the active apps aggregate.
If SOPS decryption or Secret application fails, this
dedicated Kustomization fails closed while unrelated applications continue
reconciling. Keep every runtime and both successor migrations inactive. During
later migration activation, preserve failed Job evidence and prefer forward
repair for a compatible partial schema; the
reviewed Starbase-only database/role cleanup remains available while no
application data exists. Never remove or replace the credentials without a
rotation plan bound to the database roles.

The original RC2 core-migration attempt failed before container start because GHCR
rejected an anonymous manifest request. Its bounded authenticated recovery and
all migration acceptance invariants passed. The temporary resource-scoped Flux
force annotation has been removed from desired state. RC4 uses new execution
identities bound to both the migration set and migrator image; both Jobs remain
suspended. Token expiry, rotation, verification, revocation, and recovery
evidence are defined in
[`starbase-ghcr-pull-recovery.md`](../../../../docs/infrastructure/gitops/starbase-ghcr-pull-recovery.md).

Prometheus and Grafana remain intentionally scaled to zero. The edge stage uses
Flux, Kubernetes, retained Job/Certificate evidence, structured logs, and the
external operator as a bounded zero-replica observation path. Core activation
remains blocked until the Phase 5 candidate supplies a retained external
heartbeat and preview measurement path; missing telemetry is not called
healthy.

Subsequent activation must follow the staged gates in
[`starbase-phase4a-preflight.md`](../../../../docs/infrastructure/gitops/starbase-phase4a-preflight.md).
