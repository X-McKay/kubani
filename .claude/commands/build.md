# Build Agent

Build and optionally push an agent Docker image.

## Arguments
- `$ARGUMENTS` - Format: `[agent-name] [push] [version]`
  - `agent-name`: k8s-monitor, news-monitor, or 'all' (default: auto-detect from changed files)
  - `push`: Include to push to registry
  - `version`: Custom version tag (default: from pyproject.toml + git SHA)

## Instructions

1. **Parse arguments to determine:**
   - Which agent(s) to build
   - Whether to push to registry
   - Version tag to use

2. **If no agent specified, check for changes:**
   ```bash
   cd /home/al/git/kubani
   git diff --name-only HEAD~1 HEAD | grep '^agents/' | cut -d'/' -f2 | sort -u
   ```
   Build agents that have changes (excluding 'core' which triggers all).

3. **Get version from pyproject.toml and git SHA:**
   ```bash
   cd /home/al/git/kubani
   AGENT_NAME="k8s-monitor"  # or news-monitor
   VERSION=$(grep '^version = ' agents/${AGENT_NAME}/pyproject.toml | sed 's/version = "\(.*\)"/\1/')
   SHA_SHORT=$(git rev-parse --short HEAD)
   TAG="${VERSION}-${SHA_SHORT}"
   ```

4. **Build the image:**
   ```bash
   cd /home/al/git/kubani
   earthly ./agents/${AGENT_NAME}+docker --VERSION=$TAG
   ```

5. **If pushing, push to registry:**
   ```bash
   cd /home/al/git/kubani
   earthly --push ./agents/${AGENT_NAME}+push --VERSION=$TAG
   ```

6. **Report the result** including:
   - Agent name and image tag built
   - Version (from pyproject.toml)
   - Whether it was pushed
   - Any errors

## Examples

- `/build` - Build changed agents with auto-versioned tag
- `/build k8s-monitor` - Build k8s-monitor locally
- `/build news-monitor push` - Build and push news-monitor
- `/build all push` - Build and push all agents
- `/build k8s-monitor push 0.2.0-custom` - Build with custom version tag

## Agent Discovery

Available agents are auto-discovered from `agents/*/Earthfile` (excluding `core`):
- k8s-monitor
- news-monitor

New agents added to `agents/` directory are automatically supported.
