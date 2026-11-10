# Agent repository golden path — 2026-11-09

One layout for every agent repository, one lockfile and one Dockerfile per
repository, shared release machinery that lives in zetra, and a registration
step in Kubani, so that a person who creates a repository from the template can
deploy an agent without reading a handoff.

Decided with Al on 2026-11-09 in eight questions, each with options, costs and
tradeoffs. The chosen option is recorded here with the reason; the alternatives
are kept so the decision is not reopened by accident.

Terms: *spec* is the Agent Runtime Platform specification
(`docs/infrastructure/configuration/agent-runtime-platform-spec.md`; section
11.7 is the agent manifest). *Handoff* is a session handoff document in the same
folder. *Phase B conformance* and *qualification* are the platform test campaign
recorded there; the campaign is paused. *The security review* is the reviewed
Kubani PR that approves an AgentRelease. *Kyverno Rule 1* is the admission rule
that verifies an agent image's keyless signature against the tenant's pin. The
`automation` registry credential is the shared CI account described in
`docs/infrastructure/configuration/registry.md`. Day-to-day commands are in
`docs/infrastructure/configuration/agent-operations.md`.

## 0. TL;DR

- zetra-agents today: 13 agents, 13 identical dependency sets, 13 lockfiles
  pinning the same `agent-runtime` commit, 13 Dockerfiles (4 plain, 9
  conformance fixtures that override the SDK boundary driver), 9 hand-written
  fake MCP harnesses, and tool names repeated in code, `agent.yaml` and
  `deploy/agent.yaml`. An SDK bump is a 26-file PR.
- The scaffolding that exists (`zetra init`, zetra-template) emits a different
  SDK surface (Google ADK, OpenShell) from the one every deployed agent uses
  (`agent_runtime`). zetra's own platform doc says that surface stays only until
  Phase B conformance passes, which it has.
- Target: a repository is a uv workspace whose members are `agents/<name>/`;
  one root `uv.lock` is the image lock; one root Dockerfile with `runtime` and
  `fixture` targets; the tooling, release steps and file templates live in zetra
  and are consumed by a pinned composite action and rendered, verified files; a
  one-agent repository is a monorepo with one member; Kubani registers a
  repository into a tenant with one command.
- Nothing on the cluster changes until an agent next releases. Historical
  releases are immutable and untouched.

## 1. Decisions

| # | Question | Decision | Why, in one line |
| --- | --- | --- | --- |
| 1 | 13 lockfiles to one | **uv workspace at the repository root**, members `agents/*`, SDK git source declared once in root `[tool.uv.sources]`. | Standard uv feature; dependency sets are already identical; removes 12 places to be wrong. Alternatives: bump-by-tooling (one PR, not one source of truth); single project (package names collide: `conformance` x2, `budget_fixture` x4). |
| 2 | 13 Dockerfiles to one | **One root Dockerfile, `ARG AGENT`, targets `runtime` and `fixture`**. `fixture` is `FROM runtime`, copies `agents/$AGENT/verify_image.py`, replaces the installed `step.py` with the agent package's, runs the verifier, adds a generic label. | The 4 plain Dockerfiles differ only by name; the 9 fixtures share one structure. Nothing reads the fixture label, and every `verify_image.py` already asserts its override constant, so the target needs no per-fixture arguments. Alternatives: two Dockerfiles (duplicated pins); leave fixtures alone (9 pins rot). |
| 3 | Where "this is a fixture" is declared | **A `FIXTURES` set in the tooling beside `NETWORK_ALLOWED`**. `check` refuses a non-fixture that ships `verify_image.py` or a package `step.py`, and a fixture that lacks them. | Declaration and gate are one reviewed line; normal agents declare nothing; the set is frozen while qualification is paused. Alternatives: pyproject table (two edits per fixture); infer from files (implicit). |
| 4 | What `lockSha256` hashes | **The root `uv.lock`**, the file `uv sync --locked --package` installs from. Kubani `stage` verifies the root path at `buildRevision`, falling back to `agents/<agent>/uv.lock` for releases built before the change. The tooling and contracts are a locked dev group of the workspace root (see 6a for why this departs from the first intent of keeping the lock to image dependencies). | Committed and verifiable with `git show`; nothing downstream interprets the hash per agent. Tradeoff accepted: any dependency change moves every agent's lock hash, so "did this agent change" reads from `buildRevision` and `manifestSha256`. Alternatives: committed per-agent export (13 generated files return); build-time export (not verifiable offline). |
| 5 | One-agent repository layout | **Same layout everywhere**: `agents/<name>/` and `<agent>/vX.Y.Z` tags even with one agent. | Zero conditional logic in release tooling, Kubani `sync` and `stage`, the Registry Controller or the signer pin; the pin differs between repositories only by name. Alternatives: root layout with `vX` tags (two layouts, two tag grammars, a controller change to a security check). |
| 6 | Where shared machinery lives | **In zetra**: `platform/agent-tools` (the `zetra_agents` package, pinning the same contracts commit as the controller), a composite action with the release steps, and templates for the Dockerfile, CI and a short `release.yml` shim that `zetra init` renders and `zetra-agents render --check` verifies. zetra-agents becomes an ordinary consumer. | One zetra pin per repository. The certificate subject keeps today's shape because a composite action runs in the caller's workflow; a reusable workflow would put zetra's workflow in the subject and move agent binding into Fulcio extensions that neither the controller nor Kyverno reads (Kyverno matches extensions only exactly). Alternatives: reusable workflow (controller, contracts and Kyverno change); keep in zetra-agents (a monorepo that is also the toolchain). |
| 7 | Onboarding a new person's repository | **Register the repository into an existing tenant** with `just agent register TENANT OWNER/REPO AGENT...`: regenerates the tenant pin with the repository bound to its agent names, adds the synced Agent directory, records the source in the sync header. The repository receives the shared `automation` registry credential as secrets. | Smallest newcomer step; the command takes the tenant as an argument so a per-tenant generator is purely additive later. Tradeoff accepted: shared namespace, Session Runner and payload key; isolation is by Agent identity. Alternatives: tenant per person (a generator and a Keycloak realm change become prerequisites); shared-then-promote (promotion is a new Agent, pin entry and releases). |
| 8 | SDK surface the template emits | **Retarget `zetra init` and zetra-template to the `agent_runtime` layout**; the `src/zetra` local harness is untouched for now. | What a newcomer scaffolds is exactly what is qualified, signed and running; matches zetra's written plan. Alternatives: keep both (default remains undeployable); teach the platform to run ADK (a sandbox SDK redesign). |

## 2. Target layout

The rendered core is the same for zetra-agents and for a repository created by
`zetra init` (zetra-agents additionally carries `legacy/`, `docs/` and a
`CLAUDE.md` link). Files marked *rendered* come from the templates in zetra and
are verified by `zetra-agents render --check`; files marked *seeded* are written
once by `init` and then owned by the repository; everything else is authored.

```
<repo>/
  pyproject.toml            rendered: workspace members agents/*, [tool.uv.sources] agent-runtime = git+zetra@<sha>
  uv.lock                   one lock; its sha256 is AgentRelease.spec.lockSha256
  Dockerfile                rendered: ARG AGENT; targets runtime, fixture
  .dockerignore             rendered
  justfile                  rendered: setup, check, check-agent, build, policy-digest, preflight
  .github/workflows/ci.yml       rendered: check tools, per-agent lint/test/build matrix
  .github/workflows/release.yml  rendered shim: on tags */v*, calls X-McKay/zetra/.github/actions/agent-release@<sha>
  AGENTS.md, README.md, .gitignore   seeded once, never checked
  agents/<name>/
    pyproject.toml          authored: name, version, dependencies = ["agent-runtime"], package = false
    agent.yaml              authored: the image manifest (spec 11.7)
    deploy/agent.yaml       authored: the Agent the security review approves
    src/<package>/          authored: agent.py, instructions
    tests/                  authored
    verify_image.py         fixtures only
```

Contract points, all unchanged from today's images:

- `/app/agent.yaml`, `/app/<package>/`, `/app/.venv`, UID 1500, entrypoint
  `agent_runtime.wait`. The shared Dockerfile copies `agents/$AGENT/src/` to
  `/app/`, so the package name never appears in the Dockerfile.
- `uv sync --locked --no-dev --package zetra-agent-<name>` in the build stage,
  from the root lock.
- The `.dockerignore` keeps `tools/`, `legacy/`, tests and `.git` out of the
  build context.

The build context requires the root `pyproject.toml`, `uv.lock` and each
member's `pyproject.toml`; the Dockerfile copies them with `COPY --parents`
from the `docker/dockerfile:1.7-labs` frontend, pinned by digest.

## 3. Shared machinery in zetra

`platform/agent-tools` is today's `tools/zetra_agents` package moved and
generalised, added to `platform-check` and the platform CI matrix:

- Agents are the directories under `agents/`; `check` requires each to hold
  `agent.yaml`, `deploy/agent.yaml` and `pyproject.toml`.
- `AgentDir.lock_path` becomes the repository root lock.
- `REQUIRED` drops `Dockerfile` and `uv.lock` per agent; `check` also requires
  the root `pyproject.toml` and `uv.lock`, and `render --check` verifies the
  rendered files against the templates at the pinned commit.
- `FIXTURES` next to `NETWORK_ALLOWED`; `zetra-agents image-target <agent>`
  prints `runtime` or `fixture`.
- `zetra-agents render [--check]` writes or verifies the rendered files.
- `preflight` keeps its `--kubani PATH` argument and gains `--repository`
  (default: the origin remote); the rendered justfile exposes it as
  `just preflight`, for an operator with a Kubani checkout before tagging.
- The justfile test that copies zetra-agents' justfile moves with the justfile
  template.

`.github/actions/agent-release` is a composite action holding the steps of
today's `release.yml` job: resolve the agent from the tag, registry login,
install cosign, syft and grype from the mirror by digest, run `release.sh`
(which lives in the action; the release artifacts module stays
`zetra_agents.release` in agent-tools), publish the release assets. Inputs:
the registry credential pair, `registry` (default
`registry.almckay.io/agents`), `vuln-exceptions`, `uv-version`,
`python-version`. The calling repository's `release.yml` is the rendered shim,
which also reads the repository variables `RELEASE_RUNNER` and
`VULN_EXCEPTIONS`.

A new `agent_platform.signing.subject_regexp_for_sources` (and
`agentctl signer-annotations --source OWNER/NAME=agent,...`) accepts several
repositories, each with its own agent names, and emits one anchored expression
with the alternation inside a group, as the existing soundness test requires;
one repository gives exactly `subject_regexp_for`. The Registry Controller and
Kyverno match the expression as they do now; no controller change.

`zetra init PATH --name NAME [--owner EMAIL]` renders a repository with one
agent from the templates, pinned to the zetra commit the CLI came from
(`--zetra-rev` overrides). The Google ADK / OpenShell scaffold and its
provenance gate stay behind `zetra init --harness`, and `zetra check`, `test`,
`build`, `release` and `eval` remain the local-harness project commands; a
platform repository uses its rendered `just check`. Retargeting or retiring
those commands is deferred.

## 4. Release identity and pins

Unchanged shape: issuer `https://token.actions.githubusercontent.com`, subject
`https://github.com/<owner>/<repo>/.github/workflows/release.yml@refs/tags/<agent>/v...`,
agent name in the tag equal to `spec.agent`. A tenant pin lists each registered
repository with the agents it may sign:

```
^https://github\.com/(?:X-McKay/my-agent/\.github/workflows/release\.yml@refs/tags/(?:my-agent)|X-McKay/zetra-agents/\.github/workflows/release\.yml@refs/tags/(?:conformance|...|investigator))/v[0-9][A-Za-z0-9.+-]*$
```

Branches are sorted by repository and each carries its full `owner/name`, so a
repository under another owner is one more branch. With several repositories a
repository must name its agents; a wildcard branch is refused.

Trust is per repository: write access to a registered repository is release
authority for exactly the agents named for it, in exactly one tenant. Staging
and approval remain reviewed Kubani PRs; `just agent approve` keeps its live
gates. Image paths stay `agents/<agent>`, so agent names are unique across
tenants; `register` refuses a name already registered to another repository.

## 5. Kubani changes

- `agent_ops/stage.py`: `lockSha256` is verified against `uv.lock` at
  `buildRevision`, falling back to `agents/<agent>/uv.lock` when the root file
  is absent at that revision.
- `agent_ops/sync.py`: the header already records `<repo>`; `sync`, `stage`
  and `approve` now default the repository from it, `--repo` is an override,
  and moving an agent to another repository needs `--allow-repo-change`.
- `just agent register TENANT OWNER/REPO AGENT... --source PATH`: creates
  `apps/agents/<tenant>/<agent>/` by `sync`, lists it in the agents
  kustomization, and regenerates the tenant's signer annotation and the
  `kyverno/tenant-signers` entry from the sync headers of the tenant's
  committed Agents (Kubani's `register.subject_regexp` reproduces the contracts
  expression; a test asserts the derived pin equals the committed one byte for
  byte). One PR per registration.
- `check-sync` also verifies both pin copies equal the derivation, so a
  hand-edited pin or a pinned tenant without committed Agents fails
  `validate-local` and CI. New cases live in `tests/test_agent_ops.py`.
- Docs: `agent-operations.md` gains register and the newcomer path;
  `.claude/rules/agent-platform.md` notes that the lifecycle is unchanged and
  that `lockSha256` is the repository lock.

## 6. Sequence of pull requests

Each step is verified before the next starts. No release tag is pushed before
step 5, and that step needs Al's go-ahead.

| Step | Repository | Change | Verification |
| --- | --- | --- | --- |
| 1 | zetra | `platform/agent-tools` (moved package, discovery, root lock, `FIXTURES`, `image-target`, `render --check`), composite action, templates, `subject_regexp_for_sources`. | Unit tests in `platform-check`; render a throwaway repository, `check` passes; build the throwaway image and the investigator image from the template Dockerfile and compare the `/app` trees with the currently released images. |
| 2 | zetra | `zetra init` renders the new layout; the harness scaffold moves behind `--harness`; docs. | `zetra init` into a temp dir, `just check`, `docker build` both targets where applicable. |
| 3 | zetra-agents | Migrate to the rendered layout: root workspace and lock, root Dockerfile, shim and CI, delete 13 Dockerfiles and 13 lockfiles, replace `tools/` with the pinned `agent-tools`. | `just check` across 13 agents; images for investigator and one fixture built locally with identical `/app` trees to current images; `zetra-agents render --check` clean; CI green. |
| 4 | kubani | `stage` lock fallback, header generalisation, `register`, docs, tests. | `just test-agent-ops`; `check-sync` still clean against zetra-agents main; signer tests pass with a regenerated, byte-identical pin for zetra-agents. |
| 5 | zetra-agents, kubani | First release on the new pipeline: `investigator/v0.1.4` from merged main, then `stage`, then `approve`, then `just agent run investigator`. | Release assets verified by `stage`; `approve` gates pass on the live object; one completed session with cleanup confirmed. One tag at a time. |
| 6 | zetra-template | The repository becomes the rendered output of `zetra init`, marked as a GitHub template repository and re-rendered by CI. | CI renders from the pinned zetra and diffs clean. |

## 6a. Status (2026-11-10)

| Step | Pull request | State |
| --- | --- | --- |
| 1, 2 | zetra [#72](https://github.com/X-McKay/zetra/pull/72), [#74](https://github.com/X-McKay/zetra/pull/74) | both merged (#72 `543053a1`, #74 `0260748c`): `platform/agent-tools`, `agent-release` action, multi-repository pins, `zetra init` retargeted (harness behind `--harness`); #74 added `init` lock, git and checklist, `rename`, the action YAML fix; verified by scaffold lock+build and image equivalence |
| 3 | zetra-agents [#36](https://github.com/X-McKay/zetra-agents/pull/36), [#37](https://github.com/X-McKay/zetra-agents/pull/37), [#38](https://github.com/X-McKay/zetra-agents/pull/38) | #36 merged (`4c0184c3`), pinned to zetra `543053a1`; #37 merged (`654e53da`), re-pinned to zetra `0260748c`; #38 merged (`e87022f1`), re-pinned to zetra `9d8601c1`; [#39](https://github.com/X-McKay/zetra-agents/pull/39) merged (`1b69fb08`), re-pinned to zetra `677a2dec` |
| 4 | kubani [#409](https://github.com/X-McKay/kubani/pull/409) | merged (`fae4425b`) |
| 5 | tags `investigator/v0.1.4` and `investigator/v0.1.5`; kubani [#411](https://github.com/X-McKay/kubani/pull/411), [#412](https://github.com/X-McKay/kubani/pull/412) | `v0.1.4` failed at job set-up: the composite action's `run` line was not valid YAML; fixed in zetra #74. Nothing was built or signed. `v0.1.5`, built at zetra-agents `654e53da`, published `investigator-2026-11-09-93383f45`; staged by #411 (`0ee7d6fc`), approved by #412 (`0f35e5e0`), Ready on the cluster. The closing `just agent run investigator` is not done; see below |
| 6 | zetra-template [#8](https://github.com/X-McKay/zetra-template/pull/8), [#9](https://github.com/X-McKay/zetra-template/pull/9) | #8 merged (`dbc56b25`): the repository is what `zetra-agents init` renders, with the agent named `my-agent`; it is marked a GitHub template, and its `Template` workflow re-renders from the pinned zetra commit and diffs. #9 merged (`3174962c`): re-rendered from zetra `9d8601c1`; [#10](https://github.com/X-McKay/zetra-template/pull/10) merged (`855310de`): re-rendered from zetra `677a2dec` |

Every pull request in the sequence is merged. What remains is the last check of
step 5, one completed session with cleanup confirmed. It cannot be made with
investigator: both investigator releases require delegation, and no supported
path produces the grant handle `just agent run` then needs (see "Grant handles"
in [agent-operations.md](../../infrastructure/configuration/agent-operations.md#grant-handles)).
`investigator/v0.1.5` is the only release published in zetra-agents since step 3, so
no session has run from an image the shared pipeline built. No replacement
check is selected.

Where what shipped differs from the plan:

- Step 5 names `investigator/v0.1.4`. The first release on the new pipeline is
  `v0.1.5`, for the reason in the table, and its session check is open.
- Step 6 names `zetra init`. The template is the output of `zetra-agents init`
  from zetra `platform/agent-tools`, the command section 7 gives.
- Decision 4: the `zetra-agents` tooling and the contracts are dev dependencies
  of the workspace root, so they are in the one `uv.lock` (and therefore in
  `lockSha256`) although `--no-dev` keeps them out of the images. The
  alternative, running the tooling unlocked through `uvx`, made the release
  tooling unreproducible; a locked dev group was judged the better trade. Images
  are unaffected.
- Section 8 puts the test kit, the evidence and report helper, and declaring
  tools once outside this plan. zetra
  [#75](https://github.com/X-McKay/zetra/pull/75) (`9d8601c1`) shipped a test
  kit, the helper and tool declaration, in a different shape from the wording
  there: the kit is `zetra_agents.testing` and a pytest plugin in
  `platform/agent-tools`, not `agent_runtime.testing`; the helper is
  `agent_runtime.report`; and `zetra-agents render` derives the manifest
  `tools:` list from the code, while the MCP grants in `deploy/agent.yaml` stay
  hand-written. The same pull request added `zetra-agents run` (`just run`), a
  local session loop this plan does not mention.

## 7. The newcomer path

```
uvx --from 'git+https://github.com/X-McKay/zetra@<commit>#subdirectory=platform/agent-tools' \
  zetra-agents init my-agent --name my-agent --owner you@example.com
cd my-agent && just setup && just check
git add -A && git commit -m "my-agent"
# create the GitHub repository and push main; in its settings add the secrets
# REGISTRY_USERNAME and REGISTRY_PASSWORD (the operator supplies them) and the
# variable RELEASE_RUNNER (the self-hosted runner that reaches the registry)
git tag my-agent/v0.1.0 && git push --tags      # from merged main, one tag at a time
```

The tooling alone installs from git in seconds; `init` renders the repository, runs
`uv lock` and `git init -b main`, and prints this checklist with the operator steps
below filled in. A repository created from the GitHub template instead carries a
placeholder agent: `uv run --locked zetra-agents rename <placeholder> my-agent`.

Operator, once per repository:

```
just agent register tenant-test OWNER/my-agent my-agent --source ~/git/my-agent   # PR
```

Operator, per release, unchanged:

```
just agent stage my-agent my-agent/v0.1.0        # PR; Flux; signature and attestations verified live
just agent approve my-agent-2026-11-...-<8hex>   # PR
just agent run my-agent --task "..."
```

The scaffolded agent declares `identity.mode: agent`, so this `run` takes no
grant handle. An agent that requires delegation cannot be run yet: no supported
path produces a grant handle today. "Grant handles" in
[agent-operations.md](../../infrastructure/configuration/agent-operations.md#grant-handles)
says who would perform each step and what exists.

## 8. Not in this plan

- A tenant generator (namespace, pin, runner, reconciler, volume, Temporal
  namespace, payload key, Keycloak clients). `register` is written so this is
  additive.
- The SDK test kit (`agent_runtime.testing`: fake MCP, context builder, image
  layout fixture, a conformance test every agent inherits) and the evidence and
  report helper. Both are agent-experience work on the same layout and follow
  once step 3 lands.
- Declaring tools once in code and rendering the manifest `tools:` list and the
  Agent's MCP grants from it. Needs the test kit first.
- A reusable workflow in place of the composite action. Worth revisiting only if
  the controller learns to read Fulcio's source-repository extensions.
- Per-repository registry accounts. Credential issuance is Al's step.

Status (2026-11-10): work on the second and third items has since shipped in
zetra #75; section 6a records how it differs from the wording above.

## 9. Risks and how each is held

- **Shared fixture override path.** The `FIXTURES` gate in `check` is the only
  thing keeping a normal agent off the `fixture` target; it is tested
  explicitly, and CI builds every agent with the target the tooling prints.
- **Rendered files edited by hand.** `zetra-agents render --check` runs in
  every repository's CI; a drifted file fails the build the same way an
  unsynced Agent fails Kubani's `check-sync`.
- **`lockSha256` meaning changes.** Documented in the rules file; `stage`
  handles both shapes by revision, so nothing historical is re-verified under
  the new rule.
- **Relocating the tooling.** The package moves with its tests; zetra-agents
  pins the zetra commit that contains it, so step 3 cannot land before step 1.
- **Image equivalence.** Steps 1 and 3 compare `/app` trees, not digests, since
  timestamps differ; the Dockerfile CI step that prints the image's tools from
  `agent_runtime.step` stays as the runtime-level check.
