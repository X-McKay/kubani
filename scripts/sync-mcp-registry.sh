#!/usr/bin/env bash
# Sync MCP registry from modular files to GitOps ConfigMap
#
# This script:
# 1. Combines servers/*.json and policies/*.json into registry.json
# 2. Validates the combined JSON
# 3. Updates gitops/infrastructure/mcp-registry/configmap.yaml
#
# Usage: ./scripts/sync-mcp-registry.sh [--dry-run]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MCP_DIR="$PROJECT_ROOT/mcp"
GITOPS_CONFIGMAP="$PROJECT_ROOT/gitops/infrastructure/mcp-registry/configmap.yaml"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "Running in dry-run mode..."
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check required directories exist
if [[ ! -d "$MCP_DIR/servers" ]]; then
    log_error "Directory not found: $MCP_DIR/servers"
    exit 1
fi

if [[ ! -d "$MCP_DIR/policies" ]]; then
    log_error "Directory not found: $MCP_DIR/policies"
    exit 1
fi

# Build servers object from individual files
log_info "Building servers from $MCP_DIR/servers/"
SERVERS="{}"
for server_file in "$MCP_DIR/servers"/*.json; do
    if [[ -f "$server_file" ]]; then
        server_name=$(basename "$server_file" .json)
        log_info "  Adding server: $server_name"
        server_config=$(cat "$server_file")
        SERVERS=$(echo "$SERVERS" | jq --arg name "$server_name" --argjson config "$server_config" '.[$name] = $config')
    fi
done

# Build policies object from individual files
log_info "Building policies from $MCP_DIR/policies/"
POLICIES="{}"
for policy_file in "$MCP_DIR/policies"/*.json; do
    if [[ -f "$policy_file" ]]; then
        policy_name=$(basename "$policy_file" .json)
        log_info "  Adding policy: $policy_name"
        policy_config=$(cat "$policy_file")
        POLICIES=$(echo "$POLICIES" | jq --arg name "$policy_name" --argjson config "$policy_config" '.[$name] = $config')
    fi
done

# Combine into registry
REGISTRY=$(jq -n \
    --arg version "1.0" \
    --argjson servers "$SERVERS" \
    --argjson policies "$POLICIES" \
    '{version: $version, servers: $servers, policies: $policies}')

# Validate JSON
if ! echo "$REGISTRY" | jq . > /dev/null 2>&1; then
    log_error "Generated registry is not valid JSON"
    exit 1
fi

log_info "Registry built successfully"

# Write registry.json
REGISTRY_FILE="$MCP_DIR/registry.json"
if [[ "$DRY_RUN" == true ]]; then
    log_info "Would write to: $REGISTRY_FILE"
    echo "$REGISTRY" | jq .
else
    echo "$REGISTRY" | jq . > "$REGISTRY_FILE"
    log_info "Written: $REGISTRY_FILE"
fi

# Update GitOps ConfigMap
log_info "Updating GitOps ConfigMap: $GITOPS_CONFIGMAP"

# Read existing ConfigMap and extract non-registry parts
if [[ -f "$GITOPS_CONFIGMAP" ]]; then
    # Create the new ConfigMap content
    REGISTRY_ESCAPED=$(echo "$REGISTRY" | jq -c . | sed 's/\\/\\\\/g; s/"/\\"/g')

    if [[ "$DRY_RUN" == true ]]; then
        log_info "Would update ConfigMap with new registry"
    else
        # Generate the ConfigMap YAML
        cat > "$GITOPS_CONFIGMAP" << 'CONFIGMAP_HEADER'
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: mcp-server-registry
  namespace: ai-agents
  labels:
    app.kubernetes.io/name: mcp-registry
    app.kubernetes.io/component: configuration
data:
  # MCP Server Registry Configuration
  # This ConfigMap provides centralized discovery of MCP servers available to agents.
  # Agents read this configuration to discover available MCP servers and their capabilities.
  #
  # NOTE: This file is auto-generated from ./mcp/servers/ and ./mcp/policies/
  # Do not edit directly - run 'just mcp-sync' to update.

  # Registry format (JSON for programmatic access)
  registry.json: |
CONFIGMAP_HEADER

        # Append indented JSON
        echo "$REGISTRY" | jq . | sed 's/^/    /' >> "$GITOPS_CONFIGMAP"

        # Append README
        cat >> "$GITOPS_CONFIGMAP" << 'CONFIGMAP_README'

  # Human-readable documentation
  README.md: |
    # MCP Server Registry

    This ConfigMap provides centralized discovery of MCP (Model Context Protocol)
    servers available to AI agents in the cluster.

    NOTE: This file is auto-generated. Edit files in ./mcp/ and run 'just mcp-sync'.

    ## Available Servers

    ### kubernetes-mcp-server
    Native Kubernetes operations. Provides direct access to cluster resources
    without requiring Python kubernetes client libraries.

    **Capabilities:**
    - Pod management (list, get, logs, exec, delete)
    - Deployment operations (list, scale)
    - Event monitoring
    - Resource management (get, create, delete)
    - Helm chart operations

    ### cloudflare-docs-mcp
    Search Cloudflare documentation for infrastructure guidance.

    ## Agent Policies

    Each agent can have specific policies defining:
    - Which MCP servers they can access
    - Which operations require human approval
    - Namespace restrictions
    - Audit logging requirements

    ## Usage

    Agents should read this ConfigMap at startup to discover available
    MCP servers and configure their tool sets accordingly.

    ```python
    from kubernetes import client, config

    config.load_incluster_config()
    v1 = client.CoreV1Api()

    cm = v1.read_namespaced_config_map(
        name="mcp-server-registry",
        namespace="ai-agents"
    )
    registry = json.loads(cm.data["registry.json"])
    ```
CONFIGMAP_README

        log_info "Updated: $GITOPS_CONFIGMAP"
    fi
else
    log_warn "ConfigMap not found: $GITOPS_CONFIGMAP"
    log_warn "Skipping GitOps sync"
fi

log_info "MCP registry sync complete!"

# Summary
echo ""
echo "Summary:"
echo "  Servers: $(echo "$SERVERS" | jq 'keys | length')"
echo "  Policies: $(echo "$POLICIES" | jq 'keys | length')"
echo ""
echo "Files:"
echo "  $REGISTRY_FILE"
echo "  $GITOPS_CONFIGMAP"
