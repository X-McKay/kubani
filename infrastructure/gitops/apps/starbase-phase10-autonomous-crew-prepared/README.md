# Phase 10 autonomous crew activation preparation

This inactive overlay composes the bounded Starbase autonomous crew runtime on
top of the reader-first preparation. It enables the worker and dispatch flags,
binds core to the accepted ADR 0016 Temporal endpoint, selects the
credential-free fast model, and pins Mission evaluation to the Phase 9
deny-network environment digest.

Three additive NetworkPolicies admit only the labelled core Pod to the exact
Temporal frontend on TCP 7233, admit the matching return ingress in the
`temporal` namespace, and permit TCP 443 only to the four Kubani node `/32`s
currently returned for the application-enforced model hostname. The observed
addresses are annotated for mandatory revalidation before activation. Core remains
`external-authority=false`, mutation remains disabled, and the overlay adds no
model credential or Kubernetes API token.

The Flux path deliberately remains on Phase 9. Before activation, promote and
accept the immutable reader-first release, replace the inherited image and
release metadata with its verified values, and capture that disabled successor
digest as rollback. Activation is a separate reviewed Flux path change. A drain
sets `STARBASE_BOUNTY_AUTOMATION_DISPATCH_ENABLED=false` and advances the
`starbase.io/autonomous-runtime-revision` Pod-template annotation in the same
reviewed change so core restarts with dispatch disabled. Only after the new Pod
is ready and open histories reach zero may rollback return to the disabled
successor reader overlay.
