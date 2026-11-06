# Signed T27 transport fixture

These are the SHA256SUMS-verified `conformance-transport/v0.1.0` Agent and
AgentRelease assets from zetra-agents revision `2f0a4cb`. The release remains
unapproved. The exact transport release-workflow identity is added to both
tenant signer declarations; the harness receives only `get` on this release.

Wait for controller-derived SignatureVerified, all five attestation conditions
and NoDrift before a separate approval change. This staging performs no live
qualification and starts no Job. The suspended, unlisted manual T27 templates
and bounded operator capture procedure are in
[`agent-platform/conformance/transport`](../../../agent-platform/conformance/transport/README.md).
They must be rendered with this approved release and the current identical
published runner image for production, temporary worker and harness. Host capture
remains an operator-owned action bound to the fresh Pod UID/IP/veth; no privileged
Pod, host mount, credential output or automatic capture is introduced here.
