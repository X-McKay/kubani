# Kubani UI Deployment Guide

This guide covers deploying the improved Kubani UI with the new Rust backend.

---

## 📋 Prerequisites

- Kubernetes cluster with kubectl access
- Docker for building images
- Access to the kubani namespace
- MCP servers and registry deployed

---

## 🏗️ Building

### Backend (Rust)

```bash
cd backend

# Local build
cargo build --release

# Docker build
docker build -t kubani-ui-backend:latest .

# Tag for your registry
docker tag kubani-ui-backend:latest your-registry/kubani-ui-backend:v2.0.0
docker push your-registry/kubani-ui-backend:v2.0.0
```

### Frontend (React)

```bash
cd client

# Install dependencies
pnpm install

# Build for production
pnpm build

# The build output will be in client/dist/
```

---

## 🚀 Deployment Options

### Option 1: Kubernetes Deployment (Recommended)

Create a deployment manifest for the Rust backend:

```yaml
# backend-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kubani-ui-backend
  namespace: ai-agents
spec:
  replicas: 2
  selector:
    matchLabels:
      app: kubani-ui-backend
  template:
    metadata:
      labels:
        app: kubani-ui-backend
    spec:
      containers:
      - name: backend
        image: your-registry/kubani-ui-backend:v2.0.0
        ports:
        - containerPort: 3001
        env:
        - name: K8S_MCP_URL
          value: "http://kubernetes-mcp-server.ai-agents.svc.cluster.local:8080"
        - name: REGISTRY_URL
          value: "http://metadata-registry.ai-agents.svc.cluster.local:8000"
        - name: VLLM_URL
          value: "http://llm-api.vllm.svc.cluster.local:8000/v1"
        - name: MODEL_NAME
          value: "Qwen3.5-9B-NVFP4"
        - name: RUST_LOG
          value: "info"
        resources:
          requests:
            memory: "64Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 3001
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 3001
          initialDelaySeconds: 5
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: kubani-ui-backend
  namespace: ai-agents
spec:
  selector:
    app: kubani-ui-backend
  ports:
  - port: 3001
    targetPort: 3001
  type: ClusterIP
```

Deploy:

```bash
kubectl apply -f backend-deployment.yaml
```

For the frontend, you can either:

**A. Serve from the existing UI pod** (update the existing deployment)

**B. Use a separate static file server** (nginx, etc.)

### Option 2: Docker Compose (Development)

```yaml
# docker-compose.yml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "3001:3001"
    environment:
      - K8S_MCP_URL=http://kubernetes-mcp-server:8080
      - REGISTRY_URL=http://metadata-registry:8000
      - VLLM_URL=http://llm-api:8000/v1
      - MODEL_NAME=Qwen3.5-9B-NVFP4
      - RUST_LOG=info
    restart: unless-stopped

  frontend:
    build:
      context: ./client
      dockerfile: Dockerfile
    ports:
      - "3000:80"
    depends_on:
      - backend
    restart: unless-stopped
```

Run:

```bash
docker-compose up -d
```

---

## 🔧 Configuration

### Backend Configuration

The Rust backend is configured via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `K8S_MCP_URL` | Kubernetes MCP server URL | `http://kubernetes-mcp-server.ai-agents.svc.cluster.local:8080` |
| `REGISTRY_URL` | Agent registry URL | `http://metadata-registry.ai-agents.svc.cluster.local:8000` |
| `VLLM_URL` | vLLM API URL | `http://llm-api.vllm.svc.cluster.local:8000/v1` |
| `MODEL_NAME` | Default LLM model | `Qwen3.5-9B-NVFP4` |
| `RUST_LOG` | Log level (trace, debug, info, warn, error) | `info` |

### Frontend Configuration

Update the API base URL in `/client/src/lib/api.ts` if needed:

```typescript
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:3001';
```

Set via environment variable:

```bash
VITE_API_URL=http://your-backend-url:3001 pnpm build
```

---

## 🔍 Verification

### Health Checks

```bash
# Backend health
curl http://localhost:3001/health
# Expected: OK

# Test monitoring endpoint
curl http://localhost:3001/api/monitoring/nodes
# Expected: JSON array of nodes
```

### Logs

```bash
# Kubernetes
kubectl logs -f deployment/kubani-ui-backend -n ai-agents

# Docker
docker logs -f kubani-ui-backend
```

### Metrics

The Rust backend logs include:
- Request duration
- MCP call timing
- Cache hit/miss rates
- Error rates

---

## 🐛 Troubleshooting

### Backend won't start

**Issue**: Backend fails to start or crashes immediately

**Solutions**:
1. Check environment variables are set correctly
2. Verify MCP server is accessible
3. Check logs for specific error messages
4. Ensure port 3001 is available

```bash
# Check if MCP server is reachable
curl http://kubernetes-mcp-server.ai-agents.svc.cluster.local:8080/health

# Check port availability
netstat -tuln | grep 3001
```

### Frontend can't connect to backend

**Issue**: Frontend shows connection errors

**Solutions**:
1. Verify backend is running and healthy
2. Check CORS configuration (should allow all origins)
3. Verify API_BASE_URL is correct
4. Check network connectivity

```bash
# From frontend pod/container
curl http://kubani-ui-backend:3001/health
```

### Slow API responses

**Issue**: API endpoints are slow

**Solutions**:
1. Check MCP server response times
2. Verify cache is working (check logs for cache hits)
3. Increase backend replicas for load distribution
4. Check cluster resource utilization

```bash
# Check backend metrics
kubectl top pod -l app=kubani-ui-backend -n ai-agents
```

### Mobile layout issues

**Issue**: UI doesn't display correctly on mobile

**Solutions**:
1. Clear browser cache
2. Ensure viewport meta tag is present
3. Check browser console for errors
4. Test on different devices/browsers

---

## 📊 Monitoring

### Prometheus Metrics (Future)

The backend can be extended to expose Prometheus metrics:

```rust
// Add to Cargo.toml
// prometheus = "0.13"

// Expose metrics endpoint
.route("/metrics", get(metrics_handler))
```

### Logging

Logs are structured using the `tracing` crate:

```bash
# Set log level
RUST_LOG=debug cargo run

# Filter by module
RUST_LOG=kubani_ui_backend::api=debug cargo run
```

---

## 🔄 Rollback

If you need to rollback to the Node.js backend:

### Kubernetes

```bash
# Scale down Rust backend
kubectl scale deployment kubani-ui-backend --replicas=0 -n ai-agents

# Scale up Node.js backend (if still deployed)
kubectl scale deployment kubani-ui-nodejs --replicas=2 -n ai-agents

# Or redeploy the old version
kubectl rollout undo deployment/kubani-ui-backend -n ai-agents
```

### Docker Compose

```bash
# Stop current stack
docker-compose down

# Checkout previous version
git checkout <previous-commit>

# Start old version
docker-compose up -d
```

---

## 🔐 Security Considerations

1. **API Authentication**: Consider adding authentication to the backend
2. **CORS**: In production, restrict CORS to specific origins
3. **Rate Limiting**: Add rate limiting to prevent abuse
4. **HTTPS**: Use TLS/SSL in production
5. **Network Policies**: Restrict backend access to authorized pods only

---

## 📈 Scaling

### Horizontal Scaling

The Rust backend is stateless and can be scaled horizontally:

```bash
kubectl scale deployment kubani-ui-backend --replicas=5 -n ai-agents
```

### Vertical Scaling

Adjust resource limits based on load:

```yaml
resources:
  requests:
    memory: "128Mi"
    cpu: "200m"
  limits:
    memory: "512Mi"
    cpu: "1000m"
```

### Caching

The backend includes a 5-second cache. Adjust in `src/cache.rs`:

```rust
Cache::builder()
    .max_capacity(1000)
    .time_to_live(Duration::from_secs(10)) // Increase TTL
    .build()
```

---

## 🎯 Performance Tuning

### Backend Optimization

1. **Increase cache TTL** for less frequently changing data
2. **Adjust worker threads**: Set `TOKIO_WORKER_THREADS` env var
3. **Connection pooling**: MCP session reuse is automatic
4. **Parallel requests**: Already implemented for monitoring endpoints

### Frontend Optimization

1. **Code splitting**: Lazy load routes
2. **Image optimization**: Compress assets
3. **Bundle analysis**: Use `pnpm build --analyze`
4. **CDN**: Serve static assets from CDN

---

## 📚 Additional Resources

- [Rust Backend README](backend/README.md)
- [Improvements Documentation](IMPROVEMENTS.md)
- [Axum Documentation](https://docs.rs/axum)
- [React Flow Documentation](https://reactflow.dev)

---

## 💬 Support

For issues or questions:
1. Check the logs first
2. Review this troubleshooting guide
3. Check the GitHub issues
4. Contact the team

---

## ✅ Deployment Checklist

Before deploying to production:

- [ ] Backend builds successfully
- [ ] Frontend builds successfully
- [ ] All environment variables are set
- [ ] Health checks pass
- [ ] API endpoints respond correctly
- [ ] Mobile layout works on test devices
- [ ] Execution visualization loads
- [ ] Workflow tracking displays tasks
- [ ] Chat functionality works
- [ ] Monitoring dashboard shows data
- [ ] Registry displays agents/skills
- [ ] Logs are being collected
- [ ] Resource limits are appropriate
- [ ] Security measures are in place
- [ ] Rollback plan is documented
- [ ] Team is notified of deployment

---

**Last Updated**: January 14, 2025
