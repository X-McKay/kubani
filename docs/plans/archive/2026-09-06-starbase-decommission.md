# Starbase Decommission

Status: executed 2026-09-06

Starbase (core, gateway, connectors, Dojo) was removed from Kubani. This note
records what was removed and the imperative steps GitOps could not perform.

## Removed from Git

- Flux Kustomizations `starbase-foundation` and `starbase-dojo` (prune enabled,
  so Flux garbage-collects every resource they owned, including the
  `starbase-system`, `starbase-connectors`, and `starbase-execution`
  namespaces and the Starbase network policies in `database` and `temporal`)
- all `infrastructure/gitops/apps/starbase*` overlays
- the `starbase.io/activation-wave` label on the `databases` Kustomization
- the Starbase-only `allow-worker-ingress` policy on the Temporal frontend
- `infrastructure/observers/starbase-preview/` and the promotion, heartbeat,
  and OIDC verifier scripts with their tests
- Starbase runbooks and evidence bundles under `docs/infrastructure/gitops/`

## Authentik

Removing a blueprint file does not remove the objects it created, so the
`starbase.yaml` blueprint key now carries `state: absent` entries for the
policy binding, application, provider, scope mapping, and `starbase-operators`
group. Once `https://auth.almckay.io/application/o/starbase/.well-known/openid-configuration`
returns 404, a follow-up change removes the key from the ConfigMap.

## PostgreSQL

Flux pruning removes the bootstrap Jobs but not the databases they created.
Dropped by hand from `postgresql-0` in the `database` namespace:

- databases `starbase_core`, `starbase_gateway`, `starbase_dojo`
- roles `starbase_core_runtime`, `starbase_core_migrator`,
  `starbase_gateway_runtime`, `starbase_gateway_migrator`,
  `starbase_dojo_runtime`, `starbase_dojo_migrator`

The daily `pg_dumpall` backups taken before this date still contain the
Starbase databases and roles until retention expires.

## Verification

- `flux get kustomizations -A` shows neither Starbase Kustomization
- no `starbase-*` namespace remains
- `starbase.almckay.io` no longer resolves to a live ingress
- `just live-service-probes` passes without Starbase exemptions
