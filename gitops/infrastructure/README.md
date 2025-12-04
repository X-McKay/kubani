# Infrastructure

This directory contains infrastructure components and configurations managed by Flux CD.

## Directory Structure

```
infrastructure/
├── sources/              # Helm repositories and Git sources
│   ├── bitnami.yaml
│   ├── jetstack.yaml
│   ├── goauthentik.yaml
│   └── kustomization.yaml
├── storage/              # Storage classes and persistent volumes
│   ├── local-path-storage.yaml
│   └── kustomization.yaml
├── networking/           # Ingress controllers and network policies
│   ├── network-policy.yaml
│   └── kustomization.yaml
└── services/             # Core infrastructure services
    ├── cert-manager.yaml
    ├── postgres.yaml
    ├── redis.yaml
    ├── authentik.yaml
    ├── kustomization.yaml
    └── README.md
```

## Components

### Sources

Helm repositories and Git sources that other components can reference.

**Example: Adding a Helm Repository**

```yaml
apiVersion: source.toolkit.fluxcd.io/v1beta2
kind: HelmRepository
metadata:
  name: prometheus-community
  namespace: flux-system
spec:
  interval: 1h
  url: https://prometheus-community.github.io/helm-charts
```

### Storage

Storage classes, persistent volumes, and storage-related configurations.

**Example: NFS Storage Class**

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: nfs-storage
provisioner: nfs.csi.k8s.io
parameters:
  server: nfs-server.example.com
  share: /exported/path
volumeBindingMode: Immediate
```

### Networking

Network policies, ingress configurations, and networking components.

**Example: Allow Ingress from Specific Namespace**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-from-ingress
  namespace: production
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
```

## Adding Infrastructure Components

### 1. Create Component Manifest

Add your infrastructure component to the appropriate subdirectory:

```bash
# For storage components
vim infrastructure/storage/my-storage-class.yaml

# For networking components
vim infrastructure/networking/my-network-policy.yaml

# For Helm repositories
vim infrastructure/sources/my-helm-repo.yaml
```

### 2. Update Kustomization

Add the new resource to the corresponding `kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - existing-resource.yaml
  - my-new-resource.yaml  # Add this line
```

### 3. Commit and Push

```bash
git add infrastructure/
git commit -m "Add new infrastructure component"
git push
```

## Common Infrastructure Components

### Monitoring Stack

```yaml
# infrastructure/monitoring/prometheus.yaml
apiVersion: source.toolkit.fluxcd.io/v1beta2
kind: HelmRepository
metadata:
  name: prometheus-community
  namespace: flux-system
spec:
  interval: 1h
  url: https://prometheus-community.github.io/helm-charts
---
apiVersion: helm.toolkit.fluxcd.io/v2beta1
kind: HelmRelease
metadata:
  name: kube-prometheus-stack
  namespace: monitoring
spec:
  interval: 5m
  chart:
    spec:
      chart: kube-prometheus-stack
      sourceRef:
        kind: HelmRepository
        name: prometheus-community
        namespace: flux-system
  values:
    prometheus:
      prometheusSpec:
        retention: 30d
```

### Ingress Controller

```yaml
# infrastructure/networking/traefik.yaml
# Note: K3s includes Traefik by default
# This is an example for customizing it
apiVersion: helm.toolkit.fluxcd.io/v2beta1
kind: HelmRelease
metadata:
  name: traefik
  namespace: kube-system
spec:
  interval: 5m
  chart:
    spec:
      chart: traefik
      sourceRef:
        kind: HelmRepository
        name: traefik
        namespace: flux-system
  values:
    service:
      type: LoadBalancer
```

### Certificate Manager

```yaml
# infrastructure/networking/cert-manager.yaml
apiVersion: source.toolkit.fluxcd.io/v1beta2
kind: HelmRepository
metadata:
  name: jetstack
  namespace: flux-system
spec:
  interval: 1h
  url: https://charts.jetstack.io
---
apiVersion: helm.toolkit.fluxcd.io/v2beta1
kind: HelmRelease
metadata:
  name: cert-manager
  namespace: cert-manager
spec:
  interval: 5m
  chart:
    spec:
      chart: cert-manager
      sourceRef:
        kind: HelmRepository
        name: jetstack
        namespace: flux-system
  values:
    installCRDs: true
```

## Best Practices

1. **Namespace Organization**: Keep infrastructure components in appropriate namespaces
2. **Version Pinning**: Pin Helm chart versions for stability
3. **Resource Limits**: Set resource limits for infrastructure components
4. **High Availability**: Configure HA for critical infrastructure
5. **Monitoring**: Monitor infrastructure component health
6. **Backup**: Backup critical infrastructure configurations
7. **Documentation**: Document infrastructure dependencies and configurations

## Troubleshooting

### Check Helm Releases

```bash
flux get helmreleases --all-namespaces
```

### View Helm Release Logs

```bash
flux logs --kind=HelmRelease --name=my-release --namespace=my-namespace
```

### Check Source Status

```bash
flux get sources helm
flux get sources git
```

### Force Reconciliation

```bash
flux reconcile helmrelease my-release --namespace=my-namespace
```

## Dependencies

Infrastructure components may have dependencies on each other. Use Flux's `dependsOn` field to manage deployment order:

```yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: apps
  namespace: flux-system
spec:
  dependsOn:
    - name: infrastructure-storage
    - name: infrastructure-networking
  interval: 10m
  path: ./gitops/apps
  prune: true
  sourceRef:
    kind: GitRepository
    name: flux-system
```
