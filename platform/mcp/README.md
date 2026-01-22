# MCP Server Registry

This directory contains the centralized configuration for MCP (Model Context Protocol) servers used by AI agents in the cluster.

## Directory Structure

```
mcp/
├── README.md           # This file
├── registry.json       # Auto-generated combined registry (do not edit)
├── servers/            # Individual server configurations
│   ├── kubernetes.json
│   └── cloudflare-docs.json
└── policies/           # Agent access policies
    ├── default.json
    ├── k8s-monitor.json
    └── security-monitor.json
```

## Quick Start

```bash
# Validate configuration
just mcp-validate

# Build registry.json and sync to GitOps
just mcp-sync

# Dry-run to see what would change
./scripts/sync-mcp-registry.sh --dry-run
```

## Adding a New MCP Server

1. Create a new file in `mcp/servers/<server-name>.json`:

```json
{
  "name": "my-mcp-server",
  "description": "What this server does",
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@my-org/my-mcp-server@latest"],
  "capabilities": ["capability.one", "capability.two"],
  "readOnly": false
}
```

2. Run `just mcp-sync` to update the registry

3. Update policies if agents need access to the new server

## Server Configuration

### Transport Types

**stdio** - Runs as a local subprocess:
```json
{
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@anthropics/kubernetes-mcp-server@latest"],
  "env": {"KEY": "value"}
}
```

**sse** - Server-sent events over HTTP:
```json
{
  "transport": "sse",
  "url": "https://example.com/mcp/sse"
}
```

### Server Properties

| Property | Required | Description |
|----------|----------|-------------|
| `name` | Yes | Display name of the server |
| `description` | Yes | Human-readable description |
| `transport` | Yes | `stdio` or `sse` |
| `command` | stdio only | Command to run |
| `args` | stdio only | Command arguments |
| `env` | No | Environment variables |
| `url` | sse only | SSE endpoint URL |
| `capabilities` | No | List of capability strings |
| `namespaces` | No | Kubernetes namespaces (use `["*"]` for all) |
| `readOnly` | No | If true, server only provides read operations |

## Agent Policies

Policies control which servers an agent can access and what operations require approval.

### Policy Properties

| Property | Description |
|----------|-------------|
| `allowedServers` | List of server names the agent can use |
| `requireApproval` | Operations that need human approval (use `["*"]` for all) |
| `auditLog` | Whether to log all operations |
| `readOnly` | Force read-only mode for all servers |
| `namespaceRestrictions` | `{"deny": [...]}` or `{"allow": [...]}` for K8s namespaces |

### Example Policy

```json
{
  "allowedServers": ["kubernetes"],
  "requireApproval": ["pods.delete", "deployments.scale"],
  "auditLog": true,
  "namespaceRestrictions": {
    "deny": ["kube-system", "flux-system"]
  }
}
```

## Local Development

For local development without cluster access, set the environment variable:

```bash
export MCP_REGISTRY_FILE=./mcp/registry.json
```

Or add to your `.env` file:

```
MCP_REGISTRY_FILE=./mcp/registry.json
```

The agents will automatically use this file instead of trying to read from the Kubernetes ConfigMap.

## How It Works

1. **Source files**: Individual JSON files in `servers/` and `policies/`
2. **Build**: `just mcp-sync` combines them into `registry.json`
3. **GitOps**: The script also updates `gitops/infrastructure/mcp-registry/configmap.yaml`
4. **Deployment**: Flux CD syncs the ConfigMap to the cluster
5. **Discovery**: Agents read the ConfigMap at startup to discover available servers

## File Locations

| File | Purpose |
|------|---------|
| `mcp/servers/*.json` | Server definitions (source of truth) |
| `mcp/policies/*.json` | Agent policies (source of truth) |
| `mcp/registry.json` | Combined registry (auto-generated) |
| `gitops/infrastructure/mcp-registry/configmap.yaml` | Kubernetes ConfigMap (auto-generated) |
| `agents/core/src/core_agents/integrations/mcp.py` | Registry client code |
