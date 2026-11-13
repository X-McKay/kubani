# ARC runners

Self-hosted GitHub Actions runners (Actions Runner Controller 0.15.0) for
release jobs that need in-cluster reach to `registry.almckay.io` and the
private Sigstore. Two scale sets, both authenticated by the `kubani-arc` GitHub
App (`github-app.enc.yaml`):

- `kubani-zetra-agents`, for the public repo X-McKay/zetra-agents
  (`scale-set-zetra-agents.yaml`, guard in `job-guard.yaml`).
- `kubani-zetra`, for the public repo X-McKay/zetra, which builds the platform
  images (`scale-set-zetra.yaml`, guard in `job-guard-zetra.yaml`). The two
  have the same sandbox, build sidecar and resources; `kubani-zetra` allows one
  runner (the other allows two), has its own guard, and holds a registry login.

The sections below describe `kubani-zetra-agents` unless they say otherwise;
`kubani-zetra` has its own section at the end.

## Who can run a job here

`X-McKay/zetra-agents` is public. A repo-level scale set has no runner group,
and a `pull_request` run uses the workflow file from the PR, so a fork PR can
ask for `runs-on: kubani-zetra-agents`. Three layers stop it:

1. **Runner-side guard (this directory, `job-guard.yaml`).** Each runner pod
   has a job-started hook that the runner executes before any step. It fails
   the job unless all of the following are true:
   - the repository is X-McKay/zetra-agents,
   - the event is `push`,
   - the ref is `refs/tags/<agent>/v<version>`, and
   - the workflow is `.github/workflows/release.yml` at that tag.

   The hook reads only the `GITHUB_*` values that the runner derives from the
   job, and a workflow's own `env:` is not passed to hooks. A fork PR can
   rewrite its workflow, but it cannot rewrite this check.
2. **Kata.** Runner pods are Kata VMs, so the privileged dockerd is root in a
   guest kernel and not on rig0. NetworkPolicies still apply to them
   (`netpol.yaml`).
3. **GitHub settings on X-McKay/zetra-agents**, set by the repo owner:
   - Settings, Actions, General, "Approval for running fork pull request
     workflows from contributors": **Require approval for all external
     contributors**.
   - Settings, Rules, Rulesets: a **tag ruleset** on `*/v*` that restricts
     creation, update and deletion to the owner (bypass: repository admin
     only). Pushing a release tag is the only event the guard admits, so this
     ruleset decides who can run a job here.
   - Settings, Actions, General, Workflow permissions: **Read repository
     contents** by default. release.yml asks for `id-token: write` and
     `packages`/`attestations` itself.

## After merge

- Set the zetra-agents repository variable `RELEASE_RUNNER=kubani-zetra-agents`.
- Confirm on the cluster, before the first release:
  - dockerd starts inside the Kata guest.
  - `docker run --privileged -v /:/host` sees only the guest filesystem.
  - A non-release job (for example a `workflow_dispatch` test workflow that
    targets the runner) fails at "Set up runner" with
    `kubani runner guard: ... may not use this runner`.

## Nested build network MTU

The dind daemon inherits `/sys/class/net/eth0/mtu` from its Kata guest at startup
and applies it to Docker's default bridge with `--mtu`. This follows the actual
runner network on each node instead of pinning a cluster-specific value. Missing
or invalid MTU data prevents daemon startup. The wrapper then executes the
original pinned image entrypoint, preserving its ordinary dockerd setup.

On 2026-11-08 a runner had guest MTU 1230 but Docker bridge/container MTU 1500.
A public package-index transfer completed quickly from the runner while nested
build apt transfers stalled. Correcting the nested MTU addresses that mismatch;
it does not establish the cause of historical dind memory growth or OOMs.
The setting covers the default bridge; separately created Docker networks need
their own matching MTU configuration. Existing runner isolation, job guards and
network policies continue to apply. Only new ephemeral runners pick up this
startup change; active jobs need not be restarted.

## kubani-zetra (platform image builds)

Runs the zetra release workflow that builds, pushes and (in a later phase)
signs the images under `registry.almckay.io/platform/`. Plan:
`docs/plans/ideas/2026-11-10-platform-image-ci-signing.md`, Phase 1. Workflows
select it with `runs-on: kubani-zetra`, written in the workflow file. At most
one runner, none idle.

### Who can run a job here

X-McKay/zetra is public, so the same reasoning as above applies. The guard in
`job-guard-zetra.yaml` (a separate ConfigMap, mounted only by this scale set)
fails the job unless all four are true:

- the repository is X-McKay/zetra,
- the event is `push`,
- the ref is `refs/heads/main`, and
- the workflow reference is exactly
  `X-McKay/zetra/.github/workflows/platform-release.yml@refs/heads/main`.

It reads only `GITHUB_*` values the runner sets. These settings on the zetra
repository back it, and are set by the repository owner:

- **`main` is protected with no bypass**: changes reach it only through a pull
  request with required checks, and force pushes and deletion are blocked. A
  push to `main` runs the workflow file that is on `main`, so the guard's
  admission is only as strong as this protection. Whether administrators are
  bound, and whether a second approval is required, is not yet decided.
- Settings, Actions, General, Workflow permissions: **Read repository contents**
  by default. The release workflow asks for `id-token: write` itself.
- Settings, Actions, General, "Approval for running fork pull request
  workflows from contributors": **Require approval for all external
  contributors**.

A job the guard admits can read the registry login below; the guard and the
branch protection are what limit that.

**What the protection of `main` rests on.** "No bypass" covers people and
pushes. It does not cover these, which are therefore part of the protection:

- **The kubani-arc App's private key** (Secret `arc-runners/arc-github-app`).
  Actions Runner Controller needs the App to hold Administration read/write on
  each repository it serves, and that permission can also change or delete
  rulesets and add deploy keys. Whoever holds the key can remove the ruleset,
  push to `main` and get a job the guard admits. In the cluster that is the ARC
  controller's service account, whose Role reads Secrets in `arc-runners` (the
  App key and the registry login both). Runner pods cannot: they run under a
  service account with no permissions and `netpol.yaml` keeps them from the API
  server.
- **What is already on `main`.** Any code the release workflow runs (the
  workflow, its action and script, and every action it uses, which zetra's
  tests require to be pinned by commit hash) runs beside the login. A re-run of
  an old push to `main` runs that commit's copy of the workflow.
- **Automatic merging.** Anything allowed to merge a pull request without a
  person (auto-merge, a dependency bot) is a way onto `main`.

### The registry login

The runner container (only that container, and only on this scale set) has the
docker client configuration file `/home/runner/.docker/config.json`, mounted
read-only from the Secret `arc-runners/registry-platform-push` (type
`kubernetes.io/dockerconfigjson`, key `.dockerconfigjson`). The directory
`/home/runner/.docker` is a writable emptyDir, because the docker client and
buildx write there; only the one file comes from the Secret. The runner image
runs as user `runner` with `HOME=/home/runner`. No `docker login` step is
needed and the workflow handles no password. The login is for the account
`platform-release` (a dedicated account, revocable alone).

The Secret is `registry-platform-push.enc.yaml` in this directory and is listed
in `kustomization.yaml`. The scale set keeps no idle runner, so no pod is
scheduled, and nothing reads the Secret, until a job is queued. **The release
workflow in zetra must not merge before this directory's changes are merged and
reconciled**, because its first run would queue a runner pod that cannot start
without the Secret.

### How it was set up

Done on 2026-11-12. The steps are kept because a rotation or a second scale set
repeats them.

1. The kubani-arc GitHub App was added to X-McKay/zetra and the repository
   settings above were set (repository owner).
2. On rig0 (where `age.key` is), from a checkout of this repository, the
   operator created the login and its Secret:

   ```
   infrastructure/scripts/ops/add_registry_user.sh platform-release arc-runners/registry-platform-push infrastructure/gitops/apps/arc-runners/registry-platform-push.enc.yaml
   ```

   The script appends the user's htpasswd line to
   `infrastructure/gitops/infrastructure/registry/basic-auth-secret.enc.yaml`,
   adds `platform-release-username` and `platform-release-password` to
   `infrastructure/gitops/infrastructure/registry/credentials-secret.enc.yaml`,
   and writes the SOPS-encrypted dockerconfigjson Secret to the target file. It
   prints no value. It refuses if the user already exists.
3. One line was added to `resources:` in this directory's `kustomization.yaml`:

   ```
     - registry-platform-push.enc.yaml
   ```

4. The three encrypted files were committed with the scale set. Once merged,
   Flux reconciles them and the registry (Traefik basic-auth Secret) picks up
   the new user on its own.
5. Only then is `.github/workflows/platform-release.yml` merged in zetra.

Every registry login can push and pull (one basicAuth middleware, see
`docs/infrastructure/configuration/registry.md`); a separate account buys
separate revocation only. To rotate, follow "Rotating a Credential" in
`.claude/rules/secrets.md`; a new runner pod picks up the new Secret, since
runners are ephemeral.

### What has been shown on the runner

On 2026-11-12, after the Secret and the scale set were reconciled:

- **A release ran.** The merge of the release workflow to zetra `main` (zetra
  `4657884`, run 43273326047) was admitted by the guard, built
  `registry-controller`, pushed it with the mounted login and read back the
  digest it had reported. So the Kata runtime does lay the one Secret file over
  the scratch directory, and buildx works in that directory.
- **The guard refused.** Two throwaway workflows pushed to a zetra branch, one
  of them using the file name `platform-release.yml`, both asked for
  `kubani-zetra` and both failed at "Set up runner" with `ref
  'refs/heads/test/guard-refusal' may not use this runner (only
  refs/heads/main)`; their one step never ran.

- **All eight images were released** in one run on 2026-11-13 (zetra
  `67c908a`, tag `67c908a` in each repository under
  `registry.almckay.io/platform/`), one at a time, in about 40 minutes. Each
  digest read back from the registry matched, and `capture` is `linux/arm64`.

Not shown on the runner: a refusal for the workflow file alone (that needs a
second workflow on `main`; the tests run the guard script for it).

### Memory on rig0

A runner pod requests the memory it may use, 8Gi plus 160Mi of Kata overhead,
so the scheduler counts a build at its limit. All pods on rig0 together may use
about 27Gi and other pods request about 6Gi (2026-11-12), so two runner pods
fit and a third stays Pending until one ends; its job waits in the queue.

The 8Gi is divided by what each kind of job uses:

| Scale set | Runner | Build sidecar | of which tmpfs storage |
|---|---|---|---|
| `kubani-zetra-agents` | 4Gi | 4Gi | up to 3Gi |
| `kubani-zetra` | 1Gi | 7Gi | up to 5Gi |

Where the figures come from (`kubectl top pod -n arc-runners --containers`,
sampled every 10 seconds):

| Job | Build sidecar peak | Runner peak |
|---|---|---|
| agent release, quiet network (2026-11-06) | about 1.4Gi | about 3.6Gi while signing and scanning |
| platform image `agent-policy-service` (2026-11-13) | 3.61Gi, still rising at the last sample | 0.44Gi |
| `capture`, `budget-backend`, `conformance-capture` (Go) | 1.54 to 1.63Gi | 0.44Gi |
| `registry-controller`, `session-runner`, `netpol-attestor`, `egress-guard` (Python) | 0.27 to 1.39Gi | 0.44 to 0.45Gi |

The Agent Policy Service build ran with a 4Gi sidecar and 3Gi of storage and
passed, with too little to spare; that is why `kubani-zetra` now gives the
sidecar 7Gi. Its runner container signs and scans nothing yet. When the
release workflow starts to (an agent release peaks at about 3.6Gi doing so),
the runner needs 4Gi and the pod no longer fits in 8Gi: decide then whether a
platform build may run beside an agent release.

To change a figure, change the limit and the request together, keep the
storage at least 1Gi below the sidecar's limit, and check how many pods then
fit on rig0; `tests/test_arc_scale_sets.py` pins the figures.

Before 2026-11-12 the limits were 12Gi and 4Gi with requests of 1Gi and 512Mi,
so three pods could be scheduled with 48Gi of limits. The sidecar hit 12Gi four
times on 2026-11-06, when a process in it grew from 1 to 8Gi in 30 seconds
while `apt` downloads stalled; those builds failed, and with a lower limit the
same event fails sooner.

### NetworkPolicies

None added. `netpol.yaml` selects every pod in `arc-runners` and `arc-systems`
(`podSelector: {}`), so this scale set's runners and listener are covered, and
they reach the same things as the other scale set: DNS, the internet on 80/443
(GitHub), and Traefik for `registry.almckay.io`.
