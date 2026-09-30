# Infrastructure Documentation

Operational documentation for the Kubani homelab cluster.

## Core References

- [Repository Scope](repository-scope.md)
- [Cluster Architecture](architecture.md)
- [Decision Record](decisions.md)
- [Cluster Stability Reference](cluster/cluster-stability.md)
- [Production Checklist](operations/production-checklist.md)
- [Inference Release and Change Process](inference/release-process.md) — benchmark every vLLM image, flag, or model change before and after; baselines and drift checks
- [Scheduled Audit](operations/scheduled-audit.md)
- [Flannel Route Troubleshooting](../troubleshooting/flannel-routes-lost-after-tailscale-upgrade.md)
- [UFW Block Logs for Pod Traffic](../troubleshooting/ufw-block-logs-for-pod-traffic.md) — why these records are benign, and why iptables counters cannot be trusted on these hosts

## Configuration

- [DNS and Traefik](configuration/dns.md)
- [GPU Support](configuration/gpu.md)
- [Secrets Management](configuration/secrets.md)
- [Storage](configuration/storage.md)
- [Registry Access](configuration/registry.md)
- [Authentication](configuration/authentication.md)
- [Authentik App Access Pattern](configuration/authentik-app-access.md)

## GitOps

- [Deploying Services](gitops/guides/deploying-services.md)
- [Service Validation](gitops/guides/service-validation.md)
- [GitOps Validation](gitops/guides/validation.md)

## Operations

### Operations index

Restart procedure per workload:

| Workload | Procedure |
|---|---|
| vLLM (main/fast/embeddings) | `just inference-restart <engine>` — deletes the pod and confirms with a real completion. **Never** `kubectl rollout restart` (Flux reverts the annotation mid-load; see the GB10 runbook below) |
| Flux-managed manifests | `just flux-reconcile` (or `flux reconcile kustomization <infrastructure\|databases\|apps> --with-source` for one) |
| Longhorn volumes | Attach/detach via the Longhorn UI — see [Storage](configuration/storage.md) |
| Authentik | See [Authentik Upgrade And Recovery](operations/authentik-upgrade.md) |

Other standing procedures:

- **Node reboot**: `just node-maintenance <host> pre|post` — see [Node Maintenance](operations/node-maintenance.md)
- **Backup restore drill**: [PostgreSQL Backup and Recovery](operations/postgresql-backup-recovery.md)
- **Host maintenance (driver/OS windows on sparky)**: the `host-maintenance` skill
- **Capacity**: [Capacity Ledger](cluster/capacity.md) — `just capacity` compares it with reality
- **Maintenance cadence**: [Maintenance Calendar](operations/maintenance-calendar.md)
- **Any hot-path or data-bearing change**: [Platform Release Process](operations/release-process.md)
- **New troubleshooting doc**: [`docs/troubleshooting/_template.md`](../troubleshooting/_template.md)

Alert-to-runbook map:

| Alert | Runbook |
|---|---|
| `VllmEngineStall` | [vLLM main engine hang on GB10](../troubleshooting/vllm-main-engine-hang-gb10.md) |
| `PostgresBackupFailed` / `PostgresBackupMissing` | [PostgreSQL Backup and Recovery](operations/postgresql-backup-recovery.md) |
| `NodeNotReady` / `FluxNotReady` | [Cluster Stability Reference](cluster/cluster-stability.md) |
| `PvcAlmostFull` | [Storage](configuration/storage.md) |
| `NodeMemoryAboveCeiling` | [Capacity Ledger](cluster/capacity.md) |

- [Authentik Upgrade And Recovery](operations/authentik-upgrade.md)
- [Production Checklist](operations/production-checklist.md)
- [Inference Release and Change Process](inference/release-process.md) — benchmark every vLLM image, flag, or model change before and after; baselines and drift checks
- [Platform Release Process](operations/release-process.md) — the same discipline for Traefik, Authentik, PostgreSQL, Longhorn, agentgateway, and host driver/OS changes
- [Capacity Ledger](cluster/capacity.md)
- [Maintenance Calendar](operations/maintenance-calendar.md)
- [Node Maintenance](operations/node-maintenance.md)
- [Renovate](operations/renovate.md) — PR-only dependency updates
