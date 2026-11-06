# T29 performance fixture approval

PR #386 staged the exact public `conformance-performance/v0.1.0` Agent and
AgentRelease from zetra-agents revision `87bf469` unapproved. Published SHA256SUMS
and parsed YAML equality were checked; scanner/lint comments are the only
non-approval additions to the published AgentRelease.

Before this separate approval change, root independently verified the exact
controller release: signature valid, all five exact attestations, expected
issuer and release-tag subject, matching image/policy digests, and
`PolicyDrift=False` with `NoDrift`. `Ready=False` was solely `NotApproved`.
This change records explicit approval metadata; it activates no performance
worker/harness and submits no sessions. T29 is not qualified.

The exact tenant signer declarations, runtime resource limits and 64 MiB archive
cap remain unchanged. Collection completeness, latency/capacity targets and full
platform qualification remain separate; the literal 64 MiB workspace target
remains unqualified. No private controller receipts or raw logs are included.
