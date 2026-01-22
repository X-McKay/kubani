# Web Application Example

This example demonstrates a complete web application deployment with:
- Frontend and backend services
- ConfigMap for configuration
- Service for internal communication
- Ingress for external access (optional)
- Resource limits and health checks

## Overview

A simple web application stack showing best practices for Kubernetes deployments.

## Components

- **Frontend**: Nginx serving static content
- **Backend**: Python Flask API
- **ConfigMap**: Application configuration
- **Service**: Internal service discovery
- **Ingress**: External access (optional)

## Architecture

```
┌─────────────────────────────────────┐
│         Ingress (Optional)          │
│      web-app.example.com            │
└─────────────────────────────────────┘
                  │
┌─────────────────────────────────────┐
│      Service: web-app-frontend      │
│            Port 80                  │
└─────────────────────────────────────┘
                  │
    ┌─────────────┼─────────────┐
    ▼             ▼             ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│Frontend │  │Frontend │  │Frontend │
│  Pod 1  │  │  Pod 2  │  │  Pod 3  │
└─────────┘  └─────────┘  └─────────┘
      │            │            │
      └────────────┼────────────┘
                   ▼
┌─────────────────────────────────────┐
│      Service: web-app-backend       │
│            Port 5000                │
└─────────────────────────────────────┘
                   │
         ┌─────────┼─────────┐
         ▼         ▼         ▼
    ┌────────┐ ┌────────┐ ┌────────┐
    │Backend │ │Backend │ │Backend │
    │ Pod 1  │ │ Pod 2  │ │ Pod 3  │
    └────────┘ └────────┘ └────────┘
```

## Deployment

Automatically deployed via GitOps when committed.

### Manual Deployment

```bash
kubectl apply -k gitops/apps/base/web-app-example/
```

## Accessing the Application

### Port Forward (Development)

```bash
# Forward frontend
kubectl port-forward service/web-app-frontend 8080:80

# Access in browser
open http://localhost:8080
```

### Ingress (Production)

If you have an ingress controller installed:

```bash
# Get ingress address
kubectl get ingress web-app-ingress

# Access via hostname
curl http://web-app.example.com
```

## Configuration

### ConfigMap

Application configuration is stored in `configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: web-app-config
data:
  APP_NAME: "Example Web App"
  BACKEND_URL: "http://web-app-backend:5000"
  LOG_LEVEL: "info"
```

Update configuration:

```bash
kubectl edit configmap web-app-config
kubectl rollout restart deployment web-app-frontend
kubectl rollout restart deployment web-app-backend
```

### Secrets

For sensitive data, use Secrets:

```bash
# Create secret
kubectl create secret generic web-app-secrets \
  --from-literal=api-key=your-secret-key \
  --from-literal=db-password=your-db-password

# Reference in deployment
env:
- name: API_KEY
  valueFrom:
    secretKeyRef:
      name: web-app-secrets
      key: api-key
```

## Scaling

### Manual Scaling

```bash
# Scale frontend
kubectl scale deployment web-app-frontend --replicas=5

# Scale backend
kubectl scale deployment web-app-backend --replicas=3
```

### Auto-Scaling

Add HPA for automatic scaling:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: web-app-frontend-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: web-app-frontend
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

## Monitoring

### Check Status

```bash
# View all resources
kubectl get all -l app.kubernetes.io/name=web-app-example

# Check pod status
kubectl get pods -l app=web-app

# View logs
kubectl logs -l app=web-app-frontend --tail=50
kubectl logs -l app=web-app-backend --tail=50
```

### Health Checks

Both frontend and backend have health endpoints:

```bash
# Frontend health
kubectl port-forward service/web-app-frontend 8080:80
curl http://localhost:8080/health

# Backend health
kubectl port-forward service/web-app-backend 5000:5000
curl http://localhost:5000/health
```

## Customization

### Use Your Own Images

Replace the example images:

```yaml
containers:
- name: frontend
  image: your-registry/your-frontend:v1.0.0
- name: backend
  image: your-registry/your-backend:v1.0.0
```

### Add Database

Add a database deployment:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-app-db
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: postgres
        image: postgres:15
        env:
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: web-app-secrets
              key: db-password
        volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: web-app-db-pvc
```

### Add Persistent Storage

Create PVC for data persistence:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: web-app-data
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: local-path
```

## Troubleshooting

### Pods Not Starting

```bash
# Check pod events
kubectl describe pod -l app=web-app-frontend

# Common issues:
# - Image pull errors
# - Resource constraints
# - ConfigMap not found
```

### Service Not Accessible

```bash
# Check service endpoints
kubectl get endpoints web-app-frontend

# Verify pod labels match service selector
kubectl get pods -l app=web-app-frontend --show-labels
```

### Configuration Not Applied

```bash
# Verify ConfigMap exists
kubectl get configmap web-app-config

# Restart pods to pick up changes
kubectl rollout restart deployment web-app-frontend
```

## Best Practices Demonstrated

1. **Resource Limits**: All containers have CPU and memory limits
2. **Health Checks**: Liveness and readiness probes configured
3. **Labels**: Consistent labeling for organization
4. **ConfigMaps**: Externalized configuration
5. **Multiple Replicas**: High availability with 3 replicas
6. **Service Discovery**: Backend accessed via service name
7. **Rolling Updates**: Zero-downtime deployments

## Related Examples

- `nginx-example/` - Simple nginx deployment
- `hello-world/` - Minimal example
- `gpu-inference/` - GPU-accelerated service

## Next Steps

1. Add persistent storage for data
2. Configure ingress for external access
3. Set up monitoring with Prometheus
4. Add CI/CD pipeline for automated deployments
5. Implement blue-green or canary deployments
