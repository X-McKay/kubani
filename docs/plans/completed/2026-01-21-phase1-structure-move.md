# Phase 1: Structure & Move - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reorganize the repository into clean top-level directories (agents/, platform/, infrastructure/, tools/, docs/, config/) without changing any runtime behavior.

**Architecture:** Pure file/directory moves with import path updates. No functional changes. All existing deployments continue working until next image build.

**Tech Stack:** Git, Python imports, Earthfile paths, gitignore updates

---

## Pre-Flight Checklist

Before starting, verify:
```bash
# All tests pass
just test

# No uncommitted changes (except .claude/settings.json)
git status

# On feature/restructure branch
git branch --show-current
```

---

## Task 1: Create Directory Structure

**Files:**
- Create: `infrastructure/` (empty dir)
- Create: `platform/` (empty dir)
- Create: `config/` (empty dir)
- Create: `docs/archive/` (empty dir)

**Step 1: Create new top-level directories**

```bash
mkdir -p infrastructure platform config docs/archive
```

**Step 2: Verify structure**

```bash
ls -la | grep -E "^d" | grep -E "(infrastructure|platform|config)"
```

Expected: Three new directories listed

**Step 3: Commit**

```bash
git add infrastructure/.gitkeep platform/.gitkeep config/.gitkeep docs/archive/.gitkeep 2>/dev/null || true
git commit --allow-empty -m "chore: create new top-level directory structure

Preparing for repository reorganization:
- infrastructure/ for gitops and ansible
- platform/ for shared libraries
- config/ for configuration files
- docs/archive/ for historical documentation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Move Infrastructure Components

**Files:**
- Move: `gitops/` → `infrastructure/gitops/`
- Move: `ansible/` → `infrastructure/ansible/`

**Step 1: Move gitops directory**

```bash
git mv gitops infrastructure/gitops
```

**Step 2: Move ansible directory**

```bash
git mv ansible infrastructure/ansible
```

**Step 3: Verify moves**

```bash
ls infrastructure/
```

Expected: `ansible  gitops`

**Step 4: Commit**

```bash
git commit -m "refactor: move gitops and ansible to infrastructure/

Part of repository restructuring Phase 1.
- gitops/ → infrastructure/gitops/
- ansible/ → infrastructure/ansible/

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Move Platform Components

**Files:**
- Move: `registry/` → `platform/registry/`
- Move: `tools/mcp-common/` → `platform/mcp-common/`

**Step 1: Move registry**

```bash
git mv registry platform/registry
```

**Step 2: Move mcp-common**

```bash
git mv tools/mcp-common platform/mcp-common
```

**Step 3: Verify moves**

```bash
ls platform/
```

Expected: `mcp-common  registry`

**Step 4: Commit**

```bash
git commit -m "refactor: move registry and mcp-common to platform/

Part of repository restructuring Phase 1.
- registry/ → platform/registry/
- tools/mcp-common/ → platform/mcp-common/

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Move Skills and Evaluations Under Agents

**Files:**
- Move: `skills/` → `agents/skills/`
- Move: `evaluations/` → `agents/evaluations/`

**Step 1: Move skills directory**

```bash
git mv skills agents/skills
```

**Step 2: Move evaluations directory**

```bash
git mv evaluations agents/evaluations
```

**Step 3: Update .claude/skills symlink**

The existing symlink at `.claude/skills/development` points to `../../skills/development`.
After the move, it needs to point to `../../agents/skills/development`.

```bash
# Check current symlink
ls -la .claude/skills/development

# Remove old symlink and create new one
rm .claude/skills/development
ln -s ../../agents/skills/development .claude/skills/development

# Verify
ls -la .claude/skills/development
```

**Step 4: Verify structure**

```bash
ls agents/
```

Expected: `backup-agent  cluster-monitor  cluster-swarm  core  evaluations  k8s-monitor  learning-agent  news-monitor  README.md  skills`

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: move skills and evaluations under agents/

Part of repository restructuring Phase 1.
- skills/ → agents/skills/
- evaluations/ → agents/evaluations/
- Updated .claude/skills/development symlink

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Move Configuration Files

**Files:**
- Move: `config.default.yaml` → `config/default.yaml`
- Move: `config.production.yaml` → `config/production.yaml`
- Move: `config.local.yaml` → `config/local.yaml`

**Step 1: Move config files**

```bash
git mv config.default.yaml config/default.yaml
git mv config.production.yaml config/production.yaml
git mv config.local.yaml config/local.yaml
```

**Step 2: Create example for local config**

```bash
cp config/local.yaml config/local.yaml.example
git add config/local.yaml.example
```

**Step 3: Update .gitignore**

Add to `.gitignore`:
```
config/local.yaml
```

And ensure `config/local.yaml.example` is tracked.

**Step 4: Verify**

```bash
ls config/
```

Expected: `default.yaml  local.yaml  local.yaml.example  production.yaml`

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: move configuration files to config/

Part of repository restructuring Phase 1.
- config.default.yaml → config/default.yaml
- config.production.yaml → config/production.yaml
- config.local.yaml → config/local.yaml
- Added config/local.yaml.example

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Archive Root Documentation

**Files:**
- Move: `ReOrganization.md` → `docs/archive/ReOrganization.md`
- Keep: `README.md` at root

**Step 1: Move ReOrganization.md**

```bash
git mv ReOrganization.md docs/archive/ReOrganization.md
```

**Step 2: Verify root is clean**

```bash
ls *.md
```

Expected: Only `README.md`

**Step 3: Commit**

```bash
git commit -m "docs: archive ReOrganization.md

Moved to docs/archive/ as part of repository restructuring.
The restructuring design is now in docs/plans/2026-01-21-repository-restructuring-design.md

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Rename MCP Server Directories

**Files:**
- Move: `tools/discord-mcp-server/` → `tools/discord-mcp/`
- Move: `tools/memory-mcp-server/` → `tools/memory-mcp/`
- Move: `tools/qdrant-mcp-server/` → `tools/qdrant-mcp/`
- Move: `tools/temporal-mcp-server/` → `tools/temporal-mcp/`

**Step 1: Rename MCP server directories**

```bash
git mv tools/discord-mcp-server tools/discord-mcp
git mv tools/memory-mcp-server tools/memory-mcp
git mv tools/qdrant-mcp-server tools/qdrant-mcp
git mv tools/temporal-mcp-server tools/temporal-mcp
```

**Step 2: Verify**

```bash
ls tools/
```

Expected: `discord-mcp  kubani  memory-mcp  observability-dashboard  qdrant-mcp  temporal-mcp`

**Step 3: Commit**

```bash
git commit -m "refactor: simplify MCP server directory names

Removed redundant '-server' suffix:
- discord-mcp-server → discord-mcp
- memory-mcp-server → memory-mcp
- qdrant-mcp-server → qdrant-mcp
- temporal-mcp-server → temporal-mcp

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Update Import Paths in mcp-common Consumers

**Files:**
- Modify: `tools/discord-mcp/pyproject.toml`
- Modify: `tools/memory-mcp/pyproject.toml`
- Modify: `tools/qdrant-mcp/pyproject.toml`
- Modify: `tools/temporal-mcp/pyproject.toml`

**Step 1: Check current mcp-common references**

```bash
grep -r "mcp-common" tools/*/pyproject.toml
```

**Step 2: Update paths to platform/mcp-common**

For each MCP server's pyproject.toml, update the mcp-common dependency path from `../mcp-common` to `../../platform/mcp-common`.

**Step 3: Verify each pyproject.toml is correct**

```bash
grep -r "platform/mcp-common" tools/*/pyproject.toml
```

**Step 4: Commit**

```bash
git add tools/*/pyproject.toml
git commit -m "fix: update mcp-common paths after move to platform/

Updated dependency paths in MCP server pyproject.toml files:
- ../mcp-common → ../../platform/mcp-common

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Update Root Earthfile Paths

**Files:**
- Modify: `Earthfile`

**Step 1: Read current Earthfile**

Check for any references to moved directories (gitops, ansible, registry, mcp-common, config files).

**Step 2: Update paths as needed**

Update any IMPORT or COPY statements that reference the old locations.

**Step 3: Test Earthfile syntax**

```bash
earthly ls 2>&1 | head -20
```

Expected: No errors, lists available targets

**Step 4: Commit**

```bash
git add Earthfile
git commit -m "fix: update Earthfile paths for new directory structure

Updated paths for:
- infrastructure/gitops
- infrastructure/ansible
- platform/mcp-common
- config/ directory

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Update config_unified.py for New Config Location

**Files:**
- Modify: `agents/core/src/core_agents/config_unified.py`

**Step 1: Find config loading logic**

```bash
grep -n "config\." agents/core/src/core_agents/config_unified.py | head -20
```

**Step 2: Update config file paths**

Change config file loading from:
- `config.default.yaml` → `config/default.yaml`
- `config.{env}.yaml` → `config/{env}.yaml`
- `config.local.yaml` → `config/local.yaml`

**Step 3: Test config loading**

```bash
cd agents/core && python -c "from core_agents.config_unified import get_config; c = get_config(); print(c)"
```

**Step 4: Commit**

```bash
git add agents/core/src/core_agents/config_unified.py
git commit -m "fix: update config_unified.py for new config/ location

Updated config file paths:
- config.default.yaml → config/default.yaml
- config.{env}.yaml → config/{env}.yaml
- config.local.yaml → config/local.yaml

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Update CLAUDE.md for New Structure

**Files:**
- Modify: `.claude/CLAUDE.md`

**Step 1: Update directory structure section**

Update the directory structure documentation to reflect the new layout.

**Step 2: Update any path references**

Search for and update:
- `gitops/` → `infrastructure/gitops/`
- `ansible/` → `infrastructure/ansible/`
- `registry/` → `platform/registry/`
- `skills/` → `agents/skills/`
- `evaluations/` → `agents/evaluations/`
- `config.*.yaml` → `config/*.yaml`

**Step 3: Commit**

```bash
git add .claude/CLAUDE.md
git commit -m "docs: update CLAUDE.md for new directory structure

Updated all path references for Phase 1 restructuring.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 12: Update .gitignore for New Paths

**Files:**
- Modify: `.gitignore`

**Step 1: Check for old path references**

```bash
grep -E "(config\.|gitops|ansible|registry|skills|evaluations)" .gitignore
```

**Step 2: Update paths**

Update any gitignore entries that reference old locations.

**Step 3: Add new ignores**

Ensure these are ignored:
- `config/local.yaml`

**Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: update .gitignore for new directory structure

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 13: Run Tests and Validate

**Step 1: Run full test suite**

```bash
just test
```

Expected: All tests pass

**Step 2: Check for broken imports**

```bash
python -c "from core_agents.config_unified import get_config; print('Config OK')"
```

**Step 3: Dry-run deployment**

```bash
kubani deploy --dry-run --agent k8s-monitor
```

Expected: Manifests generate without errors

**Step 4: Final commit if any fixes needed**

```bash
git status
# If changes needed, commit them
```

---

## Task 14: Move UI to Platform

**Files:**
- Move: `ui/` → `platform/ui/`

**Step 1: Move ui directory**

```bash
git mv ui platform/ui
```

**Step 2: Verify**

```bash
ls platform/
```

Expected: `mcp  mcp-common  registry  ui`

**Step 3: Commit**

```bash
git commit -m "refactor: move ui to platform/

Part of repository restructuring Phase 1.
- ui/ → platform/ui/

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 15: Move Scripts to Infrastructure

**Files:**
- Move: `scripts/` → `infrastructure/scripts/`

**Step 1: Move scripts directory**

```bash
git mv scripts infrastructure/scripts
```

**Step 2: Verify**

```bash
ls infrastructure/
```

Expected: `ansible  gitops  scripts`

**Step 3: Commit**

```bash
git commit -m "refactor: move scripts to infrastructure/

Part of repository restructuring Phase 1.
- scripts/ → infrastructure/scripts/

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 16: Move SOPS to Infrastructure

**Files:**
- Move: `sops/` → `infrastructure/sops/`

**Step 1: Move sops directory**

```bash
git mv sops infrastructure/sops
```

**Step 2: Verify**

```bash
ls infrastructure/
```

Expected: `ansible  gitops  scripts  sops`

**Step 3: Commit**

```bash
git commit -m "refactor: move sops to infrastructure/

Part of repository restructuring Phase 1.
- sops/ → infrastructure/sops/

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 17: Move MCP Config to Platform

**Files:**
- Move: `mcp/` → `platform/mcp/`

**Step 1: Move mcp directory**

```bash
git mv mcp platform/mcp
```

**Step 2: Verify**

```bash
ls platform/
```

Expected: `mcp  mcp-common  registry  ui`

**Step 3: Commit**

```bash
git commit -m "refactor: move mcp config to platform/

Part of repository restructuring Phase 1.
- mcp/ → platform/mcp/ (MCP policies and registry config)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 18: Move Templates to Agents

**Files:**
- Move: `templates/` → `agents/templates/`

**Step 1: Move templates directory**

```bash
git mv templates agents/templates
```

**Step 2: Verify**

```bash
ls agents/
```

Expected: `backup-agent  cluster-monitor  cluster-swarm  core  evaluations  k8s-monitor  learning-agent  news-monitor  README.md  skills  templates`

**Step 3: Commit**

```bash
git commit -m "refactor: move templates to agents/

Part of repository restructuring Phase 1.
- templates/ → agents/templates/ (agent scaffolding templates)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 19: Move Troubleshooting to Docs

**Files:**
- Move: `troubleshooting/` → `docs/troubleshooting/`

**Step 1: Move troubleshooting directory**

```bash
git mv troubleshooting docs/troubleshooting
```

**Step 2: Verify**

```bash
ls docs/
```

Expected: Should include `troubleshooting/`

**Step 3: Commit**

```bash
git commit -m "docs: move troubleshooting to docs/

Part of repository restructuring Phase 1.
- troubleshooting/ → docs/troubleshooting/

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 20: Remove Accidental ~ Directory

**Files:**
- Delete: `~/` (accidental directory containing .kube)

**Step 1: Verify contents**

```bash
ls -la ~/
```

Expected: Contains `.kube` (accidentally created directory)

**Step 2: Remove from git and filesystem**

```bash
# Check if it's tracked
git ls-files '~'

# If tracked, remove from git
git rm -rf '~' 2>/dev/null || rm -rf '~'
```

**Step 3: Commit if changes**

```bash
git status
# If there are changes:
git add -A
git commit -m "chore: remove accidental ~ directory

Cleanup of mistakenly created directory.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 21: Final Structure Verification

**Step 1: Verify final structure**

```bash
ls -d */ | sort
```

Expected top-level directories:
```
agents/
cluster_manager/   # Still present - will be removed in Phase 6
config/
docs/
infrastructure/
platform/
tests/
tools/
```

**Step 2: Verify agents/ structure**

```bash
ls agents/
```

Expected:
```
backup-agent  cluster-monitor  cluster-swarm  core  evaluations  k8s-monitor  learning-agent  news-monitor  README.md  skills  templates
```

**Step 3: Verify infrastructure/ structure**

```bash
ls infrastructure/
```

Expected:
```
ansible  gitops  scripts  sops
```

**Step 4: Verify platform/ structure**

```bash
ls platform/
```

Expected:
```
mcp  mcp-common  registry  ui
```

**Step 5: Verify docs/ structure**

```bash
ls docs/
```

Expected: Should include `archive/`, `plans/`, `troubleshooting/`

**Step 6: Check for broken symlinks**

```bash
find . -xtype l 2>/dev/null
```

Expected: No broken symlinks

**Step 7: Review commit history**

```bash
git log --oneline feature/restructure ^main | head -25
```

---

## Post-Phase 1 Checklist

- [ ] All tests pass (`just test`)
- [ ] Config loading works (`python -c "from core_agents.config_unified import get_config"`)
- [ ] Dry-run deployment works (`kubani deploy --dry-run --agent k8s-monitor`)
- [ ] CLAUDE.md is updated
- [ ] .gitignore is updated
- [ ] No broken symlinks (`find . -xtype l`)
- [ ] Accidental `~/` directory removed
- [ ] Branch is ready for review

---

## Notes

- **cluster_manager/** is intentionally NOT moved in Phase 1. It will be deprecated in Phase 6 when its functionality is merged into kubani.
- **observability-dashboard** stays in tools/ for now.
- **scratch/** is intentionally NOT moved - it's working notes/ideas.
- **tests/** at root level stays for now - evaluate in later phase.
- **htmlcov/** is generated coverage output - gitignored.
- MCP servers in gitops manifests may need path updates - check `infrastructure/gitops/apps/` after the move.
