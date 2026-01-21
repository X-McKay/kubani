# Kubani Skill Development Guide

This guide provides a comprehensive overview of the LLM-integrated skill development workflow in Kubani, inspired by NVIDIA Voyager.

## Overview

The Kubani skill development system is designed for creating, evaluating, and improving skills in a highly agentic, self-improving manner. Skills are natural language Standard Operating Procedures (SOPs) that are executed by LLMs, not deterministic Python code.

**Key Features:**
- **LLM-Driven**: Skills are natural language instructions
- **Self-Improving**: Critic agent and automatic retry enable continuous learning
- **High Accuracy**: Achieved 98.3% average accuracy on complex skills
- **Voyager-Inspired**: Incorporates principles from NVIDIA Voyager
- **Seamless Integration**: Works with Claude Code and local LLMs (Ollama)

## Quick Start

```bash
# 1. Create a new skill
kubani-dev skill-llm draft "Find unused Kubernetes ConfigMaps"

# 2. Evaluate it
kubani-dev skill-llm eval skills/development/find-unused-configmaps --verbose

# 3. If accuracy is low, improve it
kubani-dev skill-llm improve skills/development/find-unused-configmaps --goals accuracy

# 4. Re-evaluate
kubani-dev skill-llm eval skills/development/find-unused-configmaps

# 5. When ready, promote to production
kubani-dev skill-llm promote skills/development/find-unused-configmaps --category core
```

## Core Concepts

### 1. Skills as Natural Language SOPs

Skills are defined in `SKILL.md` files with natural language instructions. This allows for flexible, human-readable, and LLM-executable logic.

**Example `SKILL.md`:**
```markdown
# Find Unused Kubernetes ConfigMaps

## Description
This skill finds all ConfigMaps in a given namespace that are not mounted by any pod.

## Inputs
- `namespace`: The Kubernetes namespace to search in

## Outputs
- `unused_configmaps`: A list of names of unused ConfigMaps

## Instructions
1. Get all pods in the specified namespace.
2. For each pod, get the list of mounted ConfigMaps.
3. Get all ConfigMaps in the namespace.
4. Compare the two lists and return the ConfigMaps that are not mounted by any pod.

## Output Format
CRITICAL: The output MUST be a JSON object with the following structure:

```json
{
  "unused_configmaps": [
    "configmap-1",
    "configmap-2"
  ]
}
```
```

### 2. LLM-Based Evaluation

Evaluation is performed by an LLM that executes the skill based on the `SKILL.md` instructions and compares the output to `test_cases.yaml`.

**Key Features:**
- **Self-Verification Critic**: An LLM acts as a critic to semantically validate success beyond simple assertions.
- **Automatic Retry with Feedback**: Failed tests are automatically retried with feedback from the critic and failed assertions.
- **Comprehensive Metrics**: Accuracy, latency, token usage, and critic confidence are all tracked.

### 3. Critic-Driven Improvement

The `improve` command uses critic feedback to automatically generate improved versions of skills.

**Workflow:**
1. **Analyze**: Extracts critic feedback and identifies patterns in failures.
2. **Generate**: Creates an improved `SKILL.md` that addresses critic suggestions.
3. **Validate**: The improved skill can be re-evaluated to confirm improvements.

## Directory Structure

- `skills/development/`: Active workspace for creating and testing new skills
- `skills/core/`: Production-ready, general-purpose skills
- `skills/agents/`: Production-ready, agent-specific skills
- `.claude/skills/development/`: Symlink to `skills/development/` for Claude Code integration

## CLI Commands

All commands are under the `kubani-dev skill-llm` group:

| Command | Description |
|---|---|
| `draft` | Draft a new skill using LLM-powered conversation |
| `eval` | Evaluate a skill using LLM execution |
| `improve` | Improve a skill based on evaluation results |
| `info` | Show detailed information about a skill |
| `list` | List all skills |
| `promote` | Promote a skill from development to production |
| `eval-history` | View evaluation history for a skill |

## Writing Good Skills

- **Be specific**: Use clear, step-by-step instructions.
- **Enforce format**: Specify the exact output JSON format with examples.
- **Handle errors**: Include instructions for error cases.
- **Test edge cases**: Create test cases for special inputs and failure modes.

## Voyager-Inspired Enhancements

### Phase 1: Enhanced Evaluation (Implemented)
- **Self-Verification Critic**: Semantic validation of skill execution.
- **Automatic Retry with Feedback**: Automatic retries with feedback loop.

### Future Phases (Proposed)
- **Phase 2**: Embedding-Based Skill Retrieval (Qdrant integration)
- **Phase 3**: Hierarchical Skill Composition
- **Phase 4**: Automatic Curriculum Learning

## Troubleshooting

**LLM Connection Issues**
- Check Ollama is running: `ollama list`
- Verify LLM endpoint: `curl http://localhost:11434/api/tags`
- Set custom endpoint: `--llm-url http://your-endpoint:port`

**Evaluation Timeouts**
- First test has 180s timeout (with retry)
- Subsequent tests have 120s timeout
- Use faster/smaller model for development
- Simplify skill instructions

## References

- [ADR-001: Symlinked Development Workspace](docs/adr/001-symlinked-development-workspace.md)
- [ADR-002: File-Based First Approach](docs/adr/002-file-based-first-approach.md)
- [Voyager Enhancement Proposals](VOYAGER_ENHANCEMENT_PROPOSALS.md)
- [Critic-Driven Improvement Integration](CRITIC_IMPROVEMENT_INTEGRATION.md)
