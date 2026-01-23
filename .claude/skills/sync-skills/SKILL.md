---
name: sync-skills
description: Sync Claude Code skills to other AI coding tools (Codex, Cursor, Gemini, GitHub Copilot, Kiro)
triggers:
  - new skill added
  - skill installation
  - cross-tool sync
version: "1.0.0"
---

# Sync Skills Across AI Tools

## Purpose

Ensure all skills in `.claude/skills/` are available to other AI coding tools through symlinks.

## Supported Tools

- **Codex** (`.codex/skills/`)
- **Cursor** (`.cursor/skills/`)
- **Gemini** (`.gemini/skills/`)
- **GitHub Copilot** (`.github/skills/`)
- **Kiro** (`.kiro/skills/`)

## How It Works

All skills are stored in `.claude/skills/` as the source of truth, and symlinked to other tools' directories.

## Usage

### Sync All Skills

```bash
bash .claude/skills/sync-skills/sync.sh
```

### Check Sync Status

```bash
bash .claude/skills/sync-skills/sync.sh --check
```

## What Gets Synced

- All directories in `.claude/skills/` (except README.md)
- Excludes existing symlinks (to avoid circular references)
- Creates missing symlink directories automatically

## Directory Structure

```
.claude/skills/          # Source of truth
  ├── skill-name/        # Actual skill content
  └── ...
.codex/skills/           # Symlinks
  └── skill-name -> ../../.claude/skills/skill-name
.cursor/skills/          # Symlinks
  └── skill-name -> ../../.claude/skills/skill-name
.gemini/skills/          # Symlinks
  └── skill-name -> ../../.claude/skills/skill-name
.github/skills/          # Symlinks
  └── skill-name -> ../../.claude/skills/skill-name
.kiro/skills/            # Symlinks
  └── skill-name -> ../../.claude/skills/skill-name
```

## After Installing New Skills

After installing a skill (via Vercel CLI or manually):

1. Run the sync script: `bash .claude/skills/sync-skills/sync.sh`
2. Verify symlinks were created
3. Commit the changes if needed

## Gitignore Considerations

The skill directories in other tools (`.codex/`, `.cursor/`, etc.) should be gitignored since they're just symlinks to `.claude/skills/`.

## Troubleshooting

**Broken symlinks:**
```bash
# Remove broken symlinks
find .codex/skills .cursor/skills .gemini/skills .github/skills .kiro/skills -xtype l -delete

# Re-sync
bash .claude/skills/sync-skills/sync.sh
```

**Missing tool directory:**
```bash
# Directories are created automatically, but you can create manually:
mkdir -p .codex/skills .cursor/skills .gemini/skills .github/skills .kiro/skills
```
