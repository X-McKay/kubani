# Kubani

Agent framework with Skills, Agents, and Syndicates.

## Components

- **framework/** - Core framework (config, events, memory, MCP, etc.)
- **agents/** - Reusable agent implementations
- **syndicates/** - Multi-agent orchestration
- **skills/** - Skill definitions (Markdown + YAML)

## Usage

```python
from kubani.syndicates import K8sMonitorSyndicate

syndicate = K8sMonitorSyndicate()
await syndicate.start()
```
