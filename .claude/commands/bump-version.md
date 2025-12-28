# Bump Agent Version

Increment the version number in an agent's pyproject.toml.

## Arguments
- `$ARGUMENTS` - Format: `<agent-name> <version-type|version>`
  - `agent-name`: k8s-monitor, news-monitor, or core
  - `version-type`: major, minor, patch (auto-increment)
  - `version`: Specific version like 0.2.0

## Instructions

1. **Parse arguments** to get agent name and version/type.

2. **Read current version:**
   ```bash
   cd /home/al/git/kubani
   CURRENT=$(grep '^version = ' agents/${AGENT_NAME}/pyproject.toml | sed 's/version = "\(.*\)"/\1/')
   echo "Current version: $CURRENT"
   ```

3. **Calculate new version:**
   - If `patch`: increment last number (0.1.0 -> 0.1.1)
   - If `minor`: increment middle number, reset patch (0.1.2 -> 0.2.0)
   - If `major`: increment first number, reset others (0.1.2 -> 1.0.0)
   - If specific version: use that

4. **Update pyproject.toml:**
   ```bash
   sed -i "s/^version = \".*\"/version = \"${NEW_VERSION}\"/" agents/${AGENT_NAME}/pyproject.toml
   ```

5. **Show the change:**
   ```bash
   git diff agents/${AGENT_NAME}/pyproject.toml
   ```

6. **Optionally commit:**
   Ask user if they want to commit the version bump:
   ```bash
   git add agents/${AGENT_NAME}/pyproject.toml
   git commit -m "chore(${AGENT_NAME}): bump version to ${NEW_VERSION}"
   ```

## Examples

- `/bump-version k8s-monitor patch` - 0.1.0 -> 0.1.1
- `/bump-version k8s-monitor minor` - 0.1.0 -> 0.2.0
- `/bump-version news-monitor 0.2.0` - Set specific version
- `/bump-version core major` - 0.1.0 -> 1.0.0

## Notes

- Version bumps are automatically picked up by CI
- After bumping, merge to main to trigger a new build
- The new image tag will be `{version}-{sha}` (e.g., 0.2.0-abc1234)
