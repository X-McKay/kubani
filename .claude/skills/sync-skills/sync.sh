#!/usr/bin/env bash
set -euo pipefail

# Sync Claude Code skills to other AI coding tools
# Usage: ./sync.sh [--check]

# Find repository root using git
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

# AI tool directories to sync to
TOOL_DIRS=(
  ".codex/skills"
  ".cursor/skills"
  ".gemini/skills"
  ".github/skills"
  ".kiro/skills"
)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check mode flag
CHECK_MODE=false
if [[ "${1:-}" == "--check" ]]; then
  CHECK_MODE=true
fi

echo -e "${BLUE}=== Skill Sync Tool ===${NC}"
echo

if [ "$CHECK_MODE" = true ]; then
  echo "Checking sync status..."
  echo
  all_synced=true

  for skill_dir in .claude/skills/*/; do
    skill_name=$(basename "$skill_dir")
    [ "$skill_name" = "README.md" ] && continue
    [ -L ".claude/skills/$skill_name" ] && continue

    missing=()
    for tool_dir in "${TOOL_DIRS[@]}"; do
      if [ ! -e "$tool_dir/$skill_name" ]; then
        missing+=("$tool_dir")
      fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
      echo -e "${YELLOW}$skill_name${NC}"
      echo -e "  ${RED}Missing:${NC} ${missing[*]}"
      all_synced=false
    else
      echo -e "${GREEN}$skill_name${NC} ✓"
    fi
  done

  echo
  if [ "$all_synced" = true ]; then
    echo -e "${GREEN}All skills are synced! ✓${NC}"
    exit 0
  else
    echo -e "${YELLOW}Some skills need syncing. Run without --check to sync.${NC}"
    exit 1
  fi
else
  echo "Syncing skills to AI coding tools..."
  echo

  created_count=0
  skipped_count=0

  for skill_dir in .claude/skills/*/; do
    skill_name=$(basename "$skill_dir")
    [ "$skill_name" = "README.md" ] && continue
    [ -L ".claude/skills/$skill_name" ] && continue

    skill_created=0

    for tool_dir in "${TOOL_DIRS[@]}"; do
      mkdir -p "$tool_dir"

      if [ ! -e "$tool_dir/$skill_name" ]; then
        ln -s "../../.claude/skills/$skill_name" "$tool_dir/$skill_name"
        skill_created=$((skill_created + 1))
        created_count=$((created_count + 1))
      fi
    done

    if [ $skill_created -gt 0 ]; then
      echo -e "${GREEN}$skill_name${NC} (created $skill_created symlinks)"
    else
      echo -e "${GREEN}$skill_name${NC} (already synced)"
      skipped_count=$((skipped_count + 1))
    fi
  done

  echo
  echo -e "${GREEN}Sync complete! ✓${NC}"
  echo
  echo "Summary:"
  echo -e "  ${GREEN}Created:${NC} $created_count symlinks"
  echo -e "  ${BLUE}Skipped:${NC} $skipped_count skills (already synced)"
  echo
  echo "Tool directories:"
  for tool_dir in "${TOOL_DIRS[@]}"; do
    count=$(find "$tool_dir" -type l 2>/dev/null | wc -l || echo "0")
    echo -e "  ${BLUE}$tool_dir${NC}: $count skills"
  done
fi
