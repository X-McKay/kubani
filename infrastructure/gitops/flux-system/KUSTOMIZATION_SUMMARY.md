# Flux Kustomization Summary

## Overview

This document provides a quick reference for the Flux Kustomization resources that control deployment order and dependencies in the cluster.

## Kustomization Resources

| Name | Path | Dependencies | SOPS | Health Checks |
|------|------|--------------|------|---------------|
| `infrastructure` | `./infrastructure/gitops/infrastructure` | None | OK | cert-manager |
| `databases` | `./infrastructure/gitops/apps/databases` | infrastructure | OK | postgresql, redis |
| `apps` | `./infrastructure/gitops/apps` | databases | OK | authentik |

## Deployment Order

```
infrastructure → databases → apps
```

## Quick Commands

### View Status

```bash
# All Kustomizations
kubectl get kustomizations -n flux-system

# Specific Kustomization
kubectl describe kustomization <name> -n flux-system
```

### Force Reconciliation

```bash
# Infrastructure
flux reconcile kustomization infrastructure --with-source

# Databases
flux reconcile kustomization databases --with-source

# Applications
flux reconcile kustomization apps --with-source
```

### Check Dependencies

```bash
# Infrastructure (no dependencies)
kubectl get kustomization infrastructure -n flux-system -o jsonpath='{.spec.dependsOn}'

# Databases (depends on infrastructure)
kubectl get kustomization databases -n flux-system -o jsonpath='{.spec.dependsOn}'
# Output: [{"name":"infrastructure"}]

# Applications (depends on databases)
kubectl get kustomization apps -n flux-system -o jsonpath='{.spec.dependsOn}'
# Output: [{"name":"databases"}]
```

### Verify SOPS Decryption

```bash
# Check sops-age secret exists
kubectl get secret sops-age -n flux-system

# View Kustomization decryption config
kubectl get kustomization infrastructure -n flux-system -o jsonpath='{.spec.decryption}'
```

## File Locations

- **Infrastructure Kustomization**: `infrastructure/gitops/flux-system/infrastructure-kustomization.yaml`
- **Databases Kustomization**: `infrastructure/gitops/flux-system/databases-kustomization.yaml`
- **Applications Kustomization**: `infrastructure/gitops/flux-system/apps-kustomization.yaml`
- **Flux System Kustomization**: `infrastructure/gitops/flux-system/kustomization.yaml`

## Component Locations

- **Infrastructure Components**: `infrastructure/gitops/infrastructure/`
  - cert-manager
  - Traefik configuration
  - Storage classes
  - Network policies

- **Database Components**: `infrastructure/gitops/apps/databases/` -> references:
  - `infrastructure/gitops/apps/postgresql/`
  - `infrastructure/gitops/apps/redis/`

- **Application Components**: `infrastructure/gitops/apps/` -> references:
  - `infrastructure/gitops/apps/authentik/`

## Validation

All Kustomizations have been validated:

```bash
# Validate infrastructure
kubectl apply --dry-run=client -f infrastructure/gitops/flux-system/infrastructure-kustomization.yaml

# Validate databases
kubectl apply --dry-run=client -f infrastructure/gitops/flux-system/databases-kustomization.yaml

# Validate applications
kubectl apply --dry-run=client -f infrastructure/gitops/flux-system/apps-kustomization.yaml
```

## Requirements Satisfied

This implementation satisfies the following requirements:

- **Requirement 7.2**: Flux Kustomizations configured with SOPS decryption enabled
- **Requirement 9.5**: Flux automatically synchronizes cluster state with Git (10-minute interval)

## Documentation

For detailed information, see:
- [README.md](./README.md) - Comprehensive Flux system documentation
- [DEPLOYMENT_ORDER.md](./DEPLOYMENT_ORDER.md) - Detailed deployment flow and troubleshooting
