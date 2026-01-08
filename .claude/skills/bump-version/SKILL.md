---
name: bump-version
description: Increment agent version in pyproject.toml. Use when releasing new versions, updating semantic version, or preparing for deployment.
---

# Bump Agent Version

Increment the version of an agent in its pyproject.toml using the semantic versioning script.

## Arguments

- `agent-name`: k8s-monitor, news-monitor, core, backup-agent (or 'all')
- `bump-type`: patch, minor, major

## Commands

### List All Agent Versions

```bash
python scripts/bump-version.py --list
```

### Bump Version (Dry Run)

```bash
python scripts/bump-version.py <agent-name> --type <patch|minor|major> --dry-run
```

### Bump Version

```bash
python scripts/bump-version.py <agent-name> --type <patch|minor|major>
```

### Auto-detect from Commits

```bash
python scripts/bump-version.py <agent-name> --from-commits
```

### Bump All Agents from Commits

```bash
python scripts/bump-version.py all --from-commits
```

## Just Commands

```bash
# List versions
just agent-versions

# Bump specific agent
just bump k8s-monitor patch
just bump news-monitor minor

# Auto-detect from commits
just bump-from-commits k8s-monitor

# Preview what would change
just bump-preview k8s-monitor
```

## Semantic Version Rules

- **patch** (0.1.0 -> 0.1.1): Bug fixes, maintenance (fix:, chore:, refactor:)
- **minor** (0.1.0 -> 0.2.0): New features (feat:)
- **major** (0.1.0 -> 1.0.0): Breaking changes (feat!:, BREAKING CHANGE)

## Instructions

1. **Check current versions** - Run `just agent-versions` or `python scripts/bump-version.py --list`

2. **Determine bump type** based on changes:
   - Bug fix? -> patch
   - New feature? -> minor
   - Breaking change? -> major
   - Unsure? -> Use `--from-commits` to auto-detect

3. **Preview the change** - Use `--dry-run` first

4. **Apply the bump** - Run without `--dry-run`

5. **Verify the change**:
   ```bash
   git diff agents/<agent-name>/pyproject.toml
   ```

6. **Commit the version bump**:
   ```bash
   git add agents/<agent-name>/pyproject.toml
   git commit -m "chore(<agent-name>): bump version to <new-version>"
   ```

## After Bumping

1. Run tests: `just test-agent <agent-name>`
2. Build image: `/build <agent-name> push`
3. Deploy: `/deploy <agent-name>`

## Examples

```bash
# Bump k8s-monitor patch version
python scripts/bump-version.py k8s-monitor --type patch

# Bump news-monitor minor version
python scripts/bump-version.py news-monitor --type minor

# Auto-detect from conventional commits
python scripts/bump-version.py k8s-monitor --from-commits

# Bump all agents from commits (useful for releases)
python scripts/bump-version.py all --from-commits --dry-run
```
