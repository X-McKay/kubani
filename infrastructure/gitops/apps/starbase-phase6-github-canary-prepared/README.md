# Starbase Phase 6 GitHub canary preparation

Date: 2026-08-31
Owner and approving authority: Al McKay
Status: prepared and intentionally inactive; not referenced by Flux

## Purpose and boundary

This overlay prepares the exact current GitHub connector artifact, its
credential-file contract, and the accepted connector-only public HTTPS policy
without activating a provider, adding a Secret, or changing core's expected
sources. It inherits the live namespace-bounded Kubernetes canary and keeps the
GitHub Deployment at zero replicas. The live Flux Kustomization continues to reference
`starbase-phase6-kubernetes-canary`, not this directory.

The preparation is deliberately fail-closed. If somebody referenced this
overlay prematurely, the GitHub connector would remain at zero and the absent
`starbase-github-app` Secret would prevent a future Pod from starting. The
public HTTPS NetworkPolicy has no selected running Pod while replicas remain
zero.

## Exact inactive artifact

The connector was built as `linux/amd64` from clean Starbase revision
`400711d9fbb3e068f6dff274e58db26bcae934e3` under the bounded ADR 0009
owner-local pre-production exception:

- OCI manifest:
  `sha256:c8a1f57fb78abbf5f194ef91d3e24ff105ea2422ee12a72fad707277bfb9be66`;
- OCI config / CRI image ID:
  `sha256:2863fa42085299d0c543fa8d741162921efccc03243ba5e4f36bbc9746392282`;
- OCI archive SHA-256:
  `c2eea7ddfbcc55e921afb63b23bac54b408033a0639922afb7ce577caf105ade`;
- equivalent Docker archive SHA-256:
  `f6c082212374b9e16c0430a9a4c596997619fcb36a31a0dc7e70ff804bcf1e3a`;
  and
- Trivy security evidence SHA-256:
  `3276f233a661fceb081bb308f87069a999e642628b74b3e62e2d08d6e884b21b`.

Pinned Trivy 0.70.0 reported zero fixed HIGH/CRITICAL vulnerabilities and zero
secret findings. The exact manifest alias was checksum-verified, imported, and
reported as `linux/amd64` by K3s containerd on both `asio` and `strix`. Preload
did not alter a Deployment or start a Pod.

This is not a signed, published release and has no SBOM/provenance or registry
availability claim. It may be used only for the reversible homelab canary and
must be replaced before production or ADR 0009 expiry.

## Credential contract

Activation requires a SOPS-encrypted `starbase-github-app` Secret in
`starbase-connectors` with exactly:

- `app-id` — the numeric environment-owned GitHub App ID;
- `installation-id` — the numeric installation ID; and
- `private-key.pem` — the App private key.

The Deployment mounts only `private-key.pem` at
`/var/run/secrets/starbase.io/github/private-key.pem` with mode `0440`. Its
existing restricted pod identity and `fsGroup` make that regular file readable
by the non-root connector process. The two public numeric identifiers are read
through `secretKeyRef`; values are never written into this overlay or evidence.
Static personal access tokens are not supported.

## Remaining activation change

One later reviewed activation overlay must, as a single coherent change:

1. add the SOPS-encrypted Secret and prove its exact key set without displaying
   values;
2. preserve the reviewed ADR 0012 connector-only public IPv4 TCP/443 policy and
   verify all private/reserved exclusions;
3. change the GitHub Deployment to one replica and retain required placement on
   `asio` or `strix`;
4. add `github:X-McKay/Starbase` to core's exact expected-source and connector
   identity contracts;
5. update the promotion allowlist and Flux path together; and
6. repeat health, capacity, dry-run, credential-isolation, source freshness,
   reconciliation, independent-provider comparison, restart, and rollback
   evidence.

K3s' current standard NetworkPolicy implementation has no FQDN selector.
[Starbase ADR 0012](https://github.com/X-McKay/Starbase/blob/main/docs/adr/0012-bounded-preproduction-github-egress.md)
accepts a time-bounded pre-production exception: only the
GitHub connector may reach public IPv4 TCP/443, and private, cluster,
Tailscale/CGNAT, loopback, link-local, benchmarking, documentation, multicast,
and reserved ranges are excluded. Connector code independently permits only
exact HTTPS `api.github.com` and rejects redirects. This is not hostname-aware
network enforcement and expires before mutation, production, or
`2026-11-30T23:59:59Z`. The exact GitHub App installation remains the only
external activation input.

## Rollback and cleanup

Because this overlay is inactive and unreferenced, repository rollback is
deletion or a Git revert. Once activated, rollback restores the current Phase 6
Kubernetes overlay, removes the live GitHub expected source, returns the
Deployment to zero, and removes the GitHub egress policy without replaying
migrations or removing retained findings.

Keep the node-preloaded image through the canary rollback window. Remove only
`/home/al/starbase-github-connector-400711d-oci.tar` from `asio` and `strix`
after acceptance; imported exact images remain the rollback artifact until a
normally published successor replaces them.
