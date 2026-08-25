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
retained completed database-bootstrap Job, one completed core-migration Job,
one authorized gateway-migration Job, and zero-replica Deployments. Five Secrets
separate bootstrap, core runtime, gateway runtime, core migration, and gateway
migration authority; two additional Secrets grant package-read-only GHCR pulls
to the exact Starbase ServiceAccounts. The Flux health contract requires both
the isolated restore and core migration to succeed before this layer reports
Ready. The gateway candidate extends that exact health gate to its own retained
Job. No Job has provider authority.

The internal PostgreSQL HelmRelease does not enable TLS. Database URLs therefore
state `sslmode=disable` explicitly and rely on the existing default-deny and
exact PostgreSQL NetworkPolicies for the current homelab boundary. Enabling
PostgreSQL TLS requires separately reviewed certificate and URL rotation.

The foundation deliberately excludes:

- every plaintext credential and shared all-purpose Starbase Secret;
- the Authentik blueprint;
- Certificate, DNS, and Ingress resources;
- any product migration beyond the authorized gateway migration; and
- any non-zero Starbase Deployment.

The broader sibling `starbase-phase4a` overlay remains review-only and renders
the complete dependency contract. Do not add it to the active apps aggregate.
If SOPS decryption, Secret application, or the core migration fails, this
dedicated Kustomization fails closed while unrelated applications continue
reconciling. Preserve failed Job evidence and keep every runtime and the gateway
migration inactive. Prefer forward repair for a compatible partial schema; the
reviewed Starbase-only database/role cleanup remains available while no
application data exists. Never remove or replace the credentials without a
rotation plan bound to the database roles.

The first core-migration attempt failed before container start because GHCR
rejected an anonymous manifest request. Its bounded authenticated recovery and
all migration acceptance invariants passed. The temporary resource-scoped Flux
force annotation has been removed from desired state while the completed Job
and credential bindings remain retained. Token expiry, rotation, verification,
revocation, and recovery evidence are defined in
[`starbase-ghcr-pull-recovery.md`](../../../../docs/infrastructure/gitops/starbase-ghcr-pull-recovery.md).

Subsequent activation must follow the staged gates in
[`starbase-phase4a-preflight.md`](../../../../docs/infrastructure/gitops/starbase-phase4a-preflight.md).
