# Agent repository golden path — 2026-11-09

One layout for every agent repository, one lockfile and one Dockerfile per
repository, shared release machinery that lives in zetra, and a registration
step in Kubani, so that a person who creates a repository from the template can
deploy an agent without reading a handoff.

Decided with Al on 2026-11-09 in eight questions, each with options, costs and
tradeoffs. The chosen option is recorded here with the reason; the alternatives
are kept so the decision is not reopened by accident.

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
| 4 | What `lockSha256` hashes | **The root `uv.lock`**, the file `uv sync --locked --package` installs from. Kubani `stage` verifies the root path at `buildRevision`, falling back to `agents/<agent>/uv.lock` for releases built before the change. `tools/` stays outside the workspace so the lock holds only image dependencies. | Committed and verifiable with `git show`; nothing downstream interprets the hash per agent. Tradeoff accepted: any dependency change moves every agent's lock hash, so "did this agent change" reads from `buildRevision` and `manifestSha256`. Alternatives: committed per-agent export (13 generated files return); build-time export (not verifiable offline). |
| 5 | One-agent repository layout | **Same layout everywhere**: `agents/<name>/` and `<agent>/vX.Y.Z` tags even with one agent. | Zero conditional logic in release tooling, Kubani `sync` and `stage`, the Registry Controller or the signer pin; the pin differs between repositories only by name. Alternatives: root layout with `vX` tags (two layouts, two tag grammars, a controller change to a security check). |
| 6 | Where shared machinery lives | **In zetra**: `platform/agent-tools` (the `zetra_agents` package, pinning the same contracts commit as the controller), a composite action with the release steps, and templates for the Dockerfile, CI and a short `release.yml` shim that `zetra init` renders and `zetra-agents check` verifies. zetra-agents becomes an ordinary consumer. | One zetra pin per repository. The certificate subject keeps today's shape because a composite action runs in the caller's workflow; a reusable workflow would put zetra's workflow in the subject and move agent binding into Fulcio extensions that neither the controller nor Kyverno reads (Kyverno matches extensions only exactly). Alternatives: reusable workflow (controller, contracts and Kyverno change); keep in zetra-agents (a monorepo that is also the toolchain). |
| 7 | Onboarding a new person's repository | **Register the repository into an existing tenant** with `just agent register TENANT OWNER/REPO AGENT...`: regenerates the tenant pin with the repository bound to its agent names, adds the synced Agent directory, records the source in the sync header. The repository receives the shared `automation` registry credential as secrets. | Smallest newcomer step; the command takes the tenant as an argument so a per-tenant generator is purely additive later. Tradeoff accepted: shared namespace, Session Runner and payload key; isolation is by Agent identity. Alternatives: tenant per person (a generator and a Keycloak realm change become prerequisites); shared-then-promote (promotion is a new Agent, pin entry and releases). |
| 8 | SDK surface the template emits | **Retarget `zetra init` and zetra-template to the `agent_runtime` layout**; the `src/zetra` local harness is untouched for now. | What a newcomer scaffolds is exactly what is qualified, signed and running; matches zetra's written plan. Alternatives: keep both (default remains undeployable); teach the platform to run ADK (a sandbox SDK redesign). |

## 2. Target layout

The same tree for zetra-agents and for a repository created by `zetra init`.
Files marked *rendered* come from the templates in zetra and are verified by
`zetra-agents check`; everything else is authored.

```
<repo>/
  pyproject.toml            rendered: workspace members agents/*, [tool.uv.sources] agent-runtime = git+zetra@<sha>
  uv.lock                   one lock; its sha256 is AgentRelease.spec.lockSha256
  Dockerfile                rendered: ARG AGENT; targets runtime, fixture
  .dockerignore             rendered
  justfile                  rendered: setup, check, check-agent, build, policy-digest
  .github/workflows/ci.yml       rendered: check tools, per-agent lint/test/build matrix
  .github/workflows/release.yml  rendered shim: on tags */v*, calls X-McKay/zetra/.github/actions/agent-release@<sha>
  AGENTS.md                 rendered, with a marked section for repository-specific notes
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
(Dockerfile syntax 1.7) or, if that proves unavailable on the release runner,
with an explicit per-member copy emitted by the renderer.

## 3. Shared machinery in zetra

`platform/agent-tools` is today's `tools/zetra_agents` package moved and
generalised, added to `platform-check` and the platform CI matrix:

- Agent discovery is `agents/*/agent.yaml` in any repository root.
- `AgentDir.lock_path` becomes the repository root lock.
- `REQUIRED` drops `Dockerfile` and `uv.lock` per agent; a repository-level
  check requires the rendered files and verifies them against the templates.
- `FIXTURES` next to `NETWORK_ALLOWED`; `zetra-agents image-target <agent>`
  prints `runtime` or `fixture`.
- `zetra-agents render [--check]` writes or verifies the rendered files.
- `preflight` keeps its `--kubani PATH` argument; it is an operator tool run
  from a Kubani checkout, not a newcomer step.
- The justfile test that copies zetra-agents' justfile moves with the justfile
  template.

`.github/actions/agent-release` is a composite action holding the steps of
today's `release.yml` job: resolve the agent from the tag, registry login,
install cosign, syft and grype from the mirror by digest, run the release
script, publish the release assets. The script and `release.sh` move into the
action. Inputs: registry (default `registry.almckay.io/agents`), the registry
credential pair. The calling repository's `release.yml` is the rendered shim.

`agent_platform.signing.subject_regexp_for` accepts several repositories, each
with its own agent names, and emits one anchored expression with the
alternation inside a group, as the existing soundness test requires. The
Registry Controller and Kyverno match the expression as they do now; no
controller change.

`zetra init NAME` renders a repository with one agent from the templates. The
provenance gate keeps its role with a new referent: the `agent-runtime`
revision that passed conformance on the cluster. `zetra check` and
`zetra test` delegate to `zetra-agents check` and pytest on the new layout;
the ADK template tree under `src/zetra/templates/agent` is replaced.

## 4. Release identity and pins

Unchanged shape: issuer `https://token.actions.githubusercontent.com`, subject
`https://github.com/<owner>/<repo>/.github/workflows/release.yml@refs/tags/<agent>/v...`,
agent name in the tag equal to `spec.agent`. A tenant pin lists each registered
repository with the agents it may sign:

```
^https://github\.com/X-McKay/(?:zetra-agents/\.github/workflows/release\.yml@refs/tags/(?:conformance|...|investigator)|my-agent/\.github/workflows/release\.yml@refs/tags/(?:my-agent))/v[0-9][A-Za-z0-9.+-]*$
```

Trust is per repository: write access to a registered repository is release
authority for exactly the agents named for it, in exactly one tenant. Staging
and approval remain reviewed Kubani PRs; `just agent approve` keeps its live
gates. Image paths stay `agents/<agent>`, so agent names are unique across
tenants; `register` refuses a name already registered to another repository.

## 5. Kubani changes

- `agent_ops/stage.py`: `lockSha256` is verified against `uv.lock` at
  `buildRevision`, falling back to `agents/<agent>/uv.lock` when the root file
  is absent at that revision.
- `agent_ops/sync.py`: the header's path becomes `<repo> <path>` generally;
  `check-sync` and `stage` read the repository from the header instead of a
  global `--repo` default, which stays as an override.
- `just agent register TENANT OWNER/REPO AGENT... --source PATH`: regenerates
  the tenant's signer annotation and the `kyverno/tenant-signers` entry through
  `agentctl signer-annotations` with every registered repository, creates
  `apps/agents/<tenant>/<agent>/` by `sync`, appends to the kustomization, and
  writes the registry inventory row. One PR per registration.
- `tests/test_tenant_signers.py` already asserts the two pin copies are equal
  and sound; it gains a case for a two-repository pin.
- Docs: `agent-operations.md` gains register and the newcomer path;
  `.claude/rules/agent-platform.md` notes that the lifecycle is unchanged and
  that `lockSha256` is the repository lock.

## 6. Sequence of pull requests

Each step is verified before the next starts. No release tag is pushed before
step 5, and that step needs Al's go-ahead.

| Step | Repository | Change | Verification |
| --- | --- | --- | --- |
| 1 | zetra | `platform/agent-tools` (moved package, discovery, root lock, `FIXTURES`, `image-target`, `render --check`), composite action, templates, multi-repository `subject_regexp_for`. | Unit tests in `platform-check`; render a throwaway repository, `check` passes; build the throwaway image and the investigator image from the template Dockerfile and compare the `/app` trees with the currently released images. |
| 2 | zetra | `zetra init` renders the new layout; `check` and `test` delegate; docs. | `zetra init` into a temp dir, `just check`, `docker build` both targets where applicable. |
| 3 | zetra-agents | Migrate to the rendered layout: root workspace and lock, root Dockerfile, shim and CI, delete 13 Dockerfiles and 13 lockfiles, replace `tools/` with the pinned `agent-tools`. | `just check` across 13 agents; images for investigator and one fixture built locally with identical `/app` trees to current images; `zetra-agents render --check` clean; CI green. |
| 4 | kubani | `stage` lock fallback, header generalisation, `register`, docs, tests. | `just test-agent-ops`; `check-sync` still clean against zetra-agents main; signer tests pass with a regenerated, byte-identical pin for zetra-agents. |
| 5 | zetra-agents, kubani | First release on the new pipeline: `investigator/v0.1.4` from merged main, then `stage`, then `approve`, then `just agent run investigator`. | Release assets verified by `stage`; `approve` gates pass on the live object; one completed session with cleanup confirmed. One tag at a time. |
| 6 | zetra-template | The repository becomes the rendered output of `zetra init`, marked as a GitHub template repository and re-rendered by CI. | CI renders from the pinned zetra and diffs clean. |

## 6a. Status (2026-11-09, end of day)

| Step | Pull request | State |
| --- | --- | --- |
| 1, 2 | zetra [#72](https://github.com/X-McKay/zetra/pull/72) | open; `platform/agent-tools`, `agent-release` action, multi-repository pins, `zetra init` retargeted; verified by scaffold lock+build and image equivalence |
| 3 | zetra-agents [#36](https://github.com/X-McKay/zetra-agents/pull/36) | draft, pinned to #72's head; re-pin to the merged zetra commit (`uv lock`, `zetra-agents render`) before review |
| 4 | kubani [#409](https://github.com/X-McKay/kubani/pull/409) | open; independent of the zetra merges |
| 5 | none yet | waits for 1 to 4 and a go-ahead; `investigator/v0.1.4` from merged zetra-agents main |
| 6 | none yet | waits for 1 and 2 to merge so the template is rendered from a main commit |

Deviation from decision 4 worth knowing: the `zetra-agents` tooling and the contracts
are dev dependencies of the workspace root, so they are in the one `uv.lock` (and
therefore in `lockSha256`) although `--no-dev` keeps them out of the images. The
alternative, running the tooling unlocked through `uvx`, made the release tooling
unreproducible; a locked dev group was judged the better trade. Images are unaffected.

## 7. The newcomer path

```
uvx --from 'git+https://github.com/X-McKay/zetra@<release>' zetra init my-agent --name my-agent
cd my-agent && just check
# create the GitHub repository; the operator adds the registry credential as secrets
git tag my-agent/v0.1.0 && git push --tags
```

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
