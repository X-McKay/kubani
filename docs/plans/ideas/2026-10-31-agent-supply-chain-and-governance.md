# Agent supply chain and governance: private Sigstore, multi-team registration — 2026-10-31

**Status:** idea / spec, nothing implemented. Direction chosen by Al on
2026-10-31: keyless signing on a **private Sigstore**, and the
multi-team "teams build, platform governs" model. Decisions D1–D9 below
carry defaults and are open until Al confirms them.
**Requested by:** Al
**Scope:** a private Sigstore (Fulcio, Rekor, TUF) on Kubani; keyless signing
of platform images and agent releases; release attestations; tenants,
capability catalog and tiered approval; automated registration from team
repositories into Kubani; promotion between environments; audit and
revocation.
**Builds on:** the Agent Runtime Platform stages
([agent-runtime-platform.md](../../infrastructure/configuration/agent-runtime-platform.md),
Phase A qualified 2026-10-31), the zetra-agents release flow
(X-McKay/zetra-agents README, "Releasing" and "Deploying through Kubani"),
and Kyverno Rule 1 in
`infrastructure/gitops/infrastructure/kyverno/policies/agent-sandbox-admission.yaml`.

---

## 0. TL;DR

| Layer | Default chosen | Lands in |
|---|---|---|
| Certificate authority | Fulcio (chart `sigstore/fulcio` 2.11.4, app 1.9.0), CA key in a SOPS Secret, OIDC issuers: GitHub Actions + Authentik | new `sigstore` namespace, rig0 |
| Transparency log | Rekor v1 (chart `sigstore/rekor` 1.8.8, app 1.5.5) on Trillian (chart 0.4.1) with the chart's bundled MySQL on Longhorn | `sigstore` |
| CT log | **Off** at first (`ctlog.ignoreSCT: true`); `ctlog-tiles` later (D3) | — |
| Trust root for clients | TUF repository (chart `sigstore/tuf` 0.1.33) served on the tailnet; root keys offline | `sigstore` |
| Admission | Kyverno Rule 1 switches from a public key to keyless attestors: our Fulcio root + our Rekor URL and public key, issuer + subject per tenant. No egress to public sigstore | `kyverno/policies/` |
| CI identity | Self-hosted GitHub Actions runners (ARC) on rig0 sign with their workflow OIDC token | new `arc-runners` namespace |
| Evidence | Per release: signature, SLSA provenance, SBOM, vulnerability scan, the zetra release predicate (policy bundle) | registry, as cosign attestations |
| Governance | Tenants per team and environment, a capability catalog with per-tenant allowlists, tiered CODEOWNERS approval in `apps/agents/`, CI policy checks, release→PR bot | Kubani repo + zetra-agents template |

Order (section 6): S0 key ceremony → S1 Trillian + Rekor → S2 Fulcio → S3 TUF
→ S4 sign platform images → S5 Kyverno keyless (B2) → G1 tenants + catalog
→ G2 CI checks + tiers → G3 release bot → G4 promotion → G5 audit and
recertification. One PR per stage.

---

## 1. Why private, keyless Sigstore

Decided in the 2026-10-31 discussion; recorded so the reasons survive:

- **Identity, not key custody.** With many teams, per-team cosign keys mean
  N secrets to store, rotate and revoke, and "who signed this" degrades to
  "who held the key". Keyless binds each signature to a workload identity
  (`repo/.github/workflows/release.yml@refs/tags/...`), which is what the
  admission policy actually cares about.
- **Private, not public.** Public Rekor publishes image digests, repository
  and workflow names; public Fulcio and the TUF CDN put admission on the
  internet's availability. With our own instances, Kyverno verifies offline
  against roots we pin, and nothing leaves the tailnet.
- **Transparency is the governance control.** Every signature lands in our
  Rekor; a monitor alerts on signatures from identities that should not sign
  (section 5.5). That replaces "trust the key holder" with "detect misuse".

Cost accepted: we operate a CA, a log with a database, and a TUF root. That
is the bulk of section 6.

## 2. What exists today (2026-10-31)

- Phase A of the Agent Runtime Platform is live on rig0 (Kata, tenant
  NetworkPolicies, netpol-attestor); Kyverno 1.19.2 is installed (B1) with
  webhooks scoped to `agentplatform.io/tenant`; the `agents` Gateway is up
  (AG1/AG2). B2 (the admission policies) is not enabled.
- Rule 1 is written for a **public key** with the placeholder still in place,
  and the transparency-log question is open (agent-runtime-platform.md, B2).
- No image is signed. There is no organisation cosign key.
- The Registry Controller image bundles **cosign v2.6.1** (zetra
  `platform/controller/Dockerfile`) and verifies AgentRelease signatures with
  it (spec 6.4). Anything we choose must be verifiable by cosign 2.x, which
  is why D1 defaults to Rekor v1.
- zetra-agents `scripts/release.sh` signs and attests with a key
  (`COSIGN_PRIVATE_KEY`), writes `dist/<agent>/`, and publishes a GitHub
  release; deployment into Kubani is a manual copy and three PRs.
- GitHub-hosted runners cannot reach `registry.almckay.io` (tailnet only);
  releases fall back to `just release` on rig0.

## 3. Target architecture

```
team repo (zetra-agents or a team fork of the template)
  tag <agent>/vX
    -> self-hosted runner (ARC, rig0) builds, pushes registry.almckay.io/agents/<team>/<agent>@sha256
    -> cosign sign + attest (keyless): OIDC token from GitHub Actions
         -> fulcio.almckay.io issues a 10-minute cert for the workflow identity
         -> rekor.almckay.io records signature + attestations
    -> release bot opens PR in kubani: apps/agents/<tenant>/<agent>/ (Agent + unapproved AgentRelease)
kubani CI on that PR
    -> verify signature + attestations against our Fulcio root / Rekor key
    -> recompute policySha256, check capabilities against the tenant allowlist,
       render the sandbox pod and run the Kyverno suite, check budgets
    -> CODEOWNERS for the tier must approve
merge -> Flux -> Registry Controller (cosign verify, same roots) -> approval PR -> runner smoke (T18)
admission: Kyverno Rule 1 verifies keyless signature offline (Fulcio root + Rekor pubkey pinned in the policy)
```

### 3.1 Sigstore components

| Component | Role | Exposure | Storage |
|---|---|---|---|
| Fulcio | Issues short-lived signing certs to OIDC identities | `fulcio.almckay.io` (Traefik, tailnet) + in-cluster Service | CA private key: SOPS Secret (`fulcio-ca.enc.yaml`); stateless otherwise |
| Rekor | Append-only log of signatures and attestations | `rekor.almckay.io` + in-cluster Service | Trillian tree in MySQL (Longhorn PVC, backed up) ; Rekor signer key: SOPS |
| Trillian | Merkle log backend for Rekor | in-cluster only | MySQL as above |
| TUF | Distributes the trust root (Fulcio CA, Rekor key) to cosign clients | `tuf.almckay.io`, read-only | Static repo from a Secret; root keys offline (S0) |

Fulcio needs egress to the OIDC issuers' discovery/JWKS endpoints
(`token.actions.githubusercontent.com`, `auth.almckay.io`); Rekor and
Trillian need no egress. Kyverno and the Registry Controller need **no**
egress for verification: the Fulcio root and Rekor public key are pinned in
config, not fetched.

### 3.2 Identities that may sign

| Identity | Issuer | Used for |
|---|---|---|
| `https://github.com/X-McKay/zetra-agents/.github/workflows/release.yml@refs/tags/*` | `https://token.actions.githubusercontent.com` | agent releases |
| `https://github.com/<team-org>/<repo>/.github/workflows/release.yml@refs/tags/*` | same | per-team agent repos (registered per tenant, G1) |
| `https://github.com/X-McKay/zetra/.github/workflows/platform-release.yml@refs/tags/*` | same | platform images |
| Authentik user in group `platform-signers` | `https://auth.almckay.io/application/o/sigstore/` | break-glass manual signing from rig0 |

Admission matches **issuer and subject together**; a subject from the wrong
issuer is rejected.

## 4. Governance model

### 4.1 Tenants

- One namespace per team and environment: `tenant-<team>-<env>`
  (`env` ∈ `dev`, `stg`, `prod`), matching `^tenant-[a-z0-9-]{1,50}$`.
- A tenant is created by an onboarding PR (platform team) that adds: the
  namespace with `agentplatform.io/tenant`, the four tenant NetworkPolicies,
  a ResourceQuota, a token budget ceiling, and
  `apps/agents/<tenant>/tenant.yaml` (below). This is the one step a team
  cannot do itself.

```yaml
# apps/agents/<tenant>/tenant.yaml (not applied; read by CI)
team: payments
environment: prod
owners: ["@X-McKay/payments-agents"]          # CODEOWNERS for low tier
signers:                                       # who may sign images for this tenant
  - issuer: https://token.actions.githubusercontent.com
    subject: https://github.com/X-McKay/payments-agents/.github/workflows/release.yml@refs/tags/*
allowed:                                       # catalog entries usable without escalation
  models: [llm-main, llm-fast]
  mcp: {kubernetes: [remote_read]}
  maxTokensPerDay: 2000000
promoteFrom: tenant-payments-stg               # prod accepts only digests qualified there
```

### 4.2 Capability catalog

`apps/agents/catalog.yaml` lists every model backend and MCP tool an agent
may request, each with an **effect**, a **data owner** (GitHub team) and a
**risk tier**. A tool not in the catalog cannot be requested. Data owners
are CODEOWNERS of their catalog entries, so granting "postgres
remote_read" is the database owner's decision, not the platform team's.

### 4.3 Approval tiers

| Tier | Requested capabilities | Approvers (CODEOWNERS) |
|---|---|---|
| Low | `workspace_*` only, no MCP, budget ≤ tenant default | the tenant's owners |
| Medium | any `remote_read`, on-behalf-of identity | owners + each MCP backend's data owner |
| High | catalog additions, raised budgets, any `prod` tenant first release | owners + data owners + security |

CI computes the tier from the Agent and labels the PR; CODEOWNERS enforce
it. The approval itself stays the AgentRelease `approval` block in Git
(approvedBy, approvedAt, ticket), unchanged from spec 6.2.

### 4.4 Required evidence per release

| Attestation | Tool | Required for |
|---|---|---|
| cosign signature (keyless) | cosign | all |
| zetra release predicate (`https://agentplatform.io/attestations/release/v1`) | release.sh | all |
| SLSA provenance v1 | `actions/attest-build-provenance` or `slsa-github-generator`, written to our Rekor | stg, prod |
| SPDX SBOM | syft | stg, prod |
| Vulnerability scan (no unwaived critical) | grype, waivers in the tenant dir | prod |
| Promotion: qualified in `promoteFrom` (T18 smoke passed for this digest) | runner result → attestation | prod |

Kyverno Rule 1 checks the signature (and, for prod tenants, the provenance
attestation) at admission; CI and the Registry Controller check the rest.

### 4.5 Registration flow

1. Team tags a release. The runner builds, pushes by digest, signs and
   attests keylessly, runs `zetra-agents conformance` (the local platform
   harness, separate zetra workstream), and writes `dist/`.
2. The release bot (a GitHub App scoped to `apps/agents/**` in kubani)
   opens or updates the PR with `agent.yaml` and an unapproved
   `agentrelease.yaml`.
3. Kubani CI (`agents-policy` job): cosign verify against our roots;
   recompute `policySha256` with the pinned contracts; capabilities ⊆
   tenant allowlist ∪ catalog; render the pod and run the Kyverno suite;
   quota and budget checks; required attestations present; compute the tier.
4. Merge (tier approvers). Flux applies; the controller verifies again and
   reports readiness for approval.
5. Approval PR (same tier approvers, or the same PR for Low if D9 allows).
6. The runner's smoke session (T18) result is posted back to the team's
   release and, for `stg`, recorded as the promotion attestation.

### 4.6 Visibility, revocation, recertification

- Teams have no cluster credentials. Read-only status (release readiness,
  session results, budget use, logs and traces filtered by tenant) comes
  from the controller's status and Grafana folders per tenant; a portal is
  out of scope here.
- Kill switches, each effective without the team: remove a signer from
  `tenant.yaml` (CI + a generated Kyverno attestor list), set
  `approval.approved: false`, or remove a catalog entry (the controller
  recompiles bundles; affected releases stop being ready).
- Approvals for High tier expire after 90 days; a scheduled job opens
  recertification PRs and flags capabilities unused for 30 days (from
  gateway access logs).
- Rekor monitor: a CronJob walks new entries and alerts (ntfy) on any
  certificate whose issuer/subject is not in some tenant's `signers`.

## 5. Decisions

| # | Question | Default | Why / alternative |
|---|---|---|---|
| D1 | Rekor v1 (Trillian) or Rekor v2 (`rekor-tiles`, Tessera) | **v1** | The Registry Controller bundles cosign 2.6.1 and Kyverno 1.19 verifies v1 entries; v2 needs cosign 3 and verifier support we have not tested. Revisit when the controller moves to cosign 3. |
| D2 | Trillian database | **The trillian chart's bundled MySQL** on Longhorn, nightly logical backup to the NAS | Trillian's PostgreSQL storage is newer and less used; adding a database to the existing PostgreSQL would couple the log to it. Loss of the log does not invalidate existing signatures if D3/D7 roots are kept, but loses the audit trail. |
| D3 | CT log for Fulcio certificates | **Off**, `ignoreSCT: true` | Rekor already records every signature with its certificate; a CT log adds certificate-issuance transparency. Add `ctlog-tiles` in a later stage if we want issuance monitoring. |
| D4 | How CI reaches Fulcio/Rekor/registry | **ARC self-hosted runners on rig0** (`topology.kubani.io/role=platform`) | Also fixes the existing "GitHub-hosted runners cannot reach the registry" gap. Alternative: Tailscale GitHub Action on hosted runners (an ephemeral tailnet node per job). |
| D5 | Human (break-glass) signing issuer | **Authentik**, group `platform-signers` | Authentik is the human SSO. Keycloak is the agents' IdP and stays agent-only. |
| D6 | Exposure | **Tailnet only**, `fulcio`/`rekor`/`tuf.almckay.io` through Traefik, plus in-cluster Services | Same perimeter as every other service (`.claude/rules/auth.md`); Rekor read API is unauthenticated by design, write requires a valid signature. |
| D7 | Trust root management | **TUF root keys offline** (two keys, threshold 1, kept SOPS-encrypted outside the cluster); Kyverno and the controller pin the Fulcio root and Rekor key directly instead of fetching TUF | Admission keeps working if TUF is down; TUF is only for developers' cosign clients. |
| D8 | Platform images (zetra) | **Keyless from a zetra release workflow on the same runners**; break-glass via D5 | Removes the last long-lived signing key. |
| D9 | Low-tier approval | **Same PR**: CI may set `approval.approved: true` for Low tier after the owners approve | Saves a PR for workspace-only agents; Medium and High keep the separate approval PR. |

## 6. Stages

Each stage is one PR, validated with `just validate-local`, and verified on
the cluster before the next.

| Stage | Change | Verify |
|---|---|---|
| S0 | Key ceremony (operator, off-cluster): Fulcio CA key + cert, Rekor signer key, TUF root keys. SOPS-encrypt the online keys; store the TUF root keys offline. **No key material in chat or plaintext in the repo** | `sops -d` round-trip; fingerprints recorded in this plan |
| S1 | `sigstore` namespace (default-deny + explicit pairs), Trillian (log server, signer, MySQL) and Rekor; HelmReleases pinned by chart version + digest; capacity ledger lines | `rekor-cli loginfo --rekor_server https://rekor.almckay.io`; upload and verify a test entry; MySQL backup job runs |
| S2 | Fulcio with the CA Secret, OIDC issuers GitHub Actions + Authentik (Authentik OAuth app `sigstore` via the `authentik-app` skill); `fulcio.almckay.io` | `cosign sign --fulcio-url ... --rekor-url ...` of a test image from rig0 as a `platform-signers` user; `cosign verify --certificate-identity ... --certificate-oidc-issuer ...` with our roots |
| S3 | TUF repository; `tuf.almckay.io`; developer docs for `cosign initialize --mirror https://tuf.almckay.io --root <root.json>` | `cosign initialize` + `cosign verify` with no explicit root flags |
| S4 | ARC runner scale set (D4); zetra `platform-release.yml` signs the five platform images keylessly | `cosign verify` of each platform digest by workflow identity |
| S5 | Rule 1 to keyless attestors (Fulcio root, Rekor URL + key, per-tenant issuer/subject list generated from `tenant.yaml`); controller config gets the same roots; then B2 as planned | `kyverno test` with keyless fixtures; T9b on the cluster (unsigned, wrong identity, wrong issuer all rejected; correct admitted) |
| G1 | `catalog.yaml`, `tenant.yaml` schema, tenant onboarding recipe (`just tenant-new <team> <env>`); migrate `tenant-test` | CI schema check; onboarding a `tenant-demo-dev` end to end |
| G2 | Kubani `agents-policy` CI job + CODEOWNERS tiers (4.3) | PRs with Low/Medium/High agents get the right label and required reviewers; an out-of-allowlist capability fails CI |
| G3 | zetra-agents: keyless release.sh, SLSA provenance + SBOM + scan attestations, the release bot (GitHub App) | tag → PR in kubani with green CI, no human copying |
| G4 | Environment promotion (`promoteFrom`, promotion attestation from the runner's T18 result) | a prod PR for an unqualified digest fails CI |
| G5 | Rekor monitor CronJob, recertification job, per-tenant Grafana folders | a signature from an unregistered identity raises an ntfy alert |

Prerequisites outside this plan: Phase B AP3–AP5 (APS, Registry Controller,
Session Runner) for G3–G5 to be meaningful; the local "platform in a box"
(`zetra-agents conformance`) in zetra for step 1 of 4.5.

## 7. Risks and operations

- **Fulcio CA key compromise** lets an attacker mint certificates for any
  identity. Mitigations: SOPS at rest, Fulcio runs alone in its namespace
  with no other workloads able to read the Secret, Rekor monitoring catches
  use; rotation = new CA, both roots trusted during overlap, old removed.
- **Rekor/MySQL loss** loses the audit trail, not admission (D7 pins keys;
  existing bundles carry their inclusion promises). Backups in S1.
- **Single node.** Everything lands on rig0 with the rest of the platform;
  an outage of rig0 already stops sandboxes, so signing being down at the
  same time adds no new failure mode for admission. Releases wait.
- **Availability at admission time:** none of the Sigstore services are on
  the admission path (D7). The runner, controller and Kyverno verify
  offline.
- **Capacity:** add ledger lines in S1/S2/S4 before merge (Trillian log
  server + signer, MySQL, Rekor, Fulcio, TUF, ARC controller + runners).

## 8. Open questions for Al

1. Confirm D1–D9 or change any default.
2. Are other teams' agents expected to live in zetra-agents (one repo,
   directory per team) or in their own repositories? 4.1 supports both; the
   release bot and CODEOWNERS differ.
3. Who holds the TUF root keys and the S0 ceremony: Al alone, or Al plus a
   second holder (threshold 2)?
