---
name: deploy
description: Deploy AI agents to Kubernetes cluster. Use when deploying, updating, or checking agent versions. Handles GitOps workflow with Flux CD or immediate kubectl deploys.
---

# Deploy Agent

Deploy or update an AI agent to a specific version via GitOps (recommended) or kubectl (immediate).

## Arguments

- `agent-name`: k8s-monitor, news-monitor (required)
- `version`: Image tag to deploy (optional, shows current if omitted)
- `--immediate`: Use kubectl instead of GitOps (bypasses Flux)

## Instructions

### Show Current Version

```bash
cd /home/al/git/kubani
grep "image: registry.almckay.io/${AGENT_NAME}:" gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml | head -1
```

### GitOps Deploy (Default - Recommended)

1. **Update the GitOps manifest:**
   ```bash
   cd /home/al/git/kubani
   sed -i "s|registry.almckay.io/${AGENT_NAME}:[^ ]*|registry.almckay.io/${AGENT_NAME}:${VERSION}|g" \
     gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml
   ```

2. **Commit and push:**
   ```bash
   git add gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml
   git commit -m "chore(gitops): deploy ${AGENT_NAME}:${VERSION}"
   git push
   ```

3. **Monitor the rollout:**
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

```bash
# Check git history for previous tags
git log --oneline -10 gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml

# List recent image tags from registry
docker images | grep ${AGENT_NAME}
```

## Version Format

- `0.1.0-abc1234` - Standard format: pyproject.toml version + git SHA
- `latest` - Most recent build (not recommended for production)
- `0.1.0` - Semantic version from tagged release

## Programmatic Deployment (Python API)

For automated deployments, use the GitOpsManager from core-agents:

```python
from core_agents.integrations.gitops import GitOpsManager, GitOpsConfig

config = GitOpsConfig(repo_path="/home/al/git/kubani")
manager = GitOpsManager(config)

# Deploy with automatic rollback on failure
result = await manager.deploy(
    agent_name="k8s-monitor",
    new_tag="0.3.0-abc1234",
    auto_rollback=True,
)

if result.success:
    print(f"Deployed {result.agent_name}:{result.image_tag}")
else:
    print(f"Failed: {result.error}")
```

Or use the quick_deploy helper:

```python
from core_agents.integrations.gitops import quick_deploy

result = await quick_deploy("k8s-monitor", "0.3.0", repo_path="/home/al/git/kubani")
```
