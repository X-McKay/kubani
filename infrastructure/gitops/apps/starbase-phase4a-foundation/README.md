# Starbase Phase 4A fail-closed foundation

This is the first active Starbase layer in Kubani desired state. Its dedicated
`starbase-foundation` Flux Kustomization depends on `databases`, whose health
checks include the exact content-named isolated restore verifier. A matching
activation-wave label and dependency readiness expression also require the new
databases generation to have reconciled. A failed or incomplete restore
therefore prevents this layer from being applied.

The foundation creates namespaces, service accounts, immutable release
configuration, Services, RBAC, quotas, LimitRanges, NetworkPolicies, suspended
bootstrap and migration Jobs, and zero-replica Deployments. It deliberately
excludes:

- every Secret and plaintext credential;
- the Authentik blueprint;
- Certificate, DNS, and Ingress resources;
- an unsuspended database bootstrap or migration; and
- any non-zero Starbase Deployment.

The broader sibling `starbase-phase4a` overlay remains review-only and renders
the complete dependency contract. Do not add it to the active apps aggregate.
Subsequent activation must follow the staged gates in
[`starbase-phase4a-preflight.md`](../../../../docs/infrastructure/gitops/starbase-phase4a-preflight.md).
