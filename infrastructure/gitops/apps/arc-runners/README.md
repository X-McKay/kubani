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

The Secret is not listed in `kustomization.yaml` until the operator creates it
(below). The scale set can merge before the Secret exists: it keeps no idle
runner, so no pod is scheduled, and nothing needs the Secret, until a job is
queued. **The release workflow in zetra must not merge before the Secret
exists**, because its first run would queue a runner pod that cannot start.

### Operator steps

1. Install the kubani-arc GitHub App on X-McKay/zetra and set the repository
   settings above (repository owner).
2. On rig0 (where `age.key` is), from a checkout of this repository, create the
   login and its Secret:

   ```
   infrastructure/scripts/ops/add_registry_user.sh platform-release arc-runners/registry-platform-push infrastructure/gitops/apps/arc-runners/registry-platform-push.enc.yaml
   ```

   The script appends the user's htpasswd line to
   `infrastructure/gitops/infrastructure/registry/basic-auth-secret.enc.yaml`,
   adds `platform-release-username` and `platform-release-password` to
   `infrastructure/gitops/infrastructure/registry/credentials-secret.enc.yaml`,
   and writes the SOPS-encrypted dockerconfigjson Secret to the target file. It
   prints no value. It refuses if the user already exists.
3. Add one line to `resources:` in this directory's `kustomization.yaml`:

   ```
     - registry-platform-push.enc.yaml
   ```

4. Commit the three encrypted files, push, and let Flux reconcile. The registry
   (Traefik basic-auth Secret) picks up the new user on its own.
5. Only then merge `.github/workflows/platform-release.yml` in zetra.

Every registry login can push and pull (one basicAuth middleware, see
`docs/infrastructure/configuration/registry.md`); a separate account buys
separate revocation only. To rotate, follow "Rotating a Credential" in
`.claude/rules/secrets.md`; a new runner pod picks up the new Secret, since
runners are ephemeral.

### After the Secret exists

Before the first release, show that the guard refuses a job that is not a push
to `main` running `platform-release.yml` (for example a `workflow_dispatch`
test workflow that targets `kubani-zetra`): it must fail at "Set up runner"
with `kubani runner guard: ... may not use this runner`. Then confirm the
docker client in the runner finds the login (`docker pull` of a private image,
or the first push), which has not been tested.

### NetworkPolicies

None added. `netpol.yaml` selects every pod in `arc-runners` and `arc-systems`
(`podSelector: {}`), so this scale set's runners and listener are covered, and
they reach the same things as the other scale set: DNS, the internet on 80/443
(GitHub), and Traefik for `registry.almckay.io`.
