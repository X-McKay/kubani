# Cluster Stability Reference

This document captures the decisions and operational patterns established during the cluster stability work. It is the primary reference for understanding how the cluster is structured, how workloads are placed, and how to operate it safely.

## Node Topology

The cluster spans two physical sites connected via Tailscale VPN. Every node is labeled with three topology labels applied by Ansible during provisioning.

### Label Schema

| Label | Values | Purpose |
|---|---|---|
| `topology.kubani.io/site` | `primary`, `secondary` | Physical location |
| `topology.kubani.io/network-zone` | `lan`, `remote` | Network proximity to primary site |
| `topology.kubani.io/usage-class` | `general`, `inference`, `constrained` | Workload suitability |

### Node Assignments

| Node | site | network-zone | usage-class | Role |
|---|---|---|---|---|
| sparky | primary | lan | inference | Control plane + GPU (DGX Spark GB10, ARM64) |
| rig0 | primary | lan | general | GPU workstation |
| asio | primary | lan | general | NUC |
| strix | primary | lan | general | General worker |
| osprey | secondary | remote | constrained | Secondary site, constrained resources |

Labels are defined in `infrastructure/ansible/inventory/hosts.yml` under `topology_labels` for each host. Provisioning fails clearly if any required label is missing.

**Use topology labels in manifests, not hostnames.** The only exception is hardware-specific pinning where no topology label captures the distinction.

---

## Service Tiers

Services are classified into three tiers that determine their default-on behavior.

| Tier | Services | Default state |
|---|---|---|
| Core | Traefik, cert-manager, PostgreSQL, Redis, Authentik | Always on |
| Platform | Temporal, Prometheus, Grafana, vLLM (3 models), Qdrant, Neo4j, registry, kubani-ui | Always on |
| Optional | Loki, Promtail, Nexus, AI agents | Off by default (`replicas: 0` or commented out) |

### Enabling Optional Services

**Nexus / AI agents** — set `replicas: 1` (or desired count) in the deployment manifest and commit. Flux will apply it. No manifest restructuring needed.

**Loki / Promtail** — uncomment the entries in `infrastructure/gitops/apps/monitoring/kustomization.yaml`. A comment block explains the procedure inline.

---

## Storage Policy

Each stateful workload has an explicit storage class assignment. Do not change these without understanding the rationale.

| Workload | Storage Class | Rationale |
|---|---|---|
| PostgreSQL | `longhorn` (2 replicas, Primary Site) | Relational DB needs durability + fsync |
| Redis | `local-path` (single node) | Cache; fast restart is acceptable |
| Qdrant | `longhorn` (2 replicas, Primary Site) | Vector data is expensive to rebuild |
| Neo4j | `longhorn` (2 replicas, Primary Site) | Graph data is expensive to rebuild |
| vLLM model cache | NAS-backed PVC (static binding) | Large files; no benefit from block replication |
| Alertmanager | `nas-smb` | Low-priority; NAS is fine |
| Prometheus | `local-path` or `nas-smb` | Metrics; rebuildable |

**Longhorn is restricted to Primary Site nodes only.** The `nodeSelector` in the Longhorn HelmRelease (`infrastructure/gitops/infrastructure/longhorn/helmrelease.yaml`) prevents replicas and instance managers from scheduling on osprey. This avoids cross-site replication traffic over Tailscale.

**Default storage class is `local-path`.** Any PVC without an explicit `storageClassName` lands on local-path, not Longhorn.

---

## Network Isolation

Every operational namespace has a default-deny ingress NetworkPolicy. Explicit allow rules are added for each approved traffic path.

### Operational Namespaces with Policies

`monitoring`, `vllm`, `database`, `cache`, `temporal`, `nexus`, `ai-agents`

### Cross-Namespace Allow Rules

| Source | Destination | Port |
|---|---|---|
| nexus | database (PostgreSQL) | 5432 |
| nexus | cache (Redis) | 6379 |
| temporal | database (PostgreSQL) | 5432 |
| auth | database (PostgreSQL) | 5432 |
| ai-agents | database (Qdrant) | 6333 |
| ai-agents | database (Neo4j) | 7687 |
| ai-agents | cache (Redis) | 6379 |

All namespaces also have a DNS egress allow rule (UDP/TCP 53 to kube-system).

Network policy manifests live in `infrastructure/gitops/infrastructure/networking/`.

---

## Inference Endpoint Stability

Three vLLM deployments run on sparky, all pinned via topology label:

```yaml
nodeSelector:
  topology.kubani.io/usage-class: inference
```

### GPU Memory Budget

| Model | Env var | Allocation |
|---|---|---|
| Main LLM (Qwen3.5-9B-NVFP4) | `LLM_GPU_MEMORY_UTILIZATION` | 50% |
| Fast model (Qwen3-0.6B) | `FAST_GPU_MEMORY_UTILIZATION` | 15% |
| Embeddings (Qwen3-Embed-0.6B) | `EMBEDDINGS_GPU_MEMORY_UTILIZATION` | 10% |
| Reserved (OS, CUDA, headroom) | — | 25% |

Combined utilization must not exceed 85%. This is enforced by a property test (`tests/properties/test_vllm_inference_pinning.py`).

### Restart Order

When restarting inference services manually: embeddings first, fast model second, main LLM last. This avoids GPU memory contention during startup.

---

## Tailscale-to-K3s Route Recovery

K3s is bound to Tailscale via a systemd drop-in installed by Ansible on every node:

```ini
[Unit]
BindsTo=tailscaled.service
After=tailscaled.service
```

- Control plane: `/etc/systemd/system/k3s.service.d/tailscale-recovery.conf`
- Workers: `/etc/systemd/system/k3s-agent.service.d/tailscale-recovery.conf`

When Tailscale restarts, K3s restarts automatically and Flannel re-establishes pod CIDR routes. Re-provisioning a node via `just provision` installs this configuration automatically.

See [Flannel Routes Lost After Tailscale Upgrade](../../troubleshooting/flannel-routes-lost-after-tailscale-upgrade.md) for the full incident writeup and manual recovery steps.

---

## Operational Commands

### Cluster Validation

```bash
# Check Tailscale interface, pod routes, CoreDNS, cross-node connectivity
just validate-cluster

# Validate all GitOps kustomization paths build cleanly
just validate-gitops

# Check all secret references have a corresponding .enc.yaml
just validate-secrets
```

### Deployment Rollback

```bash
# Revert the most recent image tag change for a component
just rollback <component>

# Example
just rollback nexus-orchestrator
```

The rollback command shows the current and previous image tags, prompts for confirmation, commits the revert, and pushes. Flux applies the previous version within its reconciliation interval. Force it immediately with `just flux-reconcile apps`.

### Flux Operations

```bash
# Show status of all Flux resources
just flux-status

# Force reconciliation
just flux-reconcile apps

# Suspend/resume a kustomization
just flux-suspend apps
just flux-resume apps
```

### Enabling a Scaled-Down Service

```bash
# Edit the deployment manifest
# Change: replicas: 0
# To:     replicas: 1  (or desired count)

# Commit and push — Flux applies it
git add infrastructure/gitops/apps/<service>/deployment.yaml
git commit -m "enable: scale up <service>"
git push

# Watch it come up
kubectl get pods -n <namespace> -w
```

---

## Ansible Provisioning

All node configuration is managed through Ansible. Provisioning is idempotent — running it against an already-provisioned node applies only necessary changes without disrupting running workloads.

```bash
# Provision all nodes
just provision

# Provision a specific node
just provision --limit sparky
```

Key things Ansible manages:
- Topology labels applied to Kubernetes node objects
- Tailscale-to-K3s recovery systemd drop-in
- K3s installation and configuration
- Resource reservations (`kube-reserved`, `system-reserved`)

---

## Property Tests

The cluster stability invariants are enforced by property tests in `tests/properties/`. Run them with:

```bash
just test-props
```

| Test file | Property | Validates |
|---|---|---|
| `test_topology_labels.py` | All hosts have complete topology labels | Req 2.1, 10.2 |
| `test_longhorn_site_restriction.py` | Longhorn restricted to Primary Site | Req 2.3, 3.1 |
| `test_storage_class_assignments.py` | Each workload uses correct storage class | Req 3.2–3.5 |
| `test_optional_tier_replicas.py` | Optional-tier deployments at replicas: 0 | Req 4.2, 4.5 |
| `test_namespace_network_policies.py` | Every namespace has default-deny ingress | Req 5.1 |
| `test_vllm_inference_pinning.py` | vLLM pinned to inference node; GPU ≤ 85% | Req 7.1, 7.2 |
| `test_tailscale_recovery.py` | Systemd drop-in installed on all nodes | Req 1.5, 10.1 |
| `test_gitops_validation.py` | kustomize build succeeds; secrets present | Req 8.1, 8.2 |
| `test_rollback_correctness.py` | Rollback produces previous image tag | Req 9.1 |
| `test_ansible_idempotency.py` | Ansible tasks are idempotent | Req 10.5 |

These tests run against the actual GitOps manifests and Ansible inventory files — they catch regressions when manifests are edited.
