# Phase 8 governed Gravity Dojo pre-production slice

This overlay is deployed alongside, and depends on, the accepted Phase 7
observation surface. It adds one credential-free, non-authoritative evaluation
path and deploys the signed
`0.1.0-rc.6` Dojo runtime by immutable digest, a deterministic no-change model
fixture, a fixture Sim Chamber, Temporal workflow and activity pollers, and a
service-owned PostgreSQL schema.

The temporary Temporal exception is exactly ADR 0016: namespace `default`,
frontend `temporal-frontend.temporal.svc.cluster.local:7233`, acknowledgement
`adr-0016`, no TLS or server authentication, no sensitive inputs, and no
external mutation authority. Dedicated tokenless ServiceAccounts, exact
NetworkPolicies, distinct runtime and migration database roles, and separate
read/write/sandbox tokens bound the exception. Any endpoint, namespace, trust,
input-classification, or authority expansion requires a new decision and a
normal authenticated Temporal transport.

The Dojo API has no Service or ingress. Acceptance uses an owner-local
`kubectl port-forward` for read-only evidence inspection and a local dispatcher
through a temporary Temporal port-forward. The synthetic command must retain
`non_authoritative=true`, `external_effect=false`, outcome `no_change`, and no
Sortie or chamber because a no-change advisory has nothing to rehearse.
Rollback removes the separate `starbase-dojo`
Flux Kustomization while leaving `starbase-foundation` on
`starbase-phase7-github-canary`; completed bootstrap and migration Jobs remain
as immutable evidence and the additive database is not deleted.
