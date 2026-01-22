---
name: agent-evaluation
description: Run comprehensive agent evaluations using YAML-defined test suites with multiple evaluator types including automated, LLM-as-judge, and human review.
---

# Agent Evaluation Framework

The evaluation framework provides systematic testing and quality assessment for agents.

## Quick Start

```bash
# Run full evaluation suite
kubani-dev eval k8s-monitor

# Run specific evaluation suite
kubani-dev eval k8s-monitor --suite pod_remediation

# Run with specific evaluator type
kubani-dev eval k8s-monitor --evaluator llm_judge
```

## Evaluation Suites

Evaluation suites are defined in YAML files under `evaluations/`:

```
evaluations/
├── k8s/
│   ├── pod_remediation.yaml
│   ├── resource_scaling.yaml
│   └── incident_response.yaml
└── news/
    ├── digest_quality.yaml
    └── relevance_filtering.yaml
```

### Suite Format

```yaml
name: pod_remediation
description: Evaluate k8s-monitor pod remediation capabilities
version: "1.0"
agent: k8s-monitor

# Test cases
test_cases:
  - id: oom_kill_detection
    name: OOM Kill Detection
    description: Detect and respond to OOM killed pods
    input:
      event_type: pod_failure
      pod_name: api-server-xyz
      namespace: production
      reason: OOMKilled
      container_exit_code: 137
    expected:
      action_type: remediate
      contains_analysis: true
      mentions_memory: true
    evaluator: automated
    tags: [critical, memory]

  - id: remediation_quality
    name: Remediation Quality Assessment
    description: Assess quality of remediation recommendations
    input:
      scenario: crashloop_backoff
      context: "Pod repeatedly crashing with exit code 1"
    expected:
      provides_root_cause: true
      actionable_recommendations: true
    evaluator: llm_judge
    llm_criteria:
      - name: root_cause_accuracy
        weight: 0.4
        prompt: "Does the analysis correctly identify the root cause?"
      - name: recommendation_quality
        weight: 0.3
        prompt: "Are the recommendations actionable and appropriate?"
      - name: clarity
        weight: 0.3
        prompt: "Is the response clear and well-structured?"

# Metrics to track
metrics:
  - name: detection_accuracy
    type: percentage
    threshold: 0.95
  - name: response_time_p95
    type: duration
    threshold: 5s
  - name: false_positive_rate
    type: percentage
    threshold: 0.05
```

## Evaluator Types

### Automated

Fast, deterministic checks for expected outputs:

```yaml
evaluator: automated
expected:
  action_type: remediate
  contains: ["memory", "OOM"]
  not_contains: ["error", "failed"]
```

### LLM Judge

Use an LLM to assess response quality:

```yaml
evaluator: llm_judge
llm_criteria:
  - name: accuracy
    weight: 0.5
    prompt: "Is the technical analysis accurate?"
  - name: completeness
    weight: 0.3
    prompt: "Does the response address all aspects?"
  - name: actionability
    weight: 0.2
    prompt: "Are the recommendations actionable?"
```

### Threshold

Check numeric metrics against thresholds:

```yaml
evaluator: threshold
thresholds:
  response_time: "<5s"
  confidence_score: ">=0.8"
  token_count: "<2000"
```

### Human Review

Queue for human assessment:

```yaml
evaluator: human_review
review_criteria:
  - "Is the response appropriate for production?"
  - "Would you trust this recommendation?"
discord_channel: evaluations
```

## Commands

### Run Evaluations

```bash
# Full evaluation
kubani-dev eval <agent>

# Specific suite
kubani-dev eval <agent> --suite <suite_name>

# Specific evaluator type only
kubani-dev eval <agent> --evaluator automated
kubani-dev eval <agent> --evaluator llm_judge

# Output formats
kubani-dev eval <agent> --output json
kubani-dev eval <agent> --output markdown --save report.md
```

### View Results

```bash
# View latest results
kubani-dev eval-results <agent>

# Compare runs
kubani-dev eval-compare <agent> --runs 5

# Export to dashboard
kubani-dev eval-export <agent> --format prometheus
```

### Create Test Cases

```bash
# Generate test case from interaction
kubani-dev eval-capture <agent> --interaction-id abc123

# Validate suite
kubani-dev eval-validate evaluations/k8s/pod_remediation.yaml
```

## CI/CD Integration

Add to GitHub Actions:

```yaml
- name: Run Agent Evaluations
  run: |
    kubani-dev eval k8s-monitor --output json > eval-results.json
    
- name: Check Thresholds
  run: |
    kubani-dev eval-check k8s-monitor --fail-below 0.9
```

## Metrics Dashboard

View evaluation metrics in the UI:

```bash
# Start dashboard
kubani-dev dashboard

# Navigate to: http://localhost:8080/evaluations
```

Dashboard shows:
- Pass/fail rates over time
- Metric trends
- Test case details
- Comparison between versions

## Best Practices

1. **Start with automated tests** for basic functionality
2. **Add LLM judge tests** for quality assessment
3. **Use threshold tests** for performance metrics
4. **Reserve human review** for critical decisions
5. **Tag test cases** for filtering and reporting
6. **Version your suites** to track changes
7. **Run evaluations in CI** to catch regressions
