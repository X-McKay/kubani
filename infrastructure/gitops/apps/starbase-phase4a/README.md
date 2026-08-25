# Starbase Phase 4A dependency contract

This directory composes the immutable Phase 3 Starbase bundle with Kubani-owned
database, identity, secret-reference, ingress, network, and resource-governance
bindings. It is review evidence, not active desired state.

The parent `../kustomization.yaml` deliberately does not reference this
directory. Its active foundation sibling contains only SOPS-encrypted,
workload-scoped Secrets; every database Job is suspended, the core Deployment
carries a blocking annotation, and the Authentik blueprint is not mounted by
the active Authentik HelmRelease. An accidental partial apply therefore cannot
start the database bootstrap, run product migrations, or run any Starbase
product Deployment: core and both connectors render at zero replicas until a
separately reviewed activation patch changes them.

## Included contracts

- separate `starbase_core` and `starbase_gateway` databases;
- separate runtime and migration roles for each database;
- a content-named, idempotent, suspended PostgreSQL bootstrap Job;
- four distinct runtime/migration Secret references plus a separate database
  bootstrap Secret reference;
- a public Authentik client with a per-provider issuer, strict redirect
  matching, no client secret, a dedicated non-superuser group, an application
  access binding for that group, and an explicit groups claim;
- an HTTPS Ingress that targets only the browser-facing service;
- exact database, Authentik/Traefik, Kubernetes issuer, and ingress network
  paths;
- namespace quotas and defaults sized above the accepted first-release request
  while bounding unexpected growth; and
- preferred placement on `asio` and `strix` without making either node a hard
  availability dependency.

The public Authentik client relies on PKCE enforcement by Starbase because this
provider contract does not assert an Authentik-side PKCE requirement. The live
Authentik 2026.5.6 serializer supports the explicit `authorization_code` grant
and `authorization` redirect type declared by the blueprint. Refresh remains
disabled by omitting the offline-access mapping. Membership in
`starbase-operators` is required independently by Authentik application policy
and Starbase authorization; creating the group does not grant membership.

The blueprint is owned and mounted by
`../authentik/blueprints-configmap.yaml`; this review overlay no longer emits a
duplicate Authentik ConfigMap. Its inclusion in the active apps Kustomization
can configure Authentik, but it still cannot start a Starbase workload or run a
database Job.

## Required encrypted Secrets

The active foundation provisions the following SOPS-encrypted Secrets. Their
presence does not authorize or start a consumer. Never commit plaintext or
place credentials in this directory as templates with usable values.

| Namespace | Secret | Keys | Consumer |
|---|---|---|---|
| `database` | `starbase-database-bootstrap` | `core-runtime-password`, `core-migrator-password`, `gateway-runtime-password`, `gateway-migrator-password` | suspended bootstrap Job only |
| `starbase-system` | `starbase-core-runtime` | `database-url` | core runtime |
| `starbase-system` | `starbase-gateway-runtime` | `database-url`, `session-encryption-key` | Experience Gateway runtime |
| `starbase-system` | `starbase-core-migration` | `database-url` | core migrator only |
| `starbase-system` | `starbase-gateway-migration` | `database-url` | gateway migrator only |

The session key is an independently rotatable base64-encoded 32-byte value.
Database passwords are independently generated URL-safe random values of at
least 43 characters. The URLs use the matching least-privilege role, database,
schema search path, and internal PostgreSQL service. The current PostgreSQL
HelmRelease has TLS disabled, so these URLs state `sslmode=disable`; exact
NetworkPolicies provide the current homelab transport boundary. PostgreSQL TLS
enablement requires a separately reviewed credential rotation.

## Review locally

```sh
kubectl kustomize infrastructure/gitops/apps/starbase-phase4a >/tmp/starbase-phase4a.yaml
uv run python -m unittest tests.test_starbase_phase4a -v
```

Rendering is not deployment authorization. Follow
[`starbase-phase4a-preflight.md`](../../../../docs/infrastructure/gitops/starbase-phase4a-preflight.md)
for the evidence, activation order, stop conditions, and rollback paths.
