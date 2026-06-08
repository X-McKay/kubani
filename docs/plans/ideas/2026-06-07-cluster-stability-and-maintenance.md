# Cluster Stability & Maintainability Plan

- **Date:** 2026-06-07
- **Status:** ideas
- **Author:** investigation via Claude Code (on rig0)
- **Goal:** Stop the cluster from creating network/resource problems and make it easy to keep healthy.

---

## Snapshot at time of writing

| Node | Role | Status | Notes |
|------|------|--------|-------|
| `sparky` | control-plane (sole) | Ready | ARM64 DGX Spark, GB10 GPU; also the API endpoint (`100.71.65.62:6443`) |
| `strix` | worker | Ready | amd64, **8 CPU / 15 GB** — currently carrying nearly the whole stack |
| `rig0` | worker | **NotReady** | RTX 5090; `k3s-agent` **disabled + manually stopped** (19:09, boot-stability work). This host. |
| `asio` | worker | **NotReady** | down ~19 days (kubelet last posted 2026-05-19); offline on Tailscale |

Consequences observed:
- **36 ghost `Terminating` pods** stranded on rig0/asio (kubelets unreachable, can't confirm deletion). Replacements already run on sparky/strix.
- **neo4j** and **qdrant** stuck `ContainerCreating` — Longhorn volumes (`pvc-64f9dca6…`, `pvc-674067b0…`) can't attach to strix because they're still held by dead rig0 (`VolumeAttachment` ATTACHED=false).
- **temporal-web** CrashLoopBackOff — OIDC discovery to `auth.almckay.io` returns `connection refused` (SSO/ingress dependency, not the network substrate).
- **3 vLLM** pods in `UnexpectedAdmissionError` (stale GPU-admission failures).
- **Astronomical restart counters** from months of flapping: source-controller 5935, helm-controller 5928, kustomize-controller 5039, an NFD worker 7670, gpu-operator 4182.

---

## Root causes (ranked)

1. **Cluster dataplane rides Tailscale, and rig0's Tailscale path rides WiFi backhaul.** All nodes run Flannel VXLAN bound to `tailscale0` (`--flannel-iface tailscale0`, Ansible-generated). Binding K3s to Tailscale is an intentional, documented invariant — but rig0 reaching the mesh over the Nest WiFi backhaul makes its link blip, which drops Flannel routes (see `docs/troubleshooting/flannel-routes-lost-after-tailscale-upgrade.md`) → NodeNotReady flaps → eviction churn → controller crash-loops.
2. **rig0 is missing the `tailscale-recovery.conf` systemd drop-in.** `/etc/systemd/system/k3s-agent.service.d/` does not exist on rig0, so the automatic "restart K3s when Tailscale restarts" route-recovery (relied on per `cluster-stability.md`) is **not active here**. rig0 was never fully reconciled to current provisioning standard, or it was rolled back during boot debugging.
3. **No control-plane HA.** `sparky` is the only master and the API endpoint. A sparky reboot = full API outage.
4. **No capacity headroom / governance.** With 2 of 4 nodes down, everything lands on sparky + strix; strix at 15 GB RAM is the squeeze point. Missing/loose requests-limits and PDBs mean nothing prevents overcommit.

---

## Plan

### Tier 0 — Immediate recovery (reversible)
- [ ] Force-delete the 36 ghost `Terminating` pods on rig0/asio and the 3 `UnexpectedAdmissionError` vLLM pods. Pure API cleanup; controllers own replacements.
- [ ] Recover neo4j/qdrant: release the two Longhorn volumes from dead rig0 so they attach to strix (resolved automatically if rig0 is brought back cleanly — see Tier 1).
- [ ] temporal-web: confirm `auth.almckay.io` OIDC endpoint is serving once auth/Traefik settle; restart temporal-web after. Tracked separately from the network substrate.

### Tier 1 — Fix the substrate (the health lever)
- [ ] **Move rig0's Tailscale path onto wired LAN** (not the WiFi backhaul). This is the rig0-specific instability; sparky/strix already have direct `192.168.86.x` paths.
- [ ] **Install the `tailscale-recovery.conf` drop-in on rig0** via `just provision-host rig0` so Flannel routes self-heal on Tailscale restart (closes the gap that the rest of the cluster already has).
- [ ] Re-enable `k3s-agent` on rig0 (`systemctl enable --now`) only after the above, and soak before trusting it. See risk table.
- [ ] Recover `asio` (intended live): diagnose why it's been down 19 days, re-provision, rejoin.

### Tier 2 — Keep it healthy with minimal effort (GitOps)
- [ ] Resource governance: requests/limits + PodDisruptionBudgets on core/platform tiers so strix can't be overcommitted; anti-affinity so stateful singletons (postgres, redis) don't co-locate.
- [ ] Roll the Flux/gpu-operator controllers once stable to reset the absurd restart counters (so alerting is meaningful again).
- [ ] Consider a 2nd/3rd control-plane (etcd quorum) for real HA — larger change, optional.
- [ ] Prune duplicate Longhorn/postgres image layers piling up on nodes (disk hygiene).

---

## Risk / recovery for the disruptive actions

| Action | Risk if it goes wrong | Recovery |
|--------|----------------------|----------|
| Force-delete ghost pods + UAE pods | Low — replacements already running on healthy nodes | Controllers recreate anything still desired |
| Release Longhorn volumes from dead rig0 | Low–med — must not be a live writer (old pods are dead) | Longhorn reattaches; replicas intact on healthy nodes |
| Re-enable k3s-agent on rig0 | **Reboot-class** — may re-trigger the flap/thrash being debugged | `systemctl disable --now k3s-agent` returns to current parked state; see `rig0-boot-investigation` notes |
| Rewire rig0 to wired LAN | Brief rig0 network blip | Revert cabling / interface; nodes rejoin |
| Add HA control-plane | etcd mis-init could disrupt API | Snapshot first; k3s supports rejoin/restore |

---

## Verification

```bash
just validate-cluster        # tailscale0 iface, pod CIDR routes, CoreDNS, cross-node ping
just nodes                   # all Ready
just pods | grep -v Running  # no ghosts / crashloops
just flux-status             # Flux reconciled
```

## Open decisions
1. rig0: re-enable now (with substrate fixes first) vs keep parked until BIOS/boot work from `rig0-boot-investigation` is done?
2. asio: recover in place vs reinstall?
3. HA control-plane: in scope now, or later?
