# Flux System Configuration

This directory contains the Flux CD system configuration and Kustomization resources that define the deployment order and dependencies for the cluster.

## Deployment Architecture

The cluster follows a layered deployment approach with explicit dependencies to ensure services are deployed in the correct order:

```
┌─────────────────────────────────────────────────────────┐
│                    Infrastructure                       │
│  - cert-manager (TLS certificate management)            │
│  - Traefik configuration (ingress controller)           │
│  - Storage classes and persistent volumes               │
│  - Network policies                                     │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼ (depends on)
┌─────────────────────────────────────────────────────────┐
│                      Databases                          │
│  - PostgreSQL (relational database)                     │
│  - Redis (cache and message broker)                     │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼ (depends on)
┌─────────────────────────────────────────────────────────┐
│                    Applications                         │
│  - Authentik (identity provider)                        │
│  - Other applications requiring database access         │
└─────────────────────────────────────────────────────────┘
```

## Kustomization Resources

### 1. Infrastructure Kustomization

**File**: `infrastructure-kustomization.yaml`

**Purpose**: Deploys foundational infrastructure components required by all other services.

**Configuration**:
- **Path**: `./gitops/infrastructure`
- **SOPS Decryption**: Enabled (for Cloudflare API tokens, etc.)
- **Dependencies**: None (deployed first)
- **Health Checks**: cert-manager HelmRelease

**Components**:
- cert-manager for automated TLS certificate management
- Traefik ingress controller configuration
- Storage provisioners
- Network policies

### 2. Databases Kustomization

**File**: `databases-kustomization.yaml`

**Purpose**: Deploys stateful data services that applications depend on.

**Configuration**:
- **Path**: `./gitops/apps/databases`
- **SOPS Decryption**: Enabled (for database credentials)
- **Dependencies**: `infrastructure` (waits for infrastructure to be ready)
- **Health Checks**: PostgreSQL and Redis HelmReleases

**Components**:
- PostgreSQL database with persistent storage
- Redis cache with persistent storage
- Encrypted credentials for both services

**Why Separate from Applications?**
- Databases must be fully operational before applications start
- Prevents application startup failures due to missing database connections
- Allows database initialization and migrations to complete first

### 3. Applications Kustomization

**File**: `apps-kustomization.yaml`

**Purpose**: Deploys application services that consume infrastructure and database resources.

**Configuration**:
- **Path**: `./gitops/apps/applications`
- **SOPS Decryption**: Enabled (for application secrets)
- **Dependencies**: `databases` (waits for databases to be ready)
- **Health Checks**: Authentik HelmRelease

**Components**:
- Authentik identity provider (requires PostgreSQL)
- Future applications that depend on databases

## SOPS Decryption

All three Kustomizations have SOPS decryption enabled, allowing encrypted secrets to be stored safely in Git:

```yaml
decryption:
  provider: sops
  secretRef:
    name: sops-age
```

The `sops-age` secret in the `flux-system` namespace contains the age private key used to decrypt secrets during reconciliation.

## Dependency Chain

The dependency chain ensures proper deployment order:

1. **Infrastructure** deploys first (no dependencies)
2. **Databases** waits for infrastructure to be ready (`dependsOn: infrastructure`)
3. **Applications** waits for databases to be ready (`dependsOn: databases`)

This prevents:
- Applications starting before databases are available
- Databases deploying before cert-manager is ready
- Race conditions during cluster initialization

## Health Checks

Each Kustomization includes health checks to verify critical components are ready before proceeding:

**Infrastructure**:
- Waits for cert-manager HelmRelease to be ready
- Ensures TLS certificate issuance is functional

**Databases**:
- Waits for PostgreSQL HelmRelease to be ready
- Waits for Redis HelmRelease to be ready
- Ensures databases are accepting connections

**Applications**:
- Waits for Authentik HelmRelease to be ready
- Ensures application is operational

## Reconciliation

Flux reconciles each Kustomization every 10 minutes (`interval: 10m0s`), automatically applying changes from Git to the cluster.

**Automatic Synchronization**:
- Changes committed to Git are detected within 10 minutes
- Flux applies changes in dependency order
- Failed reconciliations are retried automatically
- Status is reported in Kustomization resource status

## Monitoring Deployment Status

Check the status of each Kustomization:

```bash
# View all Kustomizations
kubectl get kustomizations -n flux-system

# Check infrastructure status
kubectl describe kustomization infrastructure -n flux-system

# Check databases status
kubectl describe kustomization databases -n flux-system

# Check applications status
kubectl describe kustomization apps -n flux-system

# View Flux logs
kubectl logs -n flux-system -l app=kustomize-controller -f
```

## Troubleshooting

### Kustomization Not Progressing

If a Kustomization is stuck waiting for dependencies:

```bash
# Check dependency status
kubectl get kustomization <dependency-name> -n flux-system

# View events
kubectl describe kustomization <name> -n flux-system

# Check health check resources
kubectl get helmrelease -A
```

### SOPS Decryption Failures

If decryption fails:

```bash
# Verify sops-age secret exists
kubectl get secret sops-age -n flux-system

# Check Kustomization status for decryption errors
kubectl describe kustomization <name> -n flux-system

# View kustomize-controller logs
kubectl logs -n flux-system -l app=kustomize-controller --tail=100
```

### Health Check Failures

If health checks prevent progression:

```bash
# Check HelmRelease status
kubectl get helmrelease -A

# Describe specific HelmRelease
kubectl describe helmrelease <name> -n <namespace>

# Check pod status
kubectl get pods -n <namespace>
```

## Adding New Services

When adding new services, consider the appropriate layer:

**Infrastructure Layer** (`gitops/infrastructure/`):
- Cluster-wide components (ingress controllers, storage, networking)
- Components with no dependencies on applications or databases

**Database Layer** (`gitops/apps/databases/`):
- Stateful data services (databases, message queues, caches)
- Services that applications depend on for data storage

**Application Layer** (`gitops/apps/applications/`):
- Business logic applications
- Services that consume infrastructure and database resources

Update the corresponding `kustomization.yaml` file to include the new service.

## Files in This Directory

- `gotk-components.yaml`: Flux CD core components (controllers, CRDs)
- `gotk-sync.yaml`: GitRepository source configuration
- `infrastructure-kustomization.yaml`: Infrastructure layer deployment
- `databases-kustomization.yaml`: Database layer deployment
- `apps-kustomization.yaml`: Application layer deployment
- `kustomization.yaml`: Aggregates all Flux resources
- `README.md`: This documentation file

## References

- [Flux Kustomization API](https://fluxcd.io/flux/components/kustomize/kustomization/)
- [Flux SOPS Integration](https://fluxcd.io/flux/guides/mozilla-sops/)
- [Flux Dependencies](https://fluxcd.io/flux/components/kustomize/kustomization/#dependencies)
- [Health Checks](https://fluxcd.io/flux/components/kustomize/kustomization/#health-assessment)
