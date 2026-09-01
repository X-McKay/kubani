# Starbase Phase 7 GitHub observation canary

Date: 2026-09-01
Owner and approving authority: Al McKay
Status: live pre-production canary; immediate acceptance passed for every
currently approved observation scope; duration gates remain open

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

The authenticated live Control Room then exposed a presentation-only lifecycle
defect: nine resolved Kubernetes startup observations and four resolved
Bounties remained visible and inflated labels that explicitly said “open.” The
durable records were correctly marked resolved. Starbase revision
`dbfc9f113a6338e832fa5e07b6e1094793f1acef` makes the React and Godot
Observatory views use the same active-finding rule while retaining the durable
history. The exact `linux/amd64` web image is:

`ghcr.io/x-mckay/starbase/web@sha256:4e97f206917bb72b4c001cb3c75822f4f642c105ef4700cc2722b1c3e3a1ff81`

Its Docker archive SHA-256 is
`62889a3603a9eb9ddc832d60b4ed38f63d6edf9435ef108b56a1f5a361161645`.
Trivy 0.74.0 found zero fixed HIGH/CRITICAL vulnerabilities and zero secrets;
the retained JSON report SHA-256 is
`e2469ee7ee92da68564d6d652edf76339541b6379c825dc97bf6c55c7e99b883`.
The first candidate was rejected before preload because it contained two fixed
HIGH `libexpat` findings. The accepted candidate upgrades only that package to
the fixed Alpine version. Matching archive checksums and the exact digest alias
were verified on both `asio` and `strix` before this desired-state change.

## Accepted owner-local image exception

Starbase
[ADR 0014](https://github.com/X-McKay/Starbase/blob/1838b0c44961eb9f82ce5d38498c26c84bf72ccb/docs/adr/0014-bounded-owner-local-observation-images.md)
accepts only these exact owner-local `linux/amd64` images for the current
single-owner, observation-only Kubani homelab:

| Workload | OCI manifest digest |
|---|---|
| web | `sha256:4e97f206917bb72b4c001cb3c75822f4f642c105ef4700cc2722b1c3e3a1ff81` |
| core | `sha256:b906d2d2d3e2aff743974cd829b548932101615f9f10ca2ad3c5413b84eb4809` |
| GitHub connector | `sha256:cdec332a5c181a0038373c1c9d3b4ac4f6eff480b51ffca67c786be2b89d93c8` |
| Kubernetes connector | `sha256:70595d0171b481ae78b221e52b11f38a67aedf6768974fb77b19a875c42ae7c5` |

The exception records, rather than removes, the lack of an independent build,
signature, SBOM, provenance attestation, registry-availability, and third-node
recovery claim. It does not permit a rebuild, replacement digest, added
provider, repository, namespace, permission, mutation, or production use.

The exception ends at the first ADR 0014 stop condition or
`2026-11-30T23:59:59Z`. Artifact or source uncertainty, loss of both node
caches, trust or scope expansion, production designation, or suspected
compromise fails closed. A normally published, signed, independently verified
successor remains required before production. This documentation-only mirror
changes no manifest or live resource and does not reset the ADR 0013
observation clock.

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

## Accepted homelab observation timing

Starbase
[ADR 0013](https://github.com/X-McKay/Starbase/blob/196a8df84ab6db0b6bf8a308407fd846b518eca4/docs/adr/0013-shortened-homelab-observation-windows.md)
reduces only the current single-owner, observation-only homelab timing gates:

- Phase 6 requires one continuous hour and one complete successful
  reconciliation cycle, whichever is longer;
- each later cohort requires 30 continuous minutes and one complete successful
  reconciliation cycle, whichever is longer; and
- final full-scope acceptance requires four continuous hours.

The current clock starts with the corrected GitHub connector Pod at
`2026-09-01T16:36:50Z`. The one-hour threshold is
`2026-09-01T17:36:50Z`; the final threshold is
`2026-09-01T20:36:50Z`. A material artifact, configuration, identity,
permission, or scope change; unexplained provider mismatch; stale source;
readiness loss; restart; Flux degradation; node pressure; or checkpoint
regression resets the applicable clock after recovery.

The shortened timing is not production soak evidence. The original 24-hour
production-shaped representative load, recovery, observability, security,
artifact, and sign-off gates remain unchanged.

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

Kubani revision `9482edc28d12908b5f4b45f48086f3db1afee0ed` completed the
corrected web rollout. All Flux Kustomizations became Ready at that revision;
the core/web Pod was Ready on `strix`, the three connector/fixture Pods were
Ready on `asio`, and all changed workloads retained zero restarts. At the final
checkpoint every node remained Ready, no failed or pending Pod existed,
`asio` used 4% CPU / 39% memory, and `strix` used 5% CPU / 20% memory.

After acceptance, the transferred web and both GitHub-connector tar archives
were removed from `asio` and `strix`. The exact imported digest-addressed
images remain on both nodes through the rollback window. The plaintext active
PEM and the orphaned GitHub key are deliberately still open credential-cleanup
items: remove the plaintext PEM only after its rollback need expires, and
revoke the orphan only through an exact owner-confirmed GitHub action. Keep
only the verified active fingerprint.
