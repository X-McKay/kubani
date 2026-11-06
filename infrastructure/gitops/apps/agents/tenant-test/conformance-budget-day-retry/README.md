# Exact daily-budget retry fixture

These are the SHA256SUMS-verified `conformance-budget-day-retry/v0.1.0` release
assets from zetra-agents revision `c4bb1e7`. The release remains unapproved.
Its canonical policy digest matches the signed asset; the original day fixture
and spent ledger remain unchanged. Only this exact release-workflow identity is
added to both tenant signer declarations. The harness Role grants only exact
Agent/release reads and tenant Pod listing.

This staging does not enable the retry route or observer identity. A separate
coordinated rollout must pin the matching APS, backend and runner images before
extending their allowlists and selecting this fixture in the suspended manual
Job. Verify all attestations and NoDrift, then approve separately. The retry has
the same 2000-token daily limit and enforced 300-token reservation; no ledger
reset or live qualification is implied.
