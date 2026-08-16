# Control Plane to asio — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the K3s control plane from sparky to asio (sqlite → embedded etcd → join → demote) and move all non-daemonset services off sparky so its memory is free for in-cluster fine-tuning.

**Architecture:** Promote asio to a second K3s server while it is still cordoned and empty, re-point agents and kubeconfigs, rebalance workloads onto the uncordoned workers, then demote sparky to an agent behind an `nvidia.com/gpu=true:NoSchedule` taint. Ansible inventory/roles are updated first so the repo describes the target state; the one-time promote/demote surgery is guided imperative commands; Ansible converges afterward.

**Tech Stack:** K3s v1.34.7+k3s1, Ansible (uv-managed), Flux GitOps, Longhorn, kubectl.

**Spec:** `docs/plans/active/2026-08-16-control-plane-to-asio.md` (moved from `ideas/` in Task 1, with two amendments recorded there — taint key and phase order).

## Global Constraints

- Always `KUBECONFIG=/home/al/.kube/config` for kubectl.
- The K3s join token is read at run time on cluster hosts only — it must never be written into the repo, the plan, logs, or any file inside a git checkout.
- No Ansible play may target rig0 in this plan. rig0 changes are two manual one-line edits executed locally.
- K3s version everywhere: `v1.34.7+k3s1`.
- `provision_cluster.yml` asserts exactly one `control_plane` host — the inventory keeps a single control-plane node (asio).
- Host IPs: sparky `100.71.65.62`, asio `100.92.107.71`, strix `100.76.45.84`, rig0 `100.77.107.81` (local).
- SSH as the ansible user with passwordless sudo (same access Ansible uses): `ssh 100.92.107.71 "sudo ..."`.
- Design amendments baked into this plan (recorded in the spec in Task 1):
  1. sparky's taint is **`nvidia.com/gpu=true:NoSchedule`**, not `gpu-workloads`: every gpu-operator daemonset tolerates only the `nvidia.com/gpu` key, and the device plugin must keep running on sparky for fine-tuning to claim the GPU. Verified against live daemonset tolerations 2026-08-16.
  2. Phase order: promote asio **before** uncordoning/rebalancing — asio is cordoned and empty, so reinstalling its k3s is zero-disruption, and agents are never pointed at a dead server.
- Expected losses on sparky after the taint (accepted): `svclb-traefik` (tolerates only control-plane/CriticalAddonsOnly; LB endpoints remain on asio/strix/rig0 and external-dns updates records) and all Longhorn daemonset pods (Longhorn is being disabled on sparky anyway). Survivors: node-exporter, csi-nfs-node, csi-smb-node (universal tolerations), gpu-operator stack (`nvidia.com/gpu` toleration).

---

### Task 1: Repo — inventory, server template, spec amendments

**Files:**
- Modify: `infrastructure/ansible/inventory/hosts.yml`
- Modify: `infrastructure/ansible/roles/k3s_control_plane/templates/k3s-server-config.yaml.j2`
- Move+Modify: `docs/plans/ideas/2026-08-16-control-plane-to-asio.md` → `docs/plans/active/2026-08-16-control-plane-to-asio.md`

**Interfaces:**
- Produces: inventory where `control_plane` = asio (with `k3s_cluster_init: true`) and `workers` = rig0, sparky, strix; sparky worker entry carries the `nvidia.com/gpu=true:NoSchedule` taint; rig0 has no taint entry. Tasks 8–9 run Ansible against this inventory.

- [ ] **Step 1: Rewrite the inventory topology**

In `infrastructure/ansible/inventory/hosts.yml`:

1. Update the header comment to:

```yaml
---
# Kubani Cluster Inventory
# Control Plane: asio
# Workers: rig0, sparky, strix
```

2. Replace the `control_plane` group's `sparky` entry with asio (moving asio's existing host vars up from `workers` and adding `k3s_cluster_init`):

```yaml
    control_plane:
      hosts:
        asio:
          ansible_host: 100.92.107.71
          tailscale_ip: 100.92.107.71
          # Wired to the LAN switch — block WiFi so Tailscale stays on the
          # switch hop instead of falling back to the WiFi router.
          block_wifi: true
          # First etcd member. Ignored on restarts once etcd is initialized;
          # required for disaster-recovery rebuilds from scratch.
          k3s_cluster_init: true
          reserved_cpu: "500m"
          reserved_memory: "1Gi"
          topology_labels:
            topology.kubani.io/site: primary
            topology.kubani.io/network-zone: lan
            topology.kubani.io/usage-class: general
          node_labels:
            node-role: control-plane
            workstation: "true"
```

3. In `workers`, remove the old `asio` entry and add `sparky` (keeping its
   existing vars, with `node-role` flipped to `worker` and the taint changed
   from `gpu-workloads`/`PreferNoSchedule` to `nvidia.com/gpu`/`NoSchedule`):

```yaml
        sparky:
          ansible_host: 100.71.65.62
          tailscale_ip: 100.71.65.62
          # Wired to the LAN switch — block WiFi so Tailscale stays on the
          # switch hop instead of falling back to the WiFi router.
          block_wifi: true
          reserved_cpu: "4"
          reserved_memory: "8Gi"
          gpu: true
          topology_labels:
            topology.kubani.io/site: primary
            topology.kubani.io/network-zone: lan
            topology.kubani.io/usage-class: inference
          node_labels:
            node-role: worker
            gpu: "true"
            workstation: "true"
          # NoSchedule keeps everything off sparky except workloads that
          # explicitly tolerate it (fine-tuning jobs, gpu-operator stack).
          # Key must be nvidia.com/gpu — the gpu-operator daemonsets
          # tolerate only that key.
          node_taints:
            - key: nvidia.com/gpu
              value: "true"
              effect: NoSchedule
```

4. In the `rig0` entry, delete the whole `node_taints:` block (the
   `nvidia.com/gpu` NoSchedule taint). It never matched the live node, and
   the databases scheduled on rig0 depend on its absence. Leave everything
   else about rig0 untouched.

- [ ] **Step 2: Add optional cluster-init to the server config template**

In `infrastructure/ansible/roles/k3s_control_plane/templates/k3s-server-config.yaml.j2`, insert directly after the `# API server` / `write-kubeconfig-mode: "0600"` block:

```jinja
{% if k3s_cluster_init | default(false) %}
# Embedded etcd (first member). Ignored on restart once etcd is initialized.
cluster-init: true
{% endif %}
```

- [ ] **Step 3: Move and amend the spec**

```bash
git mv docs/plans/ideas/2026-08-16-control-plane-to-asio.md docs/plans/active/
```

In the moved file: change `**Status:**` to `Implementation in progress`; in the "End State" and "Phases" sections replace `gpu-workloads=true:NoSchedule` with `nvidia.com/gpu=true:NoSchedule` (with a one-line note: "Amended: gpu-operator daemonsets tolerate only the nvidia.com/gpu key"); add a one-line note under "Phases" that execution order is Phase 0 → Phase 2 (promote while asio is cordoned/empty) → Phase 1 (rebalance) → demote → Phase 3, per the implementation plan.

- [ ] **Step 4: Validate**

```bash
just inventory && just lint && just validate-local
```

Expected: all pass ("Inventory is valid", lint clean, validation green).

- [ ] **Step 5: Commit**

```bash
git add -A infrastructure/ansible docs/plans
git commit -m "feat(inventory): asio becomes control plane, sparky becomes GPU worker"
```

---

### Task 2: Preflight, baselines, backups

**Files:** none (cluster/host operations only).

**Interfaces:**
- Produces: `/root/k3s-migration-backup/` on sparky; baseline memory numbers recorded in the terminal for Task 10's comparison.

- [ ] **Step 1: Reachability and preflight**

```bash
just ansible-ping
just preflight
```

Expected: all four hosts pong; preflight passes. If preflight fails on something unrelated to this migration, stop and report — do not proceed onto k3s surgery over a broken substrate.

- [ ] **Step 2: Record memory baseline on sparky**

```bash
KUBECONFIG=/home/al/.kube/config kubectl top node
ssh 100.71.65.62 "free -h"
```

Save the output in the task notes (it feeds the before/after comparison in Task 10).

- [ ] **Step 3: Check Longhorn headroom for the 20Gi replica eviction**

```bash
ssh 100.76.45.84 "df -h /var/lib/longhorn"
ssh 100.92.107.71 "df -h /var/lib/longhorn"
```

Expected: at least one node with >25Gi free. If neither has headroom, stop — the eviction target must be resolved with the user first.

- [ ] **Step 4: Back up sparky's server state (sparky-local, outside any repo)**

```bash
ssh 100.71.65.62 "sudo mkdir -p /root/k3s-migration-backup && \
  sudo systemctl stop k3s && \
  sudo cp -a /var/lib/rancher/k3s/server/db /root/k3s-migration-backup/db && \
  sudo cp /var/lib/rancher/k3s/server/token /root/k3s-migration-backup/token && \
  sudo cp /etc/rancher/k3s/config.yaml /root/k3s-migration-backup/config.yaml && \
  sudo cp /etc/rancher/k3s/upstream-resolv.conf /root/k3s-migration-backup/upstream-resolv.conf && \
  sudo systemctl start k3s && \
  sudo ls -la /root/k3s-migration-backup/"
cp /home/al/.kube/config /home/al/.kube/config.bak-pre-asio-migration
```

Expected: listing shows `db/`, `token`, `config.yaml`, `upstream-resolv.conf`; k3s comes back (next step confirms). The stop/copy/start makes the sqlite copy consistent; the API is briefly down (~30s) — workload pods keep running.

- [ ] **Step 5: Confirm the API recovered**

```bash
KUBECONFIG=/home/al/.kube/config kubectl get nodes
```

Expected: all 4 nodes listed, sparky Ready.

---

### Task 3: Migrate sparky's datastore sqlite → embedded etcd

**Files:** none (host operation on sparky).

**Interfaces:**
- Consumes: backup from Task 2.
- Produces: sparky running etcd (`/var/lib/rancher/k3s/server/db/etcd/` exists, node shows `etcd` role) so Task 4 can join asio.

- [ ] **Step 1: Enable cluster-init and restart k3s on sparky**

```bash
ssh 100.71.65.62 "echo 'cluster-init: true' | sudo tee -a /etc/rancher/k3s/config.yaml && sudo systemctl restart k3s"
```

(This edits an Ansible-managed file; that is fine — sparky's config.yaml is replaced wholesale by the agent template in Task 8.)

- [ ] **Step 2: Wait for the API and verify the migration**

```bash
until KUBECONFIG=/home/al/.kube/config kubectl get --raw /readyz >/dev/null 2>&1; do sleep 5; done
ssh 100.71.65.62 "sudo journalctl -u k3s --since '-10 min' --no-pager | grep -i -e 'migrat' -e 'etcd' | head -20"
ssh 100.71.65.62 "sudo ls /var/lib/rancher/k3s/server/db/etcd/"
KUBECONFIG=/home/al/.kube/config kubectl get nodes
```

Expected: journal shows the sqlite→etcd migration; the etcd data dir exists; sparky's ROLES column now includes `etcd` alongside `control-plane,master`; all nodes Ready.

**Rollback (if k3s fails to start with etcd):** stop k3s, remove `cluster-init: true` from `/etc/rancher/k3s/config.yaml`, restore `/var/lib/rancher/k3s/server/db` from `/root/k3s-migration-backup/db`, start k3s.

---

### Task 4: Join asio as a second server

**Files:** none (host operation on asio).

**Interfaces:**
- Consumes: etcd-backed sparky (Task 3); join token read live from sparky.
- Produces: asio as a K3s server/etcd member at `https://100.92.107.71:6443`, which Tasks 5–9 depend on.

- [ ] **Step 1: Preserve asio's resolv pin and uninstall the k3s agent**

```bash
ssh 100.92.107.71 "sudo cp /etc/rancher/k3s/upstream-resolv.conf /root/upstream-resolv.conf.bak && sudo /usr/local/bin/k3s-agent-uninstall.sh"
```

Expected: uninstall completes. asio is cordoned and hosts only daemonset pods, so nothing user-facing is disrupted. The node object `asio` remains in the cluster (still cordoned) and will be re-used when asio rejoins under the same name.

- [ ] **Step 2: Stage the join token and write asio's server config**

The token streams from sparky to a root-only file on asio — it never lands on the local machine or in the repo. The config references it via `token-file`, so the config itself contains no secret:

```bash
ssh 100.71.65.62 "sudo cat /var/lib/rancher/k3s/server/node-token" | \
  ssh 100.92.107.71 "sudo mkdir -p /etc/rancher/k3s && sudo tee /etc/rancher/k3s/join-token >/dev/null && sudo chmod 0600 /etc/rancher/k3s/join-token"
ssh 100.92.107.71 "sudo cp /root/upstream-resolv.conf.bak /etc/rancher/k3s/upstream-resolv.conf && sudo tee /etc/rancher/k3s/config.yaml >/dev/null && sudo chmod 0600 /etc/rancher/k3s/config.yaml" <<'EOF'
# K3s server configuration (joined member)
# Converged by Ansible after migration — see k3s-server-config.yaml.j2
server: https://100.71.65.62:6443
token-file: /etc/rancher/k3s/join-token
cluster-cidr: 10.42.0.0/16
service-cidr: 10.43.0.0/16
cluster-dns: 10.43.0.10
cluster-domain: cluster.local
tls-san:
  - 100.92.107.71
node-ip: 100.92.107.71
advertise-address: 100.92.107.71
flannel-iface: tailscale0
write-kubeconfig-mode: "0600"
resolv-conf: /etc/rancher/k3s/upstream-resolv.conf
EOF
```

- [ ] **Step 3: Install k3s as a server on asio**

```bash
ssh 100.92.107.71 "curl -sfL https://get.k3s.io -o /tmp/k3s_install.sh && \
  sudo INSTALL_K3S_VERSION='v1.34.7+k3s1' INSTALL_K3S_EXEC='server' sh /tmp/k3s_install.sh"
```

Expected: install completes and the `k3s` (not `k3s-agent`) service starts.

- [ ] **Step 4: Verify the two-member control plane**

```bash
KUBECONFIG=/home/al/.kube/config kubectl get nodes
ssh 100.92.107.71 "sudo k3s kubectl get --raw /readyz"
```

Expected: asio's ROLES now `control-plane,etcd,master` (still `SchedulingDisabled` — that's correct until Task 6); sparky unchanged; `/readyz` returns `ok` served by asio. If asio fails to join, check `journalctl -u k3s` on asio; rollback is `k3s-uninstall.sh` on asio + reinstall it as an agent (Task 8 Step 4 shows the agent re-add pattern) — sparky is untouched.

---

### Task 5: Re-point kubeconfigs and agents at asio

**Files:**
- Modify: `/home/al/.kube/config` (outside repo)
- Modify (if present): `/home/al/git/kubani/.kube/homelab.yaml` (gitignored)

**Interfaces:**
- Consumes: asio serving the API (Task 4).
- Produces: every kubeconfig and every agent pointing at `https://100.92.107.71:6443`, so sparky's demotion (Task 8) severs nothing.

- [ ] **Step 1: Local kubeconfigs**

```bash
sed -i 's#https://100.71.65.62:6443#https://100.92.107.71:6443#' /home/al/.kube/config
test -f /home/al/git/kubani/.kube/homelab.yaml && \
  sed -i 's#https://100.71.65.62:6443#https://100.92.107.71:6443#' /home/al/git/kubani/.kube/homelab.yaml || true
KUBECONFIG=/home/al/.kube/config kubectl get nodes
```

Expected: node list returned via asio (TLS is valid — asio's cert covers 100.92.107.71 via `tls-san`).

- [ ] **Step 2: Re-point strix's agent**

```bash
ssh 100.76.45.84 "sudo sed -i 's#https://100.71.65.62:6443#https://100.92.107.71:6443#' /etc/rancher/k3s/config.yaml && sudo systemctl restart k3s-agent"
```

- [ ] **Step 3: Re-point rig0's agent (local machine — this is the operator's workstation)**

```bash
sudo sed -i 's#https://100.71.65.62:6443#https://100.92.107.71:6443#' /etc/rancher/k3s/config.yaml
sudo systemctl restart k3s-agent
```

A k3s-agent restart does not restart running containers (containerd is a separate service) — FalkorDB/Qdrant/Redis on rig0 keep serving through it.

- [ ] **Step 4: Verify all agents reconnected**

```bash
KUBECONFIG=/home/al/.kube/config kubectl get nodes
KUBECONFIG=/home/al/.kube/config kubectl get pods -n database -o wide
```

Expected: all 4 nodes Ready; database pods on rig0 Running with no restarts attributable to the agent bounce.

---

### Task 6: Uncordon workers, move Longhorn off sparky

**Files:** none (cluster operations).

**Interfaces:**
- Consumes: healthy 4-node cluster served by asio (Task 5).
- Produces: schedulable asio/strix; zero Longhorn replicas on sparky — the precondition for Task 8's uninstall of sparky.

- [ ] **Step 1: Uncordon asio and strix**

```bash
KUBECONFIG=/home/al/.kube/config kubectl uncordon asio strix
KUBECONFIG=/home/al/.kube/config kubectl get nodes
```

Expected: no node shows `SchedulingDisabled`.

- [ ] **Step 2: Confirm the stuck registry pod schedules**

```bash
KUBECONFIG=/home/al/.kube/config kubectl get pods -n registry -o wide
```

Expected: the registry pod leaves Pending and reaches Running on the node holding its local-path PV. If still Pending after 5 minutes, `kubectl describe` it and report.

- [ ] **Step 3: Disable Longhorn scheduling on sparky and evict its replica**

```bash
KUBECONFIG=/home/al/.kube/config kubectl -n longhorn-system patch nodes.longhorn.io sparky \
  --type=merge -p '{"spec":{"allowScheduling":false,"evictionRequested":true}}'
```

- [ ] **Step 4: Wait for the replica to rebuild elsewhere**

```bash
KUBECONFIG=/home/al/.kube/config kubectl -n longhorn-system get replicas.longhorn.io \
  -o custom-columns='NAME:.metadata.name,NODE:.spec.nodeID,VOL:.spec.volumeName,STATE:.status.currentState'
KUBECONFIG=/home/al/.kube/config kubectl -n longhorn-system get volumes.longhorn.io \
  -o custom-columns='NAME:.metadata.name,NODE:.status.ownerID,ROBUST:.status.robustness,STATE:.status.state'
```

Poll until **no replica has `NODE: sparky`** and no volume is `degraded`/`faulted`. The volume being evicted is detached — Longhorn auto-attaches it for the rebuild; a 20Gi rebuild over the LAN takes minutes, not hours. If eviction stalls >30 minutes, stop and report (do not delete the replica by hand — it is the only copy of that volume's data).

---

### Task 7: Drain sparky's workloads

**Files:** none (cluster operations).

**Interfaces:**
- Consumes: schedulable asio/strix (Task 6).
- Produces: sparky cordoned with only daemonset pods; all platform services Running on asio/strix/rig0.

- [ ] **Step 1: Drain**

```bash
KUBECONFIG=/home/al/.kube/config kubectl drain sparky --ignore-daemonsets --delete-emptydir-data --timeout=15m
```

Expected: completes; sparky becomes `SchedulingDisabled`. If the drain blocks on a Longhorn `instance-manager` PDB: first re-verify Task 6 Step 4 (zero replicas AND zero engines on sparky — `kubectl -n longhorn-system get engines.longhorn.io -o wide | grep sparky` must be empty), then delete that instance-manager pod and re-run the drain.

- [ ] **Step 2: Verify everything landed and is healthy**

```bash
KUBECONFIG=/home/al/.kube/config kubectl get pods -A -o wide --field-selector spec.nodeName=sparky | grep -v -e Completed
KUBECONFIG=/home/al/.kube/config kubectl get pods -A | grep -v -e Running -e Completed
just flux-status
```

Expected: sparky hosts only daemonset pods; nothing new is Pending/CrashLooping beyond the pre-existing set (temporal ×4 — now on another node, still crashlooping until postgres is fixed; sparky's gpu-operator pods); Flux Kustomizations and HelmReleases all Ready. CoreDNS, Flux controllers, cert-manager, Longhorn CSI sidecars, external-dns, metrics-server, local-path-provisioner, reloader must all be Running on asio/strix/rig0.

---

### Task 8: Demote sparky to an agent

**Files:** none (host operations + Ansible run against committed inventory).

**Interfaces:**
- Consumes: drained sparky (Task 7); asio-only client/agent traffic (Task 5); Task 1's inventory.
- Produces: sparky as a tainted worker; asio as the sole control-plane/etcd node.

- [ ] **Step 1: Uninstall the k3s server from sparky**

```bash
ssh 100.71.65.62 "sudo /usr/local/bin/k3s-uninstall.sh"
```

(The resolv pin and server state were already backed up to `/root/k3s-migration-backup/` in Task 2. `/var/lib/longhorn` is untouched by the uninstall, and since Task 6 it holds no replicas.)

- [ ] **Step 2: Delete the node object so k3s removes sparky's etcd member**

```bash
KUBECONFIG=/home/al/.kube/config kubectl delete node sparky
sleep 30
ssh 100.92.107.71 "sudo journalctl -u k3s --since '-5 min' --no-pager | grep -i -e 'removed' -e 'member' | head"
KUBECONFIG=/home/al/.kube/config kubectl get --raw /readyz
```

Expected: journal on asio shows the etcd member removal; `/readyz` returns `ok` (asio now a single-member etcd — quorum of one, fully healthy).

- [ ] **Step 3: Restore sparky's resolv pin (the agent config references it)**

```bash
ssh 100.71.65.62 "sudo mkdir -p /etc/rancher/k3s && sudo cp /root/k3s-migration-backup/upstream-resolv.conf /etc/rancher/k3s/upstream-resolv.conf"
```

- [ ] **Step 4: Re-add sparky as a worker via Ansible**

The limit includes asio because `add_node.yml` fetches the join token from `control_plane[0]`:

```bash
uv run ansible-playbook -i infrastructure/ansible/inventory/hosts.yml \
  infrastructure/ansible/playbooks/add_node.yml --limit 'asio,sparky'
```

Expected: playbook succeeds; sparky installs as `k3s-agent` pointed at asio.

- [ ] **Step 5: Verify sparky's new identity**

```bash
KUBECONFIG=/home/al/.kube/config kubectl get nodes
KUBECONFIG=/home/al/.kube/config kubectl get node sparky -o jsonpath='{.spec.taints}'; echo
KUBECONFIG=/home/al/.kube/config kubectl get node sparky -o jsonpath='{.metadata.labels.node-role}{" "}{.metadata.labels.topology\.kubani\.io/usage-class}'; echo
```

Expected: sparky Ready with ROLES `<none>`; taints contain `nvidia.com/gpu=true:NoSchedule`; labels show `worker inference`. If the taint or labels are missing (add_node may not run node_config), apply them from the inventory definition:

```bash
KUBECONFIG=/home/al/.kube/config kubectl taint node sparky nvidia.com/gpu=true:NoSchedule --overwrite
KUBECONFIG=/home/al/.kube/config kubectl label node sparky node-role=worker --overwrite
```

- [ ] **Step 6: Keep Longhorn off the recreated sparky node**

The Longhorn node CR is recreated when sparky rejoins; re-disable scheduling:

```bash
KUBECONFIG=/home/al/.kube/config kubectl -n longhorn-system patch nodes.longhorn.io sparky \
  --type=merge -p '{"spec":{"allowScheduling":false}}'
KUBECONFIG=/home/al/.kube/config kubectl -n longhorn-system get replicas.longhorn.io -o wide | grep sparky || echo "no replicas on sparky"
```

Expected: `no replicas on sparky`.

- [ ] **Step 7: Verify expected daemonset shape on sparky**

```bash
KUBECONFIG=/home/al/.kube/config kubectl get pods -A -o wide --field-selector spec.nodeName=sparky
```

Expected present: node-exporter, csi-nfs-node, csi-smb-node, gpu-operator daemonsets (dcgm/device-plugin may still crashloop — pre-existing, out of scope). Expected absent: svclb-traefik, all longhorn-system pods, every non-daemonset pod.

---

### Task 9: Converge asio with Ansible

**Files:** none (Ansible run against Task 1's committed state).

**Interfaces:**
- Consumes: asio as sole server with the hand-written join config (Task 4).
- Produces: asio's `/etc/rancher/k3s/config.yaml` matching the repo template (no stale `server:`/`token:` lines), proving `just provision` now converges on the new topology.

- [ ] **Step 1: Run the control-plane provisioning against asio only**

The template render differs from the hand-written join config, so this restarts k3s on asio — a deliberate, gated, brief API outage:

```bash
uv run ansible-playbook -i infrastructure/ansible/inventory/hosts.yml \
  infrastructure/ansible/playbooks/provision_cluster.yml --limit asio \
  -e k3s_allow_control_plane_restart=true
```

Expected: run succeeds; the config-change restart task fires once. (asio boots from its own etcd; the removed `server:`/`token:` lines are only needed for the initial join.)

- [ ] **Step 2: Verify convergence and idempotency**

```bash
ssh 100.92.107.71 "sudo grep -c -e '^server:' -e '^token' /etc/rancher/k3s/config.yaml || true"
KUBECONFIG=/home/al/.kube/config kubectl get --raw /readyz
uv run ansible-playbook -i infrastructure/ansible/inventory/hosts.yml \
  infrastructure/ansible/playbooks/provision_cluster.yml --limit asio | tail -5
```

Expected: grep count `0`; `/readyz` ok; the second run reports `changed=0` for the config tasks (idempotent — no restart loop).

- [ ] **Step 3: Remove the staged join-token file (no longer referenced)**

```bash
ssh 100.92.107.71 "sudo shred -u /etc/rancher/k3s/join-token 2>/dev/null || true; sudo ls /etc/rancher/k3s/"
```

Expected: listing no longer contains `join-token`. (The canonical token lives in `/var/lib/rancher/k3s/server/token`, managed by k3s itself.)

---

### Task 10: Docs, drift, final verification

**Files:**
- Modify: `docs/plans/active/2026-08-16-control-plane-to-asio.md` (status → Completed)
- Modify: any doc that names sparky as the control plane (found by grep below)
- Move: both plan docs `active/` → `archive/` at the very end

**Interfaces:**
- Consumes: completed migration (Tasks 1–9), Task 2's memory baseline.

- [ ] **Step 1: Fix stale control-plane references in docs**

```bash
grep -rn -i -e 'control.plane' /home/al/git/kubani/docs --include='*.md' | grep -i sparky
```

Update each hit (excluding the two plan docs and archived/incident docs, which describe history) to name asio. If a hit is describing the past, leave it.

- [ ] **Step 2: Full validation sweep**

```bash
just validate-cluster
just flux-status
just drift
just pre-push-check
```

Expected: cluster validation green; Flux all Ready; drift reports nothing about topology (fix anything it flags before continuing); pre-push checks pass.

- [ ] **Step 3: Measure the freed memory**

```bash
KUBECONFIG=/home/al/.kube/config kubectl top node
ssh 100.71.65.62 "free -h"
KUBECONFIG=/home/al/.kube/config kubectl get node sparky -o jsonpath='{.status.allocatable.memory}'; echo
```

Compare against Task 2's baseline and record both in the spec's Verification section. Note: allocatable on sparky drops by ~9Gi versus its server days (the agent config applies the inventory's kube/system reservations); that memory is reserved for the host OS/fine-tuning tooling, not lost.

- [ ] **Step 4: Close out the plan documents**

In the spec: status → `Completed YYYY-MM-DD`, paste the before/after memory numbers, and note the two flagged follow-ups (temporal/postgresql scaled to 0; sparky nvidia device-plugin crashloop blocking GPU claims). Then:

```bash
git mv docs/plans/active/2026-08-16-control-plane-to-asio.md docs/plans/archive/
git mv docs/plans/active/2026-08-16-control-plane-to-asio-plan.md docs/plans/archive/
git add -A docs
git commit -m "docs: control plane migration to asio completed"
```

- [ ] **Step 5: Push and reconcile**

```bash
git push
just flux-reconcile
```

Expected: push passes the pre-push hooks; Flux reconciles infra → databases → apps with everything Ready. (No GitOps manifests changed in this plan, so this is a confirmation pass, not a rollout.)
