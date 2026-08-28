# Starbase RC5 runtime rollback overlay

Status: prepared and inactive

This overlay is the bounded rollback target for the Phase 5 RC5 synthetic
preview. It inherits the complete reviewed RC5 preview composition and changes
only the active core, web, and synthetic fixture images to the exact accepted
RC4 digests, plus explicit rollback annotations.

It deliberately retains the RC5 content-named migration Jobs unchanged,
suspended, and blocked. The older pruned RC4 migration Job identities are not
reintroduced, so selecting this overlay cannot replay database migrations.

The active Flux Kustomization does not reference this directory. Activation
requires a separate reviewed GitOps change that changes only the Starbase Flux
`spec.path` to this overlay. An exact revert of the RC5 promotion is forbidden
because it could recreate runnable, previously pruned Job identities. Do not
run SQL, use `kubectl rollout undo`, scale workloads imperatively, or modify
managed fields as part of this rollback.

Before proposing activation, preserve sanitized evidence and render, policy
test, and server-side dry-run this exact overlay. After reconciliation, verify
the exact RC4 image IDs, unchanged suspended RC5 Jobs, public readiness,
fail-closed authentication, synthetic freshness, database integrity, node
health and placement, Flux health, and external observation.
