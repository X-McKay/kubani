# Phase 10 autonomous crew activation preparation

This active overlay composes the bounded Starbase autonomous crew runtime on
top of the reader-first preparation. It enables the worker and dispatch flags,
binds core to the accepted ADR 0016 Temporal endpoint, selects the
credential-free fast model, and pins Mission evaluation to the Phase 9
deny-network environment digest.

Three additive NetworkPolicies admit only the labelled core Pod to the exact
Temporal frontend on TCP 7233, admit the matching return ingress in the
`temporal` namespace, and permit TCP 443 only to the four Kubani node `/32`s
returned for the application-enforced model hostname when they were revalidated
for the bounded activation attempt at the annotated UTC timestamp. Core remains
`external-authority=false`, mutation remains disabled, and the overlay adds no
model credential or Kubernetes API token.

The Flux path selects this overlay only after the RC14 reader stage repaired
legacy Bounties without target asset identities and passed its compatibility,
health, and rollback gates. The disabled RC14 reader overlay remains the
immediate rollback target. A drain sets
`STARBASE_BOUNTY_AUTOMATION_DISPATCH_ENABLED=false` and advances the
`starbase.io/autonomous-runtime-revision` Pod-template annotation in the same
reviewed change so core restarts with dispatch disabled. Only after the new Pod
is ready and open histories reach zero may rollback return to the disabled
successor reader overlay.
