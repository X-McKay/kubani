---
name: bump-version
description: Increment agent version in pyproject.toml. Use when releasing new versions, updating semantic version, or preparing for deployment.
---

# Bump Agent Version

Increment the version of an agent in its pyproject.toml.

## Arguments

- `agent-name`: k8s-monitor, news-monitor (required)
- `bump-type`: patch, minor, major, or specific version like 0.2.0

## Instructions

### Get Current Version

```bash
cd /home/al/git/kubani
AGENT_NAME="k8s-monitor"
CURRENT=$(grep '^version = ' agents/${AGENT_NAME}/pyproject.toml | sed 's/version = "\(.*\)"/\1/')
echo "Current version: $CURRENT"
```

### Calculate New Version

For semantic version bumps:
- **patch**: 0.1.0 → 0.1.1 (bug fixes)
- **minor**: 0.1.0 → 0.2.0 (new features)
- **major**: 0.1.0 → 1.0.0 (breaking changes)

Parse version components:
```bash
MAJOR=$(echo $CURRENT | cut -d. -f1)
MINOR=$(echo $CURRENT | cut -d. -f2)
PATCH=$(echo $CURRENT | cut -d. -f3)
```

### Update Version

```bash
cd /home/al/git/kubani
NEW_VERSION="0.2.0"
sed -i "s/^version = \".*\"/version = \"${NEW_VERSION}\"/" agents/${AGENT_NAME}/pyproject.toml
```

### Verify Change

```bash
grep '^version = ' agents/${AGENT_NAME}/pyproject.toml
```

### Commit (Optional)

```bash
git add agents/${AGENT_NAME}/pyproject.toml
git commit -m "chore(${AGENT_NAME}): bump version to ${NEW_VERSION}"
```

## Examples

- Bump patch version: 0.1.0 → 0.1.1
- Bump minor version: 0.1.0 → 0.2.0
- Set specific version: 0.2.0

## Notes

After bumping version:
1. Run tests: `just test-agent ${AGENT_NAME}`
2. Build: `/build ${AGENT_NAME} push`
3. Deploy: `/deploy ${AGENT_NAME} ${NEW_VERSION}-${SHA}`
