# UFW Pod-Forwarding Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the host firewall's Kubernetes pod-forwarding contract explicit and testable, eliminating ~675-836 misleading `[UFW BLOCK]` records per day on rig0.

**Architecture:** One CIDR-scoped `ufw route allow` rule, managed by the existing `prerequisites` Ansible role and applied via its `firewall` tag so K3s is never restarted. A new host-local validation section asserts the rule structurally — never from packet counters, which kube-router wipes faster than they can be read. Documentation records the corrected analysis so the next investigator does not repeat the original misdiagnosis.

**Tech Stack:** Ansible (`community.general.ufw`), bash, `just`, UFW/iptables-nft on Debian.

## Global Constraints

- Pod CIDR is `10.42.0.0/16`. Service CIDR `10.43.0.0/16` is **not** included — kube-proxy DNATs in `nat/PREROUTING`, before `filter/FORWARD`, so FORWARD never sees a `10.43.x` destination.
- The rule is **CIDR-scoped, never interface-scoped**. No `in on cni0` / `out on flannel.1`.
- The firewalld branch of `firewall.yml` is **left untouched**. All four nodes are Debian/Ubuntu.
- Validation must **never read iptables packet counters** and must **never** assert "zero recent UFW blocks" as a pass condition. Both are the traps that produced the original wrong conclusion.
- Validation must degrade to `warn`, never `fail`, when UFW is absent or `sudo -n` is unavailable. The script runs unprivileged today and must keep doing so.
- All cluster reads use `KUBECONFIG=/home/al/.kube/config`.
- Apply Ansible with `--tags firewall`. A full `just provision-host` run risks restarting K3s on the operator's workstation.
- Commit messages follow `.claude/rules/commits.md` (conventional commits; scopes `ansible`, `scripts`, `docs`, `repo`).
- This change fixes **no** DNS, Flux, or image-pull symptom. Every artifact must say so.

**Branch:** `fix/ufw-pod-forwarding` (already cut; spec committed at `0ff620c`).

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `infrastructure/ansible/roles/prerequisites/defaults/main.yml` | Declare `k8s_pod_cidr` | Modify |
| `infrastructure/ansible/roles/prerequisites/tasks/firewall.yml` | The `ufw route allow` task | Modify |
| `infrastructure/scripts/validate-cluster-network.sh` | Host-local network assertions, incl. new firewall section | Modify |
| `justfile` | Wire the orphaned validator; safe firewall-only apply | Modify |
| `docs/troubleshooting/ufw-block-logs-for-pod-traffic.md` | The durable artifact: why counters lie, why these logs are benign | Create |
| `docs/plans/active/2026-08-09-cni-ufw-firewall-investigation.md` | Original investigation + corrections | Move + modify |

**Pre-existing defect this plan also fixes:** `validate-cluster-network.sh` is orphaned. Nothing references it, and both its own header and `docs/troubleshooting/flannel-routes-lost-after-tailscale-upgrade.md` claim `just validate-cluster` runs it. It does not — `just validate-cluster` runs `validate_cluster.sh`, which never calls it. Adding a check there without wiring it would produce a check that never runs.

---

### Task 1: Wire the orphaned validator and add the failing firewall check

Written first so the check is **red on the live host** before the rule exists.

**Files:**
- Modify: `infrastructure/scripts/validate-cluster-network.sh` (insert before the Summary block at line 179; fix header at lines 11-13)
- Modify: `justfile` (add recipes adjacent to `validate-cluster` at line 123)
- Modify: `docs/troubleshooting/flannel-routes-lost-after-tailscale-upgrade.md` (lines 179-189 claim the wrong command)

**Interfaces:**
- Consumes: nothing.
- Produces: `just validate-network` — runs `infrastructure/scripts/validate-cluster-network.sh` on the current host. Section 5 emits `pass`/`fail`/`warn` through the script's existing `pass()`/`fail()`/`warn()` helpers and increments the existing `FAILURES` counter.

- [ ] **Step 1: Capture the pre-change baseline**

This is evidence for the PR and cannot be recreated after the change. Record the output.

```bash
sudo journalctl -k -b | grep -c 'UFW BLOCK.*IN=cni0 OUT=flannel.1'
sudo journalctl -k -b | grep 'IN=cni0 OUT=flannel.1' | awk '{print $3}' | cut -c1-2 | uniq -c
uptime -s
date
```

Expected: a total in the low hundreds, ~35/hour, boot time, and current time. Save to the PR notes.

- [ ] **Step 2: Add the firewall validation section**

Insert into `infrastructure/scripts/validate-cluster-network.sh` immediately before the `# 5. Summary` divider (currently `# ----` at line 179):

```bash
# ---------------------------------------------------------------------------
# 5. Host firewall pod forwarding
# ---------------------------------------------------------------------------
section "Host Firewall Pod Forwarding"

POD_CIDR="${KUBANI_POD_CIDR:-10.42.0.0/16}"

# Every assertion here reads root-only state. This script is expected to run
# unprivileged, so missing privilege is a skip and never a failure.
SUDO=""
FW_SKIP=""
if [[ $EUID -ne 0 ]]; then
    if sudo -n true 2>/dev/null; then
        SUDO="sudo -n"
    else
        FW_SKIP="not root and passwordless sudo unavailable"
    fi
fi

if [[ -n "$FW_SKIP" ]]; then
    warn "Skipping host firewall checks — $FW_SKIP"
elif ! command -v ufw &>/dev/null; then
    warn "ufw not installed — skipping host firewall checks"
elif ! $SUDO ufw status 2>/dev/null | grep -q '^Status: active'; then
    warn "ufw is not active — skipping host firewall checks"
else
    # 5a. The routed pod CIDR allow must be present.
    if $SUDO ufw status verbose 2>/dev/null | grep 'ALLOW FWD' | grep -q "$POD_CIDR"; then
        pass "UFW route allow for $POD_CIDR is present"
    else
        fail "UFW route allow for $POD_CIDR is MISSING"
        echo ""
        echo "  Pod overlay traffic currently survives only because flanneld"
        echo "  appends FLANNEL-FWD after UFW's chains. Nothing states that"
        echo "  contract. To fix:"
        echo "    just firewall-apply \$(hostname)"
    fi

    # 5b. The accept must be reached before UFW's logging chain, or the
    #     [UFW BLOCK] records continue regardless.
    # `|| true` prevents set -e from aborting the whole script when grep
    # finds no match: under pipefail, a non-matching grep makes the
    # pipeline's exit status non-zero even though cut itself succeeds, and
    # this assignment is not inside an if/while condition where set -e
    # would otherwise let it fail safely. An empty POS_USER/POS_LOG falls
    # through to the warn branch below, which already handles empty values.
    POS_USER=$($SUDO iptables -S FORWARD 2>/dev/null | grep -n -- '-j ufw-before-forward' | cut -d: -f1 || true)
    POS_LOG=$($SUDO iptables -S FORWARD 2>/dev/null | grep -n -- '-j ufw-after-logging-forward' | cut -d: -f1 || true)
    if [[ -n "$POS_USER" && -n "$POS_LOG" && "$POS_USER" -lt "$POS_LOG" ]]; then
        pass "UFW user-forward chain is evaluated before the [UFW BLOCK] log rule"
    else
        warn "Could not confirm UFW chain ordering (user=$POS_USER log=$POS_LOG)"
    fi

    # 5c. FLANNEL-FWD absence is the state in which the log records would
    #     become real drops. Warn rather than fail: flanneld owns this rule.
    if $SUDO iptables -S FLANNEL-FWD &>/dev/null; then
        pass "FLANNEL-FWD chain is present (pod CIDR backstop intact)"
    else
        warn "FLANNEL-FWD chain is ABSENT — pod traffic has no backstop accept"
    fi
fi
```

**Do not** add a check that counts recent `[UFW BLOCK]` records. Counters and log-absence are both unreliable here; see the spec.

- [ ] **Step 3: Run it and confirm the new check FAILS**

```bash
./infrastructure/scripts/validate-cluster-network.sh; echo "exit=$?"
```

Expected: section `Host Firewall Pod Forwarding` prints
`✗ UFW route allow for 10.42.0.0/16 is MISSING`, plus passes for 5b and 5c, and a non-zero exit.

This red state is the point of ordering this task first. If it passes, stop — the rule already exists and the premise is wrong.

- [ ] **Step 4: Fix the stale usage claim in the script header**

Replace lines 11-13 of `infrastructure/scripts/validate-cluster-network.sh`:

```bash
# Usage (must run ON a cluster node — checks host routes and firewall state):
#   ./infrastructure/scripts/validate-cluster-network.sh
#   just validate-network
```

- [ ] **Step 5: Add the justfile recipes**

Insert after the `validate-cluster` recipe (line 123-124):

```make
# Host-local network validation. Must run ON a node: it reads that host's
# routes, UFW state and iptables chains. Distinct from validate-cluster,
# which is kubectl-based and runs from anywhere.
validate-network:
    ./infrastructure/scripts/validate-cluster-network.sh

# Apply only the firewall tasks. Deliberately NOT provision-host: a full
# provisioning run can restart K3s, and rig0 is the operator's workstation.
# ARGS is variadic so `just firewall-apply rig0 --check --diff` works; without
# it just would read --check as another recipe name and fail.
firewall-apply host *ARGS:
    uv run ansible-playbook -i {{inventory_file}} {{ansible_dir}}/playbooks/provision_cluster.yml --limit {{host}} --tags firewall {{ARGS}}
```

- [ ] **Step 6: Correct the troubleshooting doc's wrong command**

In `docs/troubleshooting/flannel-routes-lost-after-tailscale-upgrade.md`, replace `just validate-cluster` with `just validate-network` at lines 182 and 189, and update the surrounding text to say the script checks five dimensions, adding: `5. Host firewall pod-forwarding rules`.

- [ ] **Step 7: Verify the recipes resolve**

```bash
just --list | grep -E 'validate-network|firewall-apply'
just validate-network; echo "exit=$?"
```

Expected: both recipes listed; `just validate-network` reproduces the Step 3 failure.

- [ ] **Step 8: Commit**

```bash
git add infrastructure/scripts/validate-cluster-network.sh justfile \
        docs/troubleshooting/flannel-routes-lost-after-tailscale-upgrade.md
git commit -m "feat(scripts): assert the UFW pod-forwarding contract

validate-cluster-network.sh was orphaned: nothing invoked it, and both its
own header and the flannel troubleshooting doc claimed just validate-cluster
ran it. That recipe runs validate_cluster.sh, which never calls it. Wire it
up as just validate-network and correct both claims.

The new section asserts the pod CIDR route allow, the chain ordering that
makes it effective, and FLANNEL-FWD's presence. It deliberately reads no
packet counters and never treats absence of recent [UFW BLOCK] records as a
pass: kube-router rewrites the filter table often enough to wipe counters
faster than they can be sampled, which is what misled the original
investigation.

Also adds just firewall-apply, so the rule can be applied without a full
provisioning run that could restart K3s.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Add the Ansible-managed UFW route rule

**Files:**
- Modify: `infrastructure/ansible/roles/prerequisites/defaults/main.yml` (after the `flannel_ports` block, before `# Firewall management`)
- Modify: `infrastructure/ansible/roles/prerequisites/tasks/firewall.yml` (after the `Allow Flannel ports through UFW` task, lines 59-66)

**Interfaces:**
- Consumes: `firewall_backend` (existing), the `firewall` tag from `roles/prerequisites/tasks/main.yml`.
- Produces: `k8s_pod_cidr` (string, default `"10.42.0.0/16"`) — consumed by the new task and referenced by Task 4's verification.

- [ ] **Step 1: Add the default**

In `defaults/main.yml`, after the `flannel_ports` list:

```yaml
# Kubernetes pod network. UFW's routed default is deny, so pod-to-pod
# forwarding must be allowed explicitly. Without this rule the traffic
# survives only because flanneld appends FLANNEL-FWD after UFW's chains —
# an implicit dependency, and the source of ~675-836 misleading [UFW BLOCK]
# records per day on rig0. See docs/troubleshooting/ufw-block-logs-for-pod-traffic.md
k8s_pod_cidr: "10.42.0.0/16"
```

- [ ] **Step 2: Add the rule task**

In `firewall.yml`, immediately after the `Allow Flannel ports through UFW` task:

```yaml
- name: Allow routed pod-to-pod traffic through UFW
  community.general.ufw:
    rule: allow
    route: true
    from_ip: "{{ k8s_pod_cidr }}"
    to_ip: "{{ k8s_pod_cidr }}"
    comment: "Kubernetes pod overlay forwarding"
  when: firewall_backend == "ufw"
```

Scoped to the pod CIDR on both ends, so it permits exactly the traffic
`FLANNEL-FWD` already accepts today — no widening. The service CIDR is
deliberately absent, and the rule is deliberately not interface-bound.

- [ ] **Step 3: Lint**

```bash
just lint
```

Expected: no new findings. `community.general.ufw` is already used throughout this file, so the FQCN and module are established.

- [ ] **Step 4: Syntax check without touching any host**

```bash
uv run ansible-playbook -i infrastructure/ansible/inventory/hosts.yml \
  infrastructure/ansible/playbooks/provision_cluster.yml \
  --tags firewall --syntax-check
```

Expected: `playbook: .../provision_cluster.yml` and exit 0.

- [ ] **Step 5: Commit**

```bash
git add infrastructure/ansible/roles/prerequisites/defaults/main.yml \
        infrastructure/ansible/roles/prerequisites/tasks/firewall.yml
git commit -m "fix(ansible): allow routed pod CIDR forwarding in UFW

firewall.yml opened Flannel's VXLAN ports but said nothing about the routed
pod traffic those ports carry -- permitting the transport while denying the
payload, then relying on flanneld's appended FLANNEL-FWD rule to paper over
the gap. Any reprovisioned node inherited that.

The rule is CIDR-scoped rather than interface-bound: it covers the return
path in one rule and survives flannel backend changes and interface renames,
which matters on rig0 where wired/wifi failover moves interfaces. The service
CIDR is not included -- kube-proxy DNATs before filter/FORWARD, so FORWARD
never sees a 10.43.x destination.

Permits exactly what FLANNEL-FWD already accepts, so nothing new is exposed.
NetworkPolicy is unaffected: kube-router REJECTs violations terminally at
FORWARD position 1, well before UFW's chains.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Apply to rig0 and prove the contract holds

rig0 first: it is the noisiest node (115 records this boot vs. 4 on asio, 0 on sparky), and it is the operator's workstation, so any surprise surfaces where it can be observed directly.

**Files:** none — operational task.

**Interfaces:**
- Consumes: `just firewall-apply` and `just validate-network` (Task 1), `k8s_pod_cidr` (Task 2).
- Produces: a verified green host and a recorded NetworkPolicy baseline for Task 4.

- [ ] **Step 1: Record the NetworkPolicy baseline BEFORE the change**

This is the regression control. Capture a connection that policy already forbids.

```bash
export KUBECONFIG=/home/al/.kube/config
TARGET=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus \
  -o jsonpath='{.items[0].status.podIP}')
echo "target=$TARGET"
kubectl run npcheck-pre --rm -i --restart=Never -n default \
  --image=nicolaka/netshoot --command -- \
  timeout 8 nc -vz "$TARGET" 9090; echo "exit=$?"
```

Expected: connection fails (non-zero exit) — `monitoring` carries `default-deny-ingress`.

Two ways this step can be invalid rather than informative, both of which must be resolved before proceeding:

- **`TARGET` is empty** — the label selector did not match. Find a real target with
  `kubectl get pods -n monitoring -o wide` and use any pod IP plus a port it listens on.
- **The connection *succeeds*** — the namespace is not effectively default-deny, so it is
  the wrong control. Pick another from `kubectl get netpol -A`, confirm it denies, and
  record which namespace and port were used so Task 3 Step 7 re-tests the same path.

- [ ] **Step 2: Dry-run against rig0**

```bash
just firewall-apply rig0 --check --diff
```

Expected: exactly one task reports `changed` — `Allow routed pod-to-pod traffic through UFW`. Everything else `ok`. If any other task reports changed, stop and investigate before applying.

- [ ] **Step 3: Apply**

```bash
just firewall-apply rig0
```

Expected: `changed=1`, `failed=0`.

- [ ] **Step 4: Confirm the rule landed where intended**

```bash
sudo ufw status verbose | grep 'ALLOW FWD'
sudo iptables -S ufw-user-forward
sudo iptables -S FORWARD | grep -n -E 'ufw-before-forward|ufw-after-logging-forward'
```

Expected: an `ALLOW FWD` line for `10.42.0.0/16`; an ACCEPT in `ufw-user-forward` matching source and destination `10.42.0.0/16`; and `ufw-before-forward` at a lower line number than `ufw-after-logging-forward`.

- [ ] **Step 5: Confirm the validator is now green**

```bash
just validate-network; echo "exit=$?"
```

Expected: `✓ UFW route allow for 10.42.0.0/16 is present`, plus 5b and 5c passing.

- [ ] **Step 6: Idempotency**

```bash
just firewall-apply rig0
```

Expected: `changed=0`.

- [ ] **Step 7: NetworkPolicy regression — the test that matters**

Re-run the Step 1 control. It must still be refused.

```bash
export KUBECONFIG=/home/al/.kube/config
TARGET=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus \
  -o jsonpath='{.items[0].status.podIP}')
kubectl run npcheck-post --rm -i --restart=Never -n default \
  --image=nicolaka/netshoot --command -- \
  timeout 8 nc -vz "$TARGET" 9090; echo "exit=$?"
```

Expected: still fails, same as Step 1. A **success here is a release blocker** — it would mean the UFW accept is short-circuiting NetworkPolicy, contradicting the chain analysis. If that happens, roll back immediately:

```bash
sudo ufw route delete allow from 10.42.0.0/16 to 10.42.0.0/16
```

- [ ] **Step 8: Confirm the cluster is undisturbed**

```bash
KUBECONFIG=/home/al/.kube/config kubectl get nodes
just validate-cluster
```

Expected: four nodes `Ready`; `validate-cluster` no worse than its pre-change result.

- [ ] **Step 9: Record the observation window start**

```bash
date; sudo journalctl -k -b | grep -c 'UFW BLOCK.*IN=cni0 OUT=flannel.1'
```

Note both. Task 6 compares against this. No commit — this task changes no files.

---

### Task 4: Roll out to sparky, asio and strix

**Files:** none — operational task.

**Interfaces:** consumes Task 2's rule and Task 1's recipes.

- [ ] **Step 1: Dry-run all three**

```bash
just firewall-apply sparky --check --diff
just firewall-apply asio --check --diff
just firewall-apply strix --check --diff
```

Expected: one changed task each. `strix` was unreachable over SSH during investigation — if it fails to connect, complete the other two, and record strix as outstanding rather than reporting the rollout complete.

- [ ] **Step 2: Apply, one at a time**

```bash
just firewall-apply sparky
just firewall-apply asio
just firewall-apply strix
```

Expected: `changed=1, failed=0` each. Between each, confirm nodes stay `Ready`:

```bash
KUBECONFIG=/home/al/.kube/config kubectl get nodes
```

- [ ] **Step 3: Verify each host**

```bash
for h in sparky asio strix; do
  echo "=== $h ==="
  ssh "$h" "sudo ufw status verbose | grep 'ALLOW FWD'"
done
```

Expected: an `ALLOW FWD` line for `10.42.0.0/16` on each reachable host.

- [ ] **Step 4: Idempotency across the fleet**

```bash
just firewall-apply sparky; just firewall-apply asio; just firewall-apply strix
```

Expected: `changed=0` for each.

No commit — this task changes no files.

---

### Task 5: Document the corrected analysis

The highest-value artifact. The rule stops today's noise; this stops the next misdiagnosis.

**Files:**
- Create: `docs/troubleshooting/ufw-block-logs-for-pod-traffic.md`
- Move: `docs/plans/ideas/2026-08-09-cni-ufw-firewall-investigation.md` → `docs/plans/active/`
- Modify: the moved file (append a corrections section)
- Modify: `docs/troubleshooting/README.md` (add an index entry)

**Interfaces:** consumes the evidence in `docs/superpowers/specs/2026-08-09-ufw-pod-forwarding-design.md`.

- [ ] **Step 1: Write the troubleshooting page**

Create `docs/troubleshooting/ufw-block-logs-for-pod-traffic.md` covering, in this order:

1. **The one-line answer up front:** `[UFW BLOCK] IN=cni0 OUT=flannel.1` records with `10.42.x` source and destination are **benign**. They are not a DNS cause. Do not change firewall policy in response to a DNS incident on this evidence.
2. **Why they appear:** UFW's forward path holds no drop rule — `ufw-user-forward`, `ufw-after-forward`, `ufw-reject-forward` and `ufw-track-forward` are empty; the only rule is the LOG in `ufw-after-logging-forward`. Routed-deny is enforced by the `FORWARD` policy `DROP` at the end. `FLANNEL-FWD` sits after every UFW chain and accepts `10.42.0.0/16`. The packet is logged, then accepted one rule later. Include the annotated FORWARD chain listing from spec §1.2.
3. **Why packet counters must not be trusted here** — the most important section. kube-router rewrites the whole `filter` table on resync, zeroing every counter including UFW's. Include the observed reset sequence and the finding that a 4-second-resolution capture read zero across a confirmed block event, with six resets in ten minutes.
4. **When the logs would mean something real:** only if `FLANNEL-FWD` is absent. `just validate-network` warns on exactly that.
5. **What actually causes the DNS symptoms:** link `flannel-routes-lost-after-tailscale-upgrade.md`.
6. **The fix that is now in place:** the Ansible-managed rule, `just firewall-apply <host>`, and `just validate-network`.

- [ ] **Step 2: Move the investigation doc and append corrections**

```bash
git mv docs/plans/ideas/2026-08-09-cni-ufw-firewall-investigation.md docs/plans/active/
```

Append a `## Corrections (2026-08-09)` section stating plainly:

- The "UFW forward chains had no live counter hits" evidence does not hold; counters are wiped by kube-router faster than they can be sampled.
- UFW was never dropping this traffic; the records are logged-then-accepted.
- The fall-through is transient and occurs inside kube-router's FORWARD rebuild window — not at boot, not in steady state. Cite the 17-second reset bracket around the 13:40:41 burst.
- Open question 1: all four nodes use the Tailscale underlay.
- Open question 2: the service CIDR is not needed; traffic is already DNAT'd before FORWARD.
- Open question 3: transient kube-router reprogramming, answered above.
- Open question 4 (CoreDNS locality) remains open and out of scope.
- The recommended interface-bound rules were replaced by a single CIDR-scoped rule.

Do not edit the original body. The corrections section supersedes it; preserving the original reasoning is what makes the correction legible.

- [ ] **Step 3: Index the new page**

Add to `docs/troubleshooting/README.md`, matching the existing entry format:

```markdown
- [UFW block logs for pod traffic](ufw-block-logs-for-pod-traffic.md) — `[UFW BLOCK] IN=cni0 OUT=flannel.1` records are benign; why iptables counters cannot be trusted on these hosts.
```

- [ ] **Step 4: Verify links and hooks**

```bash
just check
grep -c 'ufw-block-logs-for-pod-traffic' docs/troubleshooting/README.md
```

Expected: hooks pass; the grep returns 1.

- [ ] **Step 5: Commit**

```bash
git add docs/
git commit -m "docs(troubleshooting): record why UFW pod-traffic blocks are benign

The [UFW BLOCK] IN=cni0 OUT=flannel.1 records already cost one full
investigation that reached the wrong conclusion, and nearly enshrined
'UFW was blocking pod traffic' in the runbook as a DNS cause. The new page
states the answer first, then the chain ordering that makes these records
logged-then-accepted, then the reason packet counters cannot be trusted on
these hosts at all.

The original investigation moves to active/ with a corrections section
rather than being rewritten: preserving the original reasoning is what makes
the correction legible to the next reader.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Observe, then open the PR

**Files:** none until the PR body.

**Interfaces:** consumes the Task 1 baseline and the Task 3 window start.

- [ ] **Step 1: Full local gate**

```bash
just pre-push-check
```

Expected: passes. Address anything `just drift` reports — the wiring fix in Task 1 may change its output.

- [ ] **Step 2: Let the observation window run**

The pre-change rate was ~35 records/hour, steady across three full hours. A 6-hour window gives an expectation of ~210 records against a target of 0 — decisive. Shorter windows are not.

```bash
sudo journalctl -k --since "<window start from Task 3 Step 9>" \
  | grep -c 'UFW BLOCK.*IN=cni0 OUT=flannel.1'
```

Expected: 0.

- [ ] **Step 3: Final verification sweep**

```bash
just validate-network
just validate-cluster
KUBECONFIG=/home/al/.kube/config kubectl get nodes
```

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin fix/ufw-pod-forwarding
```

The PR body must:

- Lead with what this is: **log-noise elimination and firewall hygiene. It fixes no DNS, Flux, or image-pull symptom.**
- State the corrected finding: UFW was never dropping this traffic, and the original evidence rested on counters that kube-router wipes.
- Give the before/after record counts with the elapsed observation window.
- Confirm the NetworkPolicy regression result from Task 3 Step 7.
- Note any node not yet applied (e.g. strix if unreachable).
- **If the 6-hour window has not elapsed, say so explicitly** and report elapsed time and count rather than claiming the criterion is met.
- Link the spec and this plan.

---

## Acceptance Criteria

- [ ] `ufw status verbose` on every reachable node shows an `ALLOW FWD` line for `10.42.0.0/16`
- [ ] `iptables -S FORWARD` shows `ufw-before-forward` ahead of `ufw-after-logging-forward`
- [ ] `just firewall-apply <host>` reports `changed=0` on a second run
- [ ] The policy-forbidden connection from Task 3 Step 1 is still refused after the change
- [ ] `just validate-network` passes on rig0
- [ ] `just validate-cluster` no worse than its pre-change result
- [ ] Zero `[UFW BLOCK] IN=cni0 OUT=flannel.1` records across the observation window, against a ~35/hour baseline — or the shortfall stated plainly in the PR
- [ ] `docs/troubleshooting/ufw-block-logs-for-pod-traffic.md` states that counters are unusable and that these records are not a DNS cause
- [ ] No change to the firewalld branch of `firewall.yml`
