#!/bin/bash
# Session end hook - runs when Claude Code session ends
# Logs session summary and performs cleanup

set -e

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR"

# Create logs directory
LOG_DIR="$PROJECT_DIR/.claude/hooks/logs"
mkdir -p "$LOG_DIR"

# Get session info from stdin
INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('session_id', 'unknown'))" 2>/dev/null || echo "unknown")

# Log session end
TIMESTAMP=$(date -Iseconds)
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
UNCOMMITTED=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')

cat >> "$LOG_DIR/sessions.log" << EOF
---
timestamp: $TIMESTAMP
session_id: $SESSION_ID
branch: $BRANCH
uncommitted_changes: $UNCOMMITTED
EOF

# Remind about uncommitted changes
if [ "$UNCOMMITTED" -gt 0 ]; then
    echo ""
    echo "⚠️  You have $UNCOMMITTED uncommitted changes"
    echo "Consider committing before ending the session:"
    echo "  git add -A && git commit -m 'your message'"
    echo ""
fi

# Output summary
echo "Session ended: $SESSION_ID"
echo "Log saved to: $LOG_DIR/sessions.log"

exit 0
