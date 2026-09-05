# Phase 10 autonomous crew reader preparation

This reader-first deployment overlay establishes the compatibility stage
required by Starbase ADR 0018. It inherits the live Phase 9 foundation,
promotes the core, web, and connector Deployments to the verified
`0.1.0-rc.12` image digests,
changes the core and connector Deployments to `Recreate`, records the exact RC11
rollback digests, and defines both Bounty automation switches as false. It
deliberately adds no Temporal or model endpoint configuration and labels core
as neither a Temporal client nor an external authority.

The Flux `starbase-foundation` Kustomization points to this reader-first stage.
Merge of the separately reviewed activation change is the deployment authority.
The successor image and release metadata are bound to Starbase release manifest
`sha256:05cf425645e84fcc3d1b8de5aa0dbfd298487b40c78f8ed3d11b6d61c5cc9cfe`
for source revision `7d15dc792c5d31e3f918d837d5a84128f43bf3fa`.

Reader-first acceptance requires one connector reconciliation with no
successor-only checkpoint fields, a predecessor-reader restore check, healthy
core/web probes, and retention of the disabled successor core digest as the
post-activation rollback target. A failed check returns the Flux path to Phase
9; no database deletion or direct workload mutation is part of rollback. This
stage does not authorize or activate the autonomous Crew overlay.
