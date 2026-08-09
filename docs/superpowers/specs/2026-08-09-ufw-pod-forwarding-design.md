# Design: Make the UFW Pod-Forwarding Contract Explicit

- **Date:** 2026-08-09
- **Status:** approved, not yet implemented
- **Branch:** `fix/ufw-pod-forwarding`
- **Supersedes the conclusions of:** `docs/plans/ideas/2026-08-09-cni-ufw-firewall-investigation.md`

---

## 1. Corrected Problem Statement

The prior investigation concluded that UFW's `deny (routed)` policy was plausibly dropping
pod overlay traffic, and treated the `[UFW BLOCK] IN=cni0 OUT=flannel.1` kernel records as
a candidate cause of the cluster's DNS failures. Live re-inspection of rig0 shows that
conclusion rests on unusable evidence.

### 1.1 Why the original evidence does not hold

The investigation reasoned from iptables packet counters: UFW's forward chains showed no
hits, so UFW appeared not to be in the path. Those counters are reset continuously.
kube-router rewrites the entire `filter` table on its periodic resync, zeroing every
counter in it — including UFW's and Flannel's. Observed directly:

```
13:30:28  KUBE-ROUTER-FORWARD  37525 pkts
13:30:58  KUBE-ROUTER-FORWARD   1222 pkts   <-- reset
13:31:28  KUBE-ROUTER-FORWARD   6252 pkts
```

A 4-second-resolution capture across a confirmed block event at `13:40:41` recorded
`ufwlog=0 flannel=0 policydrop=0` throughout. The counter is wiped faster than it can be
sampled.

**Counters are structurally unusable as evidence on these hosts.** Any future diagnosis —
human or agent — that reasons from them will reach a wrong answer, exactly as this one did.

### 1.2 What is actually happening

UFW's forward path contains no drop rule. `ufw-user-forward`, `ufw-after-forward`,
`ufw-reject-forward` and `ufw-track-forward` are all empty; the only rule is the
`[UFW BLOCK]` LOG in `ufw-after-logging-forward`. The routed-deny is enforced by the
`FORWARD` policy `DROP` at the *end* of the chain. `FLANNEL-FWD` sits after every UFW
chain and accepts anything with source or destination in `10.42.0.0/16`.

rig0's live `FORWARD` chain:

```
 1  KUBE-ROUTER-FORWARD         NetworkPolicy enforced here; violations REJECTed
 2-5 kube-proxy chains
 6  ACCEPT mark 0x20000         policy-compliant traffic accepted here
 7-8 DOCKER-USER / DOCKER-FORWARD
 9  ts-forward
10  ufw-before-logging-forward
11  ufw-before-forward -> ufw-user-forward
12  ufw-after-forward           (empty)
13  ufw-after-logging-forward   "[UFW BLOCK]" LOG fires here
14  ufw-reject-forward          (empty)
15  ufw-track-forward           (empty)
16  FLANNEL-FWD                 ACCEPT 10.42.0.0/16 -- packets survive here
    policy DROP
```

A pod packet that falls through to UFW is **logged as blocked at rule 13 and then accepted
at rule 16**. The log records are benign. They are not the cause of the DNS outages.

The fall-through itself is transient, correlated with kube-router resync windows, and
affects only two flows: `DPT=53` (90 records) and `DPT=5432` (16 records) this boot.

A 10-minute capture at 4-second resolution pins the mechanism precisely. The one block
burst inside the window is bracketed by two kube-router table rewrites 17 seconds apart —
the tightest such pair in the entire capture, against a typical gap of 70s or more:

```
13:40:28  reset  (29470 ->  56)
13:40:41  <- 9 x [UFW BLOCK] IN=cni0 OUT=flannel.1
13:40:45  reset  ( 1138 -> 111)
```

The fall-through happens *inside* kube-router's FORWARD rebuild window. Six resets occurred
in those ten minutes, which is also why all 150 counter samples read zero.

### 1.3 The two defects worth fixing

1. **The accept is implicit and untested.** Pod traffic survives only because flanneld
   appends `FLANNEL-FWD` after UFW's chains. No manifest, playbook, or test states that
   contract. If `FLANNEL-FWD` is ever absent during a fall-through window, the same packets
   drop for real, and the symptom is indistinguishable from today's benign logging.

2. **The logs actively mislead.** They cost one full investigation that reached the wrong
   conclusion. Left alone, they will do so again.

### 1.4 Explicit non-goal

The DNS timeouts, Flux `github.com` resolution failures, and image-pull failures are **not**
addressed by this change. They match the documented Flannel/Tailscale route-loss pattern in
`docs/troubleshooting/flannel-routes-lost-after-tailscale-upgrade.md`. Stating this
plainly, in the docs, is part of the deliverable — so that a future reader does not mistake
this fix for a cure.

---

## 2. Environment Facts Established

Recorded here because several were open questions in the prior investigation.

| Question | Answer | Evidence |
|---|---|---|
| Do all nodes use the Tailscale underlay? | Yes, all four | node `InternalIP` values are `100.x` |
| Should the service CIDR be allowed too? | No | blocked packets read `DST=10.42.0.142 DPT=53` — already DNAT'd. kube-proxy DNATs in `nat/PREROUTING`, before `filter/FORWARD`, so FORWARD never sees a `10.43.x` destination |
| Is this a startup race or steady state? | Neither — transient, recurring | bursts every 7–10 min across the whole uptime, correlated with kube-router resync |
| Is NetworkPolicy enforced before UFW? | Yes, terminally | `KUBE-POD-FW-*` ends with `-m mark ! --mark 0x10000/0x10000 -j REJECT --reject-with icmp-port-unreachable`, at FORWARD position 1 |

Blast radius is uneven: rig0 115 records this boot, asio 4, sparky 0 (strix unreachable
over SSH at inspection time).

`ansible_connection: local` is already configured for rig0 in the inventory, with a comment
explaining the SSH-to-self constraint. No inventory change is required.

---

## 3. Design

### 3.1 The rule

```bash
ufw route allow from 10.42.0.0/16 to 10.42.0.0/16
```

This lands in `ufw-user-forward`, reached from `FORWARD` position 11 — two rules ahead of
the `[UFW BLOCK]` LOG at position 13. Evaluation terminates there. The noise stops, and the
packet's survival no longer depends on `FLANNEL-FWD` existing at that instant.

**CIDR-scoped, not interface-scoped.** The prior investigation proposed
`in on cni0 out on flannel.1` plus its reverse. CIDR-only permits the identical address
space, needs one rule instead of two because it covers the return path, and survives
flannel backend changes, additional bridges, and interface renames. Interface names are the
most likely element to drift — and rig0's wired/wifi failover makes interface-bound rules
actively worse there.

**No service CIDR rule**, for the reason in the table above.

### 3.2 Why this is safe on a node that is also a desktop

rig0 is both a K3s worker and the operator's workstation. Five properties checked:

1. **Host traffic is untouched.** `ufw route` writes only to `FORWARD`. Desktop
   applications use `INPUT`/`OUTPUT`. Nothing changes about what can reach rig0.
2. **No new exposure.** Both endpoints must be in `10.42.0.0/16` — traffic already accepted
   today one rule later. The permitted set is identical; this formalizes the status quo.
3. **NetworkPolicy is not bypassed.** kube-router REJECTs violations terminally at position
   1; a violating packet never reaches position 11. Pods with no policy have no
   `KUBE-POD-FW` chain and already fall through to the accept at 16.
4. **Docker is unaffected.** `DOCKER-USER` sits at positions 7–8, ahead of UFW, and
   `10.42.0.0/16` does not intersect `172.17.0.0/16`.
5. **Wifi failover is unaffected**, because the rule is not bound to `enp11s0`/`wlp8s0`.

### 3.3 Change surface

| File | Change |
|---|---|
| `infrastructure/ansible/roles/prerequisites/defaults/main.yml` | add `k8s_pod_cidr: "10.42.0.0/16"` |
| `infrastructure/ansible/roles/prerequisites/tasks/firewall.yml` | add one `ufw route allow` task, before `Enable UFW` |
| `infrastructure/scripts/validate-cluster-network.sh` | add a "Host firewall forwarding" section |
| `docs/troubleshooting/ufw-block-logs-for-pod-traffic.md` | new |
| `docs/plans/ideas/2026-08-09-cni-ufw-firewall-investigation.md` | move to `docs/plans/active/`, append a corrections section |

The firewalld branch of the role is deliberately left untouched: all four nodes are
Debian/Ubuntu, `firewall_backend` defaults to `ufw`, and untested firewall code is worse
than an acknowledged gap.

The Ansible task:

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

### 3.4 Validation section design

Three assertions in `validate-cluster-network.sh`. All degrade to `warn`, never `fail`,
when UFW is absent or `sudo -n` is unavailable — the script runs unprivileged today and
must keep doing so.

1. **Rule present.** `ufw status verbose` shows a route allow covering the pod CIDR.
   `fail` only when UFW is active and the rule is missing.
2. **Ordering correct.** The accept is reached before `ufw-after-logging-forward`, asserted
   structurally from `iptables -S FORWARD` and `iptables -S ufw-user-forward`.
3. **`FLANNEL-FWD` present.** `warn` if absent — that is precisely the state in which the
   log records would become real drops.

The section will **not** assert "zero recent UFW blocks" as a pass condition, and will not
read packet counters. Both are the traps that produced the original wrong conclusion.

---

## 4. Test Plan

Verification is split by what each method can actually prove.

### 4.1 Deterministic, immediate

- `just lint` (ansible-lint), `just validate-local`, `just check`
- Ansible idempotency: `--check` run, then real run, then re-run showing `changed=0`
- Structural assertion that the new accept precedes the LOG rule, via `iptables -S FORWARD`
  and `iptables -S ufw-user-forward`

### 4.2 Regression — the test that matters

Confirm NetworkPolicy still enforces after the change. From a pod in a namespace carrying
`default-deny-ingress`, attempt a connection the policy forbids and confirm it is still
refused. Section 3.2 argues from chain order that this must hold; this test proves it
rather than assuming it.

### 4.3 Behavioural — slow and honest

The phenomenon is intermittent, so a short quiet window proves nothing. The pre-change
baseline is unusually steady, which makes a clean comparison possible:

| Hour | `IN=cni0 OUT=flannel.1` records |
|---|---|
| 10:00 (partial, boot at 10:56) | 10 |
| 11:00 | 36 |
| 12:00 | 34 |
| 13:00 | 35 |

Approximately **35/hour**. Over a 6-hour post-change window the expectation is ~210
records; success is 0. That is a decisive comparison rather than a hopeful one.

### 4.4 Explicitly not claimed

- That a short post-change quiet period demonstrates success.
- That this change improves DNS reliability, Flux reconciliation, or image pulls.

---

## 5. Rollback

```bash
ufw route delete allow from 10.42.0.0/16 to 10.42.0.0/16
```

Adding an ACCEPT cannot break an existing flow. The failure mode is "no effect", not
"outage". This is the lowest-risk class of firewall change.

---

## 6. Acceptance Criteria

- [ ] `ufw status verbose` on every node shows the pod CIDR route allow
- [ ] `iptables -S FORWARD` shows the accept reached before `ufw-after-logging-forward`
- [ ] Re-running the playbook reports `changed=0`
- [ ] A policy-forbidden connection is still refused post-change
- [ ] Zero `[UFW BLOCK] IN=cni0 OUT=flannel.1` records over a 6-hour window, against a
      ~35/hour baseline
- [ ] `just validate-cluster` passes, including the new section
- [ ] `docs/troubleshooting/ufw-block-logs-for-pod-traffic.md` states that counters are
      unusable and that these logs are not a DNS cause

The 6-hour behavioural window is the only criterion that cannot complete quickly. Every
other criterion is verifiable within minutes of applying the change. If the PR is opened
before that window elapses, the PR description must say so and report the elapsed
observation time and record count, rather than claiming the criterion is met.
