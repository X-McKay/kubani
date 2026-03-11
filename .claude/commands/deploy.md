# Deploy Agent

> **Prefer `kubani ship <component>`** — it handles the full pipeline (version bump, test, build, push, manifest patch, commit, push, verify). Use `/deploy` only for rollbacks or deploying a specific pre-built version.

Deploy or rollback an agent to a specific version via GitOps (recommended) or kubectl (immediate).

## Arguments
- `$ARGUMENTS` - Format: `[agent-name] [version] [--immediate]`
  - `agent-name`: k8s-monitor, news-monitor (required)
  - `version`: Image tag to deploy (default: latest from manifest)
  - `--immediate`: Use kubectl instead of GitOps (bypasses Flux)

## Instructions

### GitOps Deploy (Default - Recommended)

1. **Parse arguments** to get agent name and version.

2. **Get the current version from manifest:**
   ```bash
   grep "image: registry.almckay.io/${AGENT_NAME}:" gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml | head -1
   ```

3. **Update the GitOps manifest:**
   ```bash
   cd /home/al/git/kubani
   sed -i "s|registry.almckay.io/${AGENT_NAME}:[^ ]*|registry.almckay.io/${AGENT_NAME}:${VERSION}|g" \
     gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml
   ```

4. **Commit and push:**
   ```bash
   git add gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml
   git commit -m "chore(gitops): deploy ${AGENT_NAME}:${VERSION}"
   git push
   ```

5. **Flux will auto-sync** the change to the cluster.

6. **Monitor the rollout:**
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl rollout status deployment/${AGENT_NAME} -n ai-agents --timeout=120s
   ```

### Immediate Deploy (--immediate flag)

Use kubectl directly for faster deployment (bypasses GitOps):

```bash
KUBECONFIG=/home/al/.kube/config kubectl set image deployment/${AGENT_NAME} \
  --all \
  -n ai-agents \
  "*=registry.almckay.io/${AGENT_NAME}:${VERSION}"
```

**Note:** Immediate deploys will be overwritten when Flux next syncs.

## Finding Available Versions

1. **Check git history for previous tags:**
   ```bash
   git log --oneline gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml
   ```

2. **List recent image tags from registry** (if crane installed):
   ```bash
   crane ls registry.almckay.io/${AGENT_NAME}
   ```

## Examples

- `/deploy k8s-monitor` - Show current version
- `/deploy k8s-monitor 0.1.0-abc1234` - Deploy specific version via GitOps
- `/deploy news-monitor 0.1.0-def5678 --immediate` - Deploy immediately via kubectl
- `/deploy k8s-monitor latest` - Deploy latest tag

## Rollback

To rollback to a previous version:

1. **Find the previous version:**
   ```bash
   git log --oneline -10 gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml
   ```

2. **Deploy that version:**
   `/deploy ${AGENT_NAME} ${PREVIOUS_VERSION}`

Or revert the git commit:
```bash
git checkout ${COMMIT_SHA} -- gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml
git commit -m "chore(gitops): rollback ${AGENT_NAME} to ${PREVIOUS_VERSION}"
git push
```

## Version Format

- `0.1.0-abc1234` - Standard format: pyproject.toml version + git SHA
- `latest` - Most recent build (not recommended for production)
- `0.1.0` - Semantic version from tagged release
