# PVC Migration to NAS Storage

This document describes the plan for migrating stateful workloads from node-local storage (`local-path`) to NAS storage (`nas-smb`) to enable workload portability across cluster nodes.

## Motivation

Several stateful services are currently bound to `rig0` via `local-path` PersistentVolumes. When rig0 is unavailable (e.g., rebooted into Windows for dual-boot), these services cannot reschedule to other nodes because their data is physically on rig0's local disk.

**Goal**: Enable services to automatically reschedule to any available node when rig0 is offline.

## Current State

### Cluster Nodes

| Node | Role | Arch | CPU | RAM | GPU | Notes |
|------|------|------|-----|-----|-----|-------|
| **rig0** | worker | amd64 | 32 cores | 64GB | RTX 5090 | Primary workstation, dual-boots Windows |
| sparky | control-plane | arm64 | 20 cores | 120GB | GB10 | DGX Spark |
| asio | worker | amd64 | 8 cores | 15GB | None | Limited capacity |
| strix | worker | amd64 | 8 cores | 15GB | AMD | Moderate capacity |

### Storage Classes

| StorageClass | Provisioner | Access | Use Case |
|--------------|-------------|--------|----------|
| `local-path` (default) | rancher.io/local-path | Node-local | Databases, caches (fast, node-bound) |
| `nas-smb` | smb.csi.k8s.io | Any node | Backups, shared data (slower, portable) |

### Services Bound to rig0's Local Storage

| Service | Namespace | Size | Mount Path | Criticality |
|---------|-----------|------|------------|-------------|
| Redis | cache | 8Gi | /data | High (latency-sensitive) |
| Qdrant | database | 10Gi | /qdrant/storage | Medium |
| Neo4j | database | 10Gi | /data | Medium |
| Loki | monitoring | 10Gi | /var/loki | Low (logs regenerate) |
| Prometheus-alertmanager | monitoring | 2Gi | /alertmanager | Low (minimal state) |

## Migration Progress

**Last Updated**: 2026-01-10

| Service | Status | Notes |
|---------|--------|-------|
| **Prometheus-alertmanager** | [OK] Completed | Migrated 2026-01-10, PVC `storage-prometheus-alertmanager-0` now uses `nas-smb` |
| **Loki** | [OK] Completed | Migrated 2026-01-10, PVC `storage-loki-0` now uses `nas-smb` |
| **Qdrant** | [pending] Pending | Requires backup before migration |
| **Neo4j** | [pending] Pending | Requires backup before migration |
| **Redis** | ⛔ Not migrating | Keeping on local-path (latency-sensitive) |

### Completed Steps

1. [OK] NAS directories created at `/volume1/kubani/k8s-volumes/{qdrant,neo4j,loki,alertmanager}`
2. [OK] Prometheus-alertmanager migrated via HelmRelease `storageClass: nas-smb`
3. [OK] Loki migrated via HelmRelease `storageClass: nas-smb`

### Remaining Steps

1. **Qdrant Migration** (see Section 1 below)
   - Create Qdrant snapshot backup
   - Create NAS PV (`gitops/infrastructure/nas-storage/pvs/qdrant-pv.yaml`)
   - Create NAS PVC (`gitops/infrastructure/qdrant/nas-pvc.yaml`)
   - Update deployment to use new PVC
   - Run data migration job
   - Verify data integrity

2. **Neo4j Migration** (see Section 2 below)
   - Create Neo4j database dump
   - Create NAS PV (`gitops/infrastructure/nas-storage/pvs/neo4j-pv.yaml`)
   - Create NAS PVC (`gitops/infrastructure/neo4j/nas-pvc.yaml`)
   - Update deployment to use new PVC
   - Run data migration job
   - Verify data integrity

---

## Migration Candidates

Based on latency sensitivity and data criticality:

| Service | Recommendation | Reason |
|---------|----------------|--------|
| **Qdrant** | Migrate to NAS | Vector DB tolerates network latency |
| **Neo4j** | Migrate to NAS | Graph queries not latency-critical |
| **Loki** | Migrate to NAS | Logs regenerate; write-heavy but tolerant |
| **Prometheus-alertmanager** | Migrate to NAS | Minimal state (silences, notification history) |
| **Redis** | Keep on local-path | In-memory cache requires low latency |

## Prerequisites

### NAS Directory Setup

Create directories on the NAS (100.72.32.10):

```bash
ssh nas "mkdir -p /volume1/kubani/k8s-volumes/{qdrant,neo4j,loki,alertmanager}"
```

### Verify NAS Connectivity

```bash
# Test SMB connectivity from any node
nc -zv 100.72.32.10 445

# Verify share is accessible
smbclient -L //100.72.32.10/kubani -U al
```

## Migration Plan

### Execution Order

1. **Prometheus-alertmanager** - Lowest risk, minimal state
2. **Loki** - Logs regenerate, low risk
3. **Qdrant** - Back up first, then migrate
4. **Neo4j** - Back up first, then migrate

---

## 1. Qdrant Migration

### New Files to Create

**`gitops/infrastructure/nas-storage/pvs/qdrant-pv.yaml`**:

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: nas-qdrant-data
  labels:
    app.kubernetes.io/name: qdrant
spec:
  capacity:
    storage: 10Gi
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ""
  csi:
    driver: smb.csi.k8s.io
    volumeHandle: nas-qdrant-data-unique-id
    volumeAttributes:
      source: "//100.72.32.10/kubani/k8s-volumes/qdrant"
    nodeStageSecretRef:
      name: nas-smb-creds
      namespace: nas-storage
  mountOptions:
    - dir_mode=0777
    - file_mode=0777
    - vers=3.0
    - noperm
```

**`gitops/infrastructure/qdrant/nas-pvc.yaml`**:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: qdrant-data-nas
  namespace: database
  labels:
    app.kubernetes.io/name: qdrant
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: ""
  volumeName: nas-qdrant-data
  resources:
    requests:
      storage: 10Gi
```

### Modify Existing Files

**`gitops/infrastructure/qdrant/deployment.yaml`** - Change PVC reference:

```yaml
# Change from:
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: qdrant-data

# To:
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: qdrant-data-nas
```

**`gitops/infrastructure/qdrant/kustomization.yaml`** - Add new resource:

```yaml
resources:
  - namespace.yaml  # if exists
  - secret.yaml
  - pvc.yaml
  - nas-pvc.yaml    # ADD THIS
  - deployment.yaml
  - service.yaml
  - ingress.yaml
```

**`gitops/infrastructure/nas-storage/kustomization.yaml`** - Add new PV:

```yaml
resources:
  - namespace.yaml
  - secret.enc.yaml
  - storageclass.yaml
  - pvs/backups-pv.yaml
  - pvs/backups-pv.yaml
  - pvs/models-pv.yaml
  - pvs/qdrant-pv.yaml    # ADD THIS
```

### Migration Steps

```bash
# 1. Ensure backup exists
kubectl exec -n database deploy/qdrant -- \
  curl -X POST 'http://localhost:6333/snapshots'

# 2. Scale down qdrant
kubectl scale deployment qdrant -n database --replicas=0

# 3. Copy data using migration job (see Migration Job section below)
# OR manually copy if NAS is mounted

# 4. Apply new manifests via GitOps
git add gitops/infrastructure/nas-storage/pvs/qdrant-pv.yaml
git add gitops/infrastructure/qdrant/nas-pvc.yaml
# Edit deployment.yaml and kustomization.yaml
git commit -m "feat(gitops): migrate qdrant to NAS storage"
git push

# 5. Wait for Flux sync or force reconciliation
flux reconcile kustomization infrastructure --with-source

# 6. Verify pod starts and can run on any node
kubectl get pods -n database -l app.kubernetes.io/name=qdrant -o wide

# 7. Verify data integrity
curl -s http://qdrant.database.svc:6333/collections | jq
```

---

## 2. Neo4j Migration

### New Files to Create

**`gitops/infrastructure/nas-storage/pvs/neo4j-pv.yaml`**:

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: nas-neo4j-data
  labels:
    app.kubernetes.io/name: neo4j
spec:
  capacity:
    storage: 10Gi
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ""
  csi:
    driver: smb.csi.k8s.io
    volumeHandle: nas-neo4j-data-unique-id
    volumeAttributes:
      source: "//100.72.32.10/kubani/k8s-volumes/neo4j"
    nodeStageSecretRef:
      name: nas-smb-creds
      namespace: nas-storage
  mountOptions:
    - dir_mode=0777
    - file_mode=0777
    - vers=3.0
    - noperm
```

**`gitops/infrastructure/neo4j/nas-pvc.yaml`**:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: neo4j-data-nas
  namespace: database
  labels:
    app.kubernetes.io/name: neo4j
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: ""
  volumeName: nas-neo4j-data
  resources:
    requests:
      storage: 10Gi
```

### Modify Existing Files

**`gitops/infrastructure/neo4j/deployment.yaml`** - Change PVC reference:

```yaml
# Change from:
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: neo4j-data

# To:
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: neo4j-data-nas
```

### Migration Steps

```bash
# 1. Create backup
kubectl exec -n database deploy/neo4j -- \
  neo4j-admin database dump --to-path=/data/backup neo4j

# 2. Scale down
kubectl scale deployment neo4j -n database --replicas=0

# 3. Copy data using migration job

# 4. Apply manifests and verify
git add gitops/infrastructure/nas-storage/pvs/neo4j-pv.yaml
git add gitops/infrastructure/neo4j/nas-pvc.yaml
git commit -m "feat(gitops): migrate neo4j to NAS storage"
git push

# 5. Verify
kubectl get pods -n database -l app.kubernetes.io/name=neo4j -o wide
```

---

## 3. Loki Migration (Helm-managed StatefulSet)

Loki is managed by a HelmRelease, which creates a StatefulSet with volumeClaimTemplates. This requires a different approach.

### Modify Existing Files

**`gitops/apps/monitoring/loki-helmrelease.yaml`** - Add storageClass:

```yaml
    singleBinary:
      replicas: 1
      resources:
        requests:
          cpu: 100m
          memory: 256Mi
        limits:
          cpu: 1
          memory: 1Gi
      persistence:
        enabled: true
        size: 10Gi
        storageClass: nas-smb    # ADD THIS LINE
```

### Migration Steps

StatefulSet volumeClaimTemplates are immutable, so we must delete and recreate:

```bash
# 1. Optional: Export existing logs
kubectl exec -n monitoring loki-0 -- \
  tar czf /tmp/loki-backup.tar.gz /var/loki
kubectl cp monitoring/loki-0:/tmp/loki-backup.tar.gz ./loki-backup.tar.gz

# 2. Delete StatefulSet (orphan pods to avoid immediate recreation)
kubectl delete statefulset loki -n monitoring --cascade=orphan

# 3. Delete old PVC
kubectl delete pvc storage-loki-0 -n monitoring

# 4. Update HelmRelease
git add gitops/apps/monitoring/loki-helmrelease.yaml
git commit -m "feat(gitops): migrate loki to NAS storage"
git push

# 5. Force Helm reconciliation
flux reconcile helmrelease loki -n monitoring

# 6. Verify new pod uses NAS storage
kubectl get pvc -n monitoring | grep loki
kubectl get pods -n monitoring -l app.kubernetes.io/name=loki -o wide
```

**Note**: Loki logs will regenerate as promtail continues sending data. Historical logs may be lost unless backed up.

---

## 4. Prometheus-alertmanager Migration (Helm-managed StatefulSet)

Alertmanager stores minimal state (silences, notification history). Safe to recreate without migration.

### Modify Existing Files

**`gitops/apps/monitoring/prometheus-helmrelease.yaml`** - Add storageClass:

```yaml
    alertmanager:
      enabled: true
      persistence:
        enabled: true
        size: 2Gi
        storageClass: nas-smb    # ADD THIS LINE
```

### Migration Steps

```bash
# 1. Delete StatefulSet
kubectl delete statefulset prometheus-alertmanager -n monitoring --cascade=orphan

# 2. Delete old PVC
kubectl delete pvc storage-prometheus-alertmanager-0 -n monitoring

# 3. Update HelmRelease
git add gitops/apps/monitoring/prometheus-helmrelease.yaml
git commit -m "feat(gitops): migrate prometheus-alertmanager to NAS storage"
git push

# 4. Force reconciliation
flux reconcile helmrelease prometheus -n monitoring

# 5. Verify
kubectl get pvc -n monitoring | grep alertmanager
kubectl get pods -n monitoring -l app.kubernetes.io/name=alertmanager -o wide
```

---

## Data Migration Job Template

For services with data that must be preserved, use this job to copy between PVCs:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: migrate-data-to-nas
  namespace: database  # Change as needed
spec:
  ttlSecondsAfterFinished: 3600
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: migrate
          image: alpine:latest
          command:
            - sh
            - -c
            - |
              echo "Installing rsync..."
              apk add --no-cache rsync
              echo "Starting migration..."
              rsync -av --progress /source/ /destination/
              echo "Migration complete!"
              ls -la /destination/
          volumeMounts:
            - name: source
              mountPath: /source
              readOnly: true
            - name: destination
              mountPath: /destination
      volumes:
        - name: source
          persistentVolumeClaim:
            claimName: qdrant-data        # Old local-path PVC
        - name: destination
          persistentVolumeClaim:
            claimName: qdrant-data-nas    # New NAS PVC
```

Run with:
```bash
kubectl apply -f migration-job.yaml
kubectl logs -f job/migrate-data-to-nas -n database
```

---

## Post-Migration Behavior

### What Changes

| Scenario | Before (local-path) | After (nas-smb) |
|----------|---------------------|-----------------|
| rig0 reboots to Windows | Services **Pending** until rig0 returns | Services **reschedule** to other nodes |
| NAS goes offline | No impact | **All migrated services down** |
| Read performance | ~500MB/s+ (local SSD) | ~100-300MB/s (network) |
| Write performance | ~400MB/s+ (local SSD) | ~50-150MB/s (network) |

### Services Remaining on local-path

| Service | Reason |
|---------|--------|
| Redis | In-memory cache requires low latency |
| PostgreSQL | Already on sparky (control-plane), critical DB |
| vLLM model-storage | Local for fast GPU access (NAS backup exists) |
| Container registry | Stays on strix for fast image pulls |

---

## Rollback Procedure

If a migration causes issues:

```bash
# 1. Scale down the deployment
kubectl scale deployment <name> -n <namespace> --replicas=0

# 2. Edit deployment to use original PVC
kubectl edit deployment <name> -n <namespace>
# Change claimName back to original (e.g., qdrant-data)

# 3. Scale back up
kubectl scale deployment <name> -n <namespace> --replicas=1

# 4. Revert GitOps changes
git revert HEAD
git push
```

---

## Cleanup

After successful migration and verification (wait at least 1 week):

```bash
# Delete old local-path PVCs (data will be lost!)
kubectl delete pvc qdrant-data -n database
kubectl delete pvc neo4j-data -n database

# PVs will be automatically deleted by local-path provisioner
```

---

## Summary Checklist

### Files to Create

| File | Purpose |
|------|---------|
| `gitops/infrastructure/nas-storage/pvs/qdrant-pv.yaml` | NAS PV for Qdrant |
| `gitops/infrastructure/nas-storage/pvs/neo4j-pv.yaml` | NAS PV for Neo4j |
| `gitops/infrastructure/qdrant/nas-pvc.yaml` | NAS PVC for Qdrant |
| `gitops/infrastructure/neo4j/nas-pvc.yaml` | NAS PVC for Neo4j |

### Files to Modify

| File | Change |
|------|--------|
| `gitops/infrastructure/qdrant/deployment.yaml` | Change PVC to `qdrant-data-nas` |
| `gitops/infrastructure/qdrant/kustomization.yaml` | Add `nas-pvc.yaml` resource |
| `gitops/infrastructure/neo4j/deployment.yaml` | Change PVC to `neo4j-data-nas` |
| `gitops/infrastructure/neo4j/kustomization.yaml` | Add `nas-pvc.yaml` resource |
| `gitops/infrastructure/nas-storage/kustomization.yaml` | Add new PV resources |
| `gitops/apps/monitoring/loki-helmrelease.yaml` | Add `storageClass: nas-smb` |
| `gitops/apps/monitoring/prometheus-helmrelease.yaml` | Add `storageClass: nas-smb` to alertmanager |

---

## References

- [NAS Storage Integration](NAS_STORAGE.md) - NAS setup and configuration
- [Kubernetes SMB CSI Driver](https://github.com/kubernetes-csi/csi-driver-smb)
- [StatefulSet Storage Migration](https://kubernetes.io/docs/tasks/run-application/migrate-statefulset/)
