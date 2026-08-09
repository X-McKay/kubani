# Cluster Stability Reference

This document captures the current placement and operational assumptions for the Kubani homelab cluster.

## Node Topology

The cluster runs on a single LAN site with K3s bound to Tailscale. Nodes are labeled by Ansible with:

- `topology.kubani.io/site`
- `topology.kubani.io/network-zone`
- `topology.kubani.io/usage-class`

Workloads should target topology labels rather than hard-coded node names whenever possible. The label schema retains the `site` / `network-zone` axes so adding a future remote node is a relabel rather than a restructure.

## Service Tiers

| Tier | Services | Default state |
|---|---|---|
| Core | Traefik, cert-manager, PostgreSQL, Redis, Authentik | Always on |
| Platform | Temporal, vLLM, Qdrant, FalkorDB, registry | Always on |
| Optional | Prometheus, Grafana, Loki, Promtail | Disabled until explicitly enabled |

The whole monitoring stack sits in the Optional tier. Loki and Promtail are
commented out of `apps/monitoring/kustomization.yaml`; Prometheus and Grafana
are deployed but scaled to zero, pending the observability decision tracked in
[2026-05-09-audit-followup.md](../../plans/ideas/2026-05-09-audit-followup.md).

`validate_cluster.sh` reads these tiers: a `required` service with no pods fails
the run, an `optional` one reports "not deployed" and passes. Move a service
between tiers here and update the matching tier field in that script.

## Storage Policy

| Workload | Storage Class | Rationale |
|---|---|---|
| PostgreSQL | `longhorn` | durable relational state |
| Redis | `local-path` | cache, fast restart acceptable |
| Qdrant | `longhorn` | expensive vector data |
| FalkorDB | `longhorn` | expensive graph data |
| vLLM model cache | NAS-backed PVC | large model files |
| Alertmanager | `nas-smb` | low-priority shared storage |
| Prometheus | `local-path` or `nas-smb` | rebuildable metrics data |

## Network Isolation

The active network-policy layer covers:

- `monitoring`
- `vllm`
- `database`
- `cache`
- `temporal`

Each operational namespace has a default-deny ingress posture plus explicit allow rules for approved traffic paths.

## Tailscale Recovery

K3s is bound to Tailscale via a systemd drop-in installed by Ansible:

- control plane: `/etc/systemd/system/k3s.service.d/tailscale-recovery.conf`
- workers: `/etc/systemd/system/k3s-agent.service.d/tailscale-recovery.conf`

When Tailscale restarts, K3s restarts as well so Flannel routes are recreated automatically.

## Common Commands

```bash
just validate-cluster
just validate-gitops-build
just validate-flux
just provision
just provision-host strix
```
