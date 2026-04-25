# Cluster Stability Reference

This document captures the current placement and operational assumptions for the Kubani homelab cluster.

## Node Topology

The cluster spans two physical sites connected by Tailscale. Nodes are labeled by Ansible with:

- `topology.kubani.io/site`
- `topology.kubani.io/network-zone`
- `topology.kubani.io/usage-class`

Workloads should target topology labels rather than hard-coded node names whenever possible.

## Service Tiers

| Tier | Services | Default state |
|---|---|---|
| Core | Traefik, cert-manager, PostgreSQL, Redis, Authentik | Always on |
| Platform | Temporal, Prometheus, Grafana, vLLM, Qdrant, Neo4j, registry | Always on |
| Optional | Loki, Promtail | Disabled until explicitly enabled |

## Storage Policy

| Workload | Storage Class | Rationale |
|---|---|---|
| PostgreSQL | `longhorn` | durable relational state |
| Redis | `local-path` | cache, fast restart acceptable |
| Qdrant | `longhorn` | expensive vector data |
| Neo4j | `longhorn` | expensive graph data |
| vLLM model cache | NAS-backed PVC | large model files |
| Alertmanager | `nas-smb` | low-priority shared storage |
| Prometheus | `local-path` or `nas-smb` | rebuildable metrics data |

Longhorn remains restricted to primary-site nodes.

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
