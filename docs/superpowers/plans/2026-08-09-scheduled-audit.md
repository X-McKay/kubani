# Scheduled Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the repository's existing checks run on a schedule without anyone remembering to type them, and make provisioning previewable first.

**Architecture:** Fix check-mode compatibility so `ansible-playbook --check` works, expose one `just audit` composite recipe following the existing idiom, then have a self-hosted GitHub Actions runner on `sparky` call that recipe weekly. The transport is deliberately dumb: it runs one command and nothing else.

**Tech Stack:** Ansible, `just`, GitHub Actions self-hosted runner.

## Global Constraints

- **Do not blanket-apply `check_mode: false` to all 33 candidate tasks.** Fix only tasks that actually block a `--check` run. Some "wait for X to be ready" tasks wait on resources that check mode never created; forcing those to run makes them hang or fail. Task 1 is iterative for this reason.
- `--check` must never change cluster or host state. If any run reports `changed` on a task that actually modified something, stop and report BLOCKED.
- All four nodes are live: `sparky` (control plane), `rig0` (worker **and the operator's desktop, in use**), `asio`, `strix`. Never restart a service.
- The self-hosted runner must be reachable **only** from `schedule` and `workflow_dispatch` triggers, never `pull_request`. A runner executing PR code would give any contributor command execution on the control plane as a user holding SSH keys and kubeconfig.
- Existing PR CI stays on GitHub-hosted runners and must not be modified.
- No credentials may be added to GitHub secrets.
- `provision-check` must NOT be part of `audit` until Task 4's gate is met.
- `validate-network` must NOT be added to `audit`: that recipe exists only on `fix/ufw-pod-forwarding` (PR #49, unmerged). This branch is cut from `main`. Adding it produces a recipe that cannot resolve.
- Conventional commits per `.claude/rules/commits.md`; scopes `ansible`, `repo`, `docs`.
- Run `just check` before each commit. If ansible-lint blocks and only ansible-lint blocks, run `just ansible-deps` first rather than `--no-verify`.

**Branch:** `feat/scheduled-audit` (already cut from `main`; spec committed at `fb30f2a`).

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `justfile` | `provision-check` and `audit` recipes | Modify |
| `infrastructure/ansible/roles/*/tasks/*.yml` | `check_mode: false` on blocking read-only probes | Modify (iteratively) |
| `.github/workflows/audit.yml` | Weekly scheduled run of `just audit` | Create |
| `docs/infrastructure/operations/scheduled-audit.md` | What the audit is, how to run it by hand, how to fix a red run | Create |

---

### Task 1: Make `--check` work end to end

**Files:**
- Modify: `justfile` (add `provision-check` next to the other validate recipes, around line 129)
- Modify: various `infrastructure/ansible/roles/*/tasks/*.yml` — **determined iteratively, not up front**

**Interfaces:**
- Consumes: nothing.
- Produces: `just provision-check` — runs `ansible-playbook provision_cluster.yml --check --diff` across all four nodes. Task 2 references it; Task 4 adds it to `audit`.

- [ ] **Step 1: Add the recipe**

Insert into `justfile` immediately after the `validate-cluster` recipe. (Do not look
for a `validate-network` recipe — it does not exist on this branch; see Task 2.)

```make
# Dry-run provisioning across all nodes. Reports configuration drift and proves
# the provisioning path still works. Changes nothing.
# No --limit: the control-plane play publishes k3s_node_token via add_host, and
# limiting to a worker skips that play, so the worker-play assert fails.
provision-check:
    uv run ansible-playbook -i {{inventory_file}} {{ansible_dir}}/playbooks/provision_cluster.yml --check --diff
```

- [ ] **Step 2: Run it and capture the red state**

```bash
just provision-check 2>&1 | tee /tmp/check-run.log; echo "exit=$?"
sed -n '/PLAY RECAP/,$p' /tmp/check-run.log
```

Expected, before any fix: fails at `TASK [prerequisites : Parse Tailscale status]` with
`the field 'args' has an invalid value ... Expecting value: line 1 column 1 (char 0)`,
and `PLAY RECAP` showing `failed=1` on all four hosts.

This is the red state. If it does not fail, stop and report BLOCKED — the premise is wrong.

- [ ] **Step 3: Fix the first blocking task**

The cause is always the same: a read-only `command`/`shell` task is skipped in check
mode, so the variable it registers is empty, and a later task parses that empty value.

Add `check_mode: false` to the *command* task (not the parsing task). For the first
failure that is `Get Tailscale status` in
`infrastructure/ansible/roles/prerequisites/tasks/tailscale_validation.yml`:

```yaml
- name: Get Tailscale status
  ansible.builtin.command: tailscale status --json
  register: tailscale_status
  changed_when: false
  failed_when: false
  check_mode: false
```

This matches the pattern already used correctly at
`infrastructure/ansible/roles/k3s_control_plane/tasks/install.yml:8-15`.

- [ ] **Step 4: Re-run and repeat until green**

```bash
just provision-check 2>&1 | tee /tmp/check-run.log; echo "exit=$?"
sed -n '/PLAY RECAP/,$p' /tmp/check-run.log
```

Repeat Steps 3-4 for each new failure. **Judgement required on each one** — apply this test before adding `check_mode: false`:

- **Add it** when the task only *reads* existing state (`tailscale status`, `kubectl get`, `nvidia-smi`, `stat`, checking whether something is installed). These are safe and are what check mode needs.
- **Do NOT add it** when the task waits for something that check mode never created (e.g. `Wait for validation pod to complete`, `Wait for NVIDIA device plugin to be ready`). Forcing those to run makes them hang or fail against a resource that does not exist. Instead, guard the *consuming* task so it tolerates a skipped result, e.g. `when: not ansible_check_mode`.

Reference list of the 33 candidates (tasks that are `command`/`shell` + `register` + `changed_when: false` + no `check_mode`). **This is a lookup table, not a to-do list** — only touch the ones that actually block:

```
bootstrap/tasks/install_tailscale.yml    Check if Tailscale is already installed; Get Tailscale status
bootstrap/tasks/validate.yml             Verify Tailscale is installed; Get Tailscale IP (if authenticated);
                                         Verify swap is disabled; Verify IP forwarding is enabled;
                                         Check available disk space; Check available memory
gitops/tasks/bootstrap_flux.yml          Pre-check Flux prerequisites; Wait for Flux controllers to be ready
gitops/tasks/verify_flux.yml             Run Flux check; Get Flux system status;
                                         Verify GitRepository source is ready; Verify Kustomization is ready
gpu_support/tasks/configure_time_slicing.yml  Wait for device plugin to restart with time-slicing config
gpu_support/tasks/deploy_device_plugin.yml    Wait for NVIDIA device plugin to be ready
gpu_support/tasks/install_driver.yml     Check if NVIDIA driver is already installed; Verify NVIDIA driver installation
gpu_support/tasks/main.yml               Check if node has GPU
gpu_support/tasks/validate_gpu.yml       Wait for node to report GPU capacity; Check if time-slicing is working;
                                         Wait for validation pod to complete; Get validation pod logs
k3s_worker/tasks/labels_taints.yml       Wait for node to be registered in cluster
node_config/handlers/main.yml            Wait for node to be ready after restart
node_config/tasks/apply_labels_taints.yml     Wait for node to be registered in cluster
node_config/tasks/configure_storage.yml       Check if local-path-provisioner is already installed
node_config/tasks/detect_hardware.yml    Detect GPU presence; Detect storage devices
prerequisites/tasks/reachability.yml     Ping own Tailscale IP; Test Tailscale peer connectivity
prerequisites/tasks/tailscale_validation.yml  Check if Tailscale is installed; Get Tailscale status
```

- [ ] **Step 5: Confirm green and that nothing changed**

```bash
just provision-check 2>&1 | tee /tmp/check-final.log
sed -n '/PLAY RECAP/,$p' /tmp/check-final.log
grep -c 'changed:' /tmp/check-final.log
KUBECONFIG=/home/al/.kube/config kubectl get nodes
```

Expected: `failed=0` and `unreachable=0` on all four hosts; all four nodes still `Ready`.

Record the `changed=N` count per host. A non-zero count is configuration drift and is
**information, not a failure** — record what each changed task was in your report.
Task 4 depends on knowing whether that count is stable.

- [ ] **Step 6: Confirm no host state was modified**

```bash
sudo ufw status verbose | grep -c 'ALLOW FWD'
KUBECONFIG=/home/al/.kube/config kubectl get pods -A --no-headers | awk '$4!="Running" && $4!="Completed"' | wc -l
```

Expected: `1` (the UFW rule still present, unchanged), and `0` unhealthy pods.

- [ ] **Step 7: Commit**

```bash
just check
git add justfile infrastructure/ansible
git commit -m "fix(ansible): make provisioning runnable in check mode

Read-only command tasks registered output that later tasks parsed, but
lacked check_mode: false. Ansible skips command tasks in check mode, so the
registered variable was empty and the consuming task failed -- the run died
at task 14 of ~100, on every host:

  TASK [prerequisites : Parse Tailscale status]
  fatal: the field 'args' has an invalid value ... Expecting value

Marking these probes check_mode: false matches the pattern already used in
k3s_control_plane/tasks/install.yml and gitops/tasks/bootstrap_flux.yml,
where read-only probes deliberately run so check mode gets real data.

Only tasks that actually blocked a run were changed. Tasks that wait on
resources check mode never creates were deliberately left alone.

Adds just provision-check, which also documents why --limit cannot be used:
the control-plane play publishes k3s_node_token via add_host, so limiting to
a worker skips it and the worker-play assert fails.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: One command that asserts everything

**Files:**
- Modify: `justfile` (add `audit` next to `validate`, around line 152)

**Interfaces:**
- Consumes: `validate`, `validate-network`, `live-service-probes` (all existing); `provision-check` (Task 1).
- Produces: `just audit` — exits 0 when everything passes, non-zero if any dependency fails. Task 3's workflow calls exactly this.

- [ ] **Step 1: Add the recipe**

Insert into `justfile` immediately after the `validate` recipe:

```make
# Everything that asserts the running system matches what is declared.
# This is what the scheduled audit runs; keep it as the single entry point so
# the scheduler stays a dumb transport.
# Two checks are deliberately excluded for now and added in Task 4:
#   provision-check  -- until it has proven stable by hand
#   validate-network -- does not exist on main yet; it lands with PR #49
audit: validate live-service-probes
```

`just` propagates failure from any dependency, so no exit-code handling is needed.

**Do not add `validate-network` here.** This branch is cut from `main`, and that
recipe only exists on `fix/ufw-pod-forwarding` (PR #49, unmerged). Adding it now
produces an `audit` recipe that fails with "Justfile does not contain recipe
`validate-network`". Verify with `grep -n 'validate-network' justfile` before
assuming otherwise.

- [ ] **Step 2: Verify it resolves and composes correctly**

```bash
just --list | grep -E '^\s*(audit|provision-check)'
just --show audit
grep -n 'validate-network' justfile || echo "confirmed absent on this branch — correct"
```

Expected: both recipes listed; `just --show audit` shows exactly two dependencies
(`validate live-service-probes`); `validate-network` confirmed absent.

- [ ] **Step 3: Run it against the healthy cluster**

```bash
just audit; echo "exit=$?"
```

Expected: `exit=0`. Every dependency already passes today, so a non-zero exit means
either a real regression or a composition error — investigate before continuing.

- [ ] **Step 4: Verify it actually fails when something is wrong**

A recipe that cannot fail is not an assertion. Prove the failure path without breaking
anything, by pointing a dependency at a kubeconfig that does not exist:

```bash
KUBECONFIG=/nonexistent/kubeconfig just validate-cluster; echo "exit=$?"
```

Expected: non-zero exit (`validate_cluster.sh` documents exit 2 for an unreachable
cluster). This confirms the underlying check reports failure rather than passing
silently, which is what `just` would propagate through `audit`.

Then confirm the real one still passes, so the environment is left as found:

```bash
just validate-cluster >/dev/null && echo "healthy path still exits 0"
```

- [ ] **Step 5: Commit**

```bash
just check
git add justfile
git commit -m "feat(repo): add just audit as the single assertion entry point

validate-cluster (44 assertions), live-service-probes (22 probes) and
validate-network all exist and are correct, but only ever run when someone
types them. Every defect found in this repo recently was found by a human or
agent happening to look, not by the system reporting it.

audit composes them into one command so a scheduler can be a dumb transport
that runs one thing. provision-check is deliberately excluded until it has
proven stable by hand -- adding it later is a one-word change with no
workflow edit.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Run it without being asked

**Files:**
- Create: `.github/workflows/audit.yml`
- Create: `docs/infrastructure/operations/scheduled-audit.md`

**Interfaces:**
- Consumes: `just audit` (Task 2).
- Produces: a weekly scheduled workflow on the `sparky` self-hosted runner.

**Operator step required:** registering a self-hosted runner needs a repo-admin
registration token from GitHub. An agent must not do this. Step 3 is written for the
operator to run; the agent performs Steps 1, 2, 4 and 5.

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/audit.yml`:

```yaml
name: audit

# schedule and workflow_dispatch ONLY. This job runs on a self-hosted runner on
# the control plane, as a user holding SSH keys and a kubeconfig. Adding a
# pull_request trigger would give anyone who can open a PR command execution on
# that host. PR validation stays on GitHub-hosted runners in validate.yml.
on:
  schedule:
    - cron: "0 9 * * 1" # Mondays 09:00 UTC
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: audit
  cancel-in-progress: false

jobs:
  audit:
    name: Assert the cluster matches what is declared
    runs-on: [self-hosted, sparky]
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4

      - name: Run the audit
        run: just audit
```

There is deliberately no notification step. A failing scheduled workflow already
emails the repository owner, and the run history in Actions is already a durable
record.

- [ ] **Step 2: Validate the workflow file parses**

```bash
uv run python -c "import yaml,sys; d=yaml.safe_load(open('.github/workflows/audit.yml')); \
print('triggers:', list(d[True].keys())); \
assert set(d[True]) == {'schedule','workflow_dispatch'}, 'FORBIDDEN TRIGGER PRESENT'; \
print('runs-on:', d['jobs']['audit']['runs-on']); print('OK')"
```

Expected: `triggers: ['schedule', 'workflow_dispatch']`, `runs-on: ['self-hosted', 'sparky']`, `OK`.

The assert is the security constraint expressed as a test. Note PyYAML parses the
bare `on:` key as boolean `True`, which is why the check indexes `d[True]`.

- [ ] **Step 3: Register the runner on sparky — OPERATOR STEP**

Get a registration token from
`https://github.com/X-McKay/kubani/settings/actions/runners/new`, then on `sparky`:

```bash
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

The runner needs `just`, `uv`, `kubectl`, `ansible` and SSH access to the other
nodes. If `gh-runner` cannot reach them, run the runner as the existing operator
user instead — that is a deliberate tradeoff between isolation and setup cost, and
either is acceptable here.

Verify: the runner shows as **Idle** at
`https://github.com/X-McKay/kubani/settings/actions/runners`.

- [ ] **Step 4: Trigger it manually and confirm it passes**

```bash
gh workflow run audit.yml
sleep 30
gh run list --workflow=audit.yml --limit 1
gh run watch "$(gh run list --workflow=audit.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```

Expected: the run completes with conclusion `success`.

If it fails on a missing tool, that is a runner environment gap, not an audit
failure — install the tool on `sparky` and re-run.

- [ ] **Step 5: Write the runbook and commit**

Create `docs/infrastructure/operations/scheduled-audit.md` covering:

1. What the audit asserts, and that it runs weekly on Mondays 09:00 UTC
2. `just audit` runs the same thing by hand, on any node
3. What a red run means: read the Actions log, find which dependency failed, run
   that one recipe directly (`just validate-cluster`, `just live-service-probes`,
   `just validate-network`)
4. Why the runner is restricted to `schedule` and `workflow_dispatch`, and that
   adding `pull_request` would give PR authors command execution on the control plane
5. That `provision-check` is not yet part of `audit`, and the gate for adding it
6. That a passing run is deliberately silent — no notification is success

Then:

```bash
just check
git add .github/workflows/audit.yml docs/infrastructure/operations/scheduled-audit.md
git commit -m "feat(repo): run the audit weekly on a self-hosted runner

The checks already existed and were correct; nothing ran them. This adds a
weekly scheduled workflow that calls just audit and nothing else, so the
scheduler stays a transport that can be replaced or deleted without touching
a single assertion.

Runs on a self-hosted runner on sparky because the cluster is Tailscale-bound
and sparky already holds the SSH keys, kubeconfig and inventory. That keeps
every credential inside the network -- nothing is added to GitHub secrets.

Restricted to schedule and workflow_dispatch. A self-hosted runner reachable
from pull_request would give anyone who can open a PR command execution on
the control plane as a user holding SSH keys and a kubeconfig. PR validation
stays on GitHub-hosted runners in validate.yml, unchanged.

No notification step: a failing scheduled workflow already emails the owner
and Actions history is already durable.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Fold the deferred checks into the schedule

Two checks were held back. Each has its own gate, and they can be added independently.

| Check | Gate |
|---|---|
| `provision-check` | Stable, explainable `changed=N` across several manual runs on different days |
| `validate-network` | PR #49 merged to `main` and this branch rebased, so the recipe exists |

Do **not** start this task in the same session as Task 1. The `provision-check` gate is
evidence over time, not a command.

**Files:**
- Modify: `justfile` (the `audit` recipe)
- Modify: `docs/infrastructure/operations/scheduled-audit.md`

**Interfaces:** consumes `provision-check` (Task 1) and `audit` (Task 2).

- [ ] **Step 1: Confirm the gate is met**

Run `just provision-check` on at least three separate occasions, on different days.

```bash
just provision-check 2>&1 | sed -n '/PLAY RECAP/,$p'
```

The gate is met when the `changed=N` count is stable and every changed task is
understood and explainable. If the count moves run to run for reasons nobody can
explain, the gate is NOT met — adding it to the schedule would produce exactly the
kind of unexplained red run that trains people to ignore the audit.

- [ ] **Step 2: Add whichever checks have met their gate**

Both gates met:

```make
audit: validate validate-network live-service-probes provision-check
```

Only the `provision-check` gate met (PR #49 still unmerged):

```make
audit: validate live-service-probes provision-check
```

Only PR #49 merged (dry run not yet stable):

```make
audit: validate validate-network live-service-probes
```

Before adding `validate-network`, confirm it exists on this branch:

```bash
grep -n '^validate-network:' justfile && echo "present — safe to add"
```

No workflow change is needed in any case. The scheduled job already runs `just audit`.

- [ ] **Step 3: Verify and update the runbook**

```bash
just audit; echo "exit=$?"
```

Expected: `exit=0`. Update `docs/infrastructure/operations/scheduled-audit.md` to
remove the note that `provision-check` is excluded, and state what a drift report in
the scheduled run means.

- [ ] **Step 4: Commit**

```bash
just check
git add justfile docs/infrastructure/operations/scheduled-audit.md
git commit -m "feat(repo): add provisioning dry-run to the scheduled audit

provision-check has produced a stable, explainable changed-task count across
several manual runs, so it is now safe to let it fail a scheduled job.

One word in the audit recipe; no workflow change. That was the point of
keeping the scheduler a dumb transport.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Acceptance Criteria

- [ ] `just provision-check` completes with `failed=0` and `unreachable=0` on all four nodes
- [ ] Every reported `changed` task in the dry run is recorded and explained
- [ ] No host or cluster state was modified by any `--check` run; all four nodes stay `Ready`
- [ ] Only tasks that actually blocked a run received `check_mode: false`
- [ ] `just audit` exits 0 against the healthy cluster and non-zero when a dependency fails
- [ ] `just audit` contains only recipes that exist on this branch — `validate-network` is NOT added until PR #49 merges
- [ ] `.github/workflows/audit.yml` has exactly the triggers `schedule` and `workflow_dispatch`
- [ ] `.github/workflows/validate.yml` is unmodified and still runs on GitHub-hosted runners
- [ ] No credentials added to GitHub secrets
- [ ] A manually dispatched audit run completes successfully on the `sparky` runner
- [ ] `provision-check` and `validate-network` are absent from `audit` until their Task 4 gates are met
