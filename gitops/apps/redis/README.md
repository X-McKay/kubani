# Redis Deployment

This directory contains the Kubernetes manifests for deploying Redis cache with encrypted credentials and DNS-based access.

## Components

- **namespace.yaml**: Creates the `cache` namespace
- **helmrelease.yaml**: Deploys Redis using the Bitnami Helm chart
- **ingressroutetcp.yaml**: Configures Traefik TCP routing for DNS-based access
- **secret.enc.yaml**: Encrypted Redis credentials (SOPS encrypted)

## Configuration

### Redis Settings

The HelmRelease is configured with:
- **Authentication**: Enabled with password from encrypted secret
- **Persistence**: 8Gi volume
- **Service Type**: ClusterIP (internal access)
- **Port**: 6379
- **Replication**: Disabled (single master, can be enabled for HA)

### DNS-Based Access

Redis is accessible via DNS name through Traefik TCP routing:

**External Access** (from Tailscale network):
```bash
# Connection string
redis://:<password>@redis.almckay.io:6379

# Using redis-cli
redis-cli -h redis.almckay.io -p 6379 -a <password>
```

**Internal Access** (from within cluster):
```bash
# Connection string
redis://:<password>@redis-master.cache.svc.cluster.local:6379

# Using redis-cli
redis-cli -h redis-master.cache.svc.cluster.local -p 6379 -a <password>
```

## Deployment

The manifests are automatically deployed by Flux CD when committed to the Git repository:

```bash
# Commit the manifests
git add gitops/apps/redis/
git commit -m "Add Redis deployment with DNS-based access"
git push

# Check deployment status
kubectl get helmrelease -n cache
kubectl get pods -n cache
kubectl get ingressroutetcp -n cache
```

## Validation

Verify the deployment:

```bash
# Check HelmRelease status
kubectl get helmrelease redis -n cache

# Check pod status
kubectl get pods -n cache

# Check service
kubectl get svc redis-master -n cache

# Check IngressRouteTCP
kubectl get ingressroutetcp redis-tcp -n cache

# Test connectivity from Tailscale network
redis-cli -h redis.almckay.io -p 6379 -a <password> PING
```

## Retrieving Credentials

```bash
# Get password
kubectl get secret redis-credentials -n cache -o jsonpath='{.data.redis-password}' | base64 -d
```

## Troubleshooting

### Pod not starting

```bash
# Check pod logs
kubectl logs -n cache -l app.kubernetes.io/name=redis

# Check events
kubectl get events -n cache --sort-by='.lastTimestamp'
```

### Secret not found

```bash
# Verify secret exists
kubectl get secret redis-credentials -n cache

# Check Flux Kustomization for decryption errors
kubectl describe kustomization apps -n flux-system
```

### Cannot connect via DNS

```bash
# Verify DNS resolution
nslookup redis.almckay.io

# Test TCP connectivity
nc -zv redis.almckay.io 6379

# Check Traefik logs
kubectl logs -n kube-system -l app.kubernetes.io/name=traefik | grep redis

# Verify IngressRouteTCP
kubectl describe ingressroutetcp redis-tcp -n cache
```

## Requirements Validation

This deployment satisfies the following requirements:

- **4.1**: HelmRelease manifest created in GitOps repository
- **4.2**: References encrypted `redis-credentials` secret
- **4.3**: Configures 8Gi persistent storage
- **4.5**: Enables authentication with password from secret
- **9.1**: Manifests organized in `gitops/apps/redis/`
- **9.2**: Encrypted secret co-located with service manifests
- **11.2**: Exposed at `redis.almckay.io` on port 6379
