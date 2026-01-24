# stuck-workflow

Diagnose a workflow stuck waiting for activity task

## Input

```json
{
  "workflow_id": "k8s-remediation-abc123",
  "namespace": "default",
  "symptom": "stuck",
  "error_message": "activity task not responding"
}
```

## Expected Output

```json
{
  "diagnosis": "Workflow stuck waiting for activity task. No active workers polling the task queue.",
  "investigation_steps": [
    "Checked workflow history - last event: ActivityTaskScheduled",
    "Verified task queue has 0 active pollers",
    "No worker heartbeats in last 5 minutes"
  ],
  "recommended_actions": [
    "Check worker pods: kubectl get pods -n ai-agents -l app=k8s-monitor",
    "Check worker logs: kubectl logs -n ai-agents <pod-name> --tail=100",
    "Restart workers: kubectl rollout restart deployment/k8s-monitor -n ai-agents"
  ],
  "prevention_tips": [
    "Add worker liveness probes",
    "Configure activity heartbeat timeouts",
    "Set up alerts for worker failures"
  ],
  "urgency": "high"
}
```

## Notes

- This example demonstrates a typical use case for this skill
- Use this as a reference for expected input/output format
- The output structure should match exactly for test validation
