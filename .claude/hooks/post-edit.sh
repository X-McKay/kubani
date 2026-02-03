#!/bin/bash
# Post-edit hook - runs after Write/Edit operations
# Automatically formats and lints modified files

# Get the file path from stdin with timeout to prevent hanging
# Claude Code sends JSON via stdin with tool_input.file_path
INPUT=$(timeout 1s cat 2>/dev/null || echo '{}')

# Parse file path from JSON - read input once, no seeking
FILE=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    ti = data.get('tool_input', {})
    print(ti.get('file_path', ti.get('path', '')))
except:
    print('')
" 2>/dev/null)

# If no file from JSON, try positional argument
if [ -z "$FILE" ]; then
    FILE="$1"
fi

# Exit if no file
if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
    exit 0
fi

# Get file extension
EXT="${FILE##*.}"

# Process Python files
if [ "$EXT" = "py" ]; then
    # Run ruff formatter (fast)
    if command -v ruff &> /dev/null; then
        ruff format "$FILE" 2>/dev/null || true
        ruff check --fix "$FILE" 2>/dev/null || true
    fi
fi

# Process YAML files
if [ "$EXT" = "yaml" ] || [ "$EXT" = "yml" ]; then
    # Validate YAML syntax
    python3 -c "import yaml; yaml.safe_load(open('$FILE'))" 2>/dev/null || {
        echo "⚠️  YAML syntax error in $FILE"
    }
fi

# Process JSON files
if [ "$EXT" = "json" ]; then
    # Validate and format JSON
    python3 -c "import json; json.load(open('$FILE'))" 2>/dev/null || {
        echo "⚠️  JSON syntax error in $FILE"
    }
fi

# Process TypeScript/JavaScript files
if [ "$EXT" = "ts" ] || [ "$EXT" = "tsx" ] || [ "$EXT" = "js" ] || [ "$EXT" = "jsx" ]; then
    # Run prettier if available
    if command -v prettier &> /dev/null; then
        prettier --write "$FILE" 2>/dev/null || true
    fi
fi

exit 0
