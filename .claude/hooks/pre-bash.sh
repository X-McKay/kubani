#!/bin/bash
# Pre-bash hook - validates commands before execution
# Warns about potentially dangerous operations

# Get command from stdin (PreToolUse provides JSON input)
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('tool_input', {}).get('command', ''))" 2>/dev/null || echo "")

# If no command from JSON, exit
if [ -z "$COMMAND" ]; then
    exit 0
fi

# Define dangerous patterns
DANGEROUS_PATTERNS=(
    "rm -rf /"
    "rm -rf /*"
    "rm -rf ~"
    "> /dev/sda"
    "mkfs."
    "dd if="
    ":(){:|:&};:"
    "chmod -R 777 /"
    "kubectl delete namespace"
    "kubectl delete --all"
    "DROP DATABASE"
    "DROP TABLE"
)

# Check for dangerous patterns
for pattern in "${DANGEROUS_PATTERNS[@]}"; do
    if [[ "$COMMAND" == *"$pattern"* ]]; then
        echo "⚠️  Potentially dangerous command detected: $pattern"
        echo "Command: $COMMAND"
        # Return exit code 2 to block the command
        exit 2
    fi
done

# ============================================================================
# PROTECTED BRANCH CHECKS - Block force push to main/master
# ============================================================================
PROTECTED_BRANCHES=("main" "master" "production" "release")

# Check for git push --force variants
if [[ "$COMMAND" =~ git[[:space:]]+push.*(-f|--force|--force-with-lease) ]]; then
    # Extract the remote and branch if specified
    for branch in "${PROTECTED_BRANCHES[@]}"; do
        # Check if pushing to a protected branch
        if [[ "$COMMAND" =~ (origin[[:space:]]+$branch|$branch:|/$branch) ]]; then
            echo "{\"decision\": \"block\", \"reason\": \"Force push to protected branch '$branch' is blocked. This requires manual intervention outside of Claude Code.\"}"
            exit 2
        fi
    done

    # If pushing to current branch, check what branch we're on
    CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "")
    for branch in "${PROTECTED_BRANCHES[@]}"; do
        if [ "$CURRENT_BRANCH" = "$branch" ]; then
            echo "{\"decision\": \"block\", \"reason\": \"Force push from protected branch '$branch' is blocked. Switch to a feature branch or use regular push.\"}"
            exit 2
        fi
    done

    # Warn about force push but allow on non-protected branches
    echo "⚠️  Force push detected on non-protected branch - proceeding with caution" >&2
fi

# ============================================================================
# PRODUCTION NAMESPACE CHECKS - Block kubectl apply to production
# ============================================================================
if [[ "$COMMAND" =~ kubectl[[:space:]]+(apply|create|delete|patch|replace) ]]; then
    if [[ "$COMMAND" =~ (-n|--namespace)[[:space:]]*(=)?[[:space:]]*(production|prod)[[:space:]] ]] || \
       [[ "$COMMAND" =~ (-n|--namespace)=(production|prod) ]]; then
        echo '{"decision": "block", "reason": "Direct kubectl modifications to production namespace are blocked. Use GitOps workflow instead."}'
        exit 2
    fi
fi

# Log commands for learning system (non-blocking)
LOG_DIR="${CLAUDE_PROJECT_DIR:-.}/.claude/hooks/logs"
mkdir -p "$LOG_DIR"
echo "$(date -Iseconds) | $COMMAND" >> "$LOG_DIR/bash_commands.log" 2>/dev/null || true

exit 0
