# PostgreSQL Deployment

This directory contains the Kubernetes manifests for deploying PostgreSQL database with encrypted credentials and DNS-based access.

## Components

- **namespace.yaml**: Creates the `database` namespace
- **helmrelease.yaml**: Deploys PostgreSQL using the Bitnami Helm chart
- **ingressroutetcp.yaml**: Configures Traefik TCP routing for DNS-based access
- **secret.enc.yaml**: Encrypted PostgreSQL credentials (SOPS encrypted)

## Prerequisites

1. **SOPS and age encryption** must be configured (see task 1)
2. **Traefik** must be configured with PostgreSQL TCP entry point (port 5432)
3. **DNS record** for `postgres.almckay.io` pointing to Traefik LoadBalancer IP

## Creating the Encrypted Secret

The PostgreSQL credentials secret must be created and encrypted using SOPS:

```bash
# Generate encrypted secret using the script
uv run python scripts/create_encrypted_secrets.py \
  --age-public-key <your-age-public-key> \
  --output-dir gitops/apps

# This will create gitops/apps/postgresql/secret.enc.yaml
```

The secret should contain:
- `postgres-password`: Admin password for postgres user
- `username`: Application user name (default: authentik)
- `password`: Application user password
- `database`: Database name (default: authentik)

## Configuration

### Database Settings

The HelmRelease is configured with:
- **Database**: `authentik`
- **Username**: `authentik`
- **Persistence**: 20Gi volume
- **Service Type**: ClusterIP (internal access)
- **Port**: 5432

### DNS-Based Access

PostgreSQL is accessible via DNS name through Traefik TCP routing:

**External Access** (from Tailscale network):
```bash
# Connection string
postgresql://authentik:<password>@postgres.almckay.io:5432/authentik

# Using psql
psql -h postgres.almckay.io -p 5432 -U authentik -d authentik
```

**Internal Access** (from within cluster):
```bash
# Connection string
postgresql://authentik:<password>@postgresql.database.svc.cluster.local:5432/authentik

# Using psql
psql -h postgresql.database.svc.cluster.local -p 5432 -U authentik -d authentik
```

## Traefik Configuration

Traefik must be configured with a PostgreSQL TCP entry point. Add to Traefik configuration:

```yaml
additionalArguments:
  - "--entrypoints.postgresql.address=:5432/tcp"

ports:
  postgresql:
    port: 5432
    expose: true
    exposedPort: 5432
    protocol: TCP
```

## DNS Configuration

After deployment, configure DNS in Cloudflare:

```bash
# Get Traefik LoadBalancer IP
kubectl get svc -n kube-system traefik -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

# Create A record in Cloudflare:
# postgres.almckay.io → <traefik-lb-ip>
```

## Deployment

The manifests are automatically deployed by Flux CD when committed to the Git repository:

```bash
# Commit the manifests
git add gitops/apps/postgresql/
git commit -m "Add PostgreSQL deployment with DNS-based access"
git push

# Check deployment status
kubectl get helmrelease -n database
kubectl get pods -n database
kubectl get ingressroutetcp -n database
```

## Validation

Verify the deployment:

```bash
# Check HelmRelease status
kubectl get helmrelease postgresql -n database

# Check pod status
kubectl get pods -n database

# Check service
kubectl get svc postgresql -n database

# Check IngressRouteTCP
kubectl get ingressroutetcp postgresql-tcp -n database

# Test connectivity from Tailscale network
psql -h postgres.almckay.io -p 5432 -U authentik -d authentik
```

## Troubleshooting

### Pod not starting

```bash
# Check pod logs
kubectl logs -n database -l app.kubernetes.io/name=postgresql

# Check events
kubectl get events -n database --sort-by='.lastTimestamp'
```

### Secret not found

```bash
# Verify secret exists
kubectl get secret postgresql-credentials -n database

# Check Flux Kustomization for decryption errors
kubectl get kustomization -n flux-system
kubectl describe kustomization apps -n flux-system
```

### Cannot connect via DNS

```bash
# Verify DNS resolution
nslookup postgres.almckay.io

# Test TCP connectivity
nc -zv postgres.almckay.io 5432

# Check Traefik logs
kubectl logs -n kube-system -l app.kubernetes.io/name=traefik

# Verify IngressRouteTCP
kubectl describe ingressroutetcp postgresql-tcp -n database
```

## Requirements Validation

This deployment satisfies the following requirements:

- **3.1**: HelmRelease manifest created in GitOps repository
- **3.2**: References encrypted `postgresql-credentials` secret
- **3.3**: Configures 20Gi persistent storage
- **3.5**: Configures database name, username, and connection parameters
- **9.1**: Manifests organized in `gitops/apps/postgresql/`
- **9.2**: Encrypted secret co-located with service manifests
- **11.1**: Exposed at `postgres.almckay.io` on port 5432
