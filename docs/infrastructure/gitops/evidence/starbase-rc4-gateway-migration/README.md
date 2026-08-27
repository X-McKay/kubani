# Starbase RC4 gateway migration evidence

Captured: `2026-08-27T17:56:38Z`

Purpose: retain the final execution evidence for the separately authorized RC4
gateway migration before any later release or cleanup can prune its immutable
Job and pod.

PR #94 merged as `c32257a32e6fa72e29fa39c9c3fd77360932dba8`.
Flux resumed exactly `starbase-gateway-migrate-c5de66b03eaf`. It ran once on
the preferred `asio` node, completed in seven seconds, and had zero failed
attempts, restarts, or nonzero exits. The pod resolved the reviewed image
`ghcr.io/x-mckay/starbase/gateway-migrator@sha256:1b7acd8ae30dc79a9491e6ffc6b526d99ee69f8e3f8302b647e94d0c6c7473db`.

Read-only PostgreSQL verification found the same one migration-ledger row and
digest, exactly two gateway tables owned by `starbase_gateway_migrator`, and
zero rows in `operator_sessions`. The core ledger, tables, ownership, and
empty state/fence tables were unchanged. PostgreSQL reported no waiting locks
or idle-in-transaction sessions.

All five Flux Kustomizations became Ready at the exact merge revision. Every
Starbase Deployment remained at zero replicas, both migration Jobs remained
Complete, and all required live-service, Certificate, Longhorn, PostgreSQL,
Authentik, registry, Temporal, model, and node checks passed. Final measured
use was `asio` 3% CPU / 30% memory and `strix` 4% CPU / 19% memory; all four
nodes were Ready and pressure-free.

The capture was read-only. It selected non-secret Job, pod, event, image,
placement, completion, retry, exit, and log-result fields. No environment
variables, Secret values, mounted files, projected tokens, or database URLs
were read.

Artifacts:

- `execution-status.json`: sanitized immutable Job and pod outcome;
- `events.json`: sanitized Job-scoped Kubernetes events; and
- `gateway-log-capture.json`: explicit successful zero-byte log capture.

Checksums are recorded in `SHA256SUMS`.
