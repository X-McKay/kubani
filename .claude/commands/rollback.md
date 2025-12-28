# Rollback Agent

Quickly rollback an agent to a previous version.

## Arguments
- `$ARGUMENTS` - Format: `<agent-name> [version|commits-back]`
  - `agent-name`: k8s-monitor, news-monitor (required)
  - `version`: Specific version tag to rollback to
  - `commits-back`: Number like `1` or `2` to go back that many deployments

## Instructions

### Option 1: Rollback to specific version

1. **Update the manifest:**
   ```bash
   cd /home/al/git/kubani
   sed -i "s|registry.almckay.io/${AGENT_NAME}:[^ ]*|registry.almckay.io/${AGENT_NAME}:${VERSION}|g" \
     gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml
   ```

2. **Commit and push:**
   ```bash
   git add gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml
   git commit -m "chore(gitops): rollback ${AGENT_NAME} to ${VERSION}"
   git push
   ```

### Option 2: Rollback N commits back

1. **Find the previous version:**
   ```bash
   git log --oneline -${N} gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml
   COMMIT_SHA=$(git log --format='%H' -${N} gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml | tail -1)
   ```

2. **Restore that file version:**
   ```bash
   git checkout ${COMMIT_SHA} -- gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml
   ```

3. **Commit and push:**
   ```bash
   git add gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml
   git commit -m "chore(gitops): rollback ${AGENT_NAME} to ${COMMIT_SHA}"
   git push
   ```

### Emergency Rollback (immediate)

For immediate rollback without waiting for Flux:

```bash
KUBECONFIG=/home/al/.kube/config kubectl rollout undo deployment/${AGENT_NAME} -n ai-agents
```

**Warning:** This will be overwritten when Flux next syncs.

## Finding Previous Versions

```bash
# Show deployment history in git
git log --oneline -10 gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml

# Show what image tag was in each commit
git log --oneline -10 gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml | while read sha msg; do
    tag=$(git show $sha:gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml | grep "image: registry" | head -1 | sed 's/.*://')
    echo "$sha: $tag"
done
```

## Examples

- `/rollback k8s-monitor 0.1.0-abc1234` - Rollback to specific version
- `/rollback k8s-monitor 1` - Rollback to previous deployment
- `/rollback news-monitor 2` - Rollback 2 deployments back

## Post-Rollback

After rollback, verify:
```bash
KUBECONFIG=/home/al/.kube/config kubectl get pods -n ai-agents -l app.kubernetes.io/name=${AGENT_NAME}
KUBECONFIG=/home/al/.kube/config kubectl logs -n ai-agents -l app.kubernetes.io/name=${AGENT_NAME} --tail=20
```
