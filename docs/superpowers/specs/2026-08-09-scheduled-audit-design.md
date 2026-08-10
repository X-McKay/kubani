# Design: Make the Existing Checks Run Without Being Asked

- **Date:** 2026-08-09
- **Status:** approved, not yet implemented
- **Branch:** `feat/scheduled-audit`

---

## 1. Problem

A single day's work surfaced eight distinct defects in this repository and cluster:

| Defect | Shape |
|---|---|
| `just provision-host <worker>` broken repo-wide | path nothing exercises |
| `provision_cluster.yml --tags firewall` never reaches the firewall tasks | path nothing exercises |
| `provision_cluster.yml --check` dies at task 14 | path nothing exercises |
| `validate-cluster-network.sh` orphaned; two docs claimed it ran | claim nothing verifies |
| Authentik runbooks pointed at a deleted Certificate | claim nothing verifies |
| `neo4j-tls` secret owned by neither Flux nor cert-manager | orphan nobody owns |
| 54 kube-router NFLOG rules writing to a group with no consumer | orphan nobody owns |
| `ansible-lint` in the dev group, never run in CI | path nothing exercises |

**Not one was surfaced by the system.** Every one was found by a human or agent
happening to look while doing something else.

The cause is not missing checks. The repository already has good ones —
`validate-cluster` (44 assertions), `live-service-probes` (22 probes),
`validate-network`, and `check_drift.py`. All of them are correct. All of them run
only when a person types them.

**The gap is that nothing runs them on its own.**

A second, compounding problem: three of the eight defects mean provisioning cannot
be safely previewed. `--limit <worker>`, `--tags`, and `--check` are all broken, so
the only working invocation of the provisioning playbook is a full, real, apply-to-
production run. You cannot automate what you cannot dry-run.

## 2. Constraints

- **No in-cluster observability plane, by design.** `cluster-stability.md` classifies
  Prometheus, Grafana, Loki and Promtail as Optional — "disabled until explicitly
  enabled". Confirmed live: prometheus-server, alertmanager, grafana,
  kube-state-metrics and pushgateway are all scaled to `0/0`, and there are no
  `PrometheusRule` resources. Maintenance signals cannot live in Prometheus.
- Monitoring hosted inside the cluster cannot report on the cluster being down.
  For a homelab where the cluster is the system, the audit loop should sit outside it.
- Single operator. Any signal that requires remembering to go and look will be missed —
  that is the failure this design exists to correct, and it must not be reintroduced.
- The cluster is Tailscale-bound; GitHub-hosted runners cannot reach it without
  exporting credentials.

## 3. Design

Three phases. Phases 1 and 2 stand alone and deliver most of the value.

### Phase 1 — Make provisioning dry-runnable

Roughly 20 read-only `command`/`shell` tasks register output that later tasks parse,
but lack `check_mode: false`. Ansible skips command tasks in check mode, so the
registered variable is empty and the consuming task fails. Observed failure:

```
TASK [prerequisites : Parse Tailscale status]
fatal: [sparky]: FAILED! => "the field 'args' has an invalid value
({'tailscale_status_json': '{{ tailscale_status.stdout | from_json }}'})
... Expecting value: line 1 column 1 (char 0)"
```

Every affected task is already `changed_when: false`. Adding `check_mode: false`
matches a pattern the repository already applies correctly in
`k3s_control_plane/tasks/install.yml` and `gitops/tasks/bootstrap_flux.yml`, where
read-only probes are deliberately allowed to run so check mode gets real data.

**Acceptance:** `ansible-playbook provision_cluster.yml --check --diff` completes
across all four nodes with `failed=0`.

Standalone value independent of any automation: provisioning changes become
previewable before they touch a live cluster.

### Phase 2 — One command that asserts everything

Two additions to the `justfile`, following the existing composite-recipe idiom
(`validate`, `pre-push-check`, `post-reconcile-validate`):

```make
# Dry-run provisioning across all nodes. Reports drift; changes nothing.
provision-check:
    uv run ansible-playbook -i {{inventory_file}} {{ansible_dir}}/playbooks/provision_cluster.yml --check --diff

# Everything that asserts the system matches what is declared.
audit: validate validate-network live-service-probes
```

`just validate` already expands to `validate-local` + `validate-cluster`. `just`
propagates failure from any dependency, so no exit-code handling is needed.

`provision-check` is deliberately **not** part of `audit` yet. It is the newest and
least proven component, and it is added in Phase 4 once it has been exercised by
hand. Until then it is run explicitly.

The audit is deliberately **scheduler-agnostic**. Whatever runs it later is a
transport that can be replaced or deleted without touching a single assertion.

### Phase 3 — Run it without being asked

A GitHub Actions self-hosted runner on `sparky`, and one workflow:

```yaml
on:
  schedule: [{cron: '0 9 * * 1'}]
  workflow_dispatch:
jobs:
  audit:
    runs-on: [self-hosted, sparky]
    steps: [checkout, "just audit"]
```

`sparky` is the always-on control plane and already holds the SSH keys, kubeconfig
and inventory the audit needs. Running there means **no credentials are stored in
GitHub**.

GitHub supplies scheduling, retry, run history and failure notification — all of
which a hand-rolled timer would have to reimplement badly. A passing run is silent;
a failing run emails and leaves a durable record in Actions.

**Security constraint, non-negotiable:** the runner is bound to `schedule` and
`workflow_dispatch` triggers only, and is scoped to this repository. It must never
be reachable from `pull_request`, because a self-hosted runner executing PR code
would give any contributor command execution on the control plane as a user holding
SSH keys and kubeconfig. Existing PR CI stays on GitHub-hosted runners, unchanged.

### Phase 4 — Fold the dry run into the schedule

Once `provision-check` has been run by hand enough times to trust its output, add it
to the `audit` recipe:

```make
audit: validate validate-network live-service-probes provision-check
```

No workflow change is needed — the scheduled job already runs `just audit`, so the
new check is picked up automatically. That is the point of keeping the transport
dumb.

The gate for this phase is judgement, not a command: `provision-check` should report
a stable, explainable set of changed tasks across consecutive manual runs before it
is allowed to fail a scheduled job.

## 4. Deliberately excluded

| Excluded | Reason |
|---|---|
| Tracking issues that auto-open and auto-close | GitHub already emails on scheduled-workflow failure, and Actions history is already a durable record. This was the most bespoke component and bought the least. Revisit only if the email proves insufficient. |
| An `--quick`/offline flag on `audit` | `pre-push-check` already covers the offline case. |
| A reporting or output-formatting layer | The underlying scripts already print summaries. |
| A standalone `audit` script | It is a composite recipe, exactly like `validate`. |
| Turning the monitoring tier on | Deliberate architecture decision recorded in `cluster-stability.md`. Out of scope. |
| Unit tests for the Python helpers | All eight observed defects were integration-shaped — orphans, broken wiring, stale claims. Unit tests would have caught none of them. |
| Alerting on NetworkPolicy enforcement gaps | Unobservable by construction: a packet that skips policy evaluation leaves no policy-layer trace. |
| Fixing `--limit <worker>` and `--tags` | Real defects, but they touch `provision_cluster.yml` control flow for a live cluster. Separate work; Phase 1 does not depend on them. |

## 5. Acceptance criteria

- [ ] `ansible-playbook provision_cluster.yml --check --diff` completes with `failed=0` on all four nodes
- [ ] The dry run reports zero changed tasks against a freshly provisioned cluster, or every reported change is explained
- [ ] `just audit` runs `validate`, `validate-network` and `live-service-probes`, and exits non-zero if any fails
- [ ] `just audit` exits 0 against the current healthy cluster
- [ ] `just provision-check` exists and is runnable, but is not yet part of `audit`
- [ ] The scheduled workflow runs on `sparky` and passes
- [ ] The workflow is triggerable only by `schedule` and `workflow_dispatch`
- [ ] Existing PR CI still runs on GitHub-hosted runners and is unchanged
- [ ] No credentials are added to GitHub secrets

## 6. Risks

**The audit becomes noisy and gets ignored.** This is the failure mode that produced
840 misleading UFW records a day. Mitigation: `drift` stays advisory rather than
blocking, and Phase 4 keeps the least-proven check out of the schedule until it is
stable. If the weekly run starts failing for reasons nobody acts on, that is a signal
to fix or remove the check, not to ignore the run.

**The runner is a persistent agent on the control plane.** Mitigated by the trigger
restriction above. It remains the only component here that needs ongoing patching.

**Scope of what this achieves.** It does not remove operator judgement from the loop.
It removes the need to remember to look. That is the achievable win for a cluster
this bespoke, and this design does not claim more.
