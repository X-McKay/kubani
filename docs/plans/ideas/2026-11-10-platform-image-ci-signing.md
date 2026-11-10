# Platform image build, signing and admission in CI — 2026-11-10

**Status:** idea, for review. Phase 0 is merged in zetra. Nothing in Phases 1
to 4 is built or tested, and they wait on the six decisions in section 1.
**Scope:** the eight image repositories under `registry.almckay.io/platform/`,
a release workflow in zetra that would build and sign them, a second runner
scale set and an admission policy in Kubani, and a helper that moves the pins.
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
built by continuous integration (CI) from a tag, signed without a long-lived
key, and verified when a pod is admitted. As of 2026-11-10 only the first step
exists: CI in zetra builds every platform image and checks the base-image pins,
and it pushes and signs nothing. The most recent deployed image is the Session
Runner built by hand from zetra `541e2ef`, and a further hand-built roll of the
Agent Policy Service and the Session Runner from zetra `18aee61a` is in
progress today, which is one more image roll that rests on a workstation build.

**How to read the evidence.** This document restates a planning report written
before zetra PR #79, against zetra `677a2de` and Kubani `2daf551c`. The report
is not in the repository; everything needed from it is here. Each claim is
marked in words: *read* means read from code, manifests or documents;
*observed live* means seen on the cluster or through the GitHub API by the
report's author; *inferred* means reasoned and not tested; *measured* means a
command was run and its result is quoted. On 2026-11-10, for this document, the
pins and line references below were read again at Kubani `606effc5`, zetra's
repository settings were read again through the GitHub API, and zetra PR #79
and its check results were read. Nothing on the cluster was observed again for
this document. The report itself changed and tested nothing.

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

## 1. Decisions needed from the operator

Phase 0 needed no decision and is done. Phases 1 and 2 wait on decisions (a),
(b) and (c). Phase 3 waits on (d), (e) and (f). Phase 4 needs no decision of
its own. The report's overall recommendation is to build each platform image
from a zetra tag on a new runner scale set that serves zetra only, to sign it
the way agents are signed, to enforce with a new Kyverno policy scoped by a
namespace label, and to cover the images already deployed with an exact-digest
allowlist and not by signing them after the fact.

| | Question | Report's recommendation | Blocks |
| --- | --- | --- | --- |
| a | Add a second runner scale set and install the kubani-arc App on zetra? | Yes | Phase 1 onward |
| b | Shared `automation` registry account, or a dedicated one? | Dedicated | Phase 1 onward |
| c | Tag ruleset on `platform/**` and branch protection on zetra `main`? | Tag ruleset yes; none given for branch protection | Phase 1 onward |
| d | May `agent-platform` pod admission fail closed on Kyverno? | Implied yes by the overall design; posed as a question | Phase 3b and 3c |
| e | Are the `vllm` and `mcp` capture sidecars in the enforcement scope? | None | Phase 3c scope |
| f | Is `conformance-capture` the `platform/capture` source built for amd64? | None; it is a question of fact | Phase 3 entries for that image |

Costs and risks below come from the report unless a sentence says "inferred
here", which marks reasoning added while writing this document.

### (a) A second runner scale set and the kubani-arc App on zetra

**Question.** Should Kubani run a second runner scale set that serves only
zetra, and should the kubani-arc GitHub App be installed on `X-McKay/zetra`?

**Why it arises.** The one scale set, `kubani-zetra-agents`, is bound to
zetra-agents (read, `apps/arc-runners/scale-set-zetra-agents.yaml:46`), the App
is installed only there (observed live), and its job guard admits only tag
pushes of zetra-agents' `release.yml` (read, `apps/arc-runners/job-guard.yaml`).
A zetra job cannot use it.

**Options.**

- *Accept.* Kubani gains `kubani-zetra` with at most one runner, the same Kata
  sandbox and build sidecar as today, and its own job guard. The cost is one
  more build sidecar with a 12Gi memory limit whenever a platform release runs.
  The existing scale set allows two runners (read, line 50), so three build
  sidecars could run at once (inferred here); the report points at
  `just capacity` to check this and gives no measured figure. The build sidecar
  has been killed for exceeding 12Gi four times during `apt` retries, with the
  cause unproven (read,
  `docs/infrastructure/configuration/agent-runtime-platform-phase-b-qualification.md:1419-1429`).
  zetra is public (observed live, and read again on 2026-11-10), so the job
  guard is what keeps other zetra workflows off the runner.
- *Decline.* Phases 1 to 4 do not proceed as designed and platform images stay
  hand-built. The release workflow needs the registry, Fulcio and Rekor, and
  the design gives it no fallback to a GitHub-hosted runner. The report does
  not evaluate a hosted-runner design or a way to share the existing scale set.

**Report's recommendation.** Accept.

### (b) Which registry account zetra's release workflow uses

**Question.** Does zetra push with the shared `automation` account or with a
dedicated account for platform images?

**Why it arises.** The registry sits behind Traefik basic authentication with
three accounts, `human`, `automation` and `kyverno` (read,
`docs/infrastructure/configuration/registry.md`). It has no per-repository
authorisation, so any account can push to `platform/*` (inferred from that
document, not tested). Neither option therefore limits where the account can
push; the signature is the only thing that would separate a CI-built image
from a hand push.

**Options.**

- *Shared `automation`.* No new account. It is the account agent repositories
  already receive as secrets under the golden path (decision 7 there). Revoking
  or rotating it touches every repository that holds it (inferred here).
- *Dedicated account.* It can be revoked on its own. The operator has to issue
  it; the report names `infrastructure/scripts/ops/add_registry_user.sh` for
  that. Credential issuance is the operator's step in either case, and the
  values go only into zetra's Actions secrets `REGISTRY_USERNAME` and
  `REGISTRY_PASSWORD`.

**Report's recommendation.** A dedicated account, so that it can be revoked
without touching anything else.

### (c) A tag ruleset on `platform/**` and branch protection on zetra `main`

**Question.** Will zetra get a ruleset that restricts who can create
`platform/**` tags, and will `main` be protected?

**Why it arises.** zetra has no rulesets and no tags, and `main` is unprotected
(observed live through the GitHub API; read again on 2026-11-10 with the same
result). In the design a tag starts a release, and the workflow file that runs
is the one at the tagged commit. A tag can therefore point at a commit that is
not on `main` and whose copy of the workflow has dropped the check that the
commit is on `main`. The runner would build and sign it under a valid
platform-release identity (inferred by the report, not tested).

**Options.**

- *Tag ruleset: only administrators create `platform/**` tags, and nobody
  updates or deletes them.* The cost is a settings change on zetra and that
  every platform release tag is pushed by an administrator. Without it, the
  weakness above is held only by the independent ancestry check in the Kubani
  helper (Phase 4), which runs when a pin is bumped and not when the image is
  signed.
- *Branch protection on `main`.* The cost is that changes to zetra `main` have
  to go through whatever the protection requires. The workflow's check that a
  commit is an ancestor of `main` shows only that the commit is on `main`; it
  says the commit was reviewed only if `main` is protected (inferred here).
- *Neither.* Signing still works. Admission would then show that a workflow
  file named `platform-release.yml` at some `platform/` tag in zetra signed the
  image, and not that the source was on `main` (inferred here). The ancestry
  check in the Phase 4 helper would be the only control left.

**Report's recommendation.** The report lists the tag ruleset as an operator
step of Phase 1, together with two repository settings: default workflow
permissions set to read-only, and approval required for workflows from fork
pull requests. It gives no recommendation on branch protection. It notes that
`main` is unprotected and chose a tag trigger partly because the alternative, a
manually dispatched workflow, would put a branch ref in the certificate
subject, which means something only when the branch is protected.

### (d) Whether `agent-platform` pod admission may fail closed on Kyverno

**Question.** Is it acceptable that pods in the `agent-platform` namespace
cannot be created or restarted while Kyverno is unavailable?

**Why it arises.** Kyverno's webhooks select only namespaces that carry the
tenant label (read, `infrastructure/kyverno/helmrelease.yaml:43-45`), and only
`tenant-test` carries it (observed live). No pod in `agent-platform`, `mcp` or
`vllm` reaches Kyverno today. Verifying platform images means bringing
`agent-platform` into that selection.

**Options.**

- *Accept.* Phase 3 can end in Enforce with failure policy Fail. While Kyverno
  is down, pod creation in `agent-platform` is denied after a 10 second
  timeout. The netpol-attestor is a DaemonSet with host networking, and its
  pods could not be recreated on any node in that state (inferred). Kyverno's
  two replicas are pinned to platform nodes, and rig0 is the only such node
  seen (read and observed live). Kyverno reaches the registry through Traefik,
  so a Traefik outage would also block admission of platform pods, though not
  image pulls, which use internal mirror endpoints (inferred). The exposure may
  begin earlier than Enforce: if unknown U2 in section 5 holds, labelling
  `agent-platform` into scope for the Audit step already places it behind the
  fail-closed webhook of the existing agent policy.
- *Decline.* The policy stays in Audit with failure policy Ignore. Unsigned or
  wrongly signed platform images are reported and still run. If U2 holds, even
  Audit cannot be had without the exposure, and that would have to be resolved
  in Phase 3a before `agent-platform` is labelled.

**Report's recommendation.** The report's design ends in Enforce with Fail,
which implies accepting. It still poses this as a question for the operator
and does not argue the acceptance separately.

### (e) Whether the `vllm` and `mcp` capture sidecars are in scope

**Question.** Should the policy also be enforced in the `vllm` and `mcp`
namespaces, where the two capture sidecar images run?

**Why it arises.** `platform/capture` runs as a sidecar in the vLLM deployment
(read, `apps/vllm/deployment.yaml:181`) and `platform/conformance-capture` as a
sidecar in the Kubernetes MCP server (read, `apps/mcp/kubernetes-mcp.yaml:83`).
They are platform images outside `agent-platform`.

**Options.**

- *In scope.* Both namespaces are labelled into Kyverno's selection and the
  two sidecars are verified at admission. Kyverno is then on the admission path
  of every pod in those namespaces, so a vLLM or MCP pod could not be recreated
  while Kyverno is unavailable (inferred here from decision (d); the same U2
  question applies).
- *Out of scope.* CI can still build and sign the two images, and the Phase 4
  test in Git still requires their pins to be allowlisted or CI-built. Nothing
  checks them at admission, so a hand-pushed image pinned by digest would run
  there.

**Report's recommendation.** None. The report says only that the two
namespaces are added if the operator accepts Kyverno on those admission paths,
so leaving them out is the default.

### (f) Whether `conformance-capture` is `platform/capture` built for amd64

**Question.** Was the image pinned as `platform/conformance-capture` built from
`platform/capture/Dockerfile` for linux/amd64?

**Why it arises.** The report inferred this from a comment in the Kubani
manifest. zetra PR #79 added that the manifest describes the sidecar as "zetra
platform/capture" and that the published image's layers match the Dockerfile,
and recorded that no build record names the commit or the command. The entry
for this repository in `platform/images.json` already assumes the answer is
yes.

**Options.**

- *Confirmed.* The entry stands, CI can build the repository, and the pinned
  digest `be4e8e6a…` leaves the allowlist when a CI build is pinned.
- *Not confirmed, or the answer is no.* The entry in `images.json` describes a
  build nobody has shown to be the deployed one. The pinned digest stays on the
  allowlist until the sidecar is replaced by a CI build, and the first CI build
  should be treated as a new image to qualify and not as a rebuild (inferred
  here).

**Report's recommendation.** None. Only the operator can say how the image was
built.

---

## 2. What exists today

### 2.1 The images

Seven Dockerfiles in zetra produce eight repositories under
`registry.almckay.io/platform/`. The pins are read from
`infrastructure/gitops/` at Kubani `606effc5` and are the same as in the
report, which also observed them on the running pods. The roll in progress
today will change the Agent Policy Service and Session Runner rows when it
lands.

| Repository | Source in zetra | Platform | Pin (tag and digest prefix) | Where it is pinned |
| --- | --- | --- | --- | --- |
| `agent-policy-service` | `platform/aps/Dockerfile` | amd64 | `4a089b5@sha256:4d568768…` | `apps/agent-platform/workloads/agent-policy-service.yaml` |
| `budget-backend` | `platform/budget-backend/Dockerfile` | amd64 | `4a089b5-amd64@sha256:1e3fb618…` | `…/workloads/budget-backend.yaml` |
| `registry-controller` | `platform/controller/Dockerfile`, context `platform` | amd64 | `1c8e481@sha256:dd8786ca…` | `…/workloads/registry-controller.yaml` |
| `session-runner` | `platform/runner/Dockerfile` | amd64 | `541e2ef@sha256:60061e2f…` | `session-runner-tenant-test.yaml`, `cleanup-reconciler.yaml`, seven `conformance-*-job.yaml`, and `tests/test_budget_conformance_wiring.py` |
| `session-runner`, retained | same | amd64 | `9c2c092@sha256:d6a785a6…` and `b2f4d57@sha256:4a443f97…` | `…/workloads/governed-workers/` (`sessions-a`, `cleanup-a`, `sessions-b`, `cleanup-b`) and `tests/test_worker_ab_staging.py`; never rebuilt |
| `egress-guard` | `platform/egress-guard/Dockerfile` | amd64 | `@sha256:2a6f650e…`, no tag | an exact-digest rule in `infrastructure/kyverno/policies/agent-sandbox-admission.yaml`, an environment variable in `registry-controller.yaml`, and about 20 Kyverno test fixtures |
| `netpol-attestor` | `platform/netpol-attestor/Dockerfile` | amd64 | `@sha256:3b6a6dc6…`, no tag | `apps/agent-platform/netpol-attestor.yaml` (DaemonSet, host networking) |
| `capture` | `platform/capture/Dockerfile` | arm64 | `ef1a16f-arm64@sha256:69c98473…` | `apps/vllm/deployment.yaml` |
| `conformance-capture` | `platform/capture/Dockerfile`, assumed (decision f) | amd64 | `5077ef0@sha256:be4e8e6a…` | `apps/mcp/kubernetes-mcp.yaml` |

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

Phases 0 to 2 are additive and change nothing that already runs. Phase 3 is
the first that can deny a pod.

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
field, so Phase 1 has to add it or settle the tag form another way.

### Phase 1: a runner for zetra and a release workflow

**Delivers.**

- In Kubani: `apps/arc-runners/scale-set-zetra.yaml`, a scale set named
  `kubani-zetra` with at most one runner and the same sandbox and build sidecar
  as the existing one, plus its own job guard. The guard admits only repository
  `X-McKay/zetra`, the push event, a ref matching
  `^refs/tags/platform/[a-z0-9-]+/[0-9a-f]{7,40}$`, and a workflow reference
  equal to `platform-release.yml` at that same tag. The README and the capacity
  ledger are updated.
- In zetra: `.github/workflows/platform-release.yml` and a composite action
  `.github/actions/platform-release/` that reuses the tool-install step and the
  vendored trust roots of the agent release action. The workflow starts on tags
  `platform/<image>/<short-sha>`, runs only on the self-hosted runner named by
  the repository variable `RELEASE_RUNNER`, with permission to request an
  identity token and to write release assets, and runs one release at a time. It
  refuses to continue unless the image is in `images.json`, the commit being
  built starts with the hash in the tag, the commit is an ancestor of
  `origin/main`, and the checkout is clean. It builds one image, pushes it
  under the tag form used today, and writes the full reference with its digest
  to the job summary and to a release asset named `image`.

The trigger is one tag for each image, not a manually dispatched workflow, for
four reasons the report gives: the image name lands in the certificate subject,
so each repository can be held to its own signer; it matches the tag-push shape
of the existing guard and of PR #246; one tag is one run, which fits the rule
of one release at a time; and a dispatched run would carry a branch ref, which
means something only with branch protection.

**Depends on** decisions (a), (b) and (c). The operator steps are: install the
kubani-arc App on zetra; create the tag ruleset; set default workflow
permissions to read-only and require approval for fork pull requests; set the
variable `RELEASE_RUNNER=kubani-zetra`; issue the registry credential and set
it as the two Actions secrets.

**Verified by** pushing a tag for `budget-backend` first, because it is the
smallest image and has no dependencies. The run should print a digest and the
image should pull. This is the plan; nothing has been run.

**What could go wrong.** The guard rejects the job, which fails at its start.
The build sidecar runs out of memory, which shows as Kata out-of-memory events;
netpol-attestor is the image most exposed because it is the only one that runs
`apt-get`. A platform build overlaps agent releases and the node runs short.

**Rollback.** Delete the tag and the release, and remove the scale set.
Nothing consumes the image yet.

### Phase 2: signing and provenance

**Delivers.** For each image the workflow signs with `cosign`, then attaches
three attestations (SLSA build provenance version 1, an SPDX bill of materials
and a vulnerability scan), each under a fresh identity token, and then verifies
its own output, as the agent release script does. The agent-only evaluation and
release attestations are left out. The certificate subject is
`https://github.com/X-McKay/zetra/.github/workflows/platform-release.yml@refs/tags/platform/<image>/<sha>`
with the GitHub Actions issuer. A function `platform_subject_regexp_for(image)`
is added beside the agent one in `platform/contracts/agent_platform/signing.py`;
the agent pattern cannot match these subjects (read). The report judges the
existing attestation builders in `platform/agent-tools` reusable; that is
inferred, not tried.

**Depends on** Phase 1, and through it on decisions (a), (b) and (c). It may
ship in the same pull request as the workflow or in the next one. One smaller
choice is left open on purpose: the threshold at which the vulnerability scan
fails the job, to be set after the first measured run.

**Verified by** running `cosign verify` and `cosign verify-attestation` from
rig0 against the exact identity. The negative test is the same command with the
zetra-agents identity, which must fail.

**What could go wrong.** Fulcio or Rekor is unreachable from the runner, or the
scan gate fails a first build. Either fails the job.

**Rollback.** None needed. Signatures are additive and can stay.

### Phase 3: admission

**Depends on** decision (d) for steps 3b and 3c, decision (e) for the scope of
3c, and decision (f) for how `conformance-capture` is entered. Step 3a consumes
nothing from Phases 1 and 2. Steps 3b and 3c need Phase 2 for a CI-signed image
to test with. The report does not state these dependencies; they are read off
what each step consumes.

**3a. Widen the selection without changing behaviour.** Add a label, for
example `kyverno.kubani.io/admission: enabled`, to `tenant-test`, with a test
that every tenant namespace carries it. In a second pull request, switch
Kyverno's webhook namespace selector to that label. One selector cannot express
"tenant label or agent-platform" (inferred), which is why a new label is
needed. This step is also where the four unknowns in section 5 (U1 to U4) are
measured, with the Kyverno 1.19.2 command-line tool and server-side dry runs.
It is verified by reading the live webhook selector and by the conformance
admission Job still passing. Rollback is reverting the selector.

**3b. Audit.** Add `infrastructure/kyverno/policies/platform-image-signature.yaml`
in Audit with failure policy Ignore, verifying digests and not rewriting them.
It has one entry for each repository that binds the certificate subject to that
image, generated from the image table; a catch-all entry for
`registry.almckay.io/platform/*` that requires some platform-release tag
identity; the roots from `kyverno/private-sigstore`; and the allowlist of
legacy digests. Then label `agent-platform` into scope. Rollback is removing
the namespace label, a one-line revert.

**The allowlist.** The report recommends an exact-digest allowlist kept in Git,
allowed only to shrink (held by a test), each entry citing the Kubani pull
request that pinned it. It rejects signing the existing images after the fact:
the certificate, and any provenance attestation, would state that the workflow
built bytes it did not build, and Kyverno could not tell those from real CI
builds; the old commits predate the workflow, so they cannot be built from a
tag; and the builds are not reproducible, so the same digests cannot be
produced again. At Kubani `606effc5` the entries would be the three
Session Runner digests, and one each for the Agent Policy Service,
budget-backend, the Registry Controller, egress-guard, netpol-attestor,
conformance-capture and capture, as listed in section 2.1. The list has to be
generated from the pins on the day 3b lands, since the roll in progress today
changes two of them. Entries leave as CI builds are pinned. The two
governed-worker digests stay until those workers retire. The egress-guard
digest stays until a coordinated bump, because an existing policy already holds
it to an exact digest.

**3c. Enforce.** Change the policy to Enforce and failure policy Fail together,
once every platform reference in GitOps either verifies or is allowlisted and
the Audit period has shown no unexpected failure. Add `mcp` and `vllm` only
under decision (e). Verification is three tests in a labelled scratch namespace
using server-side dry runs: a superseded, unsigned Session Runner digest from
Git history is reported in Audit and denied in Enforce; an image signed by the
wrong identity is denied (the operator can make one by copying a signed agent
image into `platform/sigtest` with `cosign copy`); and a CI-built image is
admitted. Rollback is a revert to Audit and Ignore, or in an emergency removing
the namespace label.

**Ordering to settle.** The report makes 3c conditional on "helper plus a unit
test" showing that every reference verifies or is allowlisted, and places that
helper and test in Phase 4. The test, at least, has to land before 3c.

### Phase 4: a helper that moves the pins

**Delivers.** `just platform-image bump <image> <sha>` in Kubani, modelled on
`infrastructure/scripts/ops/agent_ops/stage.py`. It downloads the `image` asset
for the tag; checks that the commit is an ancestor of zetra `main`,
independently of the workflow; runs `cosign verify` and
`cosign verify-attestation` against the roots Kubani holds and the exact
identity; rewrites every pin of that repository except those under
`governed-workers/`; updates `tests/test_budget_conformance_wiring.py` and the
"Built from" comments; and removes an allowlist entry that is no longer pinned.
It also adds `tests/test_platform_image_pins.py`, which requires every platform
reference in Git to name a digest and to be either allowlisted or recorded in a
committed ledger of CI builds. That test needs no registry access.

**Depends on** Phases 1 and 2 for the release asset and the signatures. It
needs no operator decision.

**Verified by** the new test. The report gives no separate verification step
for the helper itself.

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
platform images. PR #246 was not read again for this document.

---

## 4. What does not change for agent developers

This work is meant to be invisible to agent repositories. The path for a person
writing an agent stays what the golden path plan describes: `init`, run the
agent locally, `check`, and push a release tag.

- Platform releases use a separate workflow, a separate composite action and a
  separate tag namespace, `platform/<image>/<sha>`. The agent workflow shim and
  the tag form `<agent>/v<version>` are not part of the plan. The new action
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

Three places where agent work could still feel it, all of them operator-side:

- A platform build and an agent release running at once share node memory.
- Phase 3a changes which label selects namespaces for Kyverno. A tenant
  namespace that lacked the new label when the selector switches would stop
  having its agent images verified, without any error (inferred here). The
  two-step order and the test in 3a are what hold this, and any future tenant
  generator has to apply the label.
- If decision (b) goes to the shared `automation` account, a rotation of that
  account touches agent repositories and zetra together (inferred here).

---

## 5. Open risks and things not verified

**Four Kyverno behaviours the plan depends on are unmeasured.** They are to be
measured in Phase 3a.

- **U1.** Whether `skipImageReferences` matches references written as
  `repository:tag@sha256:digest`. The allowlist depends on it.
- **U2.** Whether a policy with failure policy Fail puts every namespace in the
  webhook selector behind Kyverno's fail-closed webhook. Decision (d) depends
  on it, because it decides whether the Audit step already carries the
  fail-closed exposure.
- **U3.** Whether the `ImageValidatingPolicy` kind obeys the global namespace
  selector. The report lists this without saying which policy kind the new
  policy would use.
- **U4.** Whether `imageReferences` patterns match references that carry both a
  tag and a digest.

**Not verified.**

- Whether any platform image has a signature in the registry. The documents
  say "pushed unsigned"; that was read, not checked.
- That `conformance-capture` is `platform/capture` built for amd64
  (decision f).
- That any registry account can push to `platform/*`. It is inferred from the
  registry document's statement that there is no per-repository authorisation.
- The cause of the four build sidecar out-of-memory kills at 12Gi.
- That a tag on a commit outside `main`, with an edited workflow, would be
  built and signed. It is inferred from how the guard and the workflow are
  designed, and it is the reason for decision (c).
- That the attestation builders in `platform/agent-tools` can be reused.
- That one webhook selector cannot express "tenant label or agent-platform".
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
  signature carries no embedded bundle (read). A Traefik outage would block
  admission of platform pods but not pulls (inferred). The registry, Traefik,
  sigstore and kyverno namespaces should stay out of scope.
- Once `agent-platform` is in scope, netpol-attestor pods cannot be recreated
  on any node while Kyverno is down (inferred).
- CI needs the cluster: the runners, the registry, Fulcio and Rekor. A fix
  needed while those are down cannot be built by CI. The route is a hand build
  plus an allowlist entry by pull request (inferred). Hand builds therefore do
  not disappear; they become the recorded exception.

**Other risks.**

- Capacity: a third build sidecar with a 12Gi limit beside agent releases
  (decision a). No figure has been measured.
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
- Kubani `606effc5` for the pins, `infrastructure/gitops/apps/arc-runners/`,
  and `infrastructure/gitops/infrastructure/kyverno/`.
- The GitHub API on 2026-11-10 for zetra's visibility, branch protection,
  rulesets and tags.
