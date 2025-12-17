# Build k8s-monitor Agent

Build and optionally push the k8s-monitor agent Docker image.

## Arguments
- `$ARGUMENTS` - Optional: `push` to also push to registry, or a version tag

## Instructions

1. **Determine build parameters:**
   - If `$ARGUMENTS` contains `push`, push to registry
   - If `$ARGUMENTS` contains a version (e.g., `v0.1.0`, `main-abc123`), use that version
   - Otherwise, use `latest` and build locally only

2. **Get the current git SHA for versioning:**
   ```bash
   SHA_SHORT=$(git rev-parse --short HEAD)
   BRANCH=$(git rev-parse --abbrev-ref HEAD)
   VERSION="${BRANCH}-${SHA_SHORT}"
   ```

3. **Build the image:**
   ```bash
   cd /home/al/git/kubani
   earthly ./agents/k8s-monitor+docker --VERSION=$VERSION
   ```

4. **If pushing, push to registry:**
   ```bash
   cd /home/al/git/kubani
   earthly --push ./agents/k8s-monitor+push --VERSION=$VERSION
   ```

5. **Report the result** including:
   - Image tag built
   - Whether it was pushed
   - Build time
   - Any errors

## Examples

- `/build` - Build locally with auto-versioned tag
- `/build push` - Build and push with auto-versioned tag
- `/build v0.1.0` - Build with specific version tag
- `/build push v0.1.0` - Build and push with specific version
