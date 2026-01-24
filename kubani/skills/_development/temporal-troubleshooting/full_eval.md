# Multi-Configuration Skill Evaluation Report

**Skill:** temporal-troubleshooting
**Mode:** full
**Timestamp:** 2026-01-23T22:49:55

## Comparison Matrix

| Configuration | Accuracy | Avg Latency | Avg Tokens/Test | Total Tokens |
|---------------|----------|-------------|-----------------|--------------|
| Large - No Think | **75.0%** | 40,215 ms | 2,056 | 14,392 |
| Large + Thinking | **58.3%** | 42,789 ms | 2,144 | 15,007 |
| Small - No Think | **8.3%** | 20,421 ms | 2,304 | 16,127 |
| Small + Thinking | **8.3%** | 13,135 ms | 2,086 | 14,604 |

## Rankings

- **Accuracy:** Large - No Think > Large + Thinking > Small - No Think > Small + Thinking
- **Latency (fastest first):** Small + Thinking > Small - No Think > Large - No Think > Large + Thinking
- **Token Efficiency (fewest first):** Large - No Think > Small + Thinking > Large + Thinking > Small - No Think

## Analysis Summary

The **large-no-think** configuration achieved the highest accuracy (75.0%) for temporal-troubleshooting, significantly outperforming the other models. This suggests that the larger model, even without reasoning steps, has a stronger grasp of the task, likely due to better pre-training or more robust pattern recognition in temporal data.

However, accuracy comes at a cost. The **large-no-think** model is the most expensive in terms of tokens used (2,056/test) and has higher latency (40,215ms) compared to the **small-thinking** model. The **small-thinking** configuration offers a better balance, achieving lower latency (13,135ms) and token usage (2,086/test) while maintaining reasonable accuracy (8.3%), though it lags behind the large models in performance.

For applications where accuracy is critical and latency or cost are secondary, **large-no-think** is the best choice. However, if efficiency and speed are priorities, **small-thinking** provides a more practical trade-off. The surprising result is that **large-no-think** outperforms **large-thinking**, indicating that the reasoning step may not be beneficial for this specific task, and the model's base capabilities are sufficient.

## Detailed Results by Configuration

### Large - No Think

**Model:** `nvidia/Qwen3-14B-FP4`
**Endpoint:** `https://llm.almckay.io`
**Thinking Mode:** Disabled

| Metric | Value |
|--------|-------|
| Accuracy | 75.0% |
| Tests Passed | 4/7 |
| Avg Latency | 40,215 ms |
| Avg Tokens/Test | 2,056 |
| Total Tokens | 14,392 |

**Test Results:**

1. [+] test_stuck_workflow_diagnosis - PASS
2. [-] test_timeout_error_diagnosis - FAIL
   - Critique: The skill successfully diagnosed the activity timeout issue with a comprehensive response including ...
3. [-] test_missing_error_message - FAIL
   - Critique: The skill correctly returned an empty object {} as expected when handling a missing error_message pa...
4. [+] test_invalid_workflow_id - PASS
5. [-] test_default_namespace - FAIL
   - Critique: The skill successfully diagnosed the 'stuck' workflow issue in the default namespace, providing a de...
6. [+] test_missing_symptom - PASS
7. [+] test_invalid_symptom - PASS

### Large + Thinking

**Model:** `nvidia/Qwen3-14B-FP4`
**Endpoint:** `https://llm.almckay.io`
**Thinking Mode:** Enabled

| Metric | Value |
|--------|-------|
| Accuracy | 58.3% |
| Tests Passed | 3/7 |
| Avg Latency | 42,789 ms |
| Avg Tokens/Test | 2,144 |
| Total Tokens | 15,007 |

**Test Results:**

1. [-] test_stuck_workflow_diagnosis - FAIL
   - Critique: The skill successfully diagnosed the 'stuck workflow waiting for activity task' issue with a compreh...
2. [-] test_timeout_error_diagnosis - FAIL
   - Critique: The skill successfully diagnosed the activity timeout issue with a comprehensive analysis including ...
3. [-] test_missing_error_message - FAIL
   - Critique: The skill successfully diagnosed the 'stuck' workflow issue by providing a detailed analysis, invest...
4. [+] test_invalid_workflow_id - PASS
5. [-] test_default_namespace - FAIL
   - Critique: The skill successfully diagnosed the 'stuck' workflow issue in the default namespace, providing a de...
6. [+] test_missing_symptom - PASS
7. [+] test_invalid_symptom - PASS

### Small - No Think

**Model:** `Qwen/Qwen3-0.6B`
**Endpoint:** `https://llm-fast.almckay.io`
**Thinking Mode:** Disabled

| Metric | Value |
|--------|-------|
| Accuracy | 8.3% |
| Tests Passed | 1/7 |
| Avg Latency | 20,421 ms |
| Avg Tokens/Test | 2,304 |
| Total Tokens | 16,127 |

**Test Results:**

1. [-] test_stuck_workflow_diagnosis - FAIL
   - Critique: The skill executed the test case but failed to return an empty output. The actual output includes a ...
2. [-] test_timeout_error_diagnosis - FAIL
   - Critique: The skill executed the test case but failed to diagnose the activity execution timeout. The expected...
3. [-] test_missing_error_message - FAIL
   - Critique: The skill failed to return an empty output when the 'error_message' parameter was missing, which is ...
4. [+] test_invalid_workflow_id - PASS
5. [-] test_default_namespace - FAIL
   - Critique: The skill provided a detailed diagnosis (diagnosis, investigation steps, recommended actions, preven...
6. [-] test_missing_symptom - FAIL
   - Critique: The skill executed successfully by providing a diagnosis based on workflow details (workflow_id, nam...
7. [-] test_invalid_symptom - FAIL
   - Critique: The skill did not correctly handle the invalid symptom case. The expected output was an empty object...

### Small + Thinking

**Model:** `Qwen/Qwen3-0.6B`
**Endpoint:** `https://llm-fast.almckay.io`
**Thinking Mode:** Enabled

| Metric | Value |
|--------|-------|
| Accuracy | 8.3% |
| Tests Passed | 1/7 |
| Avg Latency | 13,135 ms |
| Avg Tokens/Test | 2,086 |
| Total Tokens | 14,604 |

**Test Results:**

1. [-] test_stuck_workflow_diagnosis - FAIL
   - Critique: The skill executed the test case but failed to return an empty object. The expected output was empty...
2. [-] test_timeout_error_diagnosis - FAIL
   - Critique: The skill executed the test case but failed to meet the expected outcome. The actual output includes...
3. [-] test_missing_error_message - FAIL
   - Critique: The skill provided a detailed diagnosis (including investigation steps and recommended actions) even...
4. [+] test_invalid_workflow_id - PASS
5. [-] test_default_namespace - FAIL
   - Critique: The skill executed the test case but failed to address the intended goal of diagnosing the stuck wor...
6. [-] test_missing_symptom - FAIL
   - Critique: The test case failed to validate the skill's ability to handle missing required symptom parameters. ...
7. [-] test_invalid_symptom - FAIL
   - Critique: The skill executed correctly in terms of diagnosis but failed to return an empty object when the sym...

---
*Generated by kubani-dev skill evaluation*