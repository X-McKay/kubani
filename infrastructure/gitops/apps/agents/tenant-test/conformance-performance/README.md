# Unapproved T29 performance fixture staging

This stages the exact public `conformance-performance/v0.1.0` Agent and
AgentRelease assets from zetra-agents revision `87bf469`. Published SHA256SUMS
were checked; the only AgentRelease text additions are scanner/lint comments,
with parsed YAML equality verified against the published file.

The release remains `approval.approved: false`. Signature, all five attestations
and NoDrift require independent controller observation before a separate approval
change. This staging change does not approve the release, activate a performance
worker/harness, submit sessions, or qualify T29.

The tenant signer declarations add only the exact `conformance-performance`
release-tag name under the existing zetra-agents release workflow and issuer.
Existing runtime resource limits and the 64 MiB archive cap are unchanged.
T29 collection, latency/capacity targets and full platform qualification remain
separate; the literal 64 MiB workspace target remains unqualified. No private
verification receipts or raw logs are included here.
