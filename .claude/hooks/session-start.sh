#!/bin/bash
# Session start hook - runs when Claude Code starts a session
# This hook provides context about the project state

set -e

# Colors
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║              Kubani Development Session                      ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Project info
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR"

# Environment
if [ -f "config.local.yaml" ]; then
    ENV=$(grep "^environment:" config.local.yaml 2>/dev/null | cut -d: -f2 | tr -d ' ' || echo "unknown")
else
    ENV="development"
fi
echo -e "Environment:  ${GREEN}$ENV${NC}"

# Git info
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
LAST_COMMIT=$(git log -1 --oneline 2>/dev/null || echo "no commits")
echo -e "Branch:       ${GREEN}$BRANCH${NC}"
echo -e "Last commit:  $LAST_COMMIT"
echo ""

# Check for uncommitted changes
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    echo -e "${YELLOW}⚠️  Uncommitted changes:${NC}"
    git status --short
    echo ""
fi

# Check MCP server availability (non-blocking)
echo "MCP Servers:"
for server in temporal qdrant memory discord; do
    if command -v "${server}-mcp-server" &> /dev/null; then
        echo -e "  $server: ${GREEN}installed${NC}"
    else
        echo -e "  $server: ${YELLOW}not installed${NC}"
    fi
done
echo ""

# Quick reference
echo "Quick Commands:"
echo "  kubani-dev local-run --agent <name>  # Run agent locally"
echo "  kubani-dev eval run --suite <file>   # Run evaluations"
echo "  kubani-dev deploy --agent <name>     # Deploy to cluster"
echo "  just test                            # Run tests"
echo ""

# Output JSON for Claude Code to parse
cat << EOF
{
  "project": "kubani",
  "environment": "$ENV",
  "branch": "$BRANCH",
  "has_uncommitted_changes": $([ -n "$(git status --porcelain 2>/dev/null)" ] && echo "true" || echo "false")
}
EOF
