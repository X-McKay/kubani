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
workload-scoped SOPS-encrypted Secrets, one authorized database-bootstrap Job,
suspended migration Jobs, and zero-replica Deployments. The five Secrets
separate bootstrap, core runtime, gateway runtime, core migration, and gateway
migration authority. The bootstrap is the only runnable Starbase resource in
this activation stage and has no provider authority.

The internal PostgreSQL HelmRelease does not enable TLS. Database URLs therefore
state `sslmode=disable` explicitly and rely on the existing default-deny and
exact PostgreSQL NetworkPolicies for the current homelab boundary. Enabling
PostgreSQL TLS requires separately reviewed certificate and URL rotation.

The foundation deliberately excludes:

- every plaintext credential and shared all-purpose Starbase Secret;
- the Authentik blueprint;
- Certificate, DNS, and Ingress resources;
- an unsuspended product migration; and
- any non-zero Starbase Deployment.

The broader sibling `starbase-phase4a` overlay remains review-only and renders
the complete dependency contract. Do not add it to the active apps aggregate.
If SOPS decryption or Secret application fails, this dedicated Kustomization
fails closed while unrelated applications continue reconciling. Before the
database bootstrap completes, rollback is a reviewed revert to the suspended
Job plus the bounded Starbase-only database/role cleanup when partial state may
exist. After bootstrap, never remove or replace the credentials without a
rotation plan bound to the database roles.

Subsequent activation must follow the staged gates in
[`starbase-phase4a-preflight.md`](../../../../docs/infrastructure/gitops/starbase-phase4a-preflight.md).
