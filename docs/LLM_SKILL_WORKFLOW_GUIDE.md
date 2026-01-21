# LLM-Integrated Skill Development Workflow Guide

**Version:** 1.0  
**Date:** 2026-01-20  
**Status:** Production Ready

## Overview

This guide documents the complete LLM-integrated skill development workflow for Kubani. This system enables AI agents to create, evaluate, and improve skills using Large Language Models at every step.

## Architecture

### Core Principle

**Skills are natural language Standard Operating Procedures (SOPs), not just code.**

When an agent needs to perform a task, it reads the SKILL.md file and follows the instructions using an LLM. This makes skills:
- **Flexible:** Can adapt to different contexts
- **Maintainable:** Easy to understand and modify
- **Agentic:** Leverage LLM reasoning capabilities
- **Evaluable:** Can be tested systematically

### Components

1. **LLMClient** (`llm_client.py`)
   - Unified interface for Ollama and OpenAI-compatible APIs
   - Handles chat completions, token counting, latency tracking
   - Supports skill generation and execution

2. **SkillDrafter** (`skill_drafter.py`)
   - Conversational skill creation
   - Asks clarifying questions
   - Generates SKILL.md, test_cases.yaml, metadata.json

3. **SkillEvaluatorLLM** (`skill_evaluator_llm.py`)
   - Executes skills by having LLM follow SKILL.md
   - Runs test cases and validates assertions
   - Collects metrics (accuracy, latency, tokens)

4. **SkillImprover** (`skill_improver.py`)
   - Analyzes evaluation results
   - Suggests improvements
   - Generates improved SKILL.md

5. **CLI Commands** (`skill_llm.py`)
   - `draft`: Create new skills
   - `eval`: Evaluate skills
   - `improve`: Improve skills
   - `list`: List all skills
   - `info`: Show skill details

## Usage

### Prerequisites

1. **Install Ollama** (for local testing):
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull qwen2.5:3b
   ```

2. **Install kubani-dev**:
   ```bash
   cd /path/to/kubani
   sudo pip3 install -e tools/kubani-dev/
   ```

### Configuration

Set environment variables (optional):
```bash
export LLM_BASE_URL="http://localhost:11434"  # Ollama default
export LLM_MODEL="qwen2.5:3b"
```

Or use CLI options:
```bash
--llm-url http://your-cluster-llm:8000
--llm-model your-model-name
```

### Workflow

#### 1. Draft a Skill

**Interactive Mode** (recommended for complex skills):
```bash
kubani-dev skill-llm draft "Find unused Kubernetes ConfigMaps"
```

The LLM will ask clarifying questions:
```
🤖 Assistant: I'll help you create this skill. Let me ask a few questions:

1. What should the input parameters be?
   - Namespace name (required or optional)?
   - Should we check all namespaces or just one?

2. What should the output format be?
   - List of ConfigMap names?
   - Include additional metadata?

You: Input: namespace (required), Output: JSON list with name and age
```

**Non-Interactive Mode** (for simple skills):
```bash
kubani-dev skill-llm draft "Calculate sum of two numbers" --non-interactive
```

**Result:**
```
✅ Skill created at: skills/development/your-skill/
   - SKILL.md           (LLM-generated SOP)
   - test_cases.yaml    (LLM-generated tests)
   - metadata.json      (Skill metadata)
```

#### 2. Evaluate the Skill

```bash
kubani-dev skill-llm eval skills/development/your-skill --verbose
```

**What happens:**
1. Loads SKILL.md and test_cases.yaml
2. For each test case:
   - Sends SKILL.md as system prompt to LLM
   - Sends test inputs as user prompt
   - LLM follows instructions and returns output
   - Validates output against assertions
3. Collects metrics and generates reports

**Output:**
```
🧪 Evaluating skill: your-skill
🤖 Using LLM: qwen2.5:3b @ http://localhost:11434

[1/5] Running: test_happy_path
  ✓ result equals expected_value
[2/5] Running: test_edge_case
  ✓ result exists
...

============================================================
📊 EVALUATION RESULTS
============================================================
Accuracy:           80.0%
Tests Passed:       4/5
Assertions Passed:  8/10
Avg Latency:        5234 ms
Avg Tokens/Test:    456
Total Tokens:       2280
============================================================

💾 Results saved:
   - skills/development/your-skill/latest_eval.json
   - skills/development/your-skill/latest_eval.md
```

#### 3. Improve the Skill

If accuracy is less than 100%:
```bash
kubani-dev skill-llm improve skills/development/your-skill --goals accuracy
```

**What happens:**
1. Analyzes evaluation results using LLM
2. Identifies root causes of failures
3. Generates improved SKILL.md
4. Creates backup of original
5. Optionally re-evaluates

**Output:**
```
🔧 Improving skill: your-skill
🎯 Goals: accuracy

📊 Analysis: The skill fails on edge cases because...

💡 Improvement Suggestions:
1. [HIGH] Add explicit handling for null inputs
   → Impact: Should fix 2 failing tests
2. [MEDIUM] Clarify output format in step 3
   → Impact: Should improve consistency

Apply improvements? [Y/n]: y

✅ Skill improved and saved (backup created)
   Tokens used: 1234

🔄 Re-evaluating improved skill...
```

#### 4. List and Inspect Skills

```bash
# List all skills
kubani-dev skill-llm list

# List by category
kubani-dev skill-llm list --category development

# Show detailed info
kubani-dev skill-llm info skills/development/your-skill
```

### Skill File Structure

```
skills/
├── development/          # Work-in-progress skills
│   └── my-skill/
│       ├── SKILL.md              # Natural language SOP
│       ├── test_cases.yaml       # Test cases
│       ├── metadata.json         # Metadata
│       ├── latest_eval.json      # Latest evaluation results
│       └── latest_eval.md        # Human-readable report
├── core/                 # General-purpose skills
│   └── post-to-discord/
│       └── v1.0.0/
│           └── SKILL.md
└── agents/               # Agent-specific skills
    └── k8s-monitor/
        └── find-oom-pods/
            └── v1.0.0/
                └── SKILL.md
```

### SKILL.md Format

```markdown
# Skill: Find Unused ConfigMaps

## Description
Identifies Kubernetes ConfigMaps that are not referenced by any resources.

## Input Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| namespace | string | Yes | Kubernetes namespace to check |
| age_days | integer | No | Only check ConfigMaps older than this |

## Output Format

Returns JSON array:
```json
[
  {
    "name": "configmap-name",
    "age_days": 45,
    "size_bytes": 1024,
    "reason": "Not referenced by any Pod or Deployment"
  }
]
```

## Execution Steps

1. **List all ConfigMaps** in the specified namespace
2. **List all Pods, Deployments, StatefulSets, and DaemonSets**
3. **Check references** for each ConfigMap:
   - Check if mounted as volume
   - Check if referenced in envFrom
4. **Filter by age** if age_days parameter is provided
5. **Return results** as JSON array

## Error Handling

- If namespace doesn't exist, return error: "Namespace not found"
- If no access to namespace, return error: "Permission denied"
- If API is unavailable, return error: "Kubernetes API unavailable"

## Example Usage

Input:
```json
{
  "namespace": "production",
  "age_days": 30
}
```

Output:
```json
[
  {
    "name": "old-config",
    "age_days": 45,
    "size_bytes": 2048,
    "reason": "Not referenced by any resource"
  }
]
```
```

### Test Cases Format

```yaml
test_cases:
  - name: test_happy_path
    description: Test with namespace containing unused ConfigMaps
    inputs:
      namespace: "test-ns"
      age_days: 30
    expected_outputs:
      result:
        - name: "unused-config"
          age_days: 45
    assertions:
      - field: result
        type: exists
        description: Result should exist
      - field: result[0].name
        type: equals
        value: "unused-config"
        description: Should find the unused ConfigMap

  - name: test_empty_namespace
    description: Test with namespace containing no ConfigMaps
    inputs:
      namespace: "empty-ns"
    expected_outputs:
      result: []
    assertions:
      - field: result
        type: equals
        value: []
        description: Should return empty array

  - name: test_invalid_namespace
    description: Test with non-existent namespace
    inputs:
      namespace: "nonexistent"
    expected_outputs:
      error: "Namespace not found"
    assertions:
      - type: expect_error
        description: Should return an error
```

### Assertion Types

| Type | Description | Example |
|------|-------------|---------|
| `equals` | Exact match | `value: 42` |
| `contains` | String/array contains | `value: "error"` |
| `exists` | Field exists in output | No value needed |
| `not_empty` | Field is not empty | No value needed |
| `type` | Check type | `value: "string"` |
| `length` | Check length | `value: 5` |
| `greater_than` | Numeric comparison | `value: 100` |
| `less_than` | Numeric comparison | `value: 1000` |
| `expect_error` | Expect an error | No value needed |

## Best Practices

### Skill Design

1. **Clear Instructions:** Write step-by-step instructions that an LLM can follow
2. **Explicit Output Format:** Specify exact JSON structure expected
3. **Error Handling:** List all possible errors and how to handle them
4. **Examples:** Include concrete examples of inputs and outputs

### Test Cases

1. **Coverage:** Include happy path, edge cases, and error cases
2. **Assertions:** Use multiple assertions per test for thorough validation
3. **Descriptions:** Write clear descriptions for debugging
4. **Realistic Data:** Use realistic inputs that match production scenarios

### Evaluation

1. **Iterate:** Evaluate → Improve → Re-evaluate until accuracy is high
2. **Monitor Metrics:** Track accuracy, latency, and token usage
3. **Optimize:** Balance accuracy with latency and token cost
4. **Version:** Create new versions when making significant changes

### LLM Selection

- **Local Development:** Use Ollama with smaller models (qwen2.5:3b) for fast iteration
- **Cluster Evaluation:** Use cluster LLM endpoint for production-quality evaluation
- **Thinking Models:** Consider using reasoning models for complex skills

## Advanced Usage

### Custom LLM Endpoints

```bash
# Use cluster LLM
kubani-dev skill-llm eval my-skill \
  --llm-url http://kubani-llm.cluster.local:8000 \
  --llm-model Qwen3-14B-FP4

# Use OpenAI
export LLM_BASE_URL="https://api.openai.com"
export LLM_MODEL="gpt-4"
kubani-dev skill-llm eval my-skill
```

### Programmatic Usage

```python
from kubani_dev.llm_client import LLMClient
from kubani_dev.skill_drafter import SkillDrafter
from kubani_dev.skill_evaluator_llm import SkillEvaluatorLLM

# Initialize
llm = LLMClient(base_url="http://localhost:11434", model="qwen2.5:3b")

# Draft a skill
drafter = SkillDrafter(llm)
response = drafter.start_conversation("Create a skill to...")

# Evaluate a skill
evaluator = SkillEvaluatorLLM(llm)
results = evaluator.evaluate_skill(Path("skills/development/my-skill"))

print(f"Accuracy: {results['metrics']['accuracy']}%")
```

### Integration with Agents

Agents can discover and execute skills:

```python
from kubani_dev.llm_client import LLMClient
from pathlib import Path

# Load skill
skill_path = Path("skills/core/post-to-discord/v1.0.0/SKILL.md")
skill_sop = skill_path.read_text()

# Execute skill
llm = LLMClient()
result = llm.execute_skill(
    skill_sop=skill_sop,
    inputs={"message": "Hello from agent!", "channel": "general"}
)

print(result["output"])
```

## Troubleshooting

### Low Accuracy

**Problem:** Skill evaluation shows low accuracy (<80%)

**Solutions:**
1. Review failed test cases in `latest_eval.md`
2. Check if SKILL.md instructions are clear enough
3. Add more explicit steps or examples
4. Run improvement workflow: `kubani-dev skill-llm improve`

### High Latency

**Problem:** Evaluation takes too long (>10s per test)

**Solutions:**
1. Use a faster model (smaller size)
2. Simplify skill instructions
3. Reduce number of steps
4. Consider caching for repeated operations

### High Token Usage

**Problem:** Each evaluation uses too many tokens

**Solutions:**
1. Make SKILL.md more concise
2. Remove unnecessary examples
3. Use more direct instructions
4. Consider using a model with larger context window

### LLM Not Following Instructions

**Problem:** LLM doesn't follow SKILL.md correctly

**Solutions:**
1. Make instructions more explicit
2. Add numbered steps
3. Include concrete examples
4. Use imperative language ("Do X" not "You should do X")
5. Test with a more capable model

## Metrics and Monitoring

### Key Metrics

- **Accuracy:** Percentage of assertions that pass
- **Tests Passed:** Number of test cases that pass all assertions
- **Avg Latency:** Average time per test case execution
- **Avg Tokens:** Average tokens used per test case
- **Total Tokens:** Total tokens used in evaluation

### Tracking Over Time

```bash
# View evaluation history
ls -lt skills/development/my-skill/*.json

# Compare versions
diff skills/core/my-skill/v1.0.0/SKILL.md \
     skills/core/my-skill/v1.1.0/SKILL.md
```

## Future Enhancements

The following features are planned for future releases:

1. **Skill Registry Integration:** Store skills in database with search/discovery
2. **Temporal Workflows:** Cluster-based evaluation orchestration
3. **Automated PR Creation:** Sync improved skills back to Git
4. **Skill Developer Agent:** Fully autonomous skill development
5. **Microsandbox Integration:** Hardware-isolated evaluation
6. **Skill Versioning:** Semantic versioning with automatic bumping
7. **Skill Promotion:** Move skills from development to production

## References

- [Original Design Document](../kubani_hybrid_workflow_architecture.md)
- [Implementation Evidence](../LLM_INTEGRATION_EVIDENCE.md)
- [Workflow Scenarios](../WORKFLOW_SCENARIOS.md)
- [Strands Agent SOPs](https://strandsagents.com/latest/documentation/docs/user-guide/evals-sdk/eval-sop/)
- [NVIDIA Voyager](https://voyager.minedojo.org/)
