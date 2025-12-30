# NAS Storage Integration

This document describes the NAS storage integration for the Kubani Kubernetes cluster.

## Overview

The cluster uses a Synology NAS (nas-east) connected via Tailscale for:
- **Model backup** - LLM models replicated to NAS for disaster recovery
- **Database backups** - Automated backups via the backup-agent
- **Shared storage** - RWX volumes for multi-node workloads

## NAS Configuration

| Property | Value |
|----------|-------|
| Device | Synology DS920+ |
| Hostname | nas-east |
| Tailscale IP | 100.72.32.10 |
| Storage | 3.5TB total, ~3TB available |
| Filesystem | BTRFS |
| Share | `/volume1/kubani` (encrypted) |
| Protocol | SMB/CIFS |
| Replication | Syncs to nas-west |

### Encryption

The kubani share is encrypted at rest. The encryption key is stored in `kubani.key` at the repository root.

**Important**: After a NAS reboot, the encrypted share must be manually unlocked in DSM before Kubernetes can mount volumes.

## Architecture

### Storage Tiers

| Tier | StorageClass | Use Case | Characteristics |
|------|--------------|----------|-----------------|
| Local | `local-path` (default) | Databases, caches, metrics | Fast, node-local |
| NAS | `nas-smb` | Backups, shared data, model backup | Slower, replicated, RWX |

### Directory Structure

```
/volume1/kubani/
├── k8s-volumes/           # Kubernetes PV subdirectories
│   ├── models/            # LLM models backup (206GB)
│   ├── registry/          # Registry backup/mirror
│   └── shared/            # General shared storage
├── backups/               # Automated backup destination
│   ├── databases/         # PostgreSQL, Qdrant, Neo4j dumps
│   ├── configs/           # ConfigMap/Secret exports
│   └── gitops/            # GitOps repo mirror
└── archive/               # Long-term retention
    ├── logs/              # Loki exports
    └── metrics/           # Prometheus snapshots
```

## Components

### SMB CSI Driver

The [Kubernetes SMB CSI Driver](https://github.com/kubernetes-csi/csi-driver-smb) enables mounting SMB shares as Kubernetes volumes.

**Manifests**: `gitops/infrastructure/smb-csi-driver/`

```bash
# Check driver status
kubectl get pods -n smb-csi-driver
```

### NAS Storage Resources

**Manifests**: `gitops/infrastructure/nas-storage/`

| Resource | Purpose |
|----------|---------|
| `secret.enc.yaml` | SOPS-encrypted NAS credentials |
| `storageclass.yaml` | `nas-smb` StorageClass |
| `pvs/models-pv.yaml` | Model storage PV (500Gi RWX) |
| `pvs/backups-pv.yaml` | Backup storage PV (100Gi RWX) |

### Backup Agent

The backup-agent is a Temporal-based agent that automates database backups.

**Code**: `agents/backup-agent/`
**Manifests**: `gitops/apps/ai-agents/backup-agent/`

Features:
- PostgreSQL, Qdrant, Neo4j backup support
- Scheduled daily backups (configurable)
- Discord notifications on success/failure
- Configurable retention policy (default: 7 days)

## Usage

### Creating a PVC with NAS Storage

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-shared-data
  namespace: my-namespace
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: nas-smb
  resources:
    requests:
      storage: 10Gi
```

### Using Existing PVs

Pre-configured PVs are available:

| PV Name | Namespace | Size | Path on NAS |
|---------|-----------|------|-------------|
| `nas-model-storage` | vllm | 500Gi | `/k8s-volumes/models` |
| `nas-backups` | database | 100Gi | `/backups` |
| `nas-backups-ai-agents` | ai-agents | 100Gi | `/backups` |

### Manual NAS Access

For manual file operations:

```bash
# Mount NAS temporarily
sudo mkdir -p /mnt/nas
sudo mount -t cifs //100.72.32.10/kubani /mnt/nas \
  -o username=al,password=<password>,vers=3.0

# Copy files
rsync -av /source/ /mnt/nas/destination/

# Unmount
sudo umount /mnt/nas
```

## Operations

### Checking NAS Connectivity

```bash
# From a cluster node
nc -zv 100.72.32.10 445  # SMB port

# Check if share is accessible
smbclient -L //100.72.32.10 -U al
```

### Verifying PVC Mounts

```bash
# Check PVC status
kubectl get pvc -A | grep nas

# Check if pods can mount
kubectl describe pvc <pvc-name> -n <namespace>
```

### Resuming Model Sync

If you need to re-sync models to NAS:

```bash
# On sparky (or any node with model access)
sudo mount -t cifs //100.72.32.10/kubani/k8s-volumes/models /mnt/nas-models \
  -o username=al,password=<password>,vers=3.0

sudo rsync -av --progress /var/lib/rancher/k3s/storage/<pvc-id>/ /mnt/nas-models/

sudo umount /mnt/nas-models
```

## Considerations

### Performance

- SMB over Tailscale adds ~5-10ms latency
- Not recommended for database primary storage
- Suitable for read-heavy workloads (models, static assets)
- Model loading from NAS is slower but acceptable

### Reliability

- NAS must be online and share unlocked for mounts to work
- Tailscale connectivity required
- Pods will fail to start if NAS is unavailable
- Consider using `local-path` for critical workloads

### Security

- Credentials stored as SOPS-encrypted Kubernetes secret
- NAS share encrypted at rest (BTRFS + ecryptfs)
- Access limited to Tailscale network (100.64.0.0/10)

## Future Enhancements

### Short Term

- [ ] **Start scheduled backup workflow** - Enable automated daily backups
- [ ] **Document recovery procedures** - Step-by-step restore guide
- [ ] **Add health monitoring** - Alert if NAS becomes unreachable

### Medium Term

- [ ] **Registry mirror on NAS** - Store container images for faster pulls and offline access
- [ ] **Prometheus/Loki archival** - Export old metrics and logs to NAS archive
- [ ] **Automatic NAS unlock** - Script to unlock encrypted share on boot

### Long Term

- [ ] **Switch vLLM to NAS storage** - Enable model sharing across multiple GPU nodes
- [ ] **Synology CSI driver** - Migrate to native driver for snapshots and cloning
- [ ] **iSCSI for databases** - Better performance than SMB for block storage
- [ ] **Backup verification** - Automated restore testing

## Troubleshooting

### Mount Failures

```
mount error(13): Permission denied
```
- Check NAS credentials in secret
- Verify NAS firewall allows SMB from Tailscale range
- Ensure share is unlocked (encrypted shares)

```
mount error(115): Operation now in progress
```
- NAS may be unreachable
- Check Tailscale connectivity
- Verify NAS is powered on

### PVC Stuck in Pending

```bash
kubectl describe pvc <name> -n <namespace>
```
- Check CSI driver pods are running
- Verify PV exists and is available
- Check storage class exists

## References

- [Kubernetes SMB CSI Driver](https://github.com/kubernetes-csi/csi-driver-smb)
- [Synology DSM NFS/SMB Setup](https://kb.synology.com/en-us/DSM/help/DSM/AdminCenter/file_share_create)
- [SOPS Encryption](https://github.com/getsops/sops)
