# MCP Gateway Test Deployment

This directory contains the Kubernetes manifests for deploying the MCP Gateway in a test environment.

## Overview

The MCP Gateway provides a unified access point for multiple MCP servers, simplifying client configuration and improving observability.

## Components

- **Namespace**: `ai-agents-test` - Isolated test environment
- **Deployment**: `mcp-gateway` - Gateway application
- **Service**: `mcp-gateway` - Internal service (ClusterIP)
- **Ingress**: `mcp-gateway.almckay.io` - External access via Tailscale
- **ConfigMap**: `mcp-gateway-config` - Gateway configuration

## Upstream MCP Servers

The gateway is configured to proxy requests to the following MCP servers:

1. **discord-mcp** - Discord integration
2. **memory-mcp** - Agent memory and knowledge management
3. **skills-mcp** - Dynamic skill discovery
4. **temporal-mcp** - Workflow orchestration
5. **qdrant-mcp** - Vector database operations

## Deployment

### Prerequisites

- Kubernetes cluster with kubectl access
- Flux CD installed (for GitOps deployment)
- Tailscale egress configured for `*.almckay.io`

### Manual Deployment

```bash
# Apply the manifests
kubectl apply -k infrastructure/gitops/apps/ai-agents/mcp-gateway-test/

# Check deployment status
kubectl get pods -n ai-agents-test
kubectl get svc -n ai-agents-test
kubectl get ingress -n ai-agents-test

# View logs
kubectl logs -n ai-agents-test -l app.kubernetes.io/name=mcp-gateway -f
```

### GitOps Deployment

The manifests will be automatically deployed by Flux CD when committed to the repository.

## Configuration

The gateway configuration is stored in `gateway-config.yaml` and mounted at `/etc/mcp-gateway/gateway.yaml`.

Key configuration sections:

- **servers**: List of upstream MCP servers with connection details
- **gateway**: Gateway-specific settings (ports, timeouts)
- **observability**: Metrics, tracing, and logging configuration

## Access

- **Internal**: `http://mcp-gateway.ai-agents-test.svc:8080`
- **External**: `https://mcp-gateway.almckay.io`
- **Metrics**: `http://mcp-gateway.ai-agents-test.svc:9090/metrics`

## Testing

See the evaluation documentation in `docs/adr/` for testing procedures and results.

## Notes

- This is a **test deployment** for evaluation purposes
- The gateway image may need to be adjusted based on actual Microsoft mcp-gateway availability
- If the official image is not available, we may need to build from source or use an alternative
