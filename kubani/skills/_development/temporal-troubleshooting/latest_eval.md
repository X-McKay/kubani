# Skill Evaluation Report

**Skill:** temporal-troubleshooting  
**Timestamp:** 2026-01-23T22:46:46

## Summary

| Metric | Value |
|--------|-------|
| Accuracy | 66.7% |
| Tests Passed | 4/7 |
| Assertions Passed | 8/12 |
| Avg Latency | 28016 ms |
| Avg Tokens/Test | 2004 |
| Total Tokens | 14030 |

## Test Results

### 1. test_stuck_workflow_diagnosis - ✅ PASS

**Description:** Test diagnosis for a workflow stuck waiting for activity task

**Latency:** 28471 ms  
**Tokens:** 2079

**Assertions:**

- ✓ diagnosis equals Workflow stuck waiting for activity task. No active workers polling the task queue.
- ✓ investigation_steps contains Checked workflow history - last event: ActivityTaskScheduled
- ✓ recommended_actions contains Restart workers: kubectl rollout restart deployment/k8s-monitor -n ai-agents
- ✓ urgency equals high

### 2. test_timeout_error_diagnosis - ❌ FAIL

**Description:** Test diagnosis for activity execution timeout

**Latency:** 21454 ms  
**Tokens:** 1996

**Assertions:**

- ✓ diagnosis equals Activity exceeded its ScheduleToClose timeout (10s). Task is taking longer than configured timeout.
- ✗ investigation_steps contains Activity 'fetch_news_articles' ran for 15s but timeout was 10s
  - Expected: `Activity 'fetch_news_articles' ran for 15s but timeout was 10s`
  - Actual: `["Retrieved workflow history for 'news-digest-xyz789' to analyze failure pattern", "Identified activity 'fetch_news_articles' ran for 15s but timeout was 10s", 'Checked task queue status via list_workflows to verify worker availability', 'Examined activity timeout configuration in workflow definition', 'Reviewed worker resource constraints and task queue throughput']`
- ✗ urgency equals medium
  - Expected: `medium`
  - Actual: `high`

### 3. test_missing_error_message - ❌ FAIL

**Description:** Test handling of missing error_message parameter

**Latency:** 37190 ms  
**Tokens:** 2270

**Assertions:**

- ✗ error_message exists None
  - Expected: `None`
  - Actual: `None`

### 4. test_invalid_workflow_id - ✅ PASS

**Description:** Test handling of invalid workflow_id

**Latency:** 19598 ms  
**Tokens:** 1631

**Assertions:**

- ✓ diagnosis equals Workflow not found

### 5. test_default_namespace - ❌ FAIL

**Description:** Test handling of default namespace

**Latency:** 25713 ms  
**Tokens:** 1729

**Assertions:**

- ✗ namespace equals default
  - Expected: `default`
  - Actual: `None`

### 6. test_missing_symptom - ✅ PASS

**Description:** Test handling of missing required symptom parameter

**Latency:** 38150 ms  
**Tokens:** 2464

**Assertions:**

- ✓ diagnosis equals Missing required input: symptom

### 7. test_invalid_symptom - ✅ PASS

**Description:** Test handling of invalid symptom value

**Latency:** 25535 ms  
**Tokens:** 1861

**Assertions:**

- ✓ diagnosis equals Invalid symptom value: 'unknown'

