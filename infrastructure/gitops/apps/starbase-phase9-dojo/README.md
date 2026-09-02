# Phase 9 governed proposal and TLS Dojo service

This overlay advances the accepted Phase 8 non-authoritative Dojo slice from a
deterministic `no_change` result to one deterministic bounded `propose` result.
The proposal contains only `inspect` followed by terminal `propose`, remains
authorization-gated, runs in the deny-network fixture Sim Chamber, records no
external effect, and must retain a successful Sortie with
`teardown_state=confirmed_destroyed`.

The signed `0.1.0-rc.8` Dojo runtime retains bounded PostgreSQL and Temporal
startup ordering. The existing completed RC6 migration Job remains unchanged
because there is no schema migration. The Dojo API keeps HTTP on loopback for
its colocated activity worker and adds a TLS 1.2-or-newer listener on TCP 8443.
A ClusterIP service and exact cross-namespace NetworkPolicies expose that
listener only to `starbase-core`; there is no Ingress or public DNS record.

The encrypted Phase 9 CA key is scoped to `starbase-execution`. cert-manager
issues and rotates a 90-day ECDSA serving certificate for
`starbase-dojo.starbase-execution.svc.cluster.local`. The public CA is copied
to the foundation ConfigMap and has a documented owner and advance rotation
date. Rotation must update both the encrypted CA Secret and public ConfigMap,
verify a dual-trust transition or coordinated bounded restart, and prove core
reconnects before the old trust is removed.

Rollback returns `starbase-dojo` to
`starbase-phase8-dojo-preproduction`, which restores the signed RC6 no-change
runtime and removes the Service/TLS listener. Completed bootstrap and migration
Jobs and durable evaluation evidence are retained. Scaling the two Dojo
Deployments to zero is the emergency stop; it is not data rollback.
