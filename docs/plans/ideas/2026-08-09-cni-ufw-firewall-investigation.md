# CNI / UFW Firewall Investigation

- **Date:** 2026-08-09
- **Status:** investigation only
- **Author:** investigation via Codex on rig0
- **Scope:** Diagnose reported UFW blocks for `cni0 -> flannel.1` traffic without changing cluster or firewall state.

---

## Executive Summary

The cluster is showing real network symptoms: DNS lookups from workloads have timed out, image pulls have failed on DNS, Flux has failed to resolve GitHub, and application readiness checks have timed out. Kernel logs also contain repeated `[UFW BLOCK]` records for pod traffic leaving `cni0` toward `flannel.1`, including DNS to CoreDNS and PostgreSQL traffic to the database namespace.

The current live firewall counters do not prove that UFW is still dropping all matching traffic at the moment of inspection. The active `FORWARD` path has Kubernetes chains before UFW, and policy-marked packets are accepted before UFW's forward chains. However, UFW is configured with `deny (routed)` and the Ansible firewall role does not explicitly allow routed pod CIDR traffic between `cni0` and `flannel.1`. That is a real configuration gap: during startup, route churn, kube-router programming gaps, or packets not yet policy-marked, UFW can log or block pod overlay traffic that should be owned by the Kubernetes dataplane.

No cluster state or firewall rules were changed during this investigation.

---

## Evidence Collected

### Host firewall state

`ufw status verbose` showed:

- UFW is active.
- Incoming default policy is deny.
- Outgoing default policy is allow.
- Routed default policy is deny.
- Node-facing Kubernetes and Flannel ports are allowed, including kubelet `10250/tcp`, NodePort examples, Flannel `8472/udp`, and Flannel `8285/udp`.
- Tailscale `100.64.0.0/10` is allowed.

The important point is that exposed node ports and Flannel UDP ports are allowed, but routed pod-to-pod forwarding is not explicitly allowed by UFW.

### Forwarding chain order

`iptables` / `nft` inspection showed:

- `FORWARD` policy is `DROP`.
- Kubernetes chains run before UFW's forward chains.
- `KUBE-ROUTER-FORWARD` and `KUBE-FORWARD` had live packet counters.
- A rule accepting packets marked `0x20000` had live packet counters.
- UFW forward/logging chains had no live counter hits at the time inspected.
- `FLANNEL-FWD` exists but is appended late in `FORWARD` and had zero live hits at the time inspected.
- `FLANNEL-FWD` accepts traffic with source or destination `10.42.0.0/16`.

This means policy-compliant traffic may currently be accepted by kube-router before UFW sees it, but `FLANNEL-FWD` is not usefully protecting the traffic if packets reach UFW earlier or lack the expected mark.

### UFW block logs

Kernel logs from the current boot contain repeated UFW block records like:

- `IN=cni0 OUT=flannel.1 ... SRC=10.42.1.x DST=10.42.0.142 PROTO=UDP DPT=53`
- `IN=cni0 OUT=flannel.1 ... SRC=10.42.1.x DST=10.42.3.43 PROTO=TCP DPT=5432`

The DNS destination `10.42.0.142` is a CoreDNS pod on `sparky`. The PostgreSQL destination `10.42.3.43` is a database pod on `strix`. The source pod CIDR `10.42.1.0/24` is on `rig0`.

These records are consistent with cross-node pod traffic leaving a local pod bridge and entering the Flannel overlay. They are also consistent with the failure mode described in `docs/troubleshooting/flannel-routes-lost-after-tailscale-upgrade.md`: cross-node pod routing problems first appear as DNS failures and service timeouts.

### Cluster symptoms

Read-only event inspection found recent network-related failures:

- `flux-system` GitRepository reconciliation failed because DNS lookup for `github.com` via `10.43.0.10:53` timed out.
- `falkordb` image pull failed because DNS lookup for `registry-1.docker.io` returned a temporary DNS failure.
- `authentik-server` readiness probes timed out against an internal pod IP and port.
- `strix` had `NodeNotReady` events around the same incident window.
- Longhorn and SMB CSI components reported timeout and termination delays during the same turbulence.

These symptoms point to real cluster networking instability, not just noisy logging.

### NetworkPolicy state

The relevant NetworkPolicies appear logically correct:

- The `database`, `temporal`, `cache`, `monitoring`, and `vllm` namespaces include DNS egress policies to `kube-system` on TCP/UDP `53`.
- The live `kube-system` namespace has the expected `kubernetes.io/metadata.name: kube-system` label.
- `temporal` has egress to the `database` namespace on TCP `5432`.
- `database` allows ingress to PostgreSQL from `temporal` and auth workloads.

This makes a pure NetworkPolicy authoring bug less likely. If DNS or PostgreSQL packets were dropped, likely causes include host firewall forwarding behavior, transient kube-router rule programming, route churn, or pod startup races before packets are marked/accepted.

### Repository firewall automation

`infrastructure/ansible/roles/prerequisites/tasks/firewall.yml` configures UFW for host-facing services and Flannel UDP ports, then enables UFW. It does not currently manage either of these explicitly:

- UFW default routed policy for Kubernetes nodes.
- UFW route allow rules for pod CIDR forwarding between `cni0`, `flannel.1`, and the Tailscale-backed overlay.

This means a reprovisioned node can remain vulnerable to the same routed-forwarding mismatch.

---

## Working Theory

There are two overlapping issues:

1. **Host firewall policy is not explicitly Kubernetes-CNI aware.** UFW is configured to deny routed traffic by default. Kubernetes currently gets some traffic through by chain order and packet marks, but that is an implicit dependency rather than a deliberate host firewall contract.
2. **The cluster already has a known Flannel/Tailscale route fragility pattern.** When Tailscale or node connectivity blips, Flannel routes can disappear or become stale until K3s recreates them. During those windows, CoreDNS and cross-node service traffic can fail.

The UFW block logs are credible and should not be ignored. At the same time, because live counters showed Kubernetes accepts before UFW at the inspected moment, the next repair should validate with packet counters and targeted connectivity tests immediately before and after any firewall change.

---

## Recommended Repair Plan

These are proposed next steps only. They were not executed.

### 1. Confirm current dataplane health

Run the existing validation workflow:

```bash
just validate-cluster
```

Also confirm routes on each node:

```bash
ip route show | grep 10.42
```

Expected result: every node should have its local `10.42.x.0/24` route on `cni0` plus routes to the other node pod CIDRs via `flannel.1`.

### 2. Add explicit UFW route allowances for pod overlay forwarding

Prefer narrow route allows over changing the global routed default to allow.

Candidate rules to model in Ansible, adjusted per node/interface reality:

```bash
ufw route allow in on cni0 out on flannel.1 from 10.42.0.0/16 to 10.42.0.0/16
ufw route allow in on flannel.1 out on cni0 from 10.42.0.0/16 to 10.42.0.0/16
```

If validation shows same-node-to-overlay or overlay-to-node paths cross `tailscale0` directly on any host, add similarly narrow route rules for that observed path rather than broadening all routed traffic.

Persist the fix in `infrastructure/ansible/roles/prerequisites/tasks/firewall.yml`; do not hand-edit nodes as the long-term fix.

### 3. Keep UFW default routed deny unless testing proves it is untenable

Changing UFW's routed default to allow would likely make the symptom disappear, but it is broader than necessary. The preferred repair is an explicit allowlist for Kubernetes pod CIDR forwarding and Flannel overlay interfaces.

### 4. Re-check chain order after any UFW or K3s restart

After applying a future fix, verify:

```bash
iptables -L FORWARD -v -n --line-numbers
iptables -S FORWARD
iptables -S FLANNEL-FWD
```

Acceptance criteria:

- Pod CIDR forwarding is accepted before any UFW deny/log rule.
- UFW log counters no longer increase for valid `10.42.0.0/16 -> 10.42.0.0/16` traffic.
- `just validate-cluster` passes.
- Flux and image pulls no longer show DNS timeout events.

### 5. Revisit CoreDNS locality separately

CoreDNS currently has pods on multiple nodes, but kube-proxy can still send a pod's DNS query to a remote CoreDNS endpoint. That is normal ClusterIP behavior, but it means DNS depends on cross-node overlay health.

Possible future improvements:

- Add topology-aware routing for CoreDNS if supported by the current cluster configuration.
- Run CoreDNS with one endpoint per node before considering `internalTrafficPolicy: Local`.

Do not set `internalTrafficPolicy: Local` on kube-dns unless every schedulable node is guaranteed to have a local CoreDNS endpoint; otherwise nodes without CoreDNS would lose DNS.

---

## Validation Checklist For A Future Repair Window

- [ ] Capture `ufw status verbose`.
- [ ] Capture `iptables -L FORWARD -v -n --line-numbers`.
- [ ] Capture recent `journalctl -k` UFW block counters for `cni0` and `flannel.1`.
- [ ] Run `just validate-cluster`.
- [ ] Apply the Ansible-managed firewall route rules.
- [ ] Re-run the same captures.
- [ ] Confirm no new `[UFW BLOCK] IN=cni0 OUT=flannel.1` entries for DNS or PostgreSQL traffic.
- [ ] Confirm Flux, image pulls, and application readiness checks stop reporting DNS or internal service timeouts.

---

## Files To Touch In A Future Fix

- `infrastructure/ansible/roles/prerequisites/tasks/firewall.yml`
- `infrastructure/ansible/roles/prerequisites/defaults/main.yml`, only if the pod CIDR or interface names should become configurable defaults.
- `infrastructure/scripts/validate-cluster-network.sh`, if it does not already assert UFW route behavior and CNI-to-Flannel forwarding.

---

## Open Questions

1. Are all current nodes expected to use Flannel VXLAN over `tailscale0`, or are any nodes using LAN underlay directly?
2. Should UFW route allowances be constrained to `10.42.0.0/16` only, or should service CIDR `10.43.0.0/16` be included after route inspection?
3. Was the observed UFW logging during a node-route recovery window, a kube-router policy programming delay, or a steady-state path for specific traffic classes?
4. Should CoreDNS scheduling be changed so every active node has a local DNS endpoint?
