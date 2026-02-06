# MCP Server Deployment Guide

This guide covers deploying MCP servers to the Kubani Kubernetes cluster using GitOps with Flux CD.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Deployment Template](#deployment-template)
- [Environment Variables](#environment-variables)
- [Secrets Management](#secrets-management)
- [Health and Metrics](#health-and-metrics)
- [Service Configuration](#service-configuration)
- [Ingress and External Access](#ingress-and-external-access)
- [Deployment Process](#deployment-process)
- [Monitoring and Troubleshooting](#monitoring-and-troubleshooting)

## Overview

MCP servers in Kubani are deployed as Kubernetes Deployments with:
- Standardized resource limits and security contexts
- Health and readiness probes
- Prometheus metrics endpoints
- Automatic registry registration
- Multi-transport support (SSE for cluster deployments)

All deployments follow a standard template to ensure consistency and maintainability.

## Prerequisites

- Access to the Kubani Kubernetes cluster
- Docker image built and pushed to `registry.almckay.io`
- Secrets encrypted with SOPS (if needed)
- Understanding of Kubernetes basics

## Deployment Template

### Standard Deployment Manifest

Create `infrastructure/gitops/apps/ai-agents/myserver-mcp-server/deployment.yaml`:

```yaml
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myserver-mcp-server
  namespace: ai-agents
  labels:
    app.kubernetes.io/name: myserver-mcp-server
    app.kubernetes.io/component: mcp-server
    app.kubernetes.io/part-of: kubani
    mcp.kubani.io/server: "true"
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: myserver-mcp-server
  template:
    metadata:
      labels:
        app.kubernetes.io/name: myserver-mcp-server
        app.kubernetes.io/component: mcp-server
        mcp.kubani.io/server: "true"
    spec:
      nodeSelector:
        kubernetes.io/arch: amd64
      containers:
        - name: mcp-server
          image: registry.almckay.io/myserver-mcp-server:0.1.0
          imagePullPolicy: Always
          args:
            - --mode
            - sse
            - --port
            - "8080"
          ports:
            - name: http
              containerPort: 8080
              protocol: TCP
            - name: metrics
              containerPort: 9090
              protocol: TCP
          env:
            - name: MCP_SERVER_ID
              value: "myserver-mcp"
            - name: REGISTRY_URL
              value: "http://registry.ai-agents.svc:8000"
            - name: MCP_ALLOWED_HOSTS
              value: "myserver-mcp.almckay.io,myserver-mcp.almckay.io:*,localhost,localhost:*,127.0.0.1,127.0.0.1:*,10.*,10.*:*,100.*,100.*:*,*.almckay.io,*.almckay.io:*,myserver-mcp-server.ai-agents.svc,myserver-mcp-server.ai-agents.svc:*,myserver-mcp-server.ai-agents.svc.cluster.local,myserver-mcp-server.ai-agents.svc.cluster.local:*,*.svc,*.svc:*,*.svc.cluster.local,*.svc.cluster.local:*"
            # Add your backend-specific environment variables here
            - name: BACKEND_URL
              value: "http://backend-service:8080"
          resources:
            requests:
              cpu: 50m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
          securityContext:
            runAsNonRoot: true
            runAsUser: 1000
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: false
            capabilities:
              drop:
                - ALL
          livenessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 30
            periodSeconds: 30
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 10
            periodSeconds: 10
            failureThreshold: 3
      restartPolicy: Always
```

### Key Components Explained

#### Labels

Required labels for all MCP servers:
- `app.kubernetes.io/name`: Unique server name
- `app.kubernetes.io/component`: Always `mcp-server`
- `app.kubernetes.io/part-of`: Always `kubani`
- `mcp.kubani.io/server`: Always `"true"` (enables registry reconciliation)

#### Container Arguments

```yaml
args:
  - --mode
  - sse        # Use SSE transport for cluster deployments
  - --port
  - "8080"     # Standard MCP port
```

#### Ports

Two ports are required:
- `8080`: MCP protocol (SSE/HTTP)
- `9090`: Health and metrics endpoints

#### Resources

Standard resource limits:
```yaml
resources:
  requests:
    cpu: 50m      # Minimum guaranteed CPU
    memory: 128Mi # Minimum guaranteed memory
  limits:
    cpu: 500m     # Maximum CPU (can burst)
    memory: 512Mi # Maximum memory (hard limit)
```

Adjust based on your server's needs, but start with these defaults.

#### Security Context

Required security settings:
```yaml
securityContext:
  runAsNonRoot: true              # Never run as root
  runAsUser: 1000                 # Run as non-privileged user
  allowPrivilegeEscalation: false # Prevent privilege escalation
  readOnlyRootFilesystem: false   # Allow writes to /tmp if needed
  capabilities:
    drop:
      - ALL                       # Drop all Linux capabilities
```

#### Health Probes

Both liveness and readiness probes are required:

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: http
  initialDelaySeconds: 30  # Wait for startup
  periodSeconds: 30        # Check every 30s
  failureThreshold: 3      # Restart after 3 failures

readinessProbe:
  httpGet:
    path: /health
    port: http
  initialDelaySeconds: 10  # Quick initial check
  periodSeconds: 10        # Check frequently
  failureThreshold: 3      # Remove from service after 3 failures
```

## Environment Variables

### Required Variables

All MCP servers must set:

```yaml
env:
  - name: MCP_SERVER_ID
    value: "myserver-mcp"  # Unique identifier for registry
  
  - name: REGISTRY_URL
    value: "http://registry.ai-agents.svc:8000"  # Registry service URL
  
  - name: MCP_ALLOWED_HOSTS
    value: "myserver-mcp.almckay.io,localhost,..."  # DNS rebinding protection
```

### MCP_ALLOWED_HOSTS

This variable configures DNS rebinding protection. Include:
- External domain: `myserver-mcp.almckay.io`
- Localhost: `localhost`, `127.0.0.1`
- Pod network: `10.*` (Kubernetes pod CIDR)
- Tailscale: `100.*` (Tailscale network)
- Service DNS: `*.svc`, `*.svc.cluster.local`
- Specific service: `myserver-mcp-server.ai-agents.svc`

Template:
```
myserver-mcp.almckay.io,myserver-mcp.almckay.io:*,localhost,localhost:*,127.0.0.1,127.0.0.1:*,10.*,10.*:*,100.*,100.*:*,*.almckay.io,*.almckay.io:*,myserver-mcp-server.ai-agents.svc,myserver-mcp-server.ai-agents.svc:*,myserver-mcp-server.ai-agents.svc.cluster.local,myserver-mcp-server.ai-agents.svc.cluster.local:*,*.svc,*.svc:*,*.svc.cluster.local,*.svc.cluster.local:*
```

### Backend-Specific Variables

Add environment variables for your backend services:

```yaml
env:
  # Database connection
  - name: DATABASE_URL
    value: "postgresql://postgres:5432/mydb"
  
  # Redis cache
  - name: REDIS_URL
    value: "redis://redis.database.svc:6379"
  
  # API endpoints
  - name: BACKEND_API_URL
    value: "http://backend-api.default.svc:8080"
```

## Secrets Management

**CRITICAL**: Never commit unencrypted secrets to Git!

### Using Kubernetes Secrets

1. **Create Secret Manifest**

Create `infrastructure/gitops/apps/ai-agents/myserver-mcp-server/secret.yaml`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: myserver-mcp-server-secrets
  namespace: ai-agents
type: Opaque
stringData:
  API_KEY: "your-api-key-here"
  API_SECRET: "your-api-secret-here"
  DATABASE_PASSWORD: "your-db-password"
```

2. **Encrypt with SOPS**

```bash
# Encrypt the secret
sops --encrypt secret.yaml > secret.enc.yaml

# Delete the plain file
rm secret.yaml

# Commit only the encrypted version
git add secret.enc.yaml
git commit -m "Add encrypted secrets for myserver-mcp"
```

3. **Reference in Deployment**

```yaml
env:
  - name: API_KEY
    valueFrom:
      secretKeyRef:
        name: myserver-mcp-server-secrets
        key: API_KEY
  
  - name: API_SECRET
    valueFrom:
      secretKeyRef:
        name: myserver-mcp-server-secrets
        key: API_SECRET
```

### SOPS Setup

If SOPS is not yet configured, see [SOPS Setup Guide](../../infrastructure/gitops/SOPS_SETUP.md).

Quick setup:
```bash
# Generate age key
age-keygen -o age.key

# Create .sops.yaml
cat > .sops.yaml <<EOF
creation_rules:
  - path_regex: \.enc\.yaml$
    encrypted_regex: ^(data|stringData)$
    age: $(grep public age.key | cut -d: -f2 | tr -d ' ')
EOF

# Create Kubernetes secret with private key
kubectl create secret generic sops-age \
  --namespace=flux-system \
  --from-file=age.agekey=age.key
```

### Secret Best Practices

1. **Always use SOPS** - Never commit plain secrets
2. **Use Kubernetes secrets** - Don't hardcode in deployment
3. **Rotate regularly** - Update secrets every 6-12 months
4. **Minimal access** - Only grant access to necessary services
5. **Audit access** - Monitor who accesses secrets
6. **Backup age.key** - Store securely, you can't decrypt without it

### Pre-Commit Hooks

The repository has pre-commit hooks to prevent committing secrets:

```bash
# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## Health and Metrics

### Health Endpoint

All MCP servers expose `/health` on port 9090:

```bash
# Check health
curl http://myserver-mcp-server.ai-agents.svc:9090/health
```

Response format:
```json
{
  "status": "healthy",
  "backends": {
    "database": {
      "status": "healthy",
      "latency_ms": 5.2
    },
    "cache": {
      "status": "healthy",
      "latency_ms": 1.8
    }
  },
  "uptime_seconds": 3600.5,
  "version": "0.1.0"
}
```

### Metrics Endpoint

Prometheus metrics are exposed at `/metrics` on port 9090:

```bash
# View metrics
curl http://myserver-mcp-server.ai-agents.svc:9090/metrics
```

Standard metrics:
- `mcp_requests_total` - Total requests by tool and status
- `mcp_request_duration_seconds` - Request latency histogram
- `mcp_active_connections` - Current active connections
- `mcp_backend_requests_total` - Backend requests by service
- `mcp_backend_latency_seconds` - Backend latency histogram

### Prometheus ServiceMonitor

Create `infrastructure/gitops/apps/ai-agents/myserver-mcp-server/servicemonitor.yaml`:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: myserver-mcp-server
  namespace: ai-agents
  labels:
    app.kubernetes.io/name: myserver-mcp-server
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: myserver-mcp-server
  endpoints:
    - port: metrics
      interval: 30s
      path: /metrics
```

## Service Configuration

Create `infrastructure/gitops/apps/ai-agents/myserver-mcp-server/service.yaml`:

```yaml
---
apiVersion: v1
kind: Service
metadata:
  name: myserver-mcp-server
  namespace: ai-agents
  labels:
    app.kubernetes.io/name: myserver-mcp-server
    app.kubernetes.io/component: mcp-server
spec:
  type: ClusterIP
  ports:
    - name: http
      port: 8080
      targetPort: http
      protocol: TCP
    - name: metrics
      port: 9090
      targetPort: metrics
      protocol: TCP
  selector:
    app.kubernetes.io/name: myserver-mcp-server
```

## Ingress and External Access

### Tailscale Ingress

For external access via Tailscale, create an ingress:

Create `infrastructure/gitops/apps/ai-agents/myserver-mcp-server/ingress.yaml`:

```yaml
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myserver-mcp-server
  namespace: ai-agents
  annotations:
    tailscale.com/funnel: "true"
    tailscale.com/hostname: "myserver-mcp"
spec:
  ingressClassName: tailscale
  rules:
    - host: myserver-mcp.almckay.io
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: myserver-mcp-server
                port:
                  number: 8080
```

This creates a Tailscale egress URL: `https://myserver-mcp.almckay.io`

### Internal-Only Services

If your MCP server should only be accessible within the cluster, omit the Ingress and use the service DNS:
- Internal URL: `http://myserver-mcp-server.ai-agents.svc:8080`

## Deployment Process

### 1. Create Directory Structure

```bash
mkdir -p infrastructure/gitops/apps/ai-agents/myserver-mcp-server
cd infrastructure/gitops/apps/ai-agents/myserver-mcp-server
```

### 2. Create Manifests

Create the following files:
- `deployment.yaml` - Main deployment
- `service.yaml` - Service definition
- `secret.enc.yaml` - Encrypted secrets (if needed)
- `ingress.yaml` - External access (if needed)
- `servicemonitor.yaml` - Prometheus monitoring (optional)
- `kustomization.yaml` - Kustomize configuration

### 3. Create Kustomization

Create `kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: ai-agents
resources:
  - deployment.yaml
  - service.yaml
  - secret.enc.yaml
  - ingress.yaml
```

### 4. Add to Parent Kustomization

Edit `infrastructure/gitops/apps/ai-agents/kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  # ... existing servers ...
  - myserver-mcp-server
```

### 5. Build and Push Docker Image

```bash
# Build image
docker build -t registry.almckay.io/myserver-mcp-server:0.1.0 \
  -f kubani/mcp/servers/myserver/Dockerfile .

# Push to registry
docker push registry.almckay.io/myserver-mcp-server:0.1.0
```

### 6. Commit and Push

```bash
# Add files
git add infrastructure/gitops/apps/ai-agents/myserver-mcp-server/

# Commit
git commit -m "Add myserver-mcp-server deployment"

# Push
git push origin main
```

### 7. Verify Deployment

Flux will automatically deploy within 1-5 minutes:

```bash
# Watch Flux reconciliation
flux get kustomizations --watch

# Check deployment status
kubectl get deployment myserver-mcp-server -n ai-agents

# Check pod status
kubectl get pods -n ai-agents -l app.kubernetes.io/name=myserver-mcp-server

# View logs
kubectl logs -n ai-agents -l app.kubernetes.io/name=myserver-mcp-server -f

# Check health
kubectl exec -n ai-agents deployment/myserver-mcp-server -- \
  curl -s http://localhost:9090/health | jq
```

### 8. Verify Registry Registration

```bash
# Query registry
curl http://registry.ai-agents.svc:8000/api/v1/mcp/servers | jq

# Check for your server
curl http://registry.ai-agents.svc:8000/api/v1/mcp/servers/myserver-mcp | jq
```

## Monitoring and Troubleshooting

### Check Pod Status

```bash
# Get pod status
kubectl get pods -n ai-agents -l app.kubernetes.io/name=myserver-mcp-server

# Describe pod
kubectl describe pod -n ai-agents -l app.kubernetes.io/name=myserver-mcp-server

# View events
kubectl get events -n ai-agents --sort-by='.lastTimestamp'
```

### View Logs

```bash
# Follow logs
kubectl logs -n ai-agents -l app.kubernetes.io/name=myserver-mcp-server -f

# View previous logs (if crashed)
kubectl logs -n ai-agents -l app.kubernetes.io/name=myserver-mcp-server --previous

# View logs from specific container
kubectl logs -n ai-agents deployment/myserver-mcp-server -c mcp-server
```

### Check Health

```bash
# Port-forward to access health endpoint
kubectl port-forward -n ai-agents deployment/myserver-mcp-server 9090:9090

# In another terminal
curl http://localhost:9090/health | jq
curl http://localhost:9090/metrics
```

### Common Issues

#### Pod Not Starting

Check:
1. Image exists and is accessible
2. Secrets are properly encrypted and referenced
3. Resource limits are sufficient
4. Node has capacity

```bash
kubectl describe pod -n ai-agents -l app.kubernetes.io/name=myserver-mcp-server
```

#### Health Check Failing

Check:
1. Server is listening on correct port (8080)
2. Health endpoint is implemented
3. Backend services are accessible
4. Sufficient startup time (initialDelaySeconds)

```bash
kubectl logs -n ai-agents -l app.kubernetes.io/name=myserver-mcp-server
```

#### Not Registered in Registry

Check:
1. REGISTRY_URL is correct
2. Registry service is running
3. Network policies allow communication
4. Server logs for registration errors

```bash
kubectl logs -n ai-agents -l app.kubernetes.io/name=myserver-mcp-server | grep -i registry
```

#### SOPS Decryption Failing

Check:
1. `sops-age` secret exists in `flux-system` namespace
2. Flux Kustomization has `decryption.provider: sops`
3. Secret is properly encrypted with correct age key

```bash
kubectl get secret sops-age -n flux-system
flux get kustomizations
```

### Debugging Tips

1. **Use kubectl exec** to run commands in the pod:
   ```bash
   kubectl exec -it -n ai-agents deployment/myserver-mcp-server -- /bin/sh
   ```

2. **Check environment variables**:
   ```bash
   kubectl exec -n ai-agents deployment/myserver-mcp-server -- env | sort
   ```

3. **Test backend connectivity**:
   ```bash
   kubectl exec -n ai-agents deployment/myserver-mcp-server -- \
     curl -v http://backend-service:8080/health
   ```

4. **View resource usage**:
   ```bash
   kubectl top pod -n ai-agents -l app.kubernetes.io/name=myserver-mcp-server
   ```

## Next Steps

1. Deploy your MCP server following this guide
2. Verify health and metrics endpoints
3. Check registry registration
4. Run post-deployment tests (see [Testing Guide](testing-guide.md))
5. Monitor metrics in Grafana

## Additional Resources

- [Development Guide](development-guide.md)
- [Testing Guide](testing-guide.md)
- [Registry Integration Guide](registry-integration.md)
- [SOPS Setup Guide](../../infrastructure/gitops/SOPS_SETUP.md)
- [Flux CD Documentation](https://fluxcd.io/docs/)
