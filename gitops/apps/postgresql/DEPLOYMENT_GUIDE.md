# PostgreSQL Deployment Guide

This guide provides step-by-step instructions for deploying PostgreSQL with encrypted credentials and DNS-based access.

## Overview

The PostgreSQL deployment includes:
- PostgreSQL 15.x using Bitnami Helm chart
- 20Gi persistent storage
- Encrypted credentials using SOPS with age encryption
- DNS-based access via `postgres.almckay.io`
- Traefik TCP routing for external access
- ClusterIP service for internal access

## Prerequisites

Before deploying PostgreSQL, ensure the following are configured:

### 1. SOPS and Age Encryption (Task 1)

```bash
# Verify age key exists
ls -la age.key

# Verify .sops.yaml configuration
cat .sops.yaml

# Verify Flux SOPS integration
kubectl get secret sops-age -n flux-system
```

### 2. Traefik TCP Entry Point

Traefik must be configured with a PostgreSQL TCP entry point on port 5432. This should be added to the Traefik configuration:

```yaml
# gitops/infrastructure/traefik/values.yaml or similar
additionalArguments:
  - "--entrypoints.postgresql.address=:5432/tcp"

ports:
  postgresql:
    port: 5432
    expose: true
    exposedPort: 5432
    protocol: TCP
```

Apply the Traefik configuration update:

```bash
# Commit and push Traefik configuration
git add gitops/infrastructure/traefik/
git commit -m "Add PostgreSQL TCP entry point to Traefik"
git push

# Wait for Flux to reconcile
flux reconcile kustomization infrastructure --with-source

# Verify Traefik is listening on port 5432
kubectl get svc -n kube-system traefik
```

### 3. DNS Configuration

After Traefik is configured, create a DNS A record in Cloudflare:

```bash
# Get Traefik LoadBalancer IP (on Tailscale interface)
TRAEFIK_IP=$(kubectl get svc -n kube-system traefik -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "Traefik IP: $TRAEFIK_IP"

# Create A record in Cloudflare:
# Name: postgres
# Type: A
# Content: <TRAEFIK_IP>
# TTL: Auto
# Proxy: No (DNS only)
```

## Deployment Steps

### Step 1: Create Encrypted Secret

Generate the encrypted PostgreSQL credentials:

```bash
# Generate encrypted secret using the script
uv run python scripts/create_encrypted_secrets.py \
  --age-public-key $(grep 'age:' .sops.yaml | awk '{print $2}') \
  --output-dir gitops/apps

# This creates gitops/apps/postgresql/secret.enc.yaml
```

Alternatively, create the secret manually:

```bash
# Create unencrypted secret first
cat > /tmp/postgresql-secret.yaml <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: postgresql-credentials
  namespace: database
type: Opaque
stringData:
  postgres-password: "$(openssl rand -base64 32)"
  username: "authentik"
  password: "$(openssl rand -base64 32)"
  database: "authentik"
EOF

# Encrypt with SOPS
sops --encrypt \
  --age $(grep 'age:' .sops.yaml | awk '{print $2}') \
  --encrypted-regex '^(data|stringData)$' \
  /tmp/postgresql-secret.yaml > gitops/apps/postgresql/secret.enc.yaml

# Clean up temporary file
rm /tmp/postgresql-secret.yaml
```

### Step 2: Update Kustomization

Uncomment the secret reference in the kustomization file:

```bash
# Edit gitops/apps/postgresql/kustomization.yaml
# Uncomment the line: # - secret.enc.yaml
sed -i '' 's/# - secret.enc.yaml/- secret.enc.yaml/' gitops/apps/postgresql/kustomization.yaml
```

### Step 3: Commit and Deploy

```bash
# Add all PostgreSQL manifests
git add gitops/apps/postgresql/

# Commit
git commit -m "Deploy PostgreSQL with encrypted credentials and DNS-based access"

# Push to trigger Flux reconciliation
git push

# Force Flux to reconcile immediately (optional)
flux reconcile kustomization apps --with-source
```

### Step 4: Monitor Deployment

```bash
# Watch HelmRelease status
kubectl get helmrelease postgresql -n database -w

# Watch pod creation
kubectl get pods -n database -w

# Check logs
kubectl logs -n database -l app.kubernetes.io/name=postgresql -f
```

## Verification

### 1. Verify Kubernetes Resources

```bash
# Check namespace
kubectl get namespace database

# Check HelmRelease
kubectl get helmrelease postgresql -n database
kubectl describe helmrelease postgresql -n database

# Check pods
kubectl get pods -n database
kubectl describe pod -n database -l app.kubernetes.io/name=postgresql

# Check service
kubectl get svc postgresql -n database

# Check PVC
kubectl get pvc -n database

# Check IngressRouteTCP
kubectl get ingressroutetcp postgresql-tcp -n database
kubectl describe ingressroutetcp postgresql-tcp -n database

# Check secret (should be decrypted by Flux)
kubectl get secret postgresql-credentials -n database
```

### 2. Verify Internal Connectivity

Test database connectivity from within the cluster:

```bash
# Create a test pod
kubectl run -it --rm psql-test \
  --image=postgres:15 \
  --restart=Never \
  --namespace=database \
  -- bash

# Inside the pod, connect to PostgreSQL
psql -h postgresql.database.svc.cluster.local -p 5432 -U authentik -d authentik

# Test query
\l
\dt
\q
exit
```

### 3. Verify DNS-Based External Access

Test connectivity from a machine on the Tailscale network:

```bash
# Test DNS resolution
nslookup postgres.almckay.io

# Test TCP connectivity
nc -zv postgres.almckay.io 5432

# Connect with psql (requires PostgreSQL client)
psql -h postgres.almckay.io -p 5432 -U authentik -d authentik

# Test query
\l
\dt
\q
```

### 4. Verify Persistence

```bash
# Check PVC status
kubectl get pvc -n database

# Check PV
kubectl get pv | grep database

# Verify data directory is mounted
kubectl exec -n database -it $(kubectl get pod -n database -l app.kubernetes.io/name=postgresql -o jsonpath='{.items[0].metadata.name}') -- df -h /bitnami/postgresql
```

## Connection Information

### Internal Access (from within cluster)

```bash
# Connection string
postgresql://authentik:<password>@postgresql.database.svc.cluster.local:5432/authentik

# Environment variables
PGHOST=postgresql.database.svc.cluster.local
PGPORT=5432
PGUSER=authentik
PGPASSWORD=<password>
PGDATABASE=authentik
```

### External Access (from Tailscale network)

```bash
# Connection string
postgresql://authentik:<password>@postgres.almckay.io:5432/authentik

# Environment variables
PGHOST=postgres.almckay.io
PGPORT=5432
PGUSER=authentik
PGPASSWORD=<password>
PGDATABASE=authentik
```

### Retrieving Credentials

```bash
# Get username
kubectl get secret postgresql-credentials -n database -o jsonpath='{.data.username}' | base64 -d

# Get password
kubectl get secret postgresql-credentials -n database -o jsonpath='{.data.password}' | base64 -d

# Get database name
kubectl get secret postgresql-credentials -n database -o jsonpath='{.data.database}' | base64 -d
```

## Troubleshooting

### Pod Not Starting

```bash
# Check pod status
kubectl get pods -n database

# Check pod events
kubectl describe pod -n database -l app.kubernetes.io/name=postgresql

# Check pod logs
kubectl logs -n database -l app.kubernetes.io/name=postgresql

# Check HelmRelease status
kubectl describe helmrelease postgresql -n database
```

### Secret Not Found

```bash
# Verify secret exists
kubectl get secret postgresql-credentials -n database

# If missing, check Flux Kustomization
kubectl get kustomization apps -n flux-system
kubectl describe kustomization apps -n flux-system

# Check for SOPS decryption errors
kubectl logs -n flux-system -l app=kustomize-controller
```

### Cannot Connect via DNS

```bash
# Verify DNS resolution
nslookup postgres.almckay.io
dig postgres.almckay.io

# Test TCP connectivity
nc -zv postgres.almckay.io 5432
telnet postgres.almckay.io 5432

# Check Traefik logs
kubectl logs -n kube-system -l app.kubernetes.io/name=traefik | grep postgresql

# Verify IngressRouteTCP
kubectl get ingressroutetcp -n database
kubectl describe ingressroutetcp postgresql-tcp -n database

# Check Traefik configuration
kubectl get svc -n kube-system traefik
kubectl describe svc -n kube-system traefik
```

### Persistence Issues

```bash
# Check PVC status
kubectl get pvc -n database
kubectl describe pvc -n database

# Check PV
kubectl get pv | grep database

# Check storage class
kubectl get storageclass

# Check pod volume mounts
kubectl describe pod -n database -l app.kubernetes.io/name=postgresql | grep -A 10 Mounts
```

### Connection Refused

```bash
# Verify service is running
kubectl get svc postgresql -n database

# Check service endpoints
kubectl get endpoints postgresql -n database

# Test from within cluster
kubectl run -it --rm psql-test \
  --image=postgres:15 \
  --restart=Never \
  --namespace=database \
  -- psql -h postgresql.database.svc.cluster.local -p 5432 -U authentik -d authentik
```

## Maintenance

### Backup Database

```bash
# Create backup
kubectl exec -n database -it $(kubectl get pod -n database -l app.kubernetes.io/name=postgresql -o jsonpath='{.items[0].metadata.name}') -- \
  pg_dump -U authentik authentik > backup-$(date +%Y%m%d-%H%M%S).sql

# Backup to file inside pod
kubectl exec -n database $(kubectl get pod -n database -l app.kubernetes.io/name=postgresql -o jsonpath='{.items[0].metadata.name}') -- \
  pg_dump -U authentik authentik -f /tmp/backup.sql

# Copy backup from pod
kubectl cp database/$(kubectl get pod -n database -l app.kubernetes.io/name=postgresql -o jsonpath='{.items[0].metadata.name}'):/tmp/backup.sql ./backup.sql
```

### Restore Database

```bash
# Copy backup to pod
kubectl cp ./backup.sql database/$(kubectl get pod -n database -l app.kubernetes.io/name=postgresql -o jsonpath='{.items[0].metadata.name}'):/tmp/backup.sql

# Restore from backup
kubectl exec -n database -it $(kubectl get pod -n database -l app.kubernetes.io/name=postgresql -o jsonpath='{.items[0].metadata.name}') -- \
  psql -U authentik authentik -f /tmp/backup.sql
```

### Rotate Credentials

```bash
# 1. Generate new credentials
# 2. Update secret.enc.yaml with new credentials
# 3. Commit and push
# 4. Restart PostgreSQL pod
kubectl rollout restart statefulset -n database postgresql
```

### Upgrade PostgreSQL

```bash
# Update version in helmrelease.yaml
# Commit and push
# Flux will handle the upgrade automatically

# Monitor upgrade
kubectl get helmrelease postgresql -n database -w
kubectl get pods -n database -w
```

## Requirements Validation

This deployment satisfies the following requirements from the specification:

- ✅ **3.1**: HelmRelease manifest created in GitOps repository
- ✅ **3.2**: References encrypted `postgresql-credentials` secret
- ✅ **3.3**: Configures 20Gi persistent storage for database data
- ✅ **3.5**: Configures database name (authentik), username (authentik), and connection parameters
- ✅ **9.1**: Manifests organized in `gitops/apps/postgresql/` directory
- ✅ **9.2**: Encrypted secret co-located with service manifests
- ✅ **11.1**: Exposed at `postgres.almckay.io` on port 5432 via Traefik TCP routing

## Next Steps

After PostgreSQL is deployed and verified:

1. Deploy Redis (Task 5)
2. Deploy Authentik (Task 6) - will use this PostgreSQL instance as its database
3. Configure applications to use PostgreSQL via `postgres.almckay.io`
4. Set up monitoring and alerting for PostgreSQL
5. Configure automated backups
