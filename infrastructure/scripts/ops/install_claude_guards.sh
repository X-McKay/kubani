#!/usr/bin/env bash
# Installs the rig0 Claude auto-mode rules as a root-owned managed-settings
# drop-in (docs/infrastructure/operations/claude-guards.md, kubani#273).
#
#   bash infrastructure/scripts/ops/install_claude_guards.sh
#
# Runs on rig0 in a real terminal (a `!`-prefixed command in a cloud thread does
# not run anything there), from the main checkout /home/al/git/kubani, because
# Remote Control sessions load the hook and settings from that checkout. It:
#   1. stops if the checkout has uncommitted changes, then puts it on main and
#      fast-forwards it, so the guard changes merged since are live;
#   2. validates .claude/automode.rig0.json (a managed file that is not valid
#      JSON stops Claude Code from starting) and installs it with sudo as
#      /etc/claude-code/managed-settings.d/50-kubani-automode.json;
#   3. warns if ~/.claude/settings.json still carries an autoMode block (the
#      rules should have one home) and prints the live allow entries.
# Idempotent: re-run after any change to the drop-in. Restart the rig0 Claude
# session afterwards; a running session keeps the settings it started with.
set -euo pipefail

repo=$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)
cd "$repo"
src=.claude/automode.rig0.json
dst=/etc/claude-code/managed-settings.d/50-kubani-automode.json

for tool in git jq sudo install claude; do
  command -v "$tool" >/dev/null || { echo "missing $tool" >&2; exit 1; }
done

if [[ -n "$(git status --short)" ]]; then
  echo "$repo has uncommitted changes; commit or stash them first" >&2
  git status --short >&2
  exit 1
fi
if [[ "$(git branch --show-current)" != "main" ]]; then
  echo "switching $repo from $(git branch --show-current) to main (the hook loads from here)"
  git checkout main
fi
git pull --ff-only

jq -e . "$src" >/dev/null || { echo "$src is not valid JSON; not installing" >&2; exit 1; }
jq -e '.autoMode and .parentSettingsBehavior == "merge"' "$src" >/dev/null \
  || { echo "$src lacks autoMode or parentSettingsBehavior: merge; not installing" >&2; exit 1; }

if [[ -f "$dst" ]] && cmp -s "$src" "$dst"; then
  echo "$dst already matches $src"
else
  sudo install -D -m 0644 -o root -g root "$src" "$dst"
  echo "installed $dst"
fi

if [[ -f "$HOME/.claude/settings.json" ]] \
  && jq -e '.autoMode' "$HOME/.claude/settings.json" >/dev/null 2>&1; then
  echo "note: $HOME/.claude/settings.json still has an autoMode block; remove it so the rules have one home"
fi

echo "live auto-mode allow entries (last five):"
claude auto-mode config | jq '.allow[-5:]'
echo "done: restart the rig0 Claude session for the managed settings to apply"
