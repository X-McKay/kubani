# Phase 9 signed observers and authenticated Dojo projection

This overlay advances the accepted Phase 7 observation surface without adding
provider authority. It replaces core, web, the preview fixture, and both live
read-only connectors with the exact signed `0.1.0-rc.10` successor images and
adds one read-only Gravity Dojo projection to the authenticated Experience
Gateway.

The Dojo boundary is not exposed through ingress. Core connects only to the
ClusterIP service in `starbase-execution` over TLS 1.2 or newer, validates the
exact Phase 9 CA from `starbase-dojo-ca`, and presents the existing scoped read
capability. Matching NetworkPolicies admit only `starbase-core` to the Dojo
runtime on TCP 8443. The browser receives the already bounded Experience
Gateway projection and never receives the read capability, model actions,
prompt content, or write access.

`starbase-foundation` and `starbase-dojo` reconcile concurrently against the
database dependency. This avoids a dependency cycle: core waits up to 60
seconds for transport availability and remains unready if the TLS service,
certificate, token, or projection is invalid. Contract, identity, TLS, and
data failures are not retried as rollout ordering.

Rollback returns the foundation path to
`starbase-phase7-github-canary`, removes the Dojo URL/token/CA configuration,
and restores the prior immutable image digests. It does not delete Dojo
evidence, database state, the internal CA, or completed migration Jobs. If a
reader failure is isolated to the Dojo path, removing all three reader
variables together is the smallest safe rollback.
