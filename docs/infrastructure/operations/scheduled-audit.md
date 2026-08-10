# Scheduled Audit

A GitHub Actions workflow runs `just audit` every Monday at 09:00 UTC on the
`sparky` self-hosted runner, so nobody has to remember to type it.

## What it asserts

`just audit` is the single entry point:

```
audit: cluster-identity validate live-service-probes
```

In order:

1. **`cluster-identity`** — confirms `kubectl` is pointed at the kubani cluster
   (nodes `asio rig0 sparky strix`) before anything else runs. See
   [Why `cluster-identity` runs first](#why-cluster-identity-runs-first) below.
2. **`validate`** (`validate-local` + `validate-cluster`) — inventory parses,
   secrets are encrypted, kustomize builds, and the live network/DNS/pod-CIDR
   checks pass.
3. **`live-service-probes`** — the deployed services actually respond.

Not part of `audit` yet:

- **`provision-check`** — deliberately excluded until its Ansible `--check`
  drift output has proven stable across several manual runs. See
  [Adding `provision-check`](#adding-provision-check).
- **`validate-network`** — doesn't exist on `main` yet; it lands with PR #49.

## Run it by hand

On any node with `just`, `uv`, and `kubectl` on `PATH`:

```bash
just audit
```

This is exactly what the scheduled workflow runs — same recipe, same exit
code. Useful before a change you expect to affect cluster state, or any time
you want to check without waiting for Monday.

## A passing run is silent

There is no notification step, on purpose. A failing **scheduled** workflow
already emails the repository owner, and the run history under the repo's
**Actions** tab is already a durable record. Adding a second success/failure
channel (Slack webhook, tracking issue, etc.) would just be something else
that can drift out of sync with the truth. No news from the audit is good
news.

## What a red run means

1. Open the failed run under **Actions → audit** and read the log — the
   `just audit` step output shows which recipe in the chain failed.
2. Re-run that one recipe directly to narrow it down and iterate locally,
   without waiting on the runner:
   - `just cluster-identity`
   - `just validate-cluster`
   - `just live-service-probes`

### Why `cluster-identity` runs first

The kubeconfig on `sparky` (and other nodes) has a second context,
`infosec-harness`, alongside the kubani cluster. If `kubectl` were ever
pointed at that context, every check downstream could pass while asserting
nothing about kubani — a fully green audit that means nothing.
`cluster-identity` fails loudly instead, checking node names rather than
context name (contexts get renamed; the nodes at `asio rig0 sparky strix`
are the actual thing being asserted).

**If `cluster-identity` fails**, `kubectl` is pointed at the wrong cluster.
Fix the context, don't touch the guard:

```bash
kubectl config use-context <kubani-context>
```

### Adding `provision-check`

`provision-check` (`ansible-playbook ... --check --diff` against the full
inventory) is not part of `audit` yet. Its drift output needs to be run by
hand several times and shown to be stable — no false-positive diffs from
run to run — before it's safe to fold into an unattended weekly job. Tracked
for Task 4.

## Why the runner is restricted to `schedule` and `workflow_dispatch`

The workflow runs on a self-hosted runner on `sparky`, as a user holding SSH
keys and a kubeconfig for the whole cluster. Any trigger that a PR author can
fire — `pull_request`, `push` to a branch they control, etc. — would hand
that same command execution to anyone who can open a PR. `.github/workflows/audit.yml`
therefore has exactly two triggers: `schedule` and `workflow_dispatch`
(manual, repo-collaborator only). PR validation stays where it belongs, on
GitHub-hosted runners in `.github/workflows/validate.yml`, which never
touches the cluster or holds cluster credentials.

Step 2 of the implementing task enforces this as a test — the workflow's
trigger set must equal exactly `{schedule, workflow_dispatch}` or the change
is rejected. Treat a failure there as a hard stop, not something to relax.

## Runner registration is a one-time operator step

Registering `sparky` as a self-hosted runner requires a repo-admin
registration token from GitHub and is not something an agent or the workflow
itself can do. It's a one-time setup step — see Step 3 in the implementing
task brief (`.superpowers/sdd/2026-08-09-scheduled-audit/task-3-brief.md`)
for the exact `useradd` / `config.sh` / `svc.sh` commands. Verify the runner
shows **Idle** at
`https://github.com/X-McKay/kubani/settings/actions/runners` before expecting
the schedule to fire successfully.
