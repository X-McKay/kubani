# Deploy k8s-monitor Agent

Deploy or rollback the k8s-monitor agent to a specific version.

## Arguments
- `$ARGUMENTS` - Optional: version tag to deploy (e.g., `main-abc1234`, `v0.1.0`, or `latest`)

## Instructions

1. **Determine the version to deploy:**
   - If `$ARGUMENTS` is provided, use that as the image tag
   - If empty, use `latest`

2. **Check current deployment status:**
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl get deploy k8s-monitor -n ai-agents -o jsonpath='{.spec.template.spec.containers[0].image}'
   ```

3. **Update the deployment:**
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl set image deployment/k8s-monitor \
     worker=registry.almckay.io/k8s-monitor:VERSION \
     start-scheduler=registry.almckay.io/k8s-monitor:VERSION \
     -n ai-agents
   ```
   Replace VERSION with the determined version.

4. **Wait for rollout to complete:**
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl rollout status deployment/k8s-monitor -n ai-agents --timeout=120s
   ```

5. **Verify deployment:**
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl get pods -n ai-agents -l app.kubernetes.io/name=k8s-monitor
   ```

6. **Report the result** including:
   - Previous version
   - New version deployed
   - Pod status
   - Any errors encountered

## Examples

- `/deploy` - Deploy latest version
- `/deploy main-abc1234` - Deploy specific commit
- `/deploy v0.1.0` - Deploy tagged release
- `/deploy latest` - Explicitly deploy latest

## Rollback

To rollback to a previous version:
1. Find available versions: `docker images registry.almckay.io/k8s-monitor --format '{{.Tag}}'`
2. Use this command with the previous version tag
