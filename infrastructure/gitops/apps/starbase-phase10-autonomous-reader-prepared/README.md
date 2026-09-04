# Phase 10 autonomous crew reader preparation

This inactive overlay establishes the reader-first configuration required by
Starbase ADR 0018. It inherits the live Phase 9 foundation, changes the single
core Deployment to `Recreate`, records the exact RC10 rollback digest, and
defines both Bounty automation switches as false. It deliberately adds no
Temporal or model endpoint configuration and labels core as neither a Temporal
client nor an external authority.

The Flux `starbase-foundation` Kustomization still points to Phase 9. This
directory is preparation, not deployment authority. The immutable successor
core and web digests, release annotation, and source revision must be added
from a verified Starbase release manifest before changing the Flux path to
this overlay.

Reader-first acceptance requires one connector reconciliation with no
successor-only checkpoint fields, a predecessor-reader restore check, healthy
core/web probes, and retention of the disabled successor core digest as the
post-activation rollback target. A failed check returns the Flux path to Phase
9; no database deletion or direct workload mutation is part of rollback.
