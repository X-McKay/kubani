# Core Agents

Reusable agents for multi-agent swarms.

## Agents

- **DiscordAgent**: Generic agent for publishing notifications to Discord
- **MemoryAgent**: Base agent for learning and recall capabilities

## Usage

```python
from core_agents import DiscordAgent, MemoryAgent

# Use the generic Discord agent
discord = DiscordAgent()
discord("Send a health check summary to Discord")

# Create a memory agent with custom tools
memory = MemoryAgent(
    tools=[my_search_tool, my_store_tool],
    system_prompt="Custom prompt...",
)
memory("Search for similar past issues")
```

## Installation

```bash
pip install -e agents/core
```
