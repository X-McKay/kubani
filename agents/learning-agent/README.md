# Learning Agent

Continuous learning agent for Kubani using the Voyager-style learning system.

## Overview

The Learning Agent orchestrates the continuous learning system, which includes:

- **Critic Agent**: Evaluates executions and skill proposals
- **Reflection Agent**: Synthesizes cross-agent knowledge
- **Skill Synthesizer**: Generates new skills from patterns
- **Discord Integration**: Posts proposals and receives approvals

## Configuration

Environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_API_URL` | LLM API endpoint | `http://localhost:8000/v1` |
| `LLM_MODEL` | LLM model name | `Qwen/Qwen3-14B` |
| `MCP_DISCORD_URL` | Discord MCP server URL | `http://localhost:8084` |
| `DISCORD_LEARNING_CHANNEL` | Channel for learning posts | - |
| `DISCORD_APPROVALS_CHANNEL` | Channel for approval requests | - |
| `LEARNING_ENABLED` | Enable learning loop | `true` |
| `LEARNING_CRITIC_ENABLED` | Enable critic agent | `true` |
| `LEARNING_REFLECTION_ENABLED` | Enable reflection agent | `true` |
| `LEARNING_SYNTHESIZER_ENABLED` | Enable skill synthesizer | `true` |
| `LEARNING_REQUIRE_DISCORD_APPROVAL` | Require Discord approval | `true` |

## Running

```bash
# Local development
kubani-dev local-run --agent learning-agent

# Build image
earthly +docker

# Push to registry
earthly --push +push
```

## API Endpoints

- `GET /health` - Health check
- `GET /ready` - Readiness check
- `POST /trigger-cycle` - Manually trigger learning cycle
