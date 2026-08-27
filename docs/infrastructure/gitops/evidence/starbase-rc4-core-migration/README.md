# Starbase RC4 core migration evidence

Captured: `2026-08-27T13:32:03Z`

Purpose: retain the final execution evidence for the separately authorized RC4
core migration before any later release or cleanup can prune its immutable Job
and pod.

PR #93 merged as `8616fdfb8e3df0cc0e286449c1213325c5436eae`.
Flux resumed exactly `starbase-core-migrate-67c24a8df537`. It ran once on the
preferred `asio` node, completed in five seconds, and had zero failed attempts,
restarts, or nonzero exits. The pod resolved the reviewed image
`ghcr.io/x-mckay/starbase/core-migrator@sha256:fad95f8fb51f709eb0798f96a13aaa91381141ccb31735972c31967594eee878`.

Read-only PostgreSQL verification found the same two migration-ledger rows and
digests, exactly four core tables owned by `starbase_core_migrator`, and zero
rows in `state_journal`, `state_current`, and
`connector_fence_high_water`. The gateway ledger and tables were unchanged and
`operator_sessions` remained empty. PostgreSQL reported no waiting locks or
idle-in-transaction sessions.

All five Flux Kustomizations became Ready at the exact merge revision. Every
Starbase Deployment remained at zero replicas, the gateway migration remained
suspended and never started, and all required live-service, Certificate,
Longhorn, PostgreSQL, Authentik, registry, Temporal, model, and node checks
passed. Final measured use was `asio` 4% CPU / 31% memory and `strix` 4% CPU /
19% memory.

The capture was read-only. It selected non-secret Job, pod, event, image,
placement, completion, retry, exit, and log fields. No environment variables,
Secret values, mounted files, or database URLs were read.

Artifacts:

- `execution-status.json`: sanitized immutable Job and pod outcome;
- `events.json`: sanitized Job-scoped Kubernetes events; and
- `core.log`: exact timestamped one-line completion log.

Checksums are recorded in `SHA256SUMS`.
