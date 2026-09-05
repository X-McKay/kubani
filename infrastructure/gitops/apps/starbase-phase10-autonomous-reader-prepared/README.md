# Phase 10 autonomous crew reader preparation

This reader-first deployment overlay establishes the compatibility stage
required by Starbase ADR 0018. It inherits the live Phase 9 foundation,
promotes the core, web, and connector Deployments to the verified
`0.1.0-rc.14` image digests, keeps core and the fixture on `Recreate`, changes
the live connectors to no-surge `RollingUpdate`, records the exact RC12
rollback digests, and defines both Bounty automation switches as false. It
deliberately adds no Temporal or model endpoint configuration and labels core
as neither a Temporal client nor an external authority.

The Flux `starbase-foundation` Kustomization points to this reader-first stage.
Merge of the separately reviewed activation change is the deployment authority.
The successor image and release metadata are bound to Starbase release manifest
`sha256:2c3745639a84269e1deb7731bdf62752a5aceae384b6447e9a20d07d77a02896`
for source revision `61ad6ccf06418bc9cee5c48f45823fe3131baa7b`.

Reader-first acceptance requires one connector reconciliation with no
successor-only checkpoint fields, a predecessor-reader restore check, healthy
core/web probes, and retention of the disabled successor core digest as the
post-activation rollback target. A failed check returns the Flux path to Phase
9; no database deletion or direct workload mutation is part of rollback. This
stage does not authorize or activate the autonomous Crew overlay.
