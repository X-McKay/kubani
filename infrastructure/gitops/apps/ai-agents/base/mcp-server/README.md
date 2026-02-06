# MCP Server Base Template

This directory contains the base Kustomize template for all MCP servers in the Kubani platform.

## Features

- **Standard Labels**: All deployments include consistent labels for service discovery
  - `app.kubernetes.io/name`: Server name
  - `app.kubernetes.io/component`: mcp-server
  - `app.kubernetes.io/part-of`: kubani
  - `mcp.kubani.io/server`: "true" (for registry reconciliation)

- **Resource Limits**: Consistent resource requests and limits
  - Requests: 50m CPU, 128Mi memory
  - Limits: 500m CPU, 512Mi memory

- **Security Context**: Hardened security settings
  - Run as non-root (UID 1000)
  - Drop all capabilities
  - Disable privilege escalation
  - Read-only root filesystem where possible

- **Health Checks**: HTTP-based health and readiness probes
  - Liveness probe: `/health` endpoint
  - Readiness probe: `/health` endpoint

- **Metrics**: Prometheus metrics endpoint on port 9090

- **Registry Integration**: Environment variables for registry self-registration
  - `MCP_SERVER_ID`: Unique server identifier
  - `REGISTRY_URL`: Registry service URL

## Usage

To create a new MCP server deployment:

1. Create a new directory under `infrastructure/gitops/apps/ai-agents/`
2. Create a `kustomization.yaml` that references this base:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: ai-agents

bases:
  - ../base/mcp-server

namePrefix: my-server-

images:
  - name: registry.almckay.io/mcp-server
    newName: registry.almckay.io/my-server-mcp-server
    newTag: 0.1.0

patches:
  - patch: |-
      - op: replace
        path: /spec/template/spec/containers/0/ports/0/containerPort
        value: 8084
      - op: replace
        path: /spec/template/spec/containers/0/args/3
        value: "8084"
      - op: add
        path: /spec/template/spec/containers/0/env/-
        value:
          name: MY_BACKEND_URL
          value: "http://my-backend.svc:8000"
    target:
      kind: Deployment
      name: mcp-server

resources:
  - secret.enc.yaml
```

3. Customize as needed:
   - Change port numbers
   - Add backend-specific environment variables
   - Add secrets
   - Adjust resource limits if needed

## Standard Ports

- HTTP/SSE: 8080 (default, customize per server)
- Metrics: 9090 (standard across all servers)

## Environment Variables

Standard environment variables included in the base:

- `MCP_SERVER_ID`: Unique identifier for registry
- `REGISTRY_URL`: URL of the Kubani Registry service
- `MCP_ALLOWED_HOSTS`: Allowed hosts for CORS/security

Backend-specific variables should be added via patches in the overlay.
