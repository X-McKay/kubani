# NAS Storage Integration

This document describes how the Kubani homelab uses the Synology NAS for shared and backup-oriented storage.

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

## Backed Services

- `vllm` model storage
- backup targets for PostgreSQL, Qdrant, and FalkorDB
- shared data for workloads that need RWX storage

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
