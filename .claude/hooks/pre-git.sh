#!/bin/bash
# PreToolUse guard: refuse `git commit` / `git push` when an unencrypted
# Kubernetes Secret is present in the tree.
#
# Why this exists even though git hooks are installed: an agent can run
# `git commit --no-verify`, and hooks are per-clone state a fresh clone may
# not have. This closes the agent-side path specifically.
#
# Deliberately runs only the fast Python secret scan (~1s), not full
# pre-commit, so it stays inside the hook timeout. Broader checks belong in
# the pre-push hook and CI.
#
# Exit codes: 0 allow, 2 block (stderr is surfaced to Claude).

set -uo pipefail

INPUT=$(timeout 2s cat 2>/dev/null || echo '{}')

COMMAND=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('tool_input', {}).get('command', ''))
except Exception:
    print('')
" 2>/dev/null)

[ -z "$COMMAND" ] && exit 0

# Only guard commands that create or publish history.
if ! printf '%s' "$COMMAND" \
    | grep -qE '(^|[;&|[:space:]])git[[:space:]]+([^;&|]*[[:space:]])?(commit|push)([[:space:]]|$)'; then
    exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -z "$PROJECT_DIR" ] && exit 0

SCANNER="$PROJECT_DIR/infrastructure/scripts/pre-commit/check-plaintext-secrets.py"
# Never block when the scanner is absent: this guard must not wedge work in a
# checkout that predates it.
[ -f "$SCANNER" ] || exit 0

if OUTPUT=$(cd "$PROJECT_DIR" && timeout 25s uv run python "$SCANNER" --all 2>&1); then
    exit 0
fi

# Distinguish a real finding from the scanner failing to run.
if printf '%s' "$OUTPUT" | grep -q "Unencrypted Kubernetes Secret values found"; then
    {
        echo "BLOCKED: an unencrypted Kubernetes Secret is present in the tree."
        echo
        printf '%s\n' "$OUTPUT"
        echo
        echo "Encrypt it with SOPS before committing or pushing. See .claude/rules/secrets.md."
    } >&2
    exit 2
fi

# Scanner errored (missing deps, timeout). Warn, do not block.
echo "pre-git guard: secret scan could not run; proceeding unguarded." >&2
printf '%s\n' "$OUTPUT" >&2
exit 0
