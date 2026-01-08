# Bump Agent Version

Increment the version number in an agent's pyproject.toml using semantic versioning.

## Arguments
- `$ARGUMENTS` - Format: `<agent-name> <version-type>`
  - `agent-name`: k8s-monitor, news-monitor, core, backup-agent, or 'all'
  - `version-type`: patch, minor, major

## Instructions

1. **Parse arguments** to get agent name and version type.

2. **Preview the change (dry run):**
   ```bash
   python scripts/bump-version.py ${AGENT_NAME} --type ${BUMP_TYPE} --dry-run
   ```

3. **If user confirms, apply the bump:**
   ```bash
   python scripts/bump-version.py ${AGENT_NAME} --type ${BUMP_TYPE}
   ```

4. **Verify the change:**
   ```bash
   git diff agents/${AGENT_NAME}/pyproject.toml
   ```

5. **Optionally commit:**
   Ask user if they want to commit the version bump:
   ```bash
   git add agents/${AGENT_NAME}/pyproject.toml
   git commit -m "chore(${AGENT_NAME}): bump version to ${NEW_VERSION}"
   ```

## Alternative: Auto-detect from Commits

If no version type specified, auto-detect from conventional commits:
```bash
python scripts/bump-version.py ${AGENT_NAME} --from-commits
```

## Listing Versions

Show all agent versions:
```bash
python scripts/bump-version.py --list
```

## Examples

- `/bump-version k8s-monitor patch` - 0.1.0 -> 0.1.1
- `/bump-version k8s-monitor minor` - 0.1.0 -> 0.2.0
- `/bump-version news-monitor major` - 0.1.0 -> 1.0.0
- `/bump-version all patch` - Bump all agents

## Notes

- Version bumps follow semantic versioning
- Conventional commits determine automatic bump type:
  - `feat:` -> minor
  - `fix:`, `chore:`, `refactor:` -> patch
  - `feat!:` or `BREAKING CHANGE:` -> major
- After bumping, merge to main to trigger CI build
- The new image tag will be `{version}-{sha}` (e.g., 0.2.0-abc1234)
