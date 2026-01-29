#!/bin/bash
# Sync Git resources to the Kubani Registry.
#
# This syncs:
#   - Skills (skills/**/*.md)
#   - Agents (agents/*/pyproject.toml)
#   - MCP Servers (mcp/servers/*.json)
#   - MCP Policies (mcp/policies/*.json)
#
# Usage:
#   ./scripts/sync-registry.sh              # Sync everything
#   ./scripts/sync-registry.sh --dry-run    # Preview changes
#   ./scripts/sync-registry.sh --skills     # Only sync skills
#
# Environment variables:
#   REGISTRY_URL - Registry service URL (default: http://localhost:8000)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "🔄 Syncing to registry..."
echo ""

# Pass all arguments to kubani sync
uv run kubani sync "$@"
