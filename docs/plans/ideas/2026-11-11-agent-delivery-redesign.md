# Agent delivery redesign: pipeline, registry and decoupled services — 2026-11-11

Status: **draft for review. Nothing here is implemented.** This document is the
check-in before any build work starts.

It replaces the release path described in
[agent operations](../../infrastructure/configuration/agent-operations.md) and
revises parts of the
[golden path plan](2026-11-09-agent-repo-golden-path.md) and of the
[platform specification](../../infrastructure/configuration/agent-runtime-platform-spec.md)
(sections 6, 10 and 14). Section 4 lists exactly which earlier decisions change.

Terms: *agent repository* is a source repository of one or more agents (today
`X-McKay/zetra-agents`). *Declaration* is the statement of what an agent may do:
tools, models, budgets and identity mode (today `deploy/agent.yaml`). *Release
artifact* is the signed image together with its declaration and evidence.
*Registry* is the platform service that records agents and their versions.
*Verdict* is the verifier's signed statement that a release artifact passed
verification.

## 0. Summary

- Today a one-line change to an agent costs three pull requests across two
  repositories, and a first deployment costs about eight steps and three or four
  infrastructure pull requests. The path does not work at all for a second
  repository (section 3).
- Target: an author merges a pull request in their own repository. The pipeline
  refuses anything that does not meet the requirements. A release that passes is
  built, signed and published by a pipeline the platform owns, verified and
  evaluated by the platform, registered as a new version and made current
  automatically. A person is asked only when the agent's authority changes in a
  way the tenant policy marks for review, and when an agent acts on a person's
  behalf.
- The declaration travels with each release. Kubani stops holding a copy of
  every agent and every release.
- The platform is split along responsibilities with four explicit contracts
  between the parts (section 8), so that parts can change and deploy
  independently.

## 1. Goals and non-goals

Goals:

1. Fewest steps for an author to develop, test, evaluate and deploy an agent.
2. Requirements are enforced by machines that fail closed; a person decides only
   where judgment is needed.
3. Simple agents stay simple; models, tool backends, delegated identity and
   several agents per repository add work only for the author who needs them.
4. Each platform part has one job, its own credentials and its own deployment.

Non-goals:

- Replacing the sandbox, Temporal, the gateway, Keycloak or the policy service.
- Adopting Agent Substrate. The review of it (commit `905e2a65`) found that it
  covers the sandbox and egress only, bypasses image signature admission, needs
  Kubernetes feature gates that are off by default, and does not support GPUs.
  Three of its practices are adopted in sections 12 and 15.
- A configuration-only agent tier that needs no image. It is attractive and can
  be added later on top of this design; it is not required by it.

## 2. What must stay true

| # | Property | Enforced by, after this change |
| --- | --- | --- |
| P1 | An image runs only if the platform's release pipeline built it from a trusted repository, and the platform verified it | Verifier, then Kyverno on the verifier's verdict |
| P2 | What an agent may do is declared, checked against tenant policy, and approved by a person when the policy requires | Registry |
| P3 | A release is built from a lock and carries verified evidence: tests, evaluation, software bill of materials, vulnerability scan | Release pipeline, verifier |
| P4 | Acting on a person's behalf needs that person's consent at run time | Unchanged |
| P5 | There is a durable record of every version, every verdict and every approval | Registry, transparency log, scheduled export |
| P6 | Nothing becomes current without passing an evaluation on the cluster | Registry |

P2 changes in one respect, on purpose: a person no longer approves every build.
A person approves every change of authority that the tenant policy marks for
review. A release that changes only code is verified and evaluated by machine.

## 3. What the audit found

Measured on Kubani `bf8c063b`, zetra `18aee61`, zetra-agents `1b69fb0`.

The path as it is:

| Milestone | Steps today |
| --- | --- |
| Local agent with a passing test | 3 commands |
| First deployment | About 8 steps, one of which is five actions; 3 or 4 Kubani pull requests; a shared registry password copied by hand |
| One-line change | 6 steps, 3 pull requests, 2 repositories |

The advertised path is broken for anyone but zetra-agents:

- The only runner scale set admits one repository
  (`infrastructure/gitops/apps/arc-runners/job-guard.yaml:26`).
- `just agent-preflight` imports from `<source>/tools`
  (`infrastructure/scripts/ops/agent_preflight/source.py:107`); zetra-agents no
  longer has that directory.
- A model-free agent fails in the SDK step loop unless it is a conformance
  fixture: `run_model` reads `model["name"]` unconditionally (zetra
  `platform/agent-runtime/agent_runtime/step.py:220`).
- After a second approved release, `just agent run` refuses without `--release`
  (`infrastructure/scripts/ops/agent_ops/live.py:114`).

What is coupled:

- The declaration lives twice, in the agent repository and in Kubani, held
  together by `just agent sync` and `check-sync`.
- One zetra commit pins the SDK in images, the author tooling and the contracts
  the controller runs (zetra `docs/agents.md`). They move in lockstep.
- The Registry Controller verifies signatures, administers Keycloak, compiles
  policy and renders pod templates in one process.
- Sessions have no API. `just agent run` works through `kubectl exec` into the
  runner pod.
- 11,683 of the runner package's 15,571 lines are conformance harness, shipped
  in the production image.
- Release logic (`stage`, `approve`) lives in the infrastructure repository's
  command-line tool.
- Platform images are still built and pushed by hand (zetra
  `docs/platform.md`).

## 4. Decisions

Taken with Al on 2026-11-11:

| # | Decision |
| --- | --- |
| D1 | The pipeline is the gate. Release logic moves into a pipeline the platform owns, so a repository cannot drop a required step and still obtain a valid release. |
| D2 | The verifier signs a verdict; Kyverno admits on that verdict. Admission no longer knows repositories or agent names. |
| D3 | Builds stay on self-hosted runners, and the runner setup is improved (section 9). |
| D4 | The declaration travels with each release. The registry decides per version by comparing it with the previous version and with tenant policy. |
| D5 | Live evaluation runs on the cluster as part of registration, against the built artifact, compared with the current version. Scripted scenarios stay in continuous integration. |
| D6 | Build once, then promote. A preview channel in a low-authority tenant; promotion moves the same digest. |
| D7 | Roles are defined before the interfaces are built, and every interface route needs an explicit permission rule or the build fails. |
| D8 | A status view, a way to pull a version at once, a scheduled export of registry state, a compatibility check before platform upgrades, and migration one agent at a time. |
| D9 | A release is produced by continuous integration and delivery on a merge to main. No person pushes a tag or runs a release command. |

Earlier decisions this reverses:

| Earlier decision | Where | Now |
| --- | --- | --- |
| Shared release steps as a composite action, so the certificate subject stays the caller's workflow | Golden path plan, decision 6 | A platform-owned release pipeline. The reason for the old choice was that Kyverno matches the subject only; D2 removes that constraint, because the verifier reads the full certificate and Kyverno checks only the verdict. |
| `register` binds a repository to its agent names in the tenant signer pin | Golden path plan, decision 7 | Trust is granted to a repository. The registry enforces which repository owns which agent name. |
| Staging and approval are separate reviewed pull requests | `.claude/rules/agent-platform.md`, Releases | Registration is automatic. Approval, when required, is a signed action in the registry. |
| The policy digest is compiled at build time and again by the controller, and the two must match | Specification 6.3 | The platform compiles policy from the signed declaration. One copy, so no drift check and no lockstep contracts pin for agent repositories. |
| A release is identified by a pushed tag `<agent>/vX.Y.Z` | Golden path plan, decision 5 | A merge to main that bumps the agent's version is the release (D9). The directory layout `agents/<name>/` is unchanged. |

Unchanged and reaffirmed: one workspace and one lock per repository; tools
derived from code and checked by `render --check`; consent as a person's step;
historical releases are never deleted or relabelled.

## 5. The flow

For the author:

1. Scaffold, then `just check` and `just run` locally. Unchanged.
2. Open a pull request. Continuous integration runs the same `check`, the tests
   and the scripted scenarios. A failure blocks the merge.
3. Optional: publish a preview. The build lands in the preview tenant, where the
   author can run real sessions with read-only tools and a small budget.
4. Merge a version bump for the agent.

For the platform, with no person involved:

5. The release pipeline builds from the merged commit, runs the gate again,
   signs, and publishes the release artifact.
6. The verifier checks the artifact and signs a verdict.
7. The registry records the version and compares its declaration with the
   previous version and with tenant policy (section 7).
8. The registry runs the evaluation and a smoke session on the cluster.
9. The version becomes current. New sessions use it; sessions in flight finish
   on the version they started with.
10. The result is reported on the author's commit and in the status view:
    registered, verified, evaluated, current, or the reason it stopped.

Steps for a person, today and after:

| Case | Today | After |
| --- | --- | --- |
| First deployment | About 8 steps, 3 or 4 infrastructure pull requests | Operator trusts the repository once. Author merges. |
| Code-only change | 3 pull requests | 1 pull request, in the agent repository |
| Change of authority within tenant policy | 3 pull requests | 1 pull request |
| Change of authority marked for review | 3 pull requests | 1 pull request and 1 approval |

## 6. The release artifact

The only thing the pipeline and the platform share. Stored in the registry
under the agent's path, addressed by digest:

- the image;
- the declaration, with a schema version;
- the runtime protocol version the image's SDK speaks;
- provenance naming the source repository, commit, agent and version, signed by
  the release pipeline's identity;
- attestations: test results, scripted scenario results, software bill of
  materials, vulnerability scan.

The schema is versioned and validated strictly: unknown keys are refused. It is
easier to loosen validation later than to tighten it.

## 7. Authority decisions per release

Tenant policy is platform configuration, owned by the operator and kept in
Kubani: which tool backends and tools may be granted, which models, budget
ceilings, which identity modes, and which kinds of change need review.

| The new version's authority | Outcome |
| --- | --- |
| Unchanged from the current version | Proceeds automatically |
| Changed, within what tenant policy allows without review | Proceeds automatically; the difference is recorded |
| Changed in a way tenant policy marks for review, for example a tool that writes, acting on a person's behalf, or a budget above the ceiling | Registered as pending. The author sees the exact difference. An approver approves in the registry. |
| Outside what the tenant allows | Refused. The pipeline reports failure. |

The comparison is one library. Continuous integration runs it as an early,
advisory check against a published copy of tenant policy; the registry runs it
as the authority. When they disagree, the registry wins.

## 8. Services and contracts

| Part | Its one job | Credentials it holds | Today |
| --- | --- | --- | --- |
| Registry | Record of agents and versions and their state; approve, pin, pull, roll back | Its own store | Files in Kubani written by a command-line tool and pull requests |
| Verifier | Check signature, provenance and attestations; sign a verdict | A verdict signing identity. Nothing else. | Inside the Registry Controller |
| Identity provisioner | Create and retire the agent's Keycloak client | Keycloak administration | Inside the Registry Controller |
| Runtime configuration | Pod template, compiled policy and budgets for the current version | Kubernetes writes in tenant namespaces | Inside the Registry Controller |
| Session interface | Start, status, cancel and report, with the caller's own token | Temporal client | `kubectl exec` into the runner pod |
| Session worker | Drive sandbox steps on Temporal | As today | The runner, plus the harness |
| Policy service | Runtime authorisation, token exchange, consent | As today | Unchanged in this plan |
| Conformance harness | Test tool with its own image | Test only | Inside the runner package |

Four of these are new deployments: the registry, the verifier, the identity
provisioner and the session interface. The verifier and the identity
provisioner are separated because one handles untrusted input and the other
holds an administrator credential. The authority comparison stays a library,
not a deployment.

The four contracts:

1. **The release artifact** (section 6), between the pipeline and the platform.
2. **Two authenticated interfaces**, registry and sessions, over HTTP with
   Keycloak tokens. An author needs no kubeconfig.
3. **A versioned runtime protocol** between the session worker and the SDK. The
   registry refuses a version outside the range the deployed worker supports.
4. **Activation state** on the release object. The provisioners watch it and
   react. No service calls another to cause an activation.

The registry keeps using Kubernetes objects as its store, so existing
`AgentRelease` objects stay valid. The schema needs additions, because it is
strict and drops unknown fields: optional fields on `AgentRelease` for the
version, the declaration, the runtime protocol version, the verdict, an
evaluation summary and the difference in authority; and one new kind that
records which version of an agent is current on each channel, because a flag on
each release cannot guarantee that at most one is current.

Two things in today's controller must change before a newer version can become
current automatically (checked 2026-11-11):

- A session is bound to its release by name when it is submitted, and nothing
  looks the release up again. But a release's readiness is recomputed from the
  single live `Agent` object, so changing an agent's declaration marks every
  older release as drifted and not ready, and a session still running on one of
  them is refused at its next sandbox. Compiling each release's policy from the
  declaration it carries removes this; until then, "sessions in flight finish
  on the version they started with" holds only while the declaration is
  unchanged.
- The per-agent rate limit is taken from whichever ready release is read last.
  With two ready releases of one agent the result is arbitrary. It must be
  taken from the current version.

## 9. Build and release on self-hosted runners

Facts that constrain the choice (checked 2026-11-11):

- The repositories belong to a personal account. A repository-level runner
  scale set serves one repository, and runner groups, which would let several
  repositories share one, exist only for organisations.
- A workflow cannot start a workflow in another repository without a stored
  token for that repository. The default token is scoped to its own repository.
- In a reusable workflow, the signing certificate's subject is the reusable
  workflow's own path, and the calling repository is carried in a certificate
  extension. The steps are defined entirely by the called workflow; the caller
  supplies inputs only.

Two ways to satisfy D1, D3 and D9 follow from that.

**Option A: the release runs in the agent repository's own pipeline.** A
workflow in the agent repository, on a merge to main, calls the platform's
reusable release workflow from zetra and runs it on a self-hosted scale set for
that repository.

- The scale set and its guard entry are generated from the trust registration,
  not written by hand. The registry credential is held on the runner, so no
  repository stores a password.
- The author sees the whole release, including the registry's result, in their
  own repository's run, because the last job runs inside the cluster and can
  read the registry. No extra token is needed to report results.
- The signature identifies the platform's workflow, and the verifier reads the
  calling repository from the certificate extension.
- Cost per trusted repository: one scale set (one listener pod) and one GitHub
  App installation by the repository's owner.
- The runner guard admits only a push to main from a trusted repository. A job
  the repository defines for itself on that runner could push to the registry
  but could not sign as the platform's workflow, so it could not produce
  anything the verifier accepts.

**Option B: one central pipeline in zetra.** A scheduled workflow in zetra
polls the trusted repositories for version bumps on main and builds on a single
scale set.

- Nothing is installed or stored per repository.
- A release starts on the next poll, not on the merge: five minutes at best and
  often later, and the run appears in zetra, not in the author's repository.
- Reporting a result on the author's commit needs a platform-held token with
  permission to write commit statuses on each repository.

Recommended: **Option A.** It is the literal meaning of D9, it gives the author
the result where they are already looking, and its per-repository cost is
generated. Option B stays available for a repository whose owner cannot install
the application.

In both, the build job runs the gate and builds with the platform's Dockerfile
and holds no signing identity of its own; pull request checks run on GitHub's
runners and need no cluster access. Both also serve the platform image builds
planned in pull request 420.

## 10. Verification and admission

The verifier checks that the artifact was signed by the platform's release
pipeline, that its provenance names a trusted repository and the commit that was
built, that the repository owns the agent name, and that every required
attestation is present and passing. It then signs a verdict for that digest.

Kyverno admits an agent pod only if a verdict from the verifier exists for the
image digest. The per-tenant signer regular expression, which today lists every
agent name in two files, is deleted.

What exists today (checked 2026-11-11): Kyverno v1.19.2 already admits agent
images through a `ClusterPolicy` that requires five attestations, each with
conditions on its content, including an evaluation attestation that must report
every case passed. Requiring one more attestation of a verdict type, signed by
the verifier's key, is an addition of the same shape. The verdict must repeat
the image digest, and the policy must check it. The Registry Controller also
verifies signatures itself and assumes a tag-shaped certificate subject; that
code becomes the verifier and loses the tag assumption, so there is one
verifier and not two.

## 11. Evaluation and activation

- **In continuous integration:** tests and scripted scenarios, with scripted
  model and tool replies. Deterministic, fast, required to merge. The release
  already attaches an evaluation attestation, and admission already refuses an
  image whose attestation reports a failed case; that stays.
- **On the cluster, before activation:** the registry runs the agent's
  evaluation suite and a smoke session as ordinary sessions against the built
  artifact. Results are compared with the current version's results. A
  regression beyond the declared tolerance stops activation and leaves the
  current version in place.
- **Preview channel:** a pre-release build registers into a preview tenant whose
  policy allows read-only tools, a small budget and no acting on a person's
  behalf. Promotion to the stable channel moves the same digest.
- **Rollback:** pin an earlier version in the registry. The previous version is
  never deleted.

Evaluation results are stored per version.

## 12. Roles and authorisation

| Role | May |
| --- | --- |
| Author | Publish previews, read status and results for their repository's agents |
| Approver | Approve pending versions. Not the author of the release being approved. |
| Runner | Start sessions for the agents they are granted |
| Operator | Trust repositories, set tenant policy, pin and pull versions |

Every route of the registry and session interfaces has an entry in a permission
table. A route without one is denied, and a test fails the build.

## 13. Operations

- One status view from pipeline to current version to recent sessions.
- Pull a version or disable an agent at once; the provisioners retire its
  identity.
- A scheduled export of registry state to durable storage, because git no
  longer lists versions and cluster storage has been lost before.
- Before a session worker upgrade, the registry lists current versions outside
  the new protocol range and blocks the rollout until they are resolved.

## 14. What is deleted and what stays

Deleted from Kubani once migration completes: `apps/agents/` (about 60 files),
the tenant signer pin, and the `sync`, `check-sync`, `stage` and `approve`
subcommands. Deleted from zetra: the composite release action. The workflow
rendered into agent repositories shrinks to a call to the platform's release
workflow.

Stays in Kubani: every platform service's manifests, tenant policy, the list of
trusted repositories, and `just agent state` and `run` as thin clients of the
new interfaces.

## 15. Phases

Each phase ends with something that can be checked, and can stop there.

| Phase | Work | Done when |
| --- | --- | --- |
| 0. Repair and foundations | Fix the preflight, model-free and `--release` items in section 3 (the runner item is resolved by phase 3). Clean-up items from the audit (section 17). Then, once the decisions in pull request 420 are made: build and sign platform images in continuous integration, and move the conformance harness out of the runner image. | A model-free agent runs. Preflight works against zetra-agents. Every test module runs. Platform images are built by a pipeline. |
| 1. Registry, read-only | The registry serves the existing release objects and a status view. No behaviour changes. | The status view agrees with `just agent ls` for every agent. |
| 2. Session interface | Start, status, cancel and report over HTTP. `just agent run` becomes its client. | A session completes with no `kubectl exec`. |
| 3. Platform release pipeline and verdict | The platform's release workflow (section 9), the verifier, and Kyverno admitting on the verdict, for one agent. The rate limit is taken from the current version. The old path stays for the others. | One agent is released by a merge and admitted on a verdict. |
| 4. Declaration with the release | Each release's policy is compiled from the declaration it carries, which removes the drift check. The registry decides authority per version. Approval moves into the registry. That agent's files leave Kubani. | A change of authority is approved without a Kubani pull request, and a session running on the previous version finishes. |
| 5. Evaluation and preview | Cluster-side evaluation before activation, the preview tenant, promotion by digest. | A regressed build is stopped automatically. |
| 6. Migrate the rest | One agent at a time, then delete what section 14 lists. | `apps/agents/` is gone. |

### Practices adopted from other projects

From Agent Substrate (commit `905e2a65`): a test run that fails when a
registered test did not run; the permission table of section 12; a threat table
kept as data with a generated copy checked for drift.

From Tsunami (commit `82a4b9e`), a sandbox runtime whose interface documents
were read; none of its code is used:

| Practice | Where it applies here | Phase |
| --- | --- | --- |
| One outcome shape. Every command and every interface call returns one JSON document with `ok`, and on failure an error whose code comes from one closed set, each code classed retryable or terminal, defined once in code and checked at run time. | The three operator tools now; the registry and session interfaces from their first version. Described in `docs/infrastructure/configuration/cli-contract.md`. | 0, then 1 and 2 |
| Examples as the executable contract. A corpus of valid and invalid examples, each invalid one beside the error it must produce, run by the test suite. | The tool-backend definitions and the agent declaration now; the release artifact (section 6) when it is defined. | 0, then 3 and 4 |
| Conformance as an ordinary command against a written contract, with capabilities grouped so that a part implements a whole group or none, and a missing group is reported before anything runs. | The conformance harness once it leaves the runner image; the runtime protocol between session worker and SDK (contract 3 of section 8), so that compatibility is a stated capability and not only a version range. | 0 (after pull request 420), then 3 |
| Verify a live sandbox against its declaration, returning a proof per check: what it may reach is reachable, what it may not is refused, and nothing secret is inside. | The registry's check before a version becomes current (section 11), alongside the evaluation and smoke session. | 5 |

Noted and not adopted: holding a request outside the allowlist until an
operator decides, which could help an author in the preview tenant discover the
grants an agent needs; and keeping every credential out of the sandbox by
fronting credential-bearing tools at the gateway, which is stricter than this
platform's short-lived agent token.

### Phase 0 progress, 2026-11-11

Done, on the branch that carries this document and, for the SDK, on the zetra
branch `delivery/model-free-agents`; none of it is merged or deployed:

- One test runner: every test module runs, and a run fails if a test file
  contributes no tests. The seven modules that nothing selected now run.
- `validate-gitops-build` builds all eight roots Flux reconciles, derived from
  the Flux Kustomizations.
- `just agent run` defaults to the most recently approved release;
  `check-sync` refuses an unknown name; failures of kubectl, gh and git state
  their cause; `cancel` exits 0 when accepted.
- `just agent-preflight` works against the workspace layout.
- Production commands no longer load conformance scripts by file path; the
  Keycloak administrator client is one module.
- The broken secret-generation scripts and unreferenced files are removed.
- The SDK runs an agent that declares no model, with the check, test kit,
  scaffold option and documentation to match.

Not done in phase 0: platform images built by a pipeline and the move of the
conformance harness out of the runner image, both waiting on the decisions in
pull request 420; the command-line tools' shared exit-code and output contract,
which phase 2 settles when the session interface defines it; and the
restructuring of the agent platform documentation.

## 16. To confirm before building

Confirmed by Al on 2026-11-11: a release is produced by continuous integration
and delivery on a merge to main (D9).

Assumed, for Al to confirm or reverse before phase 3:

1. Approval of a change of authority is a signed, recorded action in the
   registry in place of a reviewed pull request.
2. Option A of section 9, the release running in the agent repository's own
   pipeline on a generated scale set, is the improvement wanted for self-hosted
   builds.

Settled by reading the code and documentation on 2026-11-11, and folded into
sections 8 to 10:

- Kyverno can admit on the verifier's verdict with the policy kind already in
  use.
- A session is bound to its release at submission; the obstacle to automatic
  activation is the drift check, not the binding.
- The policy service's ledger is already behind an interface, so it can be
  split out later at modest cost. It is not split in this plan.
  `platform/budget-backend` is a test double, not the ledger.

Not yet verified:

- Whether the private certificate authority issues the certificate extension
  that names the calling repository, which Option A in section 9 relies on.
- Whether the runner guard can tell a job of the platform's reusable workflow
  from a job the calling repository defines itself.
- Whether one file can replace the two declaration files an author writes.
  The author-side review that informs this had not reported when this draft was
  written; nor had the tooling timings.

Risks:

- A central pipeline runs code from other people's repositories on a
  self-hosted runner. The build job must hold no credential and stay inside the
  existing sandboxed runner.
- Automatic activation moves trust from review to the gate. The gate has to be
  complete before phase 4 removes the pull requests.
- Four new deployments are four more images to build, sign and keep current.
  Phase 0 must make that cheap first.

## 17. Audit items independent of this redesign

Found by the audit, and worth doing whatever is decided above:

- `infrastructure/scripts/secrets.py`, `create_encrypted_secrets.py` and
  `setup_sops.py` are broken: `secrets.py` imports itself in place of the
  standard library module.
- Seven test modules are selected by no recipe and no workflow; four of them
  need pytest, which is not a dependency. Two more run locally and not in
  continuous integration.
- `mcp_registry/identity.py` loads its Keycloak client from a conformance
  fixture script by file path.
- `validate-gitops-build` builds seven of the eight roots Flux reconciles;
  `infrastructure/kyverno/policies` is missing.
- The three operator command-line tools disagree on exit codes, status casing
  and output shape. `cancel` exits 1 on success, `status` renames files on
  every call, and `check-sync` passes for an agent name that does not exist.
- `.kiro/`, `provision_cluster.sh` and `setup_ssh_key_single.sh` have no
  references. Seven manual conformance Job files sit in the live workloads
  directory.
- The agent platform documentation includes a 3,750-line specification, dated
  session handoffs and a continuation prompt; 36 of 83 documents under `docs/`
  are linked from no index.
