# Starbase Phase 7 GitHub observation canary

Date: 2026-09-01
Owner and approving authority: Al McKay
Status: prepared for merge-activated pre-production canary

## Scope

This overlay activates one read-only GitHub connector for only
`X-McKay/Starbase`. It retains the synthetic repository fixture and the
namespace-bounded Kubernetes connector so live GitHub observations can be
compared with existing durable paths without removing a known-good signal.
Mutation remains disabled globally and the GitHub App has no write permission.

The GitHub connector is required to run on `asio` or `strix`, requests 50m CPU
and 64Mi memory, and is health-gated by Flux. Immediately before the artifact
preload, all four nodes were Ready, no Pod was failed or pending, all Flux
Kustomizations were Ready, `asio` used 4% CPU / 38% memory, and `strix` used 5%
CPU / 20% memory. Refresh health and capacity immediately before merge and
after reconciliation.

## Identity and authorization

The private `Starbase Kubani Observer` GitHub App is owned by `X-McKay` and is
installed only on `X-McKay/Starbase`. Its repository permissions are read-only
Actions, Contents, Issues, Metadata, and Pull requests. Webhooks, OAuth user
authorization, device flow, organization permissions, account permissions,
enterprise permissions, and every write permission are disabled.

The SOPS-encrypted `starbase-github-app` Secret contains exactly the numeric
App ID, numeric installation ID, and one PEM private key. Only the connector
mounts the key, at
`/var/run/secrets/starbase.io/github/private-key.pem`, with mode `0440`. The
plaintext key is never committed and must be removed from the local Downloads
directory after the encrypted Secret and live token exchange are verified.

One failed browser download created an orphaned GitHub private key. It is not
present locally or in the encrypted Secret and must be revoked after the
downloaded key fingerprint and live connector are verified.

## Network and artifact boundary

The inherited ADR 0012 policy permits only the GitHub connector to reach
public IPv4 TCP/443 and excludes private, cluster, Tailscale/CGNAT, loopback,
link-local, documentation, benchmark, multicast, and reserved ranges. The
connector independently permits only exact HTTPS `api.github.com`, GET/POST,
empty or 443 port, no userinfo, and no redirects. This exception expires before
mutation, production, or `2026-11-30T23:59:59Z`.

The exact `linux/amd64` connector image was built from merged Starbase revision
`3f1a5962090e7cb54caaf213d343d1906997f017` and is referenced as:

`ghcr.io/x-mckay/starbase/github-connector@sha256:cdec332a5c181a0038373c1c9d3b4ac4f6eff480b51ffca67c786be2b89d93c8`

The Docker archive SHA-256 is
`af19e1e3788b2a0bd272ce4f52f2db98370467dfb60b7067af88b20e58e92453`.
Trivy 0.74.0 found zero fixed HIGH/CRITICAL vulnerabilities and zero secrets.
Matching checksums and exact digest-qualified `linux/amd64` aliases were
verified on both `asio` and `strix` without starting a Pod.

The first Phase 7 rollout stopped on 2026-09-01 because the `c80479e` image
treated Kubernetes' in-mount atomic Secret symlink as an arbitrary unsafe
symlink. The documented Phase 6 rollback completed at Kubani revision
`86d20ac69197275825a60003098e3c57ffd0d34b`. Starbase PR 45 added a regression
test and a bounded resolver that accepts only a regular key target contained
within the configured mount directory, then passes the validated bytes without
reopening the path. This retry uses only the corrected merged image above.

## Accepted pre-production access limitation

`starbase.almckay.io` currently publishes only the four Kubani nodes' Tailscale
CGNAT addresses, which are not publicly routable, and Authentik remains the
browser authentication boundary. This is sufficient for the current homelab
pre-production deployment, but it is not proof that the ingress rejects a
client that can already reach a node over the trusted LAN and supplies the
Starbase host name. The cluster therefore must not be described as strictly
Tailnet-only yet.

Al McKay accepted this bounded limitation on 2026-09-01 so the remaining
pre-production phases can be completed without introducing another edge proxy
or external service. The owner is Al McKay. Before any production designation,
the deployment must either enforce source-aware access at the ingress edge or
bind the entry point to the intended Tailscale interfaces, and a negative test
must prove that the same request is denied over every non-Tailscale node path.
Revisit this item after the end-to-end deployment review; authentication,
public-DNS inspection, and absence of public routes remain required in the
meantime.

## Activation and verification

Merge is the activation decision. Let Flux reconcile naturally. Before merge,
require fresh healthy nodes and Flux, adequate preferred-node capacity, the
exact image alias on both nodes, a server-side dry-run, successful local
policy tests, and proof that the SOPS file contains only the expected encrypted
fields.

After reconciliation require:

1. one Ready GitHub connector on `asio` or `strix`, at the exact image digest,
   with zero restarts;
2. fresh `github:X-McKay/Starbase`, synthetic GitHub, and Kubernetes sources in
   core;
3. live GitHub findings that agree with an independent read-only API snapshot;
4. successful installation-token rotation with no personal access token;
5. denied unauthenticated core access, no migration execution, no provider or
   cluster mutation, and no secret value in logs or API responses;
6. a one-at-a-time restart followed by repeated source/finding checks; and
7. stable node health, capacity, and fully Ready Flux after every step.

Any digest drift, broader repository or permission scope, credential exposure,
unexpected egress, stale source, reconciliation error, restart loop, migration
execution, node pressure, or Flux degradation stops the canary.

## Rollback and cleanup

Rollback is a forward GitOps change restoring the Flux path to
`./infrastructure/gitops/apps/starbase-phase6-kubernetes-canary`. That returns
the GitHub Deployment to zero, removes its public HTTPS policy and Secret, and
removes only the live GitHub expected source and identity from core. It retains
the Kubernetes canary, synthetic fixture, findings, and database state.

After acceptance, remove the plaintext downloaded PEM and the transferred
`/home/al/starbase-github-connector-3f1a596.tar` and superseded
`/home/al/starbase-github-connector-c80479e.tar` archives. Retain the imported
image through the rollback window. Revoke the orphaned GitHub key once the
downloaded key is proven live; keep only the active fingerprint.
