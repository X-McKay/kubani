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

# Log commands for learning system (non-blocking)
LOG_DIR="${CLAUDE_PROJECT_DIR:-.}/.claude/hooks/logs"
mkdir -p "$LOG_DIR"
echo "$(date -Iseconds) | $COMMAND" >> "$LOG_DIR/bash_commands.log" 2>/dev/null || true

exit 0
