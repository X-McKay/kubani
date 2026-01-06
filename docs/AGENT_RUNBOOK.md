# Agent Operations Runbook

This runbook covers common operational procedures for the Kubani AI agent system.

## Quick Reference

| Operation | Command/Action |
|-----------|----------------|
| Check agent status | `just agents` or skill: agents |
| View agent logs | `KUBECONFIG=/home/al/.kube/config kubectl logs -n ai-agents deployment/<agent> -f` |
| Restart agent | `KUBECONFIG=/home/al/.kube/config kubectl rollout restart deployment/<agent> -n ai-agents` |
| Check cluster health | `just cluster-status` or skill: cluster-status |
| Deploy new version | `just deploy <agent>` or push to main branch |
| Rollback deployment | `just rollback <agent>` or skill: rollback |

---

## Agent Status Checks

### Check All Agents

```bash
# Via Just command
just agents

# Or manually
KUBECONFIG=/home/al/.kube/config kubectl get deployments -n ai-agents \
  -l app.kubernetes.io/component=ai-agent \
  -o custom-columns=NAME:.metadata.name,READY:.status.readyReplicas,IMAGE:.spec.template.spec.containers[0].image
```

### Check Specific Agent Health

```bash
# k8s-monitor
KUBECONFIG=/home/al/.kube/config kubectl get pods -n ai-agents -l app.kubernetes.io/name=k8s-monitor

# news-monitor
KUBECONFIG=/home/al/.kube/config kubectl get pods -n ai-agents -l app.kubernetes.io/name=news-monitor
```

### View Agent Logs

```bash
# Follow logs in real-time
KUBECONFIG=/home/al/.kube/config kubectl logs -n ai-agents deployment/k8s-monitor -f --tail=100

# View previous container logs (after crash)
KUBECONFIG=/home/al/.kube/config kubectl logs -n ai-agents deployment/k8s-monitor --previous

# Filter for errors
KUBECONFIG=/home/al/.kube/config kubectl logs -n ai-agents deployment/k8s-monitor --tail=500 | grep -i error
```

---

## Common Issues and Resolutions

### Agent Pod in CrashLoopBackOff

**Symptoms:** Pod repeatedly crashes and restarts

**Diagnosis:**
```bash
# Check events
KUBECONFIG=/home/al/.kube/config kubectl get events -n ai-agents --field-selector involvedObject.name=k8s-monitor-xxx --sort-by='.lastTimestamp'

# Check logs from crashed container
KUBECONFIG=/home/al/.kube/config kubectl logs -n ai-agents <pod-name> --previous
```

**Common Causes:**
1. **Missing secrets** - Check required secrets exist:
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl get secrets -n ai-agents
   ```

2. **vLLM not ready** - Agent can't connect to LLM service:
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl get pods -n vllm
   ```

3. **Redis not available** - Event bus connection fails:
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl get pods -n redis
   ```

4. **Qdrant not available** - Skill library connection fails:
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl get pods -n qdrant
   ```

**Resolution:**
```bash
# Restart after fixing underlying issue
KUBECONFIG=/home/al/.kube/config kubectl rollout restart deployment/k8s-monitor -n ai-agents

# Wait for rollout
KUBECONFIG=/home/al/.kube/config kubectl rollout status deployment/k8s-monitor -n ai-agents
```

### Agent Not Processing Events

**Symptoms:** Agent running but no activity in logs

**Diagnosis:**
```bash
# Check Redis event bus
KUBECONFIG=/home/al/.kube/config kubectl exec -n redis deployment/redis -- redis-cli XINFO GROUPS kubani:events

# Check if consumer is registered
KUBECONFIG=/home/al/.kube/config kubectl exec -n redis deployment/redis -- redis-cli XINFO CONSUMERS kubani:events <consumer-group>
```

**Resolution:**
1. Verify agent is subscribed to correct event types
2. Check if upstream events are being published
3. Restart agent to re-register consumer

### Skill Execution Failures

**Symptoms:** Skills not executing or failing repeatedly

**Diagnosis:**
```bash
# Check skill confidence levels (via Grafana or metrics)
curl -s http://k8s-monitor.ai-agents.svc.cluster.local:8080/metrics | grep skill_confidence

# Check MCP server availability
KUBECONFIG=/home/al/.kube/config kubectl get pods -n ai-agents -l app.kubernetes.io/component=mcp-server
```

**Resolution:**
1. Verify MCP server is running
2. Check skill preconditions match the issue
3. Review skill success criteria

### Memory/Qdrant Connection Issues

**Symptoms:** "Failed to connect to Qdrant" or skill search errors

**Diagnosis:**
```bash
# Check Qdrant status
KUBECONFIG=/home/al/.kube/config kubectl get pods -n qdrant

# Test connectivity from agent
KUBECONFIG=/home/al/.kube/config kubectl exec -n ai-agents deployment/k8s-monitor -- \
  curl -s http://qdrant.qdrant.svc.cluster.local:6333/health
```

**Resolution:**
```bash
# Restart Qdrant if needed
KUBECONFIG=/home/al/.kube/config kubectl rollout restart deployment/qdrant -n qdrant

# Then restart agents to reconnect
KUBECONFIG=/home/al/.kube/config kubectl rollout restart deployment/k8s-monitor -n ai-agents
```

---

## Deployment Operations

### Deploy New Agent Version

**Via GitOps (Recommended):**
```bash
# 1. Bump version
just bump-version k8s-monitor patch  # or minor, major

# 2. Build and push
just build k8s-monitor
just push k8s-monitor <version>

# 3. Update GitOps manifest
# Edit gitops/apps/ai-agents/k8s-monitor/deployment.yaml with new image tag

# 4. Commit and push
git add -A && git commit -m "chore(gitops): deploy k8s-monitor:0.2.15"
git push

# 5. Flux auto-syncs (or force sync)
KUBECONFIG=/home/al/.kube/config flux reconcile kustomization apps -n flux-system
```

**Immediate Deploy (Bypasses GitOps):**
```bash
# Direct kubectl update (will be overwritten on next Flux sync)
KUBECONFIG=/home/al/.kube/config kubectl set image deployment/k8s-monitor \
  --all -n ai-agents "*=registry.almckay.io/k8s-monitor:0.2.15-abc1234"
```

### Rollback Deployment

**Via GitOps (Recommended):**
```bash
# 1. Find previous version
git log --oneline -5 gitops/apps/ai-agents/k8s-monitor/deployment.yaml

# 2. Restore previous manifest
git checkout abc1234 -- gitops/apps/ai-agents/k8s-monitor/deployment.yaml

# 3. Commit and push
git commit -m "chore(gitops): rollback k8s-monitor to 0.2.14"
git push
```

**Immediate Rollback:**
```bash
# Rollback to previous revision
KUBECONFIG=/home/al/.kube/config kubectl rollout undo deployment/k8s-monitor -n ai-agents

# Or to specific revision
KUBECONFIG=/home/al/.kube/config kubectl rollout undo deployment/k8s-monitor -n ai-agents --to-revision=3
```

### Scale Agents

```bash
# Scale up for high load
KUBECONFIG=/home/al/.kube/config kubectl scale deployment/k8s-monitor -n ai-agents --replicas=2

# Scale down
KUBECONFIG=/home/al/.kube/config kubectl scale deployment/k8s-monitor -n ai-agents --replicas=1
```

---

## Skill Management

### List All Skills

```bash
# Query Qdrant for skills
curl -s http://qdrant.qdrant.svc.cluster.local:6333/collections/skills/points/scroll | jq '.result.points[].payload.name'
```

### Check Skill Confidence

```bash
# Via Prometheus metrics
curl -s http://k8s-monitor.ai-agents.svc.cluster.local:8080/metrics | grep skill_confidence
```

### Reset Skill Confidence

If a skill has been incorrectly penalized:

```python
# Connect to Qdrant and update
from qdrant_client import QdrantClient

client = QdrantClient(host="qdrant.qdrant.svc.cluster.local", port=6333)
client.set_payload(
    collection_name="skills",
    payload={"confidence": 0.5, "success_count": 0, "failure_count": 0},
    points=["skill-id-here"],
)
```

### Add New Skill Manually

See [federated_architecture.md](federated_architecture.md#adding-new-skills) for the skill schema.

---

## Event Bus Operations

### Check Event Bus Status

```bash
# List all streams
KUBECONFIG=/home/al/.kube/config kubectl exec -n redis deployment/redis -- redis-cli KEYS "kubani:*"

# Check stream length
KUBECONFIG=/home/al/.kube/config kubectl exec -n redis deployment/redis -- redis-cli XLEN kubani:events

# List consumer groups
KUBECONFIG=/home/al/.kube/config kubectl exec -n redis deployment/redis -- redis-cli XINFO GROUPS kubani:events
```

### Clear Stuck Events

```bash
# Acknowledge pending events (use with caution)
KUBECONFIG=/home/al/.kube/config kubectl exec -n redis deployment/redis -- \
  redis-cli XPENDING kubani:events <consumer-group> - + 10

# Delete old events
KUBECONFIG=/home/al/.kube/config kubectl exec -n redis deployment/redis -- \
  redis-cli XTRIM kubani:events MAXLEN ~ 10000
```

### Monitor Event Flow

```bash
# Watch events in real-time
KUBECONFIG=/home/al/.kube/config kubectl exec -n redis deployment/redis -- \
  redis-cli XREAD BLOCK 0 STREAMS kubani:events $
```

---

## Approval System Operations

### Check Pending Approvals

Pending approvals appear in Discord. Check the configured webhook channel.

### Approve via Discord

React to the approval message with:
- ✅ to approve
- ❌ to reject

### Manual Approval Bypass

In emergencies, you can manually trigger actions that normally require approval:

```bash
# Connect to agent pod and run action directly
KUBECONFIG=/home/al/.kube/config kubectl exec -it -n ai-agents deployment/k8s-monitor -- python -c "
from k8s_monitor.federated.healer import HealerAgent
# ... execute action directly
"
```

---

## Metrics and Dashboards

### Access Grafana Dashboards

Navigate to: `https://grafana.almckay.io`

Key dashboards:
- **Agent Overview** - Overall agent health and activity
- **Skill Performance** - Skill execution stats and confidence
- **Remediation Activity** - Issues detected and resolved

### Key Metrics to Monitor

| Metric | Good | Warning | Critical |
|--------|------|---------|----------|
| Agent uptime | 100% | < 99% | < 95% |
| Skill success rate | > 80% | 60-80% | < 60% |
| Event processing latency | < 5s | 5-30s | > 30s |
| Approval response time | < 5m | 5-15m | > 15m |

### Alert Rules

Alerts are configured in Prometheus. Check:
```bash
KUBECONFIG=/home/al/.kube/config kubectl get prometheusrules -n monitoring
```

---

## Maintenance Procedures

### Scheduled Maintenance

1. **Notify** - Post maintenance window in Discord
2. **Scale down** - `kubectl scale deployment/<agent> --replicas=0`
3. **Perform maintenance**
4. **Scale up** - `kubectl scale deployment/<agent> --replicas=1`
5. **Verify** - Check logs and metrics

### Database Maintenance (Qdrant)

```bash
# Create backup
KUBECONFIG=/home/al/.kube/config kubectl exec -n qdrant deployment/qdrant -- \
  qdrant-backup create /backups/skills-$(date +%Y%m%d).snapshot

# Compact collection
curl -X POST "http://qdrant.qdrant.svc.cluster.local:6333/collections/skills/index"
```

### Log Rotation

Logs are handled by Kubernetes. Old logs are automatically rotated based on container runtime settings.

---

## Emergency Procedures

### Agent Causing Cluster Issues

```bash
# Immediately stop the agent
KUBECONFIG=/home/al/.kube/config kubectl scale deployment/k8s-monitor -n ai-agents --replicas=0

# Investigate logs
KUBECONFIG=/home/al/.kube/config kubectl logs -n ai-agents deployment/k8s-monitor --previous

# Fix and redeploy
```

### Event Storm

If agents are flooding the event bus:

```bash
# Stop all agents
KUBECONFIG=/home/al/.kube/config kubectl scale deployment -n ai-agents --all --replicas=0

# Clear event backlog
KUBECONFIG=/home/al/.kube/config kubectl exec -n redis deployment/redis -- redis-cli XTRIM kubani:events MAXLEN 0

# Restart agents one by one
KUBECONFIG=/home/al/.kube/config kubectl scale deployment/k8s-monitor -n ai-agents --replicas=1
# Wait and verify
KUBECONFIG=/home/al/.kube/config kubectl scale deployment/news-monitor -n ai-agents --replicas=1
```

### Skill Library Corruption

```bash
# Delete and recreate collection
curl -X DELETE "http://qdrant.qdrant.svc.cluster.local:6333/collections/skills"

# Restart agents to re-bootstrap skills
KUBECONFIG=/home/al/.kube/config kubectl rollout restart deployment/k8s-monitor -n ai-agents
```

---

## Contact and Escalation

| Level | Contact | When |
|-------|---------|------|
| L1 | Discord #alerts channel | Automated alerts |
| L2 | On-call engineer | Agent unresponsive > 15 min |
| L3 | Platform team | Data loss or security issue |
