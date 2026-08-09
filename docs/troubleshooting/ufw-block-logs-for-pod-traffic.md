# UFW Block Logs for Pod Traffic

## The one-line answer

`[UFW BLOCK] IN=cni0 OUT=flannel.1` records with a `10.42.x` source **and** `10.42.x`
destination are **benign**. They are not a DNS cause. If you found these in `dmesg` or
`journalctl -k` while chasing a DNS incident, this is not it — do not change firewall
policy on this evidence. See [What actually causes the DNS
symptoms](#what-actually-causes-the-dns-symptoms) below for where to look instead.

This page exists because one investigation already reasoned from these records to the wrong
conclusion (`docs/plans/active/2026-08-09-cni-ufw-firewall-investigation.md`). Read on before
repeating it.

---

## Why they appear

UFW's forward path holds **no drop rule** for this traffic. On every node:

- `ufw-user-forward`, `ufw-after-forward`, `ufw-reject-forward`, and `ufw-track-forward` are
  all empty (pre-fix) or contain only the pod-CIDR accept (post-fix).
- The only thing that fires is the `[UFW BLOCK]` `LOG` rule in `ufw-after-logging-forward`.
- The actual routed-deny is enforced by the `FORWARD` chain's **policy `DROP`**, at the very
  end of the chain — not by anything UFW logs.
- `FLANNEL-FWD`, installed by flanneld, sits *after* every UFW chain and accepts any packet
  with source or destination in `10.42.0.0/16`.

So a pod-to-pod packet that falls through to UFW's log rule gets logged, then **accepted one
rule later**. The log line is not a drop notice. It never was.

rig0's live `FORWARD` chain, post-fix (pre-fix is identical except rule 11 has no target
inside `ufw-user-forward`):

```
 1  KUBE-ROUTER-FORWARD         NetworkPolicy enforced here; violations REJECTed
 2-5 kube-proxy chains
 6  ACCEPT mark 0x20000         policy-compliant traffic accepted here
 7-8 DOCKER-USER / DOCKER-FORWARD
 9  ts-forward
10  ufw-before-logging-forward
11  ufw-before-forward -> ufw-user-forward   <- the new ACCEPT lands here (post-fix)
12  ufw-after-forward           (empty)
13  ufw-after-logging-forward   "[UFW BLOCK]" LOG fires here
14  ufw-reject-forward          (empty)
15  ufw-track-forward           (empty)
16  FLANNEL-FWD                 ACCEPT 10.42.0.0/16 -- the old implicit backstop
    policy DROP
```

Applied fix rule: `-A ufw-user-forward -s 10.42.0.0/16 -d 10.42.0.0/16 -j ACCEPT`.

The service CIDR (`10.43.0.0/16`) never appears here and does not need a rule: kube-proxy
DNATs ClusterIP traffic in `nat/PREROUTING`, before `filter/FORWARD` is ever evaluated, so
`FORWARD` never sees a `10.43.x` destination.

---

## Why packet counters must not be trusted here

This is the most important section, and the reason the prior investigation reached the wrong
conclusion.

kube-router rewrites the entire `filter` table on every periodic resync — that rewrite zeroes
**every counter in the table**, including UFW's and Flannel's. This was observed directly,
30 seconds apart:

```
13:30:28  KUBE-ROUTER-FORWARD  37525 pkts
13:30:58  KUBE-ROUTER-FORWARD   1222 pkts   <-- reset
13:31:28  KUBE-ROUTER-FORWARD   6252 pkts
```

A 10-minute capture at 4-second resolution (150 samples) read `ufwlog=0 flannel=0
policydrop=0` across the **entire window** — despite a confirmed 9-record `[UFW BLOCK]`
burst inside it. Six table resets occurred in those ten minutes. The confirmed burst at
`13:40:41` was bracketed by resets at `13:40:28` and `13:40:45` — 17 seconds apart, the
tightest pair in the whole capture, against a typical gap of 70 seconds or more:

```
13:40:28  reset  (29470 ->  56)
13:40:41  <- 9 x [UFW BLOCK] IN=cni0 OUT=flannel.1
13:40:45  reset  ( 1138 -> 111)
```

**The fall-through happens inside kube-router's FORWARD rebuild window.** The counter is
wiped faster than any sampling loop can read it. `ufw status verbose` counters, `iptables -L
-v`, and anything else that reads packet counts on these hosts is structurally unusable as
evidence of whether a chain is "in use" at a point in time. Reason from chain *order*
(`iptables -S FORWARD`), not from counts.

---

## Why rig0 dominates: churn, not pod count

Fleet-wide, rig0 accounts for ~99.7% of all `[UFW BLOCK] IN=cni0 OUT=flannel.1` records.
Raw cumulative counts across nodes are not comparable — journals rotate at their storage cap
(3–4GB) and retained windows differ wildly, so normalize to a rate:

| Node | Records | Retained window | Rate | Running pods | Pods <24h old | Churn |
|---|---|---|---|---|---|---|
| rig0 | 42,246 (previous 62.6-day boot) + 134 (current boot, 3.85h) | — | ~675–836/day | 25 | 10 | 40% |
| strix | 1,291 | 134 days | ~10/day, trending up (Apr 186 → Jul 368) | 13 | 2 | 15% |
| asio | 4 | 52 days | ~0.08/day | 9 | 1 | 11% |
| sparky | 0 | 44 days | 0/day | 56 | 1 | 2% |

sparky has the *most* running pods of any node and *zero* `[UFW BLOCK]` records. Pod count
does not explain the skew — pod **churn** does. Every pod create/delete forces kube-router to
rewrite the `FORWARD` chain, and that rewrite is the fall-through window described above.
rig0's 40% churn (measured as pods younger than 24h over total running pods) tracks its
outsized share of the log records; sparky's 2% churn tracks its complete absence from them.

Present this as well-supported, not proven: churn rank is not perfectly monotonic between
strix and asio (strix has higher churn and far more records, but the middle two nodes are
close enough that other factors — traffic mix, timing — plausibly contribute).

To check current per-node churn yourself:

```bash
KUBECONFIG=/home/al/.kube/config kubectl get pods -A \
  -o custom-columns='NODE:.spec.nodeName,CREATED:.metadata.creationTimestamp' \
  --sort-by=.metadata.creationTimestamp
```

Also note: the LOG rule is rate-limited (`-m limit --limit 3/min --limit-burst 10`, a ceiling
of 4,320 records/day). Bursts of 7–9 records within a single second were observed on rig0,
meaning the limiter was saturating during active windows. **The record counts above are a
throttled sample, not a packet count.** True fall-through volume is unknown and strictly
higher than what the log shows.

---

## Security analysis

The fix (`-A ufw-user-forward -s 10.42.0.0/16 -d 10.42.0.0/16 -j ACCEPT`) does not widen
what was already reachable.

- **Strictly narrower than the existing backstop.** `FLANNEL-FWD` (rule 16, pre-existing)
  accepts any packet with source **or** destination in `10.42.0.0/16` — either endpoint. The
  new rule requires **both**. It cannot permit a single packet that rule 16 would not already
  have permitted one rule later. It has no effect on pod→internet, internet→pod, or NodePort
  traffic — none of those match `-s 10.42.0.0/16 -d 10.42.0.0/16`.
- **Only sees connection-initiating packets.** `ufw-before-forward` accepts
  `RELATED,ESTABLISHED` traffic ahead of the new rule, so by the time a packet reaches it, it
  is always a new connection attempt.
- **The only behavioural delta is that the log line stops firing.** Verified rule counts at
  the time of the change: `ufw-after-forward` 0, `ufw-reject-forward` 0, `ufw-track-forward`
  0, `ufw-after-logging-forward` 1 (the LOG rule itself), `FLANNEL-FWD` 2 (the accept rules).
  Everything the new ACCEPT short-circuits was either empty or would have accepted the packet
  anyway.
- **NetworkPolicy is not bypassed.** kube-router's `KUBE-POD-FW-*` chains terminate with
  `-m mark ! --mark 0x10000/0x10000 -j REJECT --reject-with icmp-port-unreachable` at
  `FORWARD` position 1 — ten rules ahead of UFW. A policy-violating packet is rejected there
  and never reaches the new rule. Tested live: a `default`-namespace pod attempting to reach
  `database/qdrant` at `10.42.1.70:6333` was refused both before and after the change.
- **One genuine regression — stated plainly.** If `FLANNEL-FWD` were absent *and*
  kube-router were mid-rebuild at the same instant, that compound failure used to fail
  **closed** (packet dropped) and now fails **open** (packet accepted by the new rule). This
  is a deliberate fail-open choice: failing closed there means a cluster-wide networking
  outage every time kube-router resyncs while `FLANNEL-FWD` is missing, and NetworkPolicy
  enforcement (rule 1) is unaffected either way — it happens ten rules earlier regardless of
  how this rule resolves. `just validate-network` check 5c warns when `FLANNEL-FWD` is
  absent, which is the precondition for this regression to matter. Check it if you suspect
  this path:

  ```bash
  sudo iptables -S FLANNEL-FWD
  ```

---

## Enforcement gaps (the most important operational finding)

A packet only reaches the `[UFW BLOCK]` LOG rule if it passed `FORWARD` rules 1–6 **without**
being marked `0x20000` — meaning kube-router never evaluated it against NetworkPolicy at all.
It was then accepted downstream (by `FLANNEL-FWD` pre-fix, or by the new rule post-fix). So
rig0 was experiencing on the order of **675 NetworkPolicy-evaluation gaps per day** — windows
where policy simply did not run against a packet, one way or the other.

Almost all of the observed traffic in these gaps was DNS and Postgres traffic that policy
permits anyway (see the flow breakdown above), so in practice this has been low-stakes. But
traffic that a policy **should** deny would also pass unevaluated during the same windows,
and nothing distinguishes it from the benign traffic in the log.

This predates the fix in this document, is neither caused nor widened by it — and is now
**less visible**, because the log line that used to mark these windows no longer fires.

**Enforcement gaps are unobservable by construction.** A packet that skips policy evaluation
leaves no policy-layer trace. "Did denied traffic slip through during a gap?" is permanently
unanswerable after the fact — there is nothing to query. We deliberately chose not to bolt on
a monitor with an invented threshold; a metric built on a fabricated cutoff would give false
confidence, not real coverage. Instead, here is how to reason about the gap directly:

- **Per-node pod churn** (the primary driver of gap frequency — see above):
  ```bash
  KUBECONFIG=/home/al/.kube/config kubectl get pods -A \
    -o custom-columns='NODE:.spec.nodeName,CREATED:.metadata.creationTimestamp'
  ```
- **Whether the backstop accept is present** (does not affect the gap, but affects whether a
  gap fails open or closed):
  ```bash
  sudo iptables -S FLANNEL-FWD
  ```
- **Why counters can't help you here**: see [Why packet counters must not be trusted
  here](#why-packet-counters-must-not-be-trusted-here). Any attempt to correlate
  `KUBE-ROUTER-FORWARD` hit counts with gap frequency will read noise, not signal.

If you need to reduce gap frequency, the lever is pod churn (batch pod restarts, avoid tight
create/delete loops on rig0), not the firewall.

---

## When the logs would mean something real

Only if `FLANNEL-FWD` is absent from the `FORWARD` chain. That removes the backstop accept
that makes today's fall-through benign, and turns the same log line into an actual drop.
`just validate-network` warns on exactly this condition (check 5c). If you see that warning
alongside `[UFW BLOCK]` records, treat it as real and investigate why `FLANNEL-FWD` is
missing (flanneld crash, restart mid-rule-install, etc.) rather than re-deriving this whole
analysis from scratch.

---

## What actually causes the DNS symptoms

DNS timeouts, Flux `github.com` resolution failures, and image-pull DNS failures are a
**separate, unrelated problem**. See
[`flannel-routes-lost-after-tailscale-upgrade.md`](flannel-routes-lost-after-tailscale-upgrade.md).
This document's fix resolves none of those symptoms — it removes benign log noise and makes
an existing implicit accept explicit. It does not claim to improve cluster reliability beyond
that.

---

## The fix that is now in place

- **Rule**: `ufw route allow from 10.42.0.0/16 to 10.42.0.0/16`, applied via the
  `prerequisites` Ansible role (`infrastructure/ansible/roles/prerequisites/tasks/firewall.yml`),
  driven by `k8s_pod_cidr` in `infrastructure/ansible/roles/prerequisites/defaults/main.yml`.
- **Apply to one host**: `just firewall-apply <host>`. This runs a dedicated playbook,
  `infrastructure/ansible/playbooks/firewall.yml` — it does **not** reuse
  `provision_cluster.yml --tags firewall`, for two reasons:
  1. `provision_cluster.yml` pulls the `prerequisites` role via a dynamic `include_role`
     tagged only `prerequisites`. Dynamic includes are opaque to tag selection, so
     `--tags firewall` never selects it — the include point itself is never reached.
  2. `provision_cluster.yml`'s worker play asserts on `k3s_node_token` with `tags: always`,
     and that variable is only defined after the control-plane play has run. Any
     `--limit <worker>` invocation of `provision_cluster.yml` fails on that assertion before
     reaching any firewall task.

  The same assertion means `just provision-host <worker>` is broken today for the same
  reason — this is pre-existing and deliberately left unfixed here; it is out of scope for
  this change.
- **Validate**: `just validate-network` (part of `just validate-cluster`) checks rule
  presence, chain ordering, and `FLANNEL-FWD` presence — see
  `infrastructure/scripts/validate-cluster-network.sh`. It never asserts "zero recent UFW
  blocks" and never reads packet counters, for the reasons given above.

---

## Known gaps, not addressed here

1. **54 kube-router NFLOG rules write NetworkPolicy drops to nflog-group 100 with no consumer
   installed.** Those logs are generated by the kernel and immediately discarded — there is
   no `nflog`/`ulogd`-style listener consuming that group. If you want a real audit trail of
   NetworkPolicy denials, that consumer needs to be built; nothing here provides it.
2. **rig0's 40% pod churn drives both the `FORWARD` rebuild frequency and the enforcement
   gaps described above.** Reducing churn on rig0 (fewer, less frequent pod restarts) would
   reduce both the noise this document explains and the (unobservable) enforcement-gap
   window. No change to reduce that churn is made here.
