# timeout-error

Diagnose activity execution timeout

## Input

```json
{
  "workflow_id": "news-digest-xyz789",
  "namespace": "default",
  "symptom": "failed",
  "error_message": "activity execution timeout"
}
```

## Expected Output

```json
{
  "diagnosis": "Activity exceeded its ScheduleToClose timeout (10s). Task is taking longer than configured timeout.",
  "investigation_steps": [
    "Reviewed workflow history - ActivityTaskTimedOut event found",
    "Activity 'fetch_news_articles' ran for 15s but timeout was 10s",
    "Worker logs show external API latency spike"
  ],
  "recommended_actions": [
    "Increase activity timeout in workflow code: ScheduleToCloseTimeout=30s",
    "Add retry policy with exponential backoff",
    "Optimize external API calls or add caching",
    "Deploy updated workflow version"
  ],
  "prevention_tips": [
    "Set realistic timeouts based on p95 latency metrics",
    "Use heartbeats for long-running activities",
    "Implement circuit breakers for external dependencies"
  ],
  "urgency": "medium"
}
```

## Notes

- This example demonstrates a typical use case for this skill
- Use this as a reference for expected input/output format
- The output structure should match exactly for test validation
