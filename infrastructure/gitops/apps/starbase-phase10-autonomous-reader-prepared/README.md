# Phase 10 autonomous crew reader preparation

This inactive overlay establishes the reader-first configuration required by
Starbase ADR 0018. It inherits the live Phase 9 foundation, promotes the core,
web, and connector Deployments to the verified `0.1.0-rc.11` image digests,
changes the single core Deployment to `Recreate`, records the exact RC10
rollback digests, and defines both Bounty automation switches as false. It
deliberately adds no Temporal or model endpoint configuration and labels core
as neither a Temporal client nor an external authority.

The Flux `starbase-foundation` Kustomization points to this reader-first stage.
Merge of the separately reviewed activation change is the deployment authority.
The successor image and release metadata are bound to Starbase release manifest
`sha256:4c26e778b72a81ea89af0a505c59f24cbef2a8adb302a791f937231ef1e38ae8`
for source revision `5ffa445a21796c8d745197186fbf348f056893e4`.

Reader-first acceptance requires one connector reconciliation with no
successor-only checkpoint fields, a predecessor-reader restore check, healthy
core/web probes, and retention of the disabled successor core digest as the
post-activation rollback target. A failed check returns the Flux path to Phase
9; no database deletion or direct workload mutation is part of rollback. This
stage does not authorize or activate the autonomous Crew overlay.
