# ARC runners

Self-hosted GitHub Actions runners (Actions Runner Controller 0.15.0) for
release jobs that need in-cluster reach to `registry.almckay.io` and the
private Sigstore. One scale set: `kubani-zetra-agents`, for the public repo
X-McKay/zetra-agents, authenticated by the `kubani-arc` GitHub App
(`github-app.enc.yaml`).

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
