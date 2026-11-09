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

The corrected `conformance-transport/v0.1.1` release is staged separately in
`agentrelease-v0.1.1.yaml` with approval false. Its published definition matches
exactly; the original v0.1.0 release and failed run31 remain retained. Require
controller signature, all five attestations and NoDrift before a separate approval.
The installed fixture strictly classifies a complete bounded TLS fatal alert.
Host capture remains deferred; this staging and source verification do not
qualify T27. The new runner also reports missing capture as failed checks.

## Model-free replacement

`conformance-transport/v0.1.2` is staged as `conformance-transport-2026-11-08-6b1f8f93`
with approval false. Its Agent declares no model capabilities. Exact published
assets and policy compilation were verified; separate controller verification
and approval remain required. Historical releases stay retained and no longer
match the updated Agent policy. This change activates no qualification sessions.
