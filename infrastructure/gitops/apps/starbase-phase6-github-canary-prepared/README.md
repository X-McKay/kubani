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

The connector was built as `linux/amd64` from clean, merged Starbase revision
`c80479e7684f56e615fe3d469c0bdcdf8739393e` under the bounded ADR 0009
owner-local pre-production exception:

- Kubernetes/containerd manifest:
  `sha256:12a713610d1f3e599d66ae103d46d72e1902d0f473d1cd175a6ef9cecc526974`;
- OCI-archive manifest:
  `sha256:d45859f6b16d4757f3fdc0ff00790b4421f4cb4be81670db411259ef917dea3d`;
- OCI config / CRI image ID:
  `sha256:fa45c0b94374ddb37eced1bd4bcdb083de1859945f068494733685d00f97f050`;
- OCI archive SHA-256:
  `cc2c12bea5bb29318ece8aac982d69d87f34eeeac5411030ee0a2eeacf9087a5`;
- equivalent Docker archive SHA-256:
  `73d71bbcf20941f7af424740db842ee1a570cbd754463fcf8494ba77b6011947`;
  and
- Trivy security evidence SHA-256:
  `7471da05687db0d1594b3943ff1b67ce319078af00e9b73cf043fa114279791c`.

Pinned Trivy 0.74.0 reported zero fixed HIGH/CRITICAL vulnerabilities and zero
secret findings from the Docker archive. The OCI archive was retained because
Trivy 0.74.0 does not accept Podman's OCI tar directly. The Docker archive was
checksum-verified as
`73d71bbcf20941f7af424740db842ee1a570cbd754463fcf8494ba77b6011947`,
imported, and the digest-qualified GHCR-compatible alias above reported as
`linux/amd64` by K3s containerd on both `asio` and `strix`. Preload did not
alter a Deployment or start a Pod. The earlier `400711d` connector artifact
predates Starbase ADR 0012's exact-destination and redirect enforcement and is
ineligible for activation.

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

Keep the node-preloaded image through the canary rollback window. Remove
`/home/al/starbase-github-connector-c80479e.tar` and the superseded
`/home/al/starbase-github-connector-400711d-oci.tar` from `asio` and `strix`
only after acceptance; imported exact images remain the rollback artifact
until a normally published successor replaces them.
