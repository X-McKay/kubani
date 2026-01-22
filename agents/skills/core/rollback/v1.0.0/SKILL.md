---
name: rollback
description: Rollback AI agent to a previous version. Use when reverting a deployment, undoing changes, or recovering from failed deploys.
---

# Rollback Agent

Quickly rollback an agent to a previous version.

## Arguments

- `agent-name`: k8s-monitor, news-monitor (required)
- `version`: Specific version tag to rollback to
- `commits-back`: Number like `1` or `2` to go back that many deployments

## Instructions

### Option 1: Rollback to Specific Version

```bash
cd /home/al/git/kubani
AGENT_NAME="k8s-monitor"
VERSION="0.1.0-abc1234"

sed -i "s|registry.almckay.io/${AGENT_NAME}:[^ ]*|registry.almckay.io/${AGENT_NAME}:${VERSION}|g" \
  gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml

git add gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml
git commit -m "chore(gitops): rollback ${AGENT_NAME} to ${VERSION}"
git push
```

### Option 2: Rollback N Commits Back

```bash
cd /home/al/git/kubani
AGENT_NAME="k8s-monitor"
N=1

COMMIT_SHA=$(git log --format='%H' -${N} gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml | tail -1)
git checkout ${COMMIT_SHA} -- gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml

git add gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml
git commit -m "chore(gitops): rollback ${AGENT_NAME} to ${COMMIT_SHA}"
git push
```

### Emergency Rollback (Immediate)

For immediate rollback without waiting for Flux:

```bash
KUBECONFIG=/home/al/.kube/config kubectl rollout undo deployment/${AGENT_NAME} -n ai-agents
```

**Warning:** This will be overwritten when Flux next syncs.

## Finding Previous Versions

```bash
AGENT_NAME="k8s-monitor"

# Show deployment history in git
git log --oneline -10 gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml

# Show what image tag was in each commit
git log --oneline -10 gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml | while read sha msg; do
    tag=$(git show $sha:gitops/apps/ai-agents/${AGENT_NAME}/deployment.yaml | grep "image: registry" | head -1 | sed 's/.*://')
    echo "$sha: $tag"
done
```

## Post-Rollback Verification

```bash
KUBECONFIG=/home/al/.kube/config kubectl get pods -n ai-agents -l app.kubernetes.io/name=${AGENT_NAME}
KUBECONFIG=/home/al/.kube/config kubectl logs -n ai-agents -l app.kubernetes.io/name=${AGENT_NAME} --tail=20
```
