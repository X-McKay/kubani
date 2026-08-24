# Kubani storage integration

This document describes Kubani storage tiers, including how the Synology NAS is
used for shared and backup-oriented storage.

## Overview

The NAS is used for:

- large model storage
- shared RWX volumes
- database and configuration backups

## Storage Tiers

| Tier | StorageClass | Use Case |
|---|---|---|
| Local | `local-path` | fast local storage for caches and rebuildable state |
| Longhorn | `longhorn` | durable replicated block storage for core stateful services |
| NAS | `nas-smb` / `nas-nfs` | shared storage, backups, model data |
| Retained node-local | `local-path-retain` | bounded development recovery copies that must survive accidental PVC deletion |

## Backed Services

- `vllm` model storage
- backup targets for PostgreSQL, Qdrant, and FalkorDB
- shared data for workloads that need RWX storage

The development PostgreSQL recovery copy is intentionally placed on `rig0`,
separate from the PostgreSQL volume on `strix`. It uses `local-path-retain` so
deleting its claim releases rather than erases the underlying volume. This is a
single-node recovery copy, not high availability or a production-grade backup
service. See
[`postgresql-backup-recovery.md`](../operations/postgresql-backup-recovery.md)
for encryption, restore verification, and removal gates.

## Manifests

- `infrastructure/gitops/infrastructure/smb-csi-driver/`
- `infrastructure/gitops/infrastructure/nfs-csi-driver/`
- `infrastructure/gitops/infrastructure/nas-storage/`

## Basic Checks

```bash
kubectl get pvc -A | grep -E 'nas|longhorn'
kubectl get pods -n smb-csi-driver
kubectl get pods -n nfs-csi
```

## Notes

- NAS-backed storage is slower than local block storage and should be reserved for the workloads that actually need shared access or off-node persistence.
- Longhorn remains the preferred default for durable single-writer state in the primary site.
- `local-path-retain` volumes still depend on one node and require an explicit
  recovery or deletion decision after their claim is removed.
