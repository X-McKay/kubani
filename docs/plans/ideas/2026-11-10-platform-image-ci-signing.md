# Platform image build, signing and admission in CI — 2026-11-10

**Status:** idea, decisions recorded. Phase 0 is merged in zetra. The six
decisions in section 1 were made on 2026-11-11. Nothing in Phases 1 to 4 is
built or tested, and Phase 1 now waits only on the operator's own steps, listed
below.
**Scope:** the eight image repositories under `registry.almckay.io/platform/`,
a release workflow in zetra that would build and sign them on a merge to
`main`, a second runner scale set and an admission policy in Kubani, and a
helper that moves the pins.
**Builds on:** the private Sigstore and the agent image signature policy
(`infrastructure/gitops/infrastructure/sigstore/README.md`,
`infrastructure/gitops/infrastructure/kyverno/policies/agent-image-signature.yaml`),
the agent repository golden path
(`docs/plans/ideas/2026-11-09-agent-repo-golden-path.md`), and the open plan in
kubani PR #246 (agent supply chain and governance).

The platform images (the Agent Policy Service, the Session Runner, the Registry
Controller and five others) are still built by hand on the operator's
workstation and pushed to the registry, and no admission rule checks who built
any of them. This plan moves them onto the route agent images already take:
built by continuous integration (CI) on a merge to zetra `main`, signed
without a long-lived key, and verified when a pod is admitted, with the limits
on admission that decision (d) sets. As of 2026-11-11 only the first step
exists: CI in zetra builds every platform image and checks the base-image pins,
and it pushes and signs nothing. The most recent deployed images are the Agent
Policy Service and the Session Runner built by hand from zetra `18aee61` and
pinned by Kubani PR #419 (`1faeda02`), read on 2026-11-11, which is one more
image roll that rests on a workstation build.

**What the plan now waits on.** Nothing waits on a further decision. Phase 1
waits on three steps that only the operator can take, because each is a
setting on GitHub or a credential:

1. Install the kubani-arc GitHub App on `X-McKay/zetra` (decision a). Only the
   repository owner can do this.
2. Protect zetra `main`, and set the two repository settings the plan already
   lists: default workflow permissions read-only, and approval required for
   workflows from fork pull requests (decision c). Protection means that
   changes reach `main` only through a pull request with required checks, and
   that force pushes and deletion of `main` are blocked.
3. Mint the dedicated registry account with
   `infrastructure/scripts/ops/add_registry_user.sh` and provide it to the
   runner (decision b). How the runner receives it is in Phase 1.

Nothing else in Phase 1 needs the operator. Phases 2 to 4 follow from Phase 1
and from measurements, not from decisions.

**How this relates to the wider redesign.** The redesign recorded in
`docs/plans/ideas/2026-11-11-agent-delivery-redesign.md` (written on another
branch; not read from this one) decided on 2026-11-11 that releases are
produced by CI/CD on a merge to `main`, on a self-hosted runner scale set for
each trusted repository, with the registry credential held on the runner and
not in the repository. Platform images follow that rule for building. They
follow a different rule for deploying: a platform image reaches the cluster
only through a reviewed change of a pin in this repository, because the
platform is infrastructure. Building on merge deploys nothing.

**How to read the evidence.** This document restates a planning report written
before zetra PR #79, against zetra `677a2de` and Kubani `2daf551c`. The report
is not in the repository; everything needed from it is here. Each claim is
marked in words: *read* means read from code, manifests or documents;
*observed live* means seen on the cluster or through the GitHub API by the
report's author; *inferred* means reasoned and not tested; *measured* means a
command was run and its result is quoted; *decided* means chosen on the date
given, with the reason, and is not a claim about the repository. On 2026-11-10,
for this document, zetra's repository settings were read through the GitHub API
and zetra PR #79 and its check results were read. On 2026-11-11 the pins and
line references below were read again at Kubani `bf8c063b` (current `main`), and
every pin in the table matched the manifests by `grep` over
`infrastructure/gitops/` and `tests/`. Nothing on the cluster was observed again
for this document. The report itself changed and tested nothing.

**Terms.** *zetra* is the repository `X-McKay/zetra`, which holds the source of
the platform images; *zetra-agents* is the repository of agents. A *platform
image* is one of the eight repositories in section 2. A *pin* is an image
reference in a Kubani manifest that names a digest. A *runner scale set* is a
group of self-hosted GitHub Actions runners managed in the cluster by the
Actions Runner Controller; the *kubani-arc GitHub App* is the credential that
lets the controller register runners with a repository; the *job guard* is a
script on the runner that refuses any job except the ones it names. The *build
sidecar* is the Docker daemon container that runs beside each runner.
*Keyless signing* means `cosign` obtains a short-lived certificate from the
cluster's private certificate authority (Fulcio) in exchange for the GitHub
Actions identity token of the running workflow, and records the signature in a
transparency log (Rekor); the *certificate subject* is the workflow path and
Git ref written into that certificate. An *attestation* is a signed statement
about an image, here build provenance, a software bill of materials and a
vulnerability scan. *Kyverno* is the admission controller that verifies agent
image signatures today. A policy in *Audit* reports a violation and admits the
pod; in *Enforce* it denies the pod. A webhook with failure policy *Ignore*
admits pods when Kyverno cannot answer; with *Fail* it denies them, which this
document calls *fail closed*. The *allowlist* is a list of exact image digests
that the new policy would admit without a signature.

---

## 1. Decisions, made 2026-11-11

The planning report posed six questions to the operator. The operator
delegated them, and they were decided on 2026-11-11 as part of the wider
redesign described near the top of this document. This section records, for
each, the question, the decision, the reasons, and what it changes in the
phases. The options that were not taken are kept briefly so that a decision is
not reopened by accident. Reasons marked *decided* are reasoning from that
date, not facts read in the repository; the facts they rest on carry their own
marks.

| | Question | Report's recommendation | Decision | Changes |
| --- | --- | --- | --- | --- |
| a | Add a second runner scale set and install the kubani-arc App on zetra? | Yes | Yes | Phase 1; operator step 1 |
| b | Shared `automation` registry account, or a dedicated one? | Dedicated | Dedicated, held on the runner, not in Actions secrets | Phase 1; operator step 3 |
| c | Tag ruleset on `platform/**` and branch protection on zetra `main`? | Tag ruleset yes; none given for branch protection | Protect `main`; release on a merge to `main`; no tags, no tag ruleset | Phases 1, 2, 4; operator step 2 |
| d | May `agent-platform` pod admission fail closed on Kyverno? | Implied yes; posed as a question | No. Enforce while Kyverno is available, admit when it cannot answer | Phase 3 |
| e | Are the `vllm` and `mcp` capture sidecars in the enforcement scope? | None | Out of scope for admission | Phase 3 |
| f | Is `conformance-capture` the `platform/capture` source built for amd64? | None; a question of fact | Treated as not confirmed | Phase 3 allowlist; first CI build qualified as new |

Costs and risks below come from the report unless a sentence says "inferred
here", which marks reasoning added while writing this document.

### (a) A second runner scale set and the kubani-arc App on zetra

**Question.** Should Kubani run a second runner scale set that serves only
zetra, and should the kubani-arc GitHub App be installed on `X-McKay/zetra`?

**Decision (decided 2026-11-11).** Yes to both. Kubani gains a scale set,
`kubani-zetra`, and the App is installed on zetra.

**Reasons.** A personal GitHub account has no runner groups, so a scale set
bound to one repository serves that repository only (decided 2026-11-11). The
wider redesign therefore gives every trusted repository its own generated scale
set, and zetra is one more. Installing the App on zetra is a step only the
repository owner can take; it is operator step 1.

**Why it arose.** The one scale set, `kubani-zetra-agents`, is bound to
zetra-agents (read 2026-11-11, `apps/arc-runners/scale-set-zetra-agents.yaml:46`),
the App is installed only there (observed live), and its job guard admits only
tag pushes of zetra-agents' `release.yml` (read,
`apps/arc-runners/job-guard.yaml`). A zetra job cannot use it.

**Costs that remain.** One more build sidecar with a 12Gi memory limit whenever
a platform release runs. The existing scale set allows two runners (read
2026-11-11, line 50), so three build sidecars could run at once (inferred
here); the report points at `just capacity` to check this and gives no measured
figure. The build sidecar has been killed for exceeding 12Gi four times during
`apt` retries, with the cause unproven (read,
`docs/infrastructure/configuration/agent-runtime-platform-phase-b-qualification.md:1419-1429`).
That is why decision (c) limits platform releases to one job at a time. zetra
is public (observed live, and read again on 2026-11-10), so the job guard is
what keeps other zetra workflows off the runner.

**Option not taken.** Decline: platform images stay hand-built, or a design
that uses a GitHub-hosted runner is evaluated. The release workflow needs the
registry, Fulcio and Rekor, which a hosted runner cannot reach, and the report
evaluated no way to share the existing scale set.

**Changes.** Phase 1 delivers the scale set and its guard. Operator step 1.

### (b) Which registry account zetra's release workflow uses

**Question.** Does zetra push with the shared `automation` account or with a
dedicated account for platform images?

**Decision (decided 2026-11-11).** A dedicated account, held on the runner and
not in zetra's Actions secrets.

**Reasons.** It can be revoked on its own, and the wider redesign moves
registry credentials off repositories onto the runners that use them (decided
2026-11-11). Keeping the credential out of the repository's Actions secrets
also means a workflow change cannot print it from the secret store; it is still
readable by a job that runs on the runner, which is why the job guard and the
branch protection in decision (c) matter (inferred here).

**Why it arose.** The registry sits behind Traefik basic authentication with
three accounts, `human`, `automation` and `kyverno` (read,
`docs/infrastructure/configuration/registry.md`). It has no per-repository
authorisation, so any account can push to `platform/*` (inferred from that
document, not tested). Neither option therefore limits where the account can
push; the signature is the only thing that separates a CI-built image from a
hand push.

**Option not taken.** The shared `automation` account: no new account, but
revoking or rotating it touches every repository that holds it (inferred here).

**Changes.** Phase 1 describes how the runner receives the credential. Minting
the account is operator step 3, run by the operator with
`infrastructure/scripts/ops/add_registry_user.sh`; no one else mints it and
this plan holds no value of it.

### (c) Protect zetra `main` and release on a merge to `main`

**Question.** Will zetra get a ruleset that restricts who can create
`platform/**` tags, and will `main` be protected?

**Decision (decided 2026-11-11).** Protect zetra `main`, and release platform
images on a merge to `main`, not on a tag. This replaces the plan's tag
trigger. There are no `platform/**` tags and so no tag ruleset. Protection
means that changes reach `main` only through a pull request with required
checks, and that force pushes and deletion are blocked.

**Reasons.**

- The wider redesign decided that releases are produced by CI/CD on a merge to
  `main`, and that no person pushes a tag (decided 2026-11-11).
- The report noted that a branch ref in the certificate subject means something
  only when the branch is protected. The decision is to protect it.
- The weakness the tag ruleset addressed no longer exists. zetra has no
  rulesets and no tags, and `main` is unprotected (observed live through the
  GitHub API; read again on 2026-11-10 with the same result). In the tag design
  a tag could point at a commit that is not on `main`, whose copy of the
  workflow had dropped the check that the commit is on `main`, and the runner
  would build and sign it under a valid platform-release identity (inferred by
  the report, not tested). A push to `main` always runs the workflow file that
  is on `main`, so that case cannot arise. Branch protection replaces the
  ruleset. What remains is that the workflow file on `main` is itself changed
  only through a reviewed pull request, so the control is as strong as the
  protection is. Two points of that are not settled by the decision: whether
  administrators are bound by the protection, and whether a second approval is
  required. A sole owner cannot approve their own pull request (inferred here),
  so "reviewed" means a pull request that passed its required checks unless a
  second approver exists. Neither point has been tested.

**What it changes.**

- *Certificate subject.* It becomes
  `https://github.com/X-McKay/zetra/.github/workflows/platform-release.yml@refs/heads/main`
  with the GitHub Actions issuer. The image name is no longer part of the
  subject, so the subject cannot hold each repository to its own signer, which
  the tag form did. Every platform image is signed under one subject, and what
  keeps one image from being signed in place of another is the review of the
  workflow, not Fulcio (inferred here). Phase 2 and Phase 3 are updated to
  match.
- *Job guard.* It admits only repository `X-McKay/zetra`, the push event, the
  ref `refs/heads/main`, and a workflow reference equal to
  `X-McKay/zetra/.github/workflows/platform-release.yml@refs/heads/main`.
- *Image tag.* The tag is the first seven characters of the commit hash of the
  merge commit on `main`. Read 2026-11-11 in the manifests: the Session Runner
  and the Agent Policy Service are pinned as `:18aee61@sha256:…`, the Registry
  Controller as `:1c8e481@…`, and the retained governed-worker pins as
  `:9c2c092@…` and `:b2f4d57@…`, all seven characters. Two older pins carry an
  architecture suffix (`4a089b5-amd64` for budget-backend and `ef1a16f-arm64`
  for capture) and two have no tag. The next CI build of those drops the suffix
  (inferred here). Because the merged `platform/images.json` has no tag-suffix
  field, this settles the question the report left to Phase 1.
- *What is built.* A release runs only for images whose build inputs changed in
  the merge, one at a time. The build inputs of an image are the Dockerfile and
  the build context named in `platform/images.json`. The one-at-a-time rule
  exists because of the build sidecar kills described under decision (a).
- *What is not deployed.* Deploying a platform image stays a reviewed change of
  a pin in this repository. Building on merge deploys nothing.

**Options not taken.** The tag trigger with a ruleset that lets only
administrators create `platform/**` tags: it needs a person to push a tag for
every release, which the redesign removes. Neither protection nor ruleset:
signing would work, and admission would show only that a workflow named
`platform-release.yml` signed the image, not that the source was on a protected
branch.

**Changes.** Phases 1, 2 and 4; operator step 2. The two repository settings
the report listed (default workflow permissions read-only, approval required
for workflows from fork pull requests) stay, and branch protection is added to
the operator's steps.

### (d) `agent-platform` admission must not fail closed on Kyverno

**Question.** Is it acceptable that pods in the `agent-platform` namespace
cannot be created or restarted while Kyverno is unavailable?

**Decision (decided 2026-11-11).** No. What is wanted instead, in order of
preference:

1. The new policy in Enforce while Kyverno is available, with a failure policy
   of Ignore, so that pods are admitted when Kyverno cannot answer.
2. Violations reported for pods already running, by background scanning, once
   Kyverno is back. *Background scanning* is Kyverno's periodic evaluation of
   resources already in the cluster; it reports and denies nothing.
3. A test in Git that refuses a pin that is neither CI-built nor allowlisted
   before it merges. This control does not depend on admission at all.

**Reasons (decided 2026-11-11, resting on facts marked where they are read).**

- Kyverno's replicas run on the platform nodes and only one such node exists,
  which is also the operator's workstation (read and observed live by the
  report: `infrastructure/kyverno/helmrelease.yaml` selects
  `topology.kubani.io/role: platform` at line 38 and sets two replicas at
  line 49).
- Kyverno reaches the registry through the ingress, so an ingress outage would
  also block platform pods from being recreated (inferred by the report).
- The cluster has a record of availability incidents.
- The images in question are the operator's own code. The realistic failure is a
  hand-built or stale image, not hostile code. Hostile code is the case for
  agent images, and the agent policy stays fail closed.

**Why it arose.** Kyverno's webhooks select only namespaces that carry the
tenant label (read 2026-11-11, `infrastructure/kyverno/helmrelease.yaml:43-46`),
and only `tenant-test` carries it (observed live). No pod in `agent-platform`,
`mcp` or `vllm` reaches Kyverno today. Verifying platform images means bringing
`agent-platform` into that selection. The comment at the top of that file says
every policy there fails closed and that the selector is what confines a
Kyverno outage to tenant namespaces (read 2026-11-11). Whether adding a second
namespace to the selector, with a policy that fails open, leaves that namespace
behind the existing fail-closed webhook is unknown U2 in section 5. Preference 1
depends on its answer, and Phase 3 measures it first.

**Option not taken.** Enforce with failure policy Fail, so that pod creation in
`agent-platform` is denied after a 10 second timeout while Kyverno is down. The
netpol-attestor is a DaemonSet with host networking, and its pods could not be
recreated on any node in that state (inferred).

**What each outcome protects against.** Stated in the table after step 3d of
Phase 3, once U2 is measured.

**Changes.** Phase 3 is rewritten around U2.

### (e) The `vllm` and `mcp` capture sidecars are out of scope for admission

**Question.** Should the policy also be enforced in the `vllm` and `mcp`
namespaces, where the two capture sidecar images run?

**Decision (decided 2026-11-11).** No. CI still builds and signs both images,
and the Phase 3 test in Git still covers their pins.

**Reasons.** The availability argument of decision (d), stronger for the
model-serving namespace, where a pod that cannot be recreated is a model outage
(decided 2026-11-11). Read 2026-11-11: `platform/capture` runs as a sidecar in
the vLLM deployment (`apps/vllm/deployment.yaml:181`) and
`platform/conformance-capture` as a sidecar in the Kubernetes MCP server
(`apps/mcp/kubernetes-mcp.yaml:83`).

**What it leaves open.** Nothing checks those two images at admission, so a
hand-pushed image pinned by digest would run there. The Git test refuses such a
pin before it merges, but does not see a change made directly on the cluster.

**Option not taken.** Label both namespaces into Kyverno's selection. Kyverno
would then be on the admission path of every pod there.

**Changes.** Phase 3 scope: `agent-platform` only.

### (f) `conformance-capture` is treated as not confirmed

**Question.** Was the image pinned as `platform/conformance-capture` built from
`platform/capture/Dockerfile` for linux/amd64?

**Decision (decided 2026-11-11).** Treated as not confirmed.

**Reasons.** The report inferred the answer from a comment in the Kubani
manifest. zetra PR #79 added that the manifest describes the sidecar as "zetra
platform/capture" and that the published image's layers match the Dockerfile,
and recorded that no build record names the commit or the command. Nobody can
show how the deployed image was built, and the decision does not need the fact
(decided 2026-11-11).

**What it changes.** The pinned digest `be4e8e6a…` stays on the allowlist until
a CI build replaces it. The first CI build is qualified as a new image and not
as a rebuild (inferred here). The entry for this repository in
`platform/images.json` already assumes the answer is yes. Whether that entry
should stay is a zetra question and is left open here.

**Option not taken.** Treating the answer as yes: the pinned digest would leave
the allowlist when a CI build is pinned, and the first build would be a rebuild.

---

## 2. What exists today

### 2.1 The images

Seven Dockerfiles in zetra produce eight repositories under
`registry.almckay.io/platform/`. The pins are read from
`infrastructure/gitops/` and `tests/` at Kubani `bf8c063b` (read 2026-11-11).
The rows for the Agent Policy Service and the Session Runner changed from the
earlier version of this document, which gave `4a089b5` and `541e2ef`: Kubani PR
#419 (`1faeda02`) pinned both to zetra `18aee61`. The other rows are as in the
report, which also observed them on the running pods. Whether the pods run the
`18aee61` pins was not observed again.

| Repository | Source in zetra | Platform | Pin (tag and digest prefix) | Where it is pinned |
| --- | --- | --- | --- | --- |
| `agent-policy-service` | `platform/aps/Dockerfile` | amd64 | `18aee61@sha256:cddd4c51…` | `apps/agent-platform/workloads/agent-policy-service.yaml` |
| `budget-backend` | `platform/budget-backend/Dockerfile` | amd64 | `4a089b5-amd64@sha256:1e3fb618…` | `…/workloads/budget-backend.yaml` |
| `registry-controller` | `platform/controller/Dockerfile`, context `platform` | amd64 | `1c8e481@sha256:dd8786ca…` | `…/workloads/registry-controller.yaml` |
| `session-runner` | `platform/runner/Dockerfile` | amd64 | `18aee61@sha256:a893f302…` | `session-runner-tenant-test.yaml`, `cleanup-reconciler.yaml`, seven `conformance-*-job.yaml`, and `tests/test_budget_conformance_wiring.py` |
| `session-runner`, retained | same | amd64 | `9c2c092@sha256:d6a785a6…` and `b2f4d57@sha256:4a443f97…` | `…/workloads/governed-workers/` (`sessions-a`, `cleanup-a`, `sessions-b`, `cleanup-b`) and `tests/test_worker_ab_staging.py`; never rebuilt |
| `egress-guard` | `platform/egress-guard/Dockerfile` | amd64 | `@sha256:2a6f650e…`, no tag | an exact-digest rule in `infrastructure/kyverno/policies/agent-sandbox-admission.yaml`, an environment variable in `registry-controller.yaml`, and about 20 Kyverno test fixtures |
| `netpol-attestor` | `platform/netpol-attestor/Dockerfile` | amd64 | `@sha256:3b6a6dc6…`, no tag | `apps/agent-platform/netpol-attestor.yaml` (DaemonSet, host networking) |
| `capture` | `platform/capture/Dockerfile` | arm64 | `ef1a16f-arm64@sha256:69c98473…` | `apps/vllm/deployment.yaml` |
| `conformance-capture` | `platform/capture/Dockerfile`, assumed, not confirmed (decision f) | amd64 | `5077ef0@sha256:be4e8e6a…` | `apps/mcp/kubernetes-mcp.yaml` |

Every one of these was built by hand on rig0 from a zetra checkout with
`docker build --pull --no-cache` and pushed (read, the kubani PR #415 body and
the "Built from" comments in the manifests). The documents say the images were
pushed unsigned
(`docs/infrastructure/configuration/agent-runtime-platform-handoff.md:34-36`).
Whether any of them has a signature in the registry was not verified; it could
not be determined without registry access.

### 2.2 How agent images are signed and verified

The plan copies this route, so it is summarised here. All of it is read from
code and manifests unless marked.

- **Signer.** `.github/actions/agent-release/` in zetra is a composite action,
  which runs inside the calling repository's workflow. Fulcio therefore
  certifies the caller's workflow path and tag, for example
  `https://github.com/<repo>/.github/workflows/release.yml@refs/tags/<agent>/v<version>`.
- **Release steps.** Build, push, generate a bill of materials, scan, sign,
  attach five attestations, then verify what was just signed. The tools come
  from mirror images pinned by digest.
- **Trust root.** Signers hold no keys. The roots of the private Fulcio, Rekor
  and certificate transparency log are not served by an update framework; they
  are vendored in zetra and in the ConfigMap `kyverno/private-sigstore`. Fulcio
  certifies any GitHub workflow that reaches it, so trust is decided at
  verification, by matching the certificate subject.
- **Policy.** `agent-image-signature.yaml` is in Enforce with failure policy
  Fail (read, and observed live). It matches pods in namespaces that carry the
  `agentplatform.io/tenant` label and images under
  `registry.almckay.io/agents/*`. The expected subject comes per namespace from
  the ConfigMap `kyverno/tenant-signers`.
- **Why Audit came first.** An error inside a rule follows the policy's failure
  policy, not the rule's action, so that policy ran in Audit with Ignore until
  it had verified a real release, and both settings were then changed together.
- **Exceptions.** Kyverno's PolicyException feature is switched off on the
  admission controller (observed live), so an exemption has to be written into
  the policy.

---

## 3. Phases

Phases 0 to 2 are additive and change nothing that already runs. Phase 3 can
deny a pod, and only in outcome A of step 3c; its step 3b can refuse a merge.

### Phase 0: explicit inputs and a build check — done

**Delivered** by zetra PR #79, merged as `bad3e3da` on 2026-11-10:

- `platform/images.json` lists the eight repositories with Dockerfile, build
  context, target platform and build arguments.
- Every `FROM` in the seven platform Dockerfiles names a tag and the digest of
  a multi-platform index. No tag changed.
- `.github/workflows/platform.yml` has an `images` job that builds each entry
  with `docker buildx build --pull --no-cache` on a GitHub-hosted runner, with
  read-only permissions and no secret. It pushes nothing and signs nothing.
- `platform/contracts/tests/test_images.py` fails when a platform Dockerfile
  has no entry, when a `FROM` lacks a tag or a digest, or when a build argument
  in `images.json` is not declared by its Dockerfile or differs from the
  Dockerfile's default.

**Depended on** no decision.

**Verified by** (read from the pull request): all eight entries built on rig0
with the job's own commands; the eight `images` jobs passed on GitHub; each
test fails under a matching mutation.

**Known holes recorded on that pull request, none of them tested or closed:**

- An image named by `COPY --from=` or by `RUN --mount=...,from=` is not
  checked for a pin; only `FROM` lines are.
- A digest is not checked to belong to its tag.
- An `ARG` that is declared only before the first `FROM`, declared twice with
  different defaults, or that appears inside a `RUN` heredoc counts as
  declared.
- The agent Dockerfile template under `platform/agent-tools` is not covered by
  these tests. Read at zetra `18aee61` for this document: its two Python stages
  are pinned by digest and its `uv` stage is pinned by tag only.
- Builds are not bit-for-bit reproducible, because netpol-attestor's
  `apt-get install` is unpinned (inferred; no comparison of two builds is
  recorded).

**Difference from the report's proposal.** The report wanted `images.json` to
carry a tag suffix for each repository (today's tags end in nothing, `-amd64`
or `-arm64`, and two repositories have no tag). The merged file has no such
field. Decision (c) settles it: the tag is the seven-character commit hash and
nothing else, so no field is needed.

### Phase 1: a runner for zetra and a release workflow

**Delivers.**

- In Kubani: `apps/arc-runners/scale-set-zetra.yaml`, a scale set named
  `kubani-zetra` with at most one runner and the same sandbox and build sidecar
  as the existing one, plus its own job guard. The guard admits only repository
  `X-McKay/zetra`, the push event, the ref `refs/heads/main`, and a workflow
  reference equal to
  `X-McKay/zetra/.github/workflows/platform-release.yml@refs/heads/main`. The
  README and the capacity ledger are updated.
- In Kubani: the registry credential on the runner, as described below.
- In zetra: `.github/workflows/platform-release.yml` and a composite action
  `.github/actions/platform-release/` that reuses the tool-install step and the
  vendored trust roots of the agent release action. The workflow starts on a
  push to `main` that changes the build inputs of at least one image in
  `platform/images.json` (its Dockerfile or build context). It runs only on the
  scale set, naming it in `runs-on: kubani-zetra` in the workflow itself, so
  that no repository variable has to be set (decided 2026-11-11; the agent
  workflow uses a variable, which would add an operator step here). It has
  permission to request an identity token, and releases the changed images one
  at a time. For each it refuses to continue unless the image is in
  `images.json`, the commit being built is an ancestor of `origin/main`, and
  the checkout is clean. It builds one image, pushes it as
  `platform/<image>:<first seven characters of the commit hash>`, and writes the
  full reference with its digest to the job summary.

**One at a time.** The scale set allows one runner, and the workflow runs its
images in a matrix with one job at a time. A workflow `concurrency` group is
not used for this: GitHub keeps only one waiting run per group and cancels an
older waiting one, which could drop a release when two merges land close
together (inferred here from GitHub's documented behaviour; not tested). With
the queue at the runner, a waiting job is not dropped. The limit exists
because the build sidecar has been killed for exceeding its memory limit during
retries (decision a).

**How the runner receives the registry credential (decided 2026-11-11; not yet
tested).** The existing scale set has no registry credential: its runner and
dind containers read `scale-set-zetra-agents.yaml` and mount only the job guard
and scratch volumes (read 2026-11-11). The expected shape for `kubani-zetra` is
a SOPS-encrypted Secret in the `arc-runners` namespace, listed in
`apps/arc-runners/kustomization.yaml` beside `github-app.enc.yaml`, holding the
dedicated account's name and password. It is mounted read-only as files into
the runner container of the `kubani-zetra` pod template only, for example at
`/home/runner/registry-credential`, and not set as environment variables, which
would appear in the pod specification. The composite action reads the two files
and runs `docker login --password-stdin` against the dind daemon, and logs out
at the end of the job. The Secret is created by the operator, encrypted under
the rules in `.claude/rules/secrets.md`; nothing in this plan carries a value.
Two things are not settled and are for the first run: whether the runner
container can read the mounted files under its security context, and whether
`buildx` push inside the nested daemon finds the login. Ephemeral runners
(one job per pod) mean the credential exists only for the life of a job.

**Why a merge to `main` and not a tag or a dispatch.** The report chose a tag
for four reasons: the image name lands in the certificate subject; it matches
the tag-push shape of the existing guard and of PR #246; one tag is one run;
and a dispatched run would carry a branch ref, which means something only with
branch protection. Decision (c) replaces it: the branch is protected, and a
push to `main` is one run per merge. The first reason is lost, which Phase 2
records. The second still describes PR #246 and not this plan; see "Fit with
kubani PR #246".

**Depends on** the operator's three steps listed near the top: the App on
zetra; branch protection and the two repository settings; and the dedicated
registry account provided to the runner. No further decision is needed.

**Verified by** first showing that the guard refuses a job that is not a push to
`main` running the release workflow, as the scale set's README does for the
existing scale set, and then merging a change to `budget-backend`, because it
is the smallest image and has no dependencies. The run should print a digest and
the image should pull. This is the plan; nothing has been run.

**What could go wrong.** The guard rejects the job, which fails at its start.
The build sidecar runs out of memory, which shows as Kata out-of-memory events;
netpol-attestor is the image most exposed because it is the only one that runs
`apt-get`. A platform build overlaps agent releases and the node runs short. A
merge changes an image that nobody meant to release, because the detection of
build inputs is wrong; the registry then holds an extra image that nothing pins.

**Rollback.** Remove the workflow file from `main` through a pull request, and
remove the scale set. Images already pushed stay and nothing consumes them
until a pin changes.

### Phase 2: signing and provenance

**Delivers.** For each image the workflow signs with `cosign`, then attaches
three attestations (SLSA build provenance version 1, an SPDX bill of materials
and a vulnerability scan), each under a fresh identity token, and then verifies
its own output, as the agent release script does. The agent-only evaluation and
release attestations are left out. The certificate subject is
`https://github.com/X-McKay/zetra/.github/workflows/platform-release.yml@refs/heads/main`
with the GitHub Actions issuer (decided 2026-11-11, decision c). It is the same
for every image, so a function beside the agent one in
`platform/contracts/agent_platform/signing.py` returns one pattern, and no
longer takes an image name as the report's `platform_subject_regexp_for(image)`
did. The agent pattern cannot match these subjects (read). The report judges the
existing attestation builders in `platform/agent-tools` reusable; that is
inferred, not tried.

**What the shared subject costs.** Verification can no longer say that an image
was signed by the release of that image; it says that the platform release
workflow on `main` signed it. A change to the workflow that pushed and signed
some other image into a platform repository would still verify (inferred here).
The control is the review of changes to that workflow file.

**Depends on** Phase 1, and through it on the operator's steps. It may
ship in the same pull request as the workflow or in the next one. One smaller
choice is left open on purpose: the threshold at which the vulnerability scan
fails the job, to be set after the first measured run.

**Verified by** running `cosign verify` and `cosign verify-attestation` from
rig0 against the exact identity. The negative test is the same command with the
zetra-agents identity, which must fail.

**What could go wrong.** Fulcio or Rekor is unreachable from the runner, or the
scan gate fails a first build. Either fails the job.

**Rollback.** None needed. Signatures are additive and can stay.

### Phase 3: measure, a control in Git, and admission

**Scope (decisions d, e, f; decided 2026-11-11).** Admission covers
`agent-platform` only. It never fails closed on Kyverno. The `vllm` and `mcp`
namespaces are out of scope for admission, and `conformance-capture` is entered
on the allowlist as an image whose origin is unknown.

**Depends on** nothing from the operator. Steps 3a and 3b consume nothing from
Phases 1 and 2. Steps 3c and 3d need Phase 2, to have a CI-signed image to test
with. Nothing in Phase 3 depends on Phase 4. The report does not state these
dependencies; they are read off what each step consumes.

**3a. Measure first, with U2 first.** Section 5 lists four Kyverno behaviours
that are unmeasured (U1 to U4). This step is where they are measured, with the
Kyverno 1.19.2 command-line tool and server-side dry runs, in a scratch
namespace and before any real namespace is labelled. U2 comes first because
decision (d) depends on it.

- *U2: does a policy with failure policy Ignore leave its namespace behind a
  fail-closed webhook?* Kyverno applies one namespace selector to its resource
  webhooks (read 2026-11-11, `infrastructure/kyverno/helmrelease.yaml:3-8` and
  `43-46`), and the existing agent policies fail closed on pods. A pod in a
  newly selected namespace may therefore go to a fail-closed entry whatever the
  new policy says. That is the reason to expect that U2 holds, but it is
  inferred and untested. The measurement reads the webhook configuration that
  Kyverno generates when a throwaway policy with failure policy Ignore matches
  pods in a scratch namespace that is in the selector, and shows which webhook
  entry receives that namespace's pod requests and with what failure policy.
  If the configuration leaves doubt, the remaining test is to make the admission
  controller unavailable for a short window and create a pod in the scratch
  namespace. That test also blocks pod creation in tenant namespaces while it
  runs, so it is done only after the operator has agreed to the window (this
  method is inferred here and has not been tried).
- *U1, U3, U4.* Whether `skipImageReferences` matches `tag@digest` references
  (U1), whether the `ImageValidatingPolicy` kind obeys the global namespace
  selector (U3), and whether `imageReferences` patterns match references that
  carry both a tag and a digest (U4).

After decisions (d) and (e) narrow the scope, U2 matters in every outcome,
because it chooses between the two outcomes of 3c. U1, U3 and U4 matter only if
the admission policy is built, which is outcome A below. In outcome B they do
not decide anything for admission; the scheduled job has to match `tag@digest`
references and exact digests in its own code, and a unit test covers that. An
unnumbered question is also measured here: whether Kyverno's background scanning
evaluates a signature check on running pods, which preference 2 of decision (d)
assumes. It is not on the list of four because the report did not list it.

Measurement changes nothing that runs. Rollback is deleting the scratch
namespace and the throwaway policy.

**3b. The control in Git: the allowlist, the ledger and the test.** This was
Phase 4 in the first version of this plan. Phase 4 delivered the test, and the
enforcement step (3c there, 3d here) was conditional on it, so the plan
depended on a later phase. The smaller change is to move the test, which needs
only the allowlist and no registry access, and to leave the rest of Phase 4 where it is; the alternative, moving the whole
admission step after Phase 4, would renumber everything. The step delivers:

- the allowlist, as a file in Git: the exact digests of the images already
  deployed, with the Kubani pull request that pinned each (see below);
- a committed ledger of CI builds, empty until the first CI-built image is
  pinned; until the Phase 4 helper exists, a CI-built pin is added by hand with
  its ledger entry in the same pull request;
- `tests/test_platform_image_pins.py`, which requires every platform reference
  in GitOps and in the tests to name a digest and to be either on the allowlist
  or in the ledger, and which fails if the allowlist grows.

This is the control that does not depend on admission. It refuses, before the
merge, a pin that is neither CI-built nor allowlisted. It does not see a change
made directly on the cluster, and it does not see a platform image reference
written outside GitOps and `tests/`.

**The allowlist.** The report recommends an exact-digest allowlist kept in Git,
allowed only to shrink (held by the test above), each entry citing the Kubani
pull request that pinned it. It rejects signing the existing images after the
fact: the certificate, and any provenance attestation, would state that the
workflow built bytes it did not build, and Kyverno could not tell those from
real CI builds; the old commits predate the workflow, so they cannot be built by
it, which builds only what was merged; and the builds are not reproducible, so
the same digests cannot be produced again. At Kubani `bf8c063b` (read
2026-11-11) the entries would be the three Session Runner digests (`18aee61`,
`9c2c092`, `b2f4d57`), and one each for the Agent Policy Service,
budget-backend, the Registry Controller, egress-guard, netpol-attestor,
conformance-capture and capture, as listed in section 2.1. The list has to be
generated from the pins on the day 3b lands, since pins move. Entries leave as
CI builds are pinned. The two governed-worker digests stay until those workers
retire. The egress-guard digest stays until a coordinated bump, because an
existing policy already holds it to an exact digest. The `conformance-capture`
digest stays until a CI build replaces it (decision f).

**3c. The two outcomes of U2.**

*Outcome A: U2 does not hold, and `agent-platform` can be selected without being
put behind a fail-closed webhook.* Add a label, for example
`kyverno.kubani.io/admission: enabled`, to `tenant-test`, with a test that every
tenant namespace carries it. In a second pull request, switch Kyverno's webhook
namespace selector to that label. One selector cannot express "tenant label or
agent-platform" (inferred), which is why a new label is needed. Then add
`infrastructure/kyverno/policies/platform-image-signature.yaml` in Audit with
failure policy Ignore, verifying digests and not rewriting them. It has one
entry for `registry.almckay.io/platform/*` that requires the platform release
subject of decision (c) (one entry, because every platform image shares that
subject); the roots from `kyverno/private-sigstore`; and the allowlist. Then
label `agent-platform` into scope. Rollback is removing the namespace label, a
one-line revert.

*Outcome B: U2 holds, or the measurement leaves it open.* `agent-platform` is
not labelled and no admission policy is applied to it, so its pods stay out of
Kyverno's path as today. In its place:

- a scheduled verification job in the cluster that lists the images of the pods
  running in `agent-platform`, skips the exact digests on the allowlist, runs
  `cosign verify` for the rest against the vendored roots and the platform
  release subject, and alerts when one fails. (Whether it also reads the `vllm`
  and `mcp` sidecars is open. It touches no admission path, so decision (e) does
  not forbid it.) It needs read access to the registry and a destination for the
  alert; both are unsettled here. If a registry credential has to be minted for
  it, that is an operator step at that point (inferred here), and the alert
  destination is not chosen in this plan;
- the 3b test, which stays the primary control.

**3d. Enforce (outcome A only).** Change the policy from Audit to Enforce once
every platform reference in GitOps either verifies or is allowlisted (the 3b
test holds the second half) and the Audit period has shown no unexpected
failure. The failure policy stays Ignore throughout, so only one setting
changes; the agent policy changed two together because its failure policy was
Fail. Verification is tests in a labelled scratch namespace using server-side
dry runs: a superseded, unsigned Session Runner digest from Git history is
reported in Audit and denied in Enforce; an image signed by the wrong identity
is denied (the operator can make one by copying a signed agent image into
`platform/sigtest` with `cosign copy`); a CI-built image is admitted; and, with
the operator's agreement to a window, a pod is still admitted when the
admission controller cannot answer. Rollback is a revert to Audit, or in an
emergency removing the namespace label.

**What each outcome protects against, and what it does not (decided
2026-11-11; the protections are inferred and untested).**

| | Outcome A: Enforce with Ignore | Outcome B: scheduled job and Git test |
| --- | --- | --- |
| A hand-built or stale image pinned in a manifest | Refused at the merge by the 3b test, and denied at admission while Kyverno answers | Refused at the merge by the 3b test |
| A hand-built or stale image applied directly to the cluster | Denied while Kyverno answers; admitted while it cannot, then reported by background scanning once it is back | Runs until the next job run, which then alerts |
| A pod recreated during a Kyverno or ingress outage | Admitted, unverified (this is the price of failing open) | Admitted; the job checks it later |
| Pods of `vllm` and `mcp` | Not checked at admission; the 3b test covers their pins | Not checked at admission; the 3b test covers their pins |
| An image signed under the right subject by a changed workflow | Not detected; held by review of the workflow file | Not detected; held by review of the workflow file |
| A forged or stolen registry credential used to push a lookalike | Fails verification at admission | Fails verification in the job, after the fact |

Neither outcome stops a person with cluster access from changing a running
workload, and neither covers Kyverno, the runner image or the signing tools,
which section 5 lists as bootstrap gaps.

### Phase 4: a helper that moves the pins

**Delivers.** `just platform-image bump <image> <sha>` in Kubani, modelled on
`infrastructure/scripts/ops/agent_ops/stage.py`. With no tag and no release
asset, it resolves the digest of `platform/<image>:<sha>` in the registry
(inferred here; the method is not tried); checks that the commit is an ancestor
of zetra `main`, independently of the workflow; runs `cosign verify` and
`cosign verify-attestation` against the roots Kubani holds and the exact
subject of decision (c); rewrites every pin of that repository except those
under `governed-workers/`; updates `tests/test_budget_conformance_wiring.py`
and the "Built from" comments; removes an allowlist entry that is no longer
pinned; and appends the build to the ledger. The bump is the reviewed pull
request of decision (c): the helper edits files and opens nothing that deploys.
The test it must satisfy, `tests/test_platform_image_pins.py`, is delivered in
step 3b.

**Depends on** Phases 1 and 2 for the signatures and the pushed images. It
needs no operator decision.

**Verified by** the 3b test passing on the pull request the helper produces.
The report gives no separate verification step for the helper itself.

**Rollback.** Revert the pin pull request. Reverting a Session Runner pin is
not safe while a session is in flight (read, kubani PR #415).

### Fit with kubani PR #246

PR #246 is an open plan document for the agent supply chain. The report read it
and says this plan fits its sections S4, D7 and D8 (a keyless zetra
`platform-release.yml` on the cluster's runners, roots pinned directly,
verification by workflow identity). It lists four differences to record there:
eight repositories and not five; a second scale set scoped to zetra and not
literally the same runners; no break-glass issuer deployed (observed live), so
break-glass here is a hand build plus an allowlist entry made by pull request;
and that #246 does not cover admission enforcement or webhook scope for
platform images. A fifth difference follows from decision (c): this plan
releases on a merge to `main` and not on a tag push, which may differ from the
tag-push shape in #246 (inferred; #246 was not read again for this document).

---

## 4. What does not change for agent developers

This work is meant to be invisible to agent repositories. The path for a person
writing an agent stays what the golden path plan describes: `init`, run the
agent locally, `check`, and push a release tag.

- Platform releases use a separate workflow and a separate composite action,
  and start on a merge to zetra `main`, not on a tag. The agent workflow shim
  and the tag form `<agent>/v<version>` are not part of the plan. The new action
  reuses the agent release action's tool-install step and vendored roots; the
  report does not say how, so if that means moving files, the agent action's
  behaviour and the certificate subject it produces have to stay the same
  (inferred here).
- Agent releases keep their own scale set and job guard. The new guard admits
  zetra only.
- The plan lists no change to the agent signature policy, the per-tenant signer
  pins or the image path `registry.almckay.io/agents/*`. The pattern that
  matches agent certificate subjects cannot match a platform subject (read).
- The plan lists no change to `just agent register`, `stage`, `approve` or
  `run`.
- The new subject function lands in the contracts package that agent tooling
  also pins. It is an addition, and an agent repository sees it only when it
  next moves its zetra pin (inferred here).
- Protecting zetra `main` (decision c) applies to the zetra repository, whose
  contracts package and agent release action agent repositories also pin. A
  change to either now reaches `main` through a pull request with required
  checks (inferred here).

Two places where agent work could still feel it, all of them operator-side:

- A platform build and an agent release running at once share node memory.
- In outcome A of Phase 3c, the change of the selector label alters which
  namespaces Kyverno selects. A tenant namespace that lacked the new label when
  the selector switches would stop having its agent images verified, without any
  error (inferred here). The two-step order and the test in 3c are what hold
  this, and any future tenant generator has to apply the label. In outcome B the
  selector does not change.

Decision (b) removed a third place, a rotation of the shared `automation`
account touching agent repositories and zetra together.

---

## 5. Open risks and things not verified

**Four Kyverno behaviours the plan depends on are unmeasured.** They are
measured in Phase 3a, U2 first. After decisions (d) and (e), only U2 matters in
every outcome; U1, U3 and U4 matter only if the admission policy is built
(outcome A of Phase 3c).

- **U1.** Whether `skipImageReferences` matches references written as
  `repository:tag@sha256:digest`. The allowlist in the admission policy depends
  on it.
- **U2.** Whether a policy with failure policy Ignore, or any policy, leaves the
  namespaces in the webhook selector behind Kyverno's fail-closed webhook
  because other policies there fail closed. The report posed it for a policy
  with failure policy Fail. Decision (d) depends on it: it decides whether
  `agent-platform` can be selected at all without the fail-closed exposure the
  decision refuses.
- **U3.** Whether the `ImageValidatingPolicy` kind obeys the global namespace
  selector. The report lists this without saying which policy kind the new
  policy would use.
- **U4.** Whether `imageReferences` patterns match references that carry both a
  tag and a digest.

An unnumbered question is also open: whether background scanning evaluates a
signature check on running pods (Phase 3a).

**Not verified.**

- Whether any platform image has a signature in the registry. The documents
  say "pushed unsigned"; that was read, not checked.
- That `conformance-capture` is `platform/capture` built for amd64
  (decision f).
- That any registry account can push to `platform/*`. It is inferred from the
  registry document's statement that there is no per-repository authorisation.
- The cause of the four build sidecar out-of-memory kills at 12Gi.
- That branch protection on zetra `main` will be set as decision (c) describes,
  and whether it binds administrators and requires a second approval. The
  decision does not say, and nothing has been set. Until it is set, a push to
  `main` is not reviewed and the certificate subject means little.
- That the credential mounted on the runner can be read by the runner container
  and used by the nested daemon (Phase 1; not tested).
- That GitHub keeps one waiting run per `concurrency` group and drops older
  ones, which is why Phase 1 serialises at the runner (inferred from GitHub's
  documentation; not tested).
- That the attestation builders in `platform/agent-tools` can be reused.
- That one webhook selector cannot express "tenant label or agent-platform".
- That `conformance-capture` can be built by CI at all (decision f).
- That the Registry Controller verifies agent images only.
- The durations of the Phase 0 builds on a cold runner, beyond the single set
  of check results on PR #79, and the four holes in the pin tests listed under
  Phase 0.
- That only `tenant-test` carries the tenant label and that rig0 is the only
  platform node. Both were observed live by the report's author and not
  observed again for this document.

**Bootstrap and circular dependencies.**

- Kyverno would verify the platform images, and nothing verifies Kyverno. It is
  an upstream image pinned by tag only (`reg.kyverno.io/kyverno/kyverno:v1.19.2`),
  and its namespace is excluded from its own webhook (observed live).
- The Registry Controller is a platform image. Kyverno would verify it, not the
  controller itself, so a bad controller could not block its own replacement
  (this rests on the inference that it verifies agent images only).
- The signing tools come from the mirror by digest. The runner and build
  sidecar images are upstream images (read).
- Kyverno needs the registry through Traefik to verify, and Rekor only when a
  signature carries no embedded bundle (read). Under decision (d) a Traefik
  outage no longer blocks admission of platform pods: they are admitted
  unverified (outcome A), or are not on Kyverno's path (outcome B). Pulls are
  not affected (inferred). The registry, Traefik, sigstore and kyverno
  namespaces should stay out of scope.
- Under decision (d), netpol-attestor pods can be recreated while Kyverno is
  down, because the policy fails open (outcome A) or is not applied (outcome B).
  The same decision is the reason a recreated pod in that window is not
  verified.
- CI needs the cluster: the runners, the registry, Fulcio and Rekor. A fix
  needed while those are down cannot be built by CI. The route is a hand build
  plus an allowlist entry by pull request (inferred). Hand builds therefore do
  not disappear; they become the recorded exception.

**Other risks.**

- Capacity: a third build sidecar with a 12Gi limit beside agent releases
  (decision a). No figure has been measured. Decision (c) limits platform
  releases to one job at a time, which does not limit them against agent
  releases.
- The release credential lives on the runner pod. A job allowed by the guard can
  read it. The guard and branch protection are what limit that, and the
  guard's admission of `refs/heads/main` is only as strong as the protection of
  that branch.
- Phase 0 adds nine jobs to every push and pull request event in zetra (read,
  PR #79).
- The Phase 0 pin tests cover `platform/*/Dockerfile` only and have the holes
  listed there. A later phase that treats "the bases are pinned" as an input to
  provenance inherits them.

---

## 6. Sources

- The planning report described under "How to read the evidence"; not in the
  repository.
- zetra PR #79, `ci(platform): build every platform image in CI from pinned
  bases`, merged as `bad3e3da` on 2026-11-10, and its check results.
- zetra `main` at `18aee61` for `platform/images.json`,
  `.github/workflows/platform.yml`, `docs/platform.md` and the agent Dockerfile
  template.
- Kubani `bf8c063b` (read 2026-11-11) for the pins,
  `infrastructure/gitops/apps/arc-runners/`, and
  `infrastructure/gitops/infrastructure/kyverno/`; the first version of this
  document read them at `606effc5`.
- The GitHub API on 2026-11-10 for zetra's visibility, branch protection,
  rulesets and tags.
- `docs/plans/ideas/2026-11-11-agent-delivery-redesign.md`, written on another
  branch and not read from this one. The decisions in section 1 are restated
  from the instruction that carried them, dated 2026-11-11.
