# List Agents

Show all available agents, their versions, and deployment status.

## Arguments
- `$ARGUMENTS` - Optional: specific agent name for detailed info

## Instructions

1. **Discover all agents:**
   ```bash
   cd /home/al/git/kubani
   for earthfile in agents/*/Earthfile; do
       agent_dir=$(dirname "$earthfile")
       agent_name=$(basename "$agent_dir")
       [ "$agent_name" = "core" ] && continue

       # Get version from pyproject.toml
       version=$(grep '^version = ' "$agent_dir/pyproject.toml" | sed 's/version = "\(.*\)"/\1/')

       echo "$agent_name: v$version"
   done
   ```

2. **Get deployed versions:**
   ```bash
   for agent in k8s-monitor news-monitor; do
       deployed=$(KUBECONFIG=/home/al/.kube/config kubectl get deploy $agent -n ai-agents -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo "not deployed")
       echo "$agent: $deployed"
   done
   ```

3. **Get pod status:**
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl get pods -n ai-agents -l app.kubernetes.io/component=ai-agent
   ```

4. **If specific agent requested, show detailed info:**
   - Current manifest version
   - Deployed version
   - Pod status and logs (last 10 lines)
   - Recent deployment history

## Output Format

```
=== Agents ===

k8s-monitor
  Source version: 0.1.0
  Deployed image: registry.almckay.io/k8s-monitor:0.1.0-abc1234
  Pod status: Running (1/1)

news-monitor
  Source version: 0.1.0
  Deployed image: registry.almckay.io/news-monitor:0.1.0-abc1234
  Pod status: Running (1/1)

core-agents (library)
  Source version: 0.1.0
  Published: registry.almckay.io/python/core-agents:latest
```

## Examples

- `/agents` - List all agents with versions and status
- `/agents k8s-monitor` - Detailed info for k8s-monitor
