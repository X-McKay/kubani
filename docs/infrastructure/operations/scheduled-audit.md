# Scheduled Audit

A GitHub Actions workflow is designed to run `just audit` every Monday at
09:00 UTC on the `sparky` self-hosted runner, so nobody has to remember to
type it.

> **Not active yet.** The `sparky` self-hosted runner has not been
> registered. Until it is registered **and** a manual `workflow_dispatch` run
> has completed successfully, the scheduled Monday run will sit **Queued**
> with no runner to pick it up, and GitHub silently cancels queued runs after
> roughly 24 hours. A cancelled run does **not** send the failure email that
> ["A passing run is silent"](#a-passing-run-is-silent) below relies on — so
> until this audit is verified active, silence means "it never ran", not
> "it passed". See [Runner registration is a one-time operator
> step](#runner-registration-is-a-one-time-operator-step) to activate it, and
> confirm with:
>
> ```bash
> gh run list --workflow=audit.yml --limit 5
> ```
>
> Expect to see at least one `workflow_dispatch` run with conclusion
> `success` before trusting the schedule.

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
   secrets are encrypted, git hooks are installed (`hooks-check`), kustomize
   builds, and the live network/DNS/pod-CIDR checks pass.
3. **`validate-network`** — host-local checks on whichever node the audit runs
   on: Tailscale interface, pod CIDR routes, CoreDNS reachability, cross-node
   pod connectivity, and the UFW pod-forwarding rule. Must run ON a node; it
   reads that host's routes, UFW state and iptables chains.
4. **`live-service-probes`** — the deployed services actually respond.

Not part of `audit` yet:

- **`provision-check`** — deliberately excluded until its Ansible `--check`
  drift output has proven stable and explainable across several manual runs on
  different days. See [Adding `provision-check`](#adding-provision-check).

  Until then, run it by hand. It is worth running: on its first green run it
  found that `strix` was missing the `tailscale-recovery.conf` drop-in that the
  other three nodes have, and that `rig0` still has swap in `/etc/fstab`.

## Run it by hand

On any node with `just`, `uv`, `kubectl`, `pre-commit`, and `sops` on
`PATH`:

```bash
just audit
```

This is exactly what the scheduled workflow runs — same recipe, same exit
code. Useful before a change you expect to affect cluster state, or any time
you want to check without waiting for Monday.

`pre-commit` is needed because `hooks-check` (part of `validate-local`)
fails unless the repo's git hooks are actually installed, and `sops` is
needed to act on anything `secrets-check` flags.

## Known effects of the check-mode fix

This branch also makes `ansible --check` runnable, which required resolving
`skip_driver_install`, `gpu_time_slicing_enabled`, and
`gpu_time_slicing_replicas` from their `default_*` fallbacks in
`roles/gpu_support/tasks/main.yml` (previously undefined, which aborted a
real `just provision` on any GPU node before this fix).

`roles/gpu_support/defaults/main.yml` already declares
`default_gpu_time_slicing_enabled: true` — enabling time-slicing is the
role's existing declared intent, not a new decision made by this branch. The
cluster already runs a `time-slicing-config` ConfigMap and an
`nvidia-device-plugin-daemonset`; time-slicing is already in use today.

The practical effect of this fix is that the **next real** `just provision`
run will *reconcile* the device-plugin ConfigMap/DaemonSet to match the
role's declared config, which will roll the device plugin pod(s) on GPU
nodes. It does not newly enable a feature that was off. This path has only
been exercised under `--check` so far — no real `just provision` run has
proved it yet, so treat the first real run after this change as one to watch.

## A passing run is silent

There is no notification step, on purpose. A failing **scheduled** workflow
already emails the repository owner, and the run history under the repo's
**Actions** tab is already a durable record. Adding a second success/failure
channel (Slack webhook, tracking issue, etc.) would just be something else
that can drift out of sync with the truth. No news from the audit is good
news — **once the runner is registered and verified**, per the warning at
the top of this document.

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
itself can do. On `sparky`:

```bash
# Get a registration token from:
#   https://github.com/X-McKay/kubani/settings/actions/runners/new
sudo useradd -m -s /bin/bash gh-runner 2>/dev/null || true
sudo -u gh-runner bash -c '
  mkdir -p ~/actions-runner && cd ~/actions-runner
  curl -sSL -o r.tar.gz https://github.com/actions/runner/releases/latest/download/actions-runner-linux-x64.tar.gz
  tar xzf r.tar.gz
  ./config.sh --url https://github.com/X-McKay/kubani \
              --token <REGISTRATION_TOKEN> \
              --labels sparky --unattended --replace
'
cd /home/gh-runner/actions-runner && sudo ./svc.sh install gh-runner && sudo ./svc.sh start
```

The runner needs `just`, `uv`, `kubectl` and `ansible` on `PATH`, plus SSH
access to the other nodes. If `gh-runner` cannot reach them, running the
runner as the existing operator user instead is an acceptable tradeoff
between isolation and setup cost.

Verify the runner shows **Idle** at
`https://github.com/X-McKay/kubani/settings/actions/runners`, then trigger a
manual run and confirm it succeeds before trusting the schedule:

```bash
gh workflow run audit.yml
gh run list --workflow=audit.yml --limit 5
```
