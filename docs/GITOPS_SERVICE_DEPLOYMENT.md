# GitOps Service Deployment Guide

This guide walks you through deploying a new service to your Kubernetes cluster using GitOps with Flux.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Step 1: Create Service Manifests](#step-1-create-service-manifests)
- [Step 2: Test Manifests Locally](#step-2-test-manifests-locally)
- [Step 3: Deploy via GitOps](#step-3-deploy-via-gitops)
- [Step 4: Verify Deployment](#step-4-verify-deployment)
- [Step 5: Troubleshoot Issues](#step-5-troubleshoot-issues)
- [Examples](#examples)

## Overview

The GitOps workflow automatically deploys services when you commit Kubernetes manifests to the `gitops/apps/base/` directory. Flux monitors the Git repository and applies changes within 1 minute.

**Workflow:**
```
Create Manifests → Test Locally → Commit to Git → Flux Auto-Deploys → Verify
```

## Prerequisites

- Cluster is provisioned and running
- Flux is installed and operational (see [GITOPS_VALIDATION.md](./GITOPS_VALIDATION.md))
- `kubectl` configured with cluster access
- Git repository access

**Set your kubeconfig:**
```bash
export KUBECONFIG=/tmp/homelab-kubeconfig
```

## Step 1: Create Service Manifests

### 1.1 Create Service Directory

```bash
# Create directory for your service
mkdir -p gitops/apps/base/my-service

# Navigate to the directory
cd gitops/apps/base/my-service
```

### 1.2 Create Deployment Manifest

Create `deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-service
  labels:
    app: my-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: my-service
  template:
    metadata:
      labels:
        app: my-service
    spec:
      containers:
      - name: my-service
        image: nginx:1.25-alpine  # Replace with your image
        ports:
        - containerPort: 80
          name: http
        resources:
          requests:
            memory: "64Mi"
            cpu: "100m"
          limits:
            memory: "128Mi"
            cpu: "200m"
        livenessProbe:
          httpGet:
            path: /
            port: http
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /
            port: http
          initialDelaySeconds: 5
          periodSeconds: 5
```

### 1.3 Create Service Manifest

Create `service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-service
  labels:
    app: my-service
spec:
  type: ClusterIP
  ports:
  - port: 80
    targetPort: http
    protocol: TCP
    name: http
  selector:
    app: my-service
```

### 1.4 Create Kustomization File

Create `kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - deployment.yaml
  - service.yaml

labels:
  - pairs:
      app.kubernetes.io/name: my-service
      app.kubernetes.io/managed-by: flux
```

### 1.5 (Optional) Create ConfigMap

Create `configmap.yaml` if you need configuration:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-service-config
data:
  APP_ENV: "production"
  LOG_LEVEL: "info"
```

Add it to `kustomization.yaml`:
```yaml
resources:
  - deployment.yaml
  - service.yaml
  - configmap.yaml
```

### 1.6 (Optional) Create Ingress

Create `ingress.yaml` for external access:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-service
  annotations:
    kubernetes.io/ingress.class: traefik
spec:
  rules:
  - host: my-service.local
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: my-service
            port:
              number: 80
```

## Step 2: Test Manifests Locally

Before committing, validate your manifests work correctly.

### 2.1 Validate YAML Syntax

```bash
# Check YAML syntax
kubectl apply --dry-run=client -f deployment.yaml
kubectl apply --dry-run=client -f service.yaml

# Or validate all at once
kubectl apply --dry-run=client -k .
```

### 2.2 Build with Kustomize

```bash
# Preview what will be deployed
kubectl kustomize gitops/apps/base/my-service

# Check for errors
kustomize build gitops/apps/base/my-service
```

### 2.3 Test Deploy (Optional)

You can test deploy directly before using GitOps:

```bash
# Apply directly to cluster
kubectl apply -k gitops/apps/base/my-service

# Verify it works
kubectl get pods -l app=my-service
kubectl get svc my-service

# Clean up test deployment
kubectl delete -k gitops/apps/base/my-service
```

## Step 3: Deploy via GitOps

### 3.1 Commit and Push

```bash
# From repository root
git add gitops/apps/base/my-service/
git commit -m "Add my-service deployment"
git push origin main
```

### 3.2 Monitor Flux Reconciliation

Flux checks for changes every 1 minute. You can force immediate reconciliation:

```bash
# Force Flux to sync immediately
flux reconcile kustomization flux-system --with-source

# Watch reconciliation status
watch flux get kustomizations
```

Expected output:
```
NAME            REVISION                SUSPENDED       READY   MESSAGE
flux-system     main@sha1:abc1234       False           True    Applied revision: main@sha1:abc1234
```

## Step 4: Verify Deployment

### 4.1 Check Deployment Status

```bash
# Check if deployment was created
kubectl get deployments

# Check pod status
kubectl get pods -l app=my-service

# Check service
kubectl get svc my-service
```

### 4.2 Verify Pods are Running

```bash
# Detailed pod information
kubectl get pods -l app=my-service -o wide

# Check pod events
kubectl describe pod -l app=my-service

# View pod logs
kubectl logs -l app=my-service --tail=50
```

Expected output:
```
NAME                          READY   STATUS    RESTARTS   AGE
my-service-7d8f9c5b6d-abc12   1/1     Running   0          2m
my-service-7d8f9c5b6d-def34   1/1     Running   0          2m
```

### 4.3 Test Service Connectivity

```bash
# Get service details
kubectl get svc my-service

# Test from within cluster (create test pod)
kubectl run test-pod --rm -it --image=curlimages/curl -- sh
# Inside pod:
curl http://my-service

# Or port-forward to test locally
kubectl port-forward svc/my-service 8080:80
# In another terminal:
curl http://localhost:8080
```

### 4.4 Check Resource Usage

```bash
# View resource consumption
kubectl top pods -l app=my-service

# Check if resources are within limits
kubectl describe pod -l app=my-service | grep -A 5 "Limits\|Requests"
```

## Step 5: Troubleshoot Issues

### 5.1 Pod Not Starting

```bash
# Check pod status and events
kubectl describe pod -l app=my-service

# Common issues:
# - ImagePullBackOff: Wrong image name or registry access
# - CrashLoopBackOff: Application error, check logs
# - Pending: Resource constraints or node selector issues
```

### 5.2 Check Logs

```bash
# View current logs
kubectl logs -l app=my-service

# Follow logs in real-time
kubectl logs -l app=my-service -f

# View previous container logs (if crashed)
kubectl logs -l app=my-service --previous

# Logs from all replicas
kubectl logs -l app=my-service --all-containers=true
```

### 5.3 Flux Not Applying Changes

```bash
# Check Flux status
flux get kustomizations

# View Flux logs
kubectl logs -n flux-system deployment/kustomize-controller --tail=100

# Check for reconciliation errors
flux get kustomizations flux-system

# Force reconciliation
flux reconcile kustomization flux-system --with-source
```

### 5.4 Service Not Accessible

```bash
# Verify service endpoints
kubectl get endpoints my-service

# Check if pods are selected
kubectl get pods -l app=my-service

# Test service DNS
kubectl run test-pod --rm -it --image=busybox -- nslookup my-service

# Check network policies
kubectl get networkpolicies
```

### 5.5 Resource Issues

```bash
# Check node resources
kubectl top nodes

# Check if pods are evicted
kubectl get pods -A | grep Evicted

# View resource quotas
kubectl describe resourcequota

# Check pod resource requests vs limits
kubectl describe pod -l app=my-service | grep -A 10 "Containers:"
```

## Examples

### Example 1: Simple Web Service

```bash
# Create directory
mkdir -p gitops/apps/base/web-api

# Create deployment
cat > gitops/apps/base/web-api/deployment.yaml << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: web-api
  template:
    metadata:
      labels:
        app: web-api
    spec:
      containers:
      - name: api
        image: hashicorp/http-echo:latest
        args:
          - "-text=Hello from GitOps!"
        ports:
        - containerPort: 5678
EOF

# Create service
cat > gitops/apps/base/web-api/service.yaml << 'EOF'
apiVersion: v1
kind: Service
metadata:
  name: web-api
spec:
  ports:
  - port: 80
    targetPort: 5678
  selector:
    app: web-api
EOF

# Create kustomization
cat > gitops/apps/base/web-api/kustomization.yaml << 'EOF'
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - service.yaml
EOF

# Deploy
git add gitops/apps/base/web-api/
git commit -m "Add web-api service"
git push

# Wait and verify
sleep 60
kubectl get pods -l app=web-api
```

### Example 2: Service with ConfigMap

```bash
mkdir -p gitops/apps/base/config-app

# ConfigMap
cat > gitops/apps/base/config-app/configmap.yaml << 'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: config-app-config
data:
  database.url: "postgres://db:5432/myapp"
  cache.ttl: "3600"
EOF

# Deployment referencing ConfigMap
cat > gitops/apps/base/config-app/deployment.yaml << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: config-app
spec:
  replicas: 2
  selector:
    matchLabels:
      app: config-app
  template:
    metadata:
      labels:
        app: config-app
    spec:
      containers:
      - name: app
        image: nginx:alpine
        envFrom:
        - configMapRef:
            name: config-app-config
EOF

# Kustomization
cat > gitops/apps/base/config-app/kustomization.yaml << 'EOF'
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - configmap.yaml
  - deployment.yaml
EOF
```

### Example 3: Service with Persistent Storage

```bash
mkdir -p gitops/apps/base/stateful-app

# PVC
cat > gitops/apps/base/stateful-app/pvc.yaml << 'EOF'
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: stateful-app-data
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
  storageClassName: local-path
EOF

# Deployment with volume
cat > gitops/apps/base/stateful-app/deployment.yaml << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: stateful-app
spec:
  replicas: 1
  selector:
    matchLabels:
      app: stateful-app
  template:
    metadata:
      labels:
        app: stateful-app
    spec:
      containers:
      - name: app
        image: nginx:alpine
        volumeMounts:
        - name: data
          mountPath: /data
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: stateful-app-data
EOF

# Kustomization
cat > gitops/apps/base/stateful-app/kustomization.yaml << 'EOF'
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - pvc.yaml
  - deployment.yaml
EOF
```

## Best Practices

1. **Always test locally first** - Use `kubectl apply --dry-run` and `kustomize build`
2. **Set resource limits** - Prevent resource exhaustion
3. **Add health checks** - Use liveness and readiness probes
4. **Use labels consistently** - Makes troubleshooting easier
5. **Version your images** - Avoid `latest` tag in production
6. **Document your service** - Add README.md in service directory
7. **Monitor Flux logs** - Check for reconciliation errors
8. **Use namespaces** - Organize services logically (future enhancement)

## Quick Reference

```bash
# Deploy new service
git add gitops/apps/base/my-service/ && git commit -m "Add service" && git push

# Force Flux sync
flux reconcile kustomization flux-system --with-source

# Check deployment
kubectl get pods -l app=my-service

# View logs
kubectl logs -l app=my-service -f

# Delete service
rm -rf gitops/apps/base/my-service/
git add -A && git commit -m "Remove service" && git push
```

## Related Documentation

- [GitOps Validation Guide](./GITOPS_VALIDATION.md) - Verify Flux is working
- [Troubleshooting Guide](./TROUBLESHOOTING.md) - General cluster issues
- [Architecture Overview](./ARCHITECTURE.md) - System design

## Support

If you encounter issues:
1. Check [GITOPS_VALIDATION.md](./GITOPS_VALIDATION.md) to verify Flux is healthy
2. Review Flux logs: `kubectl logs -n flux-system deployment/kustomize-controller`
3. Check pod events: `kubectl describe pod -l app=your-service`
4. Verify manifests: `kubectl apply --dry-run=client -k gitops/apps/base/your-service`
