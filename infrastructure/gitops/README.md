# GitOps Layout

Flux manages the cluster from this directory.

## Structure

- `flux-system/` bootstraps Flux and defines reconciliation order
- `infrastructure/` contains cluster-wide supporting services such as Traefik, cert-manager, storage, CSI drivers, Longhorn, networking, and the in-cluster container registry
- `apps/databases/` contains the database layer that is applied before the rest of the application tier
- `apps/` contains the remaining cluster applications and platform services

## Reconciliation Order

1. `infrastructure`
2. `databases`
3. `apps`

## Local Validation

```bash
just validate-gitops-build
just validate-flux
```
