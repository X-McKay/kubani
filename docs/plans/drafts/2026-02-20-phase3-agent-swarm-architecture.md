# Phase 3: Agent Swarm Architecture for Kubani Nexus

**Author:** Claude Code
**Date:** February 20, 2026
**Status:** Draft
**Prerequisites:** Phase 1 (Nexus PI Agent), Phase 2 (MCP Gateway)

---

## Table of Contents

1. [Context and Motivation](#1-context-and-motivation)
2. [Architecture Overview](#2-architecture-overview)
3. [Design Decisions](#3-design-decisions)
4. [Implementation Steps](#4-implementation-steps)
   - Step 1: Sub-Agent Registry
   - Step 2: Intent Router
   - Step 3: Orchestrator Agent
   - Step 4: Kubernetes Specialist Agent
   - Step 5: Code Specialist Agent
   - Step 6: Research Specialist Agent
   - Step 7: Per-Agent Isolation
   - Step 8: System Prompts
   - Step 9: Modified Workflow
   - Step 10: Modified Activities
   - Step 11: Modified Worker
   - Step 12: MCP Policies
   - Step 13: Kubernetes Network Policies
5. [Testing](#5-testing)
6. [Rollback](#6-rollback)

---

## 1. Context and Motivation

### What Phases 1 & 2 Deliver

After Phase 1, Nexus is a focused **PI (Personal Intelligence) agent** with:
- **Memory MCP** — store/query knowledge and learnings
- **Skills MCP** — discover and execute registered Kubani skills
- **Fetch MCP** (stdio) — read any URL as markdown
- **web_search** — DuckDuckGo internet search
- **5 workspace tools** — read/write/edit/bash/register_skill

After Phase 2, the platform adds:
- An **MCP Gateway** that routes tool calls to ALL backend MCP servers (K8s, Temporal, Qdrant, Memory, Discord, Skills) with centralized policy enforcement.
- **Dynamic tool loading** from the gateway manifest (`GET /tools`).
- **Container-based sandbox** for code execution.
- **HITL approval flow** through the gateway and Temporal workflow signals.

The limitation is that Nexus is still a **single agent focused on PI tasks**. It cannot answer Kubernetes cluster questions, manage Temporal workflows, send Discord notifications, or perform deep vector search — those MCP servers are available through the gateway but no agent is configured to use them.

### Why Swarm Architecture

Phase 1 deliberately kept Nexus's toolset small to avoid token bloat and to align with this swarm architecture. The remaining MCP servers (K8s, Temporal, Discord, Qdrant) were deferred — not because they aren't valuable, but because they belong to specialized sub-agents.

The swarm architecture solves three problems:

1. **Capability gaps.** The PI agent can't answer cluster questions, manage workflows, send notifications, or do deep vector search. Rather than overloading one agent with 40-60 tools, we create focused specialists.

2. **Prompt focus.** A Kubernetes diagnostic prompt and a coding assistant prompt compete for the LLM's attention. Specialized prompts produce better results per-domain.

3. **Isolation.** A coding task and a Kubernetes diagnostic should run with different permissions. The code agent should be sandboxed; the K8s agent needs cluster access but no filesystem writes.

The swarm splits Nexus into:

- An **Orchestrator** (evolved from the PI agent) that classifies intent, handles PI tasks directly, and delegates domain tasks to specialists.
- **Specialist sub-agents**, each with their own system prompt, tool set, and isolation boundary.

This follows the pattern proven by:
- **Anthropic Agent SDK** multi-agent teams (90.2% improvement over single agent on SWE-bench).
- **NanoClaw** container isolation per agent group.
- **OpenClaw** hub-and-spoke gateway with session-based lane queues.

### What This Enables

- Kubernetes questions go to a **K8s Agent** with cluster tools and Prometheus.
- Workflow management goes to a **Workflow Agent** with Temporal MCP.
- Notifications and comms go to a **Comms Agent** with Discord MCP.
- Deep research goes to a **Research Agent** with Qdrant MCP and ArXiv.
- Coding tasks go to a **Code Agent** with sandbox isolation.
- PI tasks (memory, skills, fetch, web search) stay on the orchestrator.
- Multi-domain tasks get split across specialists and results synthesized.
- Each specialist has its own token budget, retry policy, and timeout.
- New specialists can be added without modifying the orchestrator prompt.

---

## 2. Architecture Overview

### Current Architecture (Phase 2)

```
User Message
    │
    ▼
┌──────────────────────────────┐
│   Conversational Gateway     │
│   (FastAPI, port 8090)       │
└──────────┬───────────────────┘
           │ Temporal Signal
           ▼
┌──────────────────────────────┐
│  NexusOrchestratorWorkflow   │
│  (Temporal Workflow)         │
│                              │
│  ┌────────────────────────┐  │
│  │   run_agent_turn       │  │
│  │   (Single Activity)    │  │
│  │                        │  │
│  │   Nexus PI Agent       │  │
│  │   1 System Prompt      │  │
│  │   PI Tools only        │  │
│  │   (memory, skills,     │  │
│  │    fetch, web_search,  │  │
│  │    workspace)          │  │
│  └────────────────────────┘  │
└──────────────────────────────┘
           │
           ▼
┌──────────────────────────────┐
│     MCP Gateway (8085)       │
│     ALL backend servers      │
│     (only Memory + Skills    │
│      used by PI agent)       │
└──────────────────────────────┘
```

### Phase 3 Architecture (Swarm)

```
User Message
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│   Conversational Gateway (FastAPI, port 8090)            │
└──────────┬───────────────────────────────────────────────┘
           │ Temporal Signal
           ▼
┌──────────────────────────────────────────────────────────┐
│  NexusOrchestratorWorkflow (Temporal Workflow)            │
│                                                          │
│  1. route_intent activity                                │
│     ┌─────────────────────────────┐                      │
│     │  Intent Router (LLM call)   │                      │
│     │  Classifies → agent(s)      │                      │
│     └──────────┬──────────────────┘                      │
│                │                                         │
│  2. Dispatch to specialist activity(ies)                 │
│     ┌──────┼───────┬────────┬────────┬──────────┐        │
│     ▼      ▼       ▼        ▼        ▼          ▼        │
│  ┌──────┐┌──────┐┌────────┐┌──────┐┌────────┐┌───────┐  │
│  │ K8s  ││Work- ││ Comms  ││Rsrch ││ Code   ││General│  │
│  │Agent ││flow  ││ Agent  ││Agent ││ Agent  ││(PI    │  │
│  │      ││Agent ││        ││      ││        ││agent) │  │
│  │k8s   ││tempo-││discord ││qdrant││read,   ││memory,│  │
│  │MCP + ││ral   ││MCP     ││MCP + ││write,  ││skills,│  │
│  │prome-││MCP   ││        ││arxiv ││edit,   ││fetch, │  │
│  │theus ││      ││        ││      ││bash    ││search │  │
│  └──┬───┘└──┬───┘└───┬────┘└──┬───┘└───┬────┘└──┬────┘  │
│      │          │           │              │             │
│  3. Synthesize results (if multi-agent)                  │
│     ┌───────────────────────────────────┐                │
│     │  run_synthesis activity           │                │
│     │  Combines sub-agent responses     │                │
│     └───────────────────────────────────┘                │
└──────────────────────────────────────────────────────────┘
```

### Per-Agent Isolation

```
┌─────────────────────────────────────────────────────────────┐
│  Temporal Worker Process                                    │
│                                                             │
│  ┌───────────────────────┐  ┌───────────────────────────┐   │
│  │  K8s Agent Activity   │  │  Workflow Agent Activity   │   │
│  │                       │  │                           │   │
│  │  MCP Gateway Policy:  │  │  MCP Gateway Policy:      │   │
│  │  nexus-k8s.json       │  │  nexus-workflow.json      │   │
│  │  - kubernetes: allow  │  │  - temporal: allow        │   │
│  │  + prometheus queries │  │  - kubernetes: deny       │   │
│  │  - others: deny       │  │  - others: deny           │   │
│  │                       │  │                           │   │
│  │  Network:             │  │  Network:                 │   │
│  │  - cluster access     │  │  - MCP gateway only       │   │
│  │  - MCP gateway        │  │                           │   │
│  └───────────────────────┘  └───────────────────────────┘   │
│                                                             │
│  ┌───────────────────────┐  ┌───────────────────────────┐   │
│  │  Comms Agent Activity │  │  Research Agent Activity   │   │
│  │                       │  │                           │   │
│  │  MCP Gateway Policy:  │  │  MCP Gateway Policy:      │   │
│  │  nexus-comms.json     │  │  nexus-research.json      │   │
│  │  - discord: allow     │  │  - qdrant: allow          │   │
│  │  - others: deny       │  │  + arxiv tools            │   │
│  │                       │  │  - others: deny           │   │
│  │  Network:             │  │                           │   │
│  │  - MCP gateway only   │  │  Network:                 │   │
│  │                       │  │  - MCP gateway + internet │   │
│  └───────────────────────┘  └───────────────────────────┘   │
│                                                             │
│  ┌───────────────────────┐  ┌───────────────────────────┐   │
│  │  Code Agent Activity  │  │  General Agent (PI agent)  │   │
│  │                       │  │                           │   │
│  │  MCP Gateway Policy:  │  │  MCP Gateway Policy:      │   │
│  │  nexus-code.json      │  │  nexus.json (Phase 1)     │   │
│  │  - all MCP: deny      │  │  - memory: allow          │   │
│  │                       │  │  - skills: allow          │   │
│  │  Network:             │  │  + fetch, web_search      │   │
│  │  - sandbox only       │  │                           │   │
│  │  - workspace fs       │  │  Network:                 │   │
│  │                       │  │  - MCP gateway + internet │   │
│  └───────────────────────┘  └───────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Communication Flow (Single-Agent Task)

```
1. User: "Why is my pod crashing in the ai-agents namespace?"

2. Gateway → Temporal Signal → NexusOrchestratorWorkflow

3. Workflow calls route_intent activity:
   Input:  "Why is my pod crashing in the ai-agents namespace?"
   Output: { "agents": ["k8s"], "reasoning": "Kubernetes diagnostic query" }

4. Workflow calls run_k8s_agent_turn activity:
   Input:  { user_message, conversation_history, memories }
   Agent:  K8s specialist with K8s MCP + Prometheus tools
   Output: { "response_text": "The pod news-collector-xyz is in CrashLoopBackOff..." }

5. Workflow publishes response via publish_response_activity

6. Gateway → WebSocket/Discord → User
```

### Communication Flow (PI Agent Fallback)

```
1. User: "Search the web for Strands Agent SDK docs and save what you find"

2. Gateway → Temporal Signal → NexusOrchestratorWorkflow

3. Workflow calls route_intent activity:
   Input:  "Search the web for Strands Agent SDK docs and save what you find"
   Output: { "agents": ["general"], "reasoning": "Web search + memory storage = PI agent" }

4. Workflow calls run_general_agent_turn activity:
   Input:  { user_message, conversation_history, memories }
   Agent:  General (PI) agent with memory, skills, fetch, web_search, workspace tools
   Output: { "response_text": "I found the Strands docs and saved key points to memory..." }

5. Workflow publishes response
```

### Communication Flow (Multi-Agent Task)

```
1. User: "Check the cluster health and write a summary report to my workspace"

2. Gateway → Temporal Signal → NexusOrchestratorWorkflow

3. Workflow calls route_intent activity:
   Input:  "Check the cluster health and write a summary report to my workspace"
   Output: { "agents": ["k8s", "code"], "reasoning": "K8s diagnostics + file writing" }

4. Workflow calls run_k8s_agent_turn (first, to get data):
   Input:  { user_message: "Check the cluster health and report findings" }
   Output: { "response_text": "Cluster status: 3 nodes healthy, 1 pod in CrashLoop..." }

5. Workflow calls run_code_agent_turn (second, with K8s results as context):
   Input:  { user_message: "Write a cluster health summary report",
             context: "K8s agent findings: 3 nodes healthy, 1 pod in CrashLoop..." }
   Output: { "response_text": "Created report at workspace/cluster-health-2026-02-20.md" }

6. Workflow calls run_synthesis activity:
   Input:  { original_message, agent_results: [k8s_result, code_result] }
   Output: { "response_text": "I checked the cluster and wrote a report. Here's the summary:..." }

7. Workflow publishes synthesized response
```

---

## 3. Design Decisions

### 3.1 How does the orchestrator pass conversation context to sub-agents?

Each sub-agent activity receives:
- `user_message`: The current user message (potentially rewritten by the orchestrator for the specific agent's task).
- `conversation_history`: The last 10 messages from the workflow state, serialized as `list[dict]`. This is the same format already used by `run_agent_turn`.
- `memories`: Relevant memories recalled before routing (same as current flow).
- `context`: Results from previous sub-agents in a multi-agent flow (new field). This is a plain string appended to the prompt.

Sub-agents do NOT share runtime state. Each activity creates a fresh Strands Agent. This is the same pattern as the current `run_agent_turn` -- we are just creating different agents with different prompts and tools.

### 3.2 How do sub-agent results get synthesized into a single response?

**Single-agent tasks:** The sub-agent's response is used directly. No synthesis needed.

**Multi-agent tasks:** A lightweight `run_synthesis` activity takes the original user message and all sub-agent responses, then calls the LLM to produce a unified response. This is a simple LLM call (no tools), similar to the existing `generate_response` activity.

### 3.3 What happens when a sub-agent fails?

Each sub-agent activity has its own retry policy (3 attempts with exponential backoff, same as `LLM_RETRY_POLICY`). If a sub-agent fails after all retries:

- The orchestrator receives an error result: `{"response_text": "Error: ...", "stop_reason": "error"}`.
- For single-agent tasks: The error is returned to the user with an explanation.
- For multi-agent tasks: Other agents continue. The synthesis step notes the failure and presents partial results.

This matches the existing error handling in `run_agent_turn` where exceptions are caught and returned as error responses.

### 3.4 How does HITL approval work with sub-agents?

HITL approval is enforced at two levels, both unchanged from Phase 2:

1. **MCP Gateway level:** The gateway enforces `requireApproval` rules per policy. When a sub-agent calls a tool that requires approval, the gateway returns a pending status. The Strands Agent sees the tool result as "NEEDS_APPROVAL" and informs the user.

2. **Bash tool level:** The 3-tier security barrier in `kubani/nexus/tools/security.py` still classifies commands. Medium-risk commands return `NEEDS_APPROVAL`. The sub-agent surfaces this to the user.

No changes to the approval mechanism are needed. The gateway policies per sub-agent (Section 4, Step 12) control which tools each agent can access.

### 3.5 What is the token budget per sub-agent?

| Agent | max_tokens | Timeout | Rationale |
|-------|-----------|---------|-----------|
| Router | 512 | 30s | Classification only, no tools |
| Orchestrator Synthesis | 2048 | 60s | Combining results, no tools |
| K8s Agent | 4096 | 5min | May need multiple tool calls + Prometheus |
| Workflow Agent | 4096 | 3min | Temporal queries are fast |
| Comms Agent | 4096 | 2min | Discord operations are fast |
| Research Agent | 4096 | 3min | Qdrant search + ArXiv |
| Code Agent | 4096 | 10min | File operations can be lengthy |
| General Agent (PI) | 4096 | 5min | Fallback with memory/skills/fetch/search |

These are set as `max_tokens` in the `OpenAIModel` params and `start_to_close_timeout` in the Temporal activity call.

### 3.6 How is conversation history shared vs. isolated?

**Shared:** All sub-agents receive the same `conversation_history` from the workflow state (last 10 messages). This is read-only context for the LLM prompt.

**Isolated:** Sub-agents do NOT write to the workflow's conversation history directly. Only the final response (from the single agent or the synthesis step) is added to the workflow state via `_publish_and_persist_response`. This prevents sub-agent intermediate chatter from polluting the conversation.

**Workflow state addition:** We add an `active_agents` field to `NexusWorkflowState` so the UI can show which sub-agents are working. This is set to the list of agent names during processing and cleared when done.

---

## 4. Implementation Steps

### Step 1: Sub-Agent Registry

**File:** `kubani/nexus/agents/__init__.py`

This file makes the `kubani/nexus/agents/` directory a Python package and re-exports the registry for convenience.

```python
"""Nexus sub-agent package.

Contains the specialized sub-agents that the orchestrator delegates to,
plus the registry that maps agent names to their configurations.
"""

from kubani.nexus.agents.registry import AgentConfig, SubAgentRegistry

__all__ = ["AgentConfig", "SubAgentRegistry"]
```

**File:** `kubani/nexus/agents/registry.py`

The registry holds configuration for each sub-agent: its name, description, system prompt file, tool set, token budget, and timeout. The orchestrator and router both consult this registry to know what agents are available.

```python
"""Sub-agent registry for the Nexus swarm.

Maps agent names to their configurations. The router uses this to know
what agents exist and what they can do. The orchestrator uses this to
create the right Strands Agent for each activity.

Usage:
    from kubani.nexus.agents.registry import SubAgentRegistry

    registry = SubAgentRegistry()
    config = registry.get("k8s")
    all_agents = registry.list_agents()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Directory containing system prompt files
PROMPTS_DIR = Path(__file__).parent / "prompts"


@dataclass(frozen=True)
class AgentConfig:
    """Configuration for a single sub-agent.

    Attributes:
        name: Short identifier used for routing (e.g., "k8s", "code").
        display_name: Human-readable name for UI display.
        description: What this agent specializes in (used by the router prompt).
        prompt_file: Filename of the system prompt in the prompts/ directory.
        tool_type: Which tool set to load ("k8s_mcp", "workspace", "research_mcp", "general").
        max_tokens: Maximum tokens for this agent's LLM responses.
        timeout_seconds: Maximum time for this agent's activity.
        mcp_policy: Name of the MCP gateway policy file (without .json).
        can_run_parallel: Whether this agent can run in parallel with others.
    """

    name: str
    display_name: str
    description: str
    prompt_file: str
    tool_type: str
    max_tokens: int = 4096
    timeout_seconds: int = 300
    mcp_policy: str = "default"
    can_run_parallel: bool = True

    @property
    def system_prompt(self) -> str:
        """Load the system prompt from the prompts/ directory."""
        prompt_path = PROMPTS_DIR / self.prompt_file
        if not prompt_path.exists():
            logger.warning(f"Prompt file not found: {prompt_path}")
            return f"You are the {self.display_name}. {self.description}"
        return prompt_path.read_text()


class SubAgentRegistry:
    """Registry of available sub-agents.

    Provides lookup by name and listing for the router prompt.
    Agents are registered at class load time (not dynamically).
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentConfig] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the built-in sub-agents."""
        self.register(AgentConfig(
            name="k8s",
            display_name="Kubernetes Agent",
            description=(
                "Specializes in Kubernetes cluster operations: pod diagnostics, "
                "deployment management, log analysis, resource monitoring, "
                "event investigation, and Prometheus metrics/alerts."
            ),
            prompt_file="k8s_agent.md",
            tool_type="k8s_mcp",
            max_tokens=4096,
            timeout_seconds=300,
            mcp_policy="nexus-k8s",
        ))

        self.register(AgentConfig(
            name="workflow",
            display_name="Workflow Agent",
            description=(
                "Specializes in Temporal workflow management: listing, querying, "
                "signaling, and monitoring workflows and schedules."
            ),
            prompt_file="workflow_agent.md",
            tool_type="temporal_mcp",
            max_tokens=4096,
            timeout_seconds=180,
            mcp_policy="nexus-workflow",
        ))

        self.register(AgentConfig(
            name="comms",
            display_name="Comms Agent",
            description=(
                "Specializes in Discord communication: sending messages, reading "
                "channels, managing reactions, and handling webhooks."
            ),
            prompt_file="comms_agent.md",
            tool_type="discord_mcp",
            max_tokens=4096,
            timeout_seconds=120,
            mcp_policy="nexus-comms",
        ))

        self.register(AgentConfig(
            name="research",
            display_name="Research Agent",
            description=(
                "Specializes in deep information retrieval: searching vector "
                "memory (Qdrant), querying the knowledge graph, searching ArXiv "
                "for academic papers, and synthesizing findings."
            ),
            prompt_file="research_agent.md",
            tool_type="research_mcp",
            max_tokens=4096,
            timeout_seconds=180,
            mcp_policy="nexus-research",
        ))

        self.register(AgentConfig(
            name="code",
            display_name="Code Agent",
            description=(
                "Specializes in coding tasks: reading, writing, and editing files, "
                "running shell commands, creating scripts, and registering new skills. "
                "Operates within a sandboxed workspace with restricted filesystem access."
            ),
            prompt_file="code_agent.md",
            tool_type="workspace",
            max_tokens=4096,
            timeout_seconds=600,
            mcp_policy="nexus-code",
            can_run_parallel=False,
        ))

        self.register(AgentConfig(
            name="general",
            display_name="General Agent (PI)",
            description=(
                "The default PI agent from Phase 1. Handles general conversation, "
                "questions about Kubani, greetings, help requests, memory "
                "management, skill discovery, web search, and URL fetching. "
                "Fallback for anything that does not clearly fit a specialist."
            ),
            prompt_file="general_agent.md",
            tool_type="pi_agent",
            max_tokens=4096,
            timeout_seconds=300,
            mcp_policy="nexus",
        ))

    def register(self, config: AgentConfig) -> None:
        """Register a sub-agent configuration.

        Args:
            config: The agent configuration to register.
        """
        self._agents[config.name] = config
        logger.debug(f"Registered sub-agent: {config.name}")

    def get(self, name: str) -> AgentConfig | None:
        """Get a sub-agent configuration by name.

        Args:
            name: The agent identifier (e.g., "k8s", "code").

        Returns:
            AgentConfig if found, None otherwise.
        """
        return self._agents.get(name)

    def list_agents(self) -> list[AgentConfig]:
        """List all registered sub-agents.

        Returns:
            List of all AgentConfig instances.
        """
        return list(self._agents.values())

    def get_router_description(self) -> str:
        """Build a description of all agents for the router prompt.

        Returns:
            Formatted string listing each agent and its description.
        """
        lines = []
        for agent in self._agents.values():
            lines.append(f"- **{agent.name}**: {agent.description}")
        return "\n".join(lines)

    def get_names(self) -> list[str]:
        """Get all registered agent names.

        Returns:
            List of agent name strings.
        """
        return list(self._agents.keys())
```

---

### Step 2: Intent Router

**File:** `kubani/nexus/agents/router.py`

The router is a lightweight LLM call (no tools) that classifies the user's message and decides which sub-agent(s) should handle it. It uses Strands `chat_structured` for reliable JSON output.

```python
"""Intent router for the Nexus swarm.

Classifies user messages and determines which sub-agent(s) should handle
the request. Uses a single LLM call with structured output -- no tools.

The router is called as a Temporal activity (route_intent) before any
sub-agent is invoked. It is intentionally lightweight: small max_tokens,
short timeout, no tool calls.

Usage:
    from kubani.nexus.agents.router import route_intent

    result = await route_intent({
        "user_message": "Why is my pod crashing?",
        "agent_descriptions": registry.get_router_description(),
        "agent_names": registry.get_names(),
        "conversation_history": [...],
    })
    # result = {"agents": ["k8s"], "reasoning": "...", "rewritten_tasks": {"k8s": "..."}}
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)

ROUTER_SYSTEM_PROMPT = """/no_think
You are a message router for the Kubani Nexus agent system. Your ONLY job is
to classify the user's message and decide which specialist agent(s) should
handle it.

## Available Agents

{agent_descriptions}

## Rules

1. Analyze the user's message and determine which agent(s) are best suited.
2. Most messages need exactly ONE agent. Only use multiple agents when the
   task clearly requires different specializations (e.g., "check cluster
   health AND write a report" needs both k8s and code).
3. If the message is a greeting, general question, or doesn't clearly fit
   a specialist, route to "general".
4. For each selected agent, provide a rewritten task description that is
   specific to that agent's specialty. This helps the agent focus.
5. If routing to multiple agents, specify the execution order. Some tasks
   must be sequential (e.g., K8s data gathering before report writing).

## Output Format

Respond with ONLY a JSON object, no other text:

{{
  "agents": ["agent_name"],
  "reasoning": "Brief explanation of why this routing was chosen",
  "parallel": false,
  "rewritten_tasks": {{
    "agent_name": "The specific task for this agent"
  }}
}}

For multi-agent tasks:

{{
  "agents": ["k8s", "code"],
  "reasoning": "Need cluster data first, then write report",
  "parallel": false,
  "rewritten_tasks": {{
    "k8s": "Check the cluster health and report all findings",
    "code": "Write a cluster health summary report based on the provided findings"
  }}
}}

Valid agent names: {agent_names}
"""

ROUTER_MAX_TOKENS = 512
ROUTER_TEMPERATURE = 0.1


@activity.defn
async def route_intent(input_data: dict[str, Any]) -> dict[str, Any]:
    """Classify the user's message and determine routing.

    This is a Temporal activity that makes a single LLM call to classify
    the user's intent and select the appropriate sub-agent(s).

    Args:
        input_data: Dict containing:
            - user_message: str - The user's message.
            - agent_descriptions: str - Formatted agent descriptions for the prompt.
            - agent_names: list[str] - Valid agent names.
            - conversation_history: list[dict] - Recent conversation for context.

    Returns:
        Dict containing:
            - agents: list[str] - Ordered list of agent names to invoke.
            - reasoning: str - Why this routing was chosen.
            - parallel: bool - Whether agents can run in parallel.
            - rewritten_tasks: dict[str, str] - Per-agent task descriptions.
    """
    user_message = input_data["user_message"]
    agent_descriptions = input_data["agent_descriptions"]
    agent_names = input_data["agent_names"]
    conversation_history = input_data.get("conversation_history", [])

    activity.heartbeat("Routing intent")
    logger.info(f"Routing message: {user_message[:100]}")

    from kubani.framework.config import get_llm_config
    from strands import Agent
    from strands.models.openai import OpenAIModel

    llm_config = get_llm_config()

    model = OpenAIModel(
        client_args={
            "api_key": llm_config.api_key or "not-needed",
            "base_url": llm_config.api_url,
        },
        model_id=llm_config.model,
        params={
            "temperature": ROUTER_TEMPERATURE,
            "max_tokens": ROUTER_MAX_TOKENS,
        },
    )

    system_prompt = ROUTER_SYSTEM_PROMPT.format(
        agent_descriptions=agent_descriptions,
        agent_names=json.dumps(agent_names),
    )

    # Build context from recent conversation
    context_lines = []
    for msg in conversation_history[-5:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")[:200]
        context_lines.append(f"{role}: {content}")

    user_prompt = user_message
    if context_lines:
        user_prompt = (
            "Recent conversation context:\n"
            + "\n".join(context_lines)
            + "\n\nNew message to route:\n"
            + user_message
        )

    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[],
        callback_handler=None,
    )

    try:
        result = await agent.invoke_async(user_prompt)
        raw_text = str(result)

        # Strip thinking tags
        raw_text = re.sub(r"<think>\s*</think>\s*", "", raw_text).strip()

        # Extract JSON from response
        routing = _extract_routing_json(raw_text, agent_names)

        logger.info(
            f"Routed to: {routing['agents']} "
            f"(reasoning: {routing['reasoning'][:100]})"
        )
        return routing

    except Exception as e:
        logger.error(f"Router error: {e}", exc_info=True)
        # Fallback: route to general agent
        return {
            "agents": ["general"],
            "reasoning": f"Router error, falling back to general: {e}",
            "parallel": False,
            "rewritten_tasks": {"general": user_message},
        }


def _extract_routing_json(
    raw_text: str, valid_agents: list[str]
) -> dict[str, Any]:
    """Extract and validate routing JSON from the LLM response.

    Handles code fences, thinking tags, and invalid agent names.

    Args:
        raw_text: The raw LLM response text.
        valid_agents: List of valid agent names for validation.

    Returns:
        Validated routing dict with agents, reasoning, parallel, rewritten_tasks.
    """
    # Strip markdown code fences
    text = raw_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    # Strip thinking tags
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse router JSON: {text[:200]}")
        return {
            "agents": ["general"],
            "reasoning": "Failed to parse routing response",
            "parallel": False,
            "rewritten_tasks": {"general": ""},
        }

    # Validate agent names
    agents = data.get("agents", ["general"])
    validated_agents = [a for a in agents if a in valid_agents]
    if not validated_agents:
        validated_agents = ["general"]

    # Ensure rewritten_tasks has entries for all agents
    rewritten_tasks = data.get("rewritten_tasks", {})
    for agent_name in validated_agents:
        if agent_name not in rewritten_tasks:
            rewritten_tasks[agent_name] = ""

    return {
        "agents": validated_agents,
        "reasoning": data.get("reasoning", ""),
        "parallel": data.get("parallel", False),
        "rewritten_tasks": rewritten_tasks,
    }
```

---

### Step 3: Orchestrator Synthesis

**File:** `kubani/nexus/agents/orchestrator.py`

The orchestrator is not a Strands Agent -- it is workflow logic plus a synthesis activity. The workflow handles routing and dispatching (Step 9). This module provides the synthesis activity that combines multi-agent results.

```python
"""Orchestrator synthesis for multi-agent results.

When multiple sub-agents are invoked, their individual responses need
to be combined into a single coherent response for the user. This
module provides the synthesis activity that does this.

For single-agent tasks, synthesis is skipped and the agent's response
is used directly.

Usage (as Temporal activity):
    result = await workflow.execute_activity(
        "run_synthesis",
        args=[{
            "original_message": "Check cluster and write report",
            "agent_results": [
                {"agent": "k8s", "response_text": "..."},
                {"agent": "code", "response_text": "..."},
            ],
        }],
        ...
    )
"""

from __future__ import annotations

import logging
import re
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)

SYNTHESIS_SYSTEM_PROMPT = """/no_think
You are a response synthesizer for the Kubani Nexus agent. Multiple specialist
agents have worked on parts of the user's request. Your job is to combine their
results into one clear, coherent response.

Rules:
1. Present the information in a logical order.
2. Remove redundancy between agent responses.
3. If any agent reported an error, note it clearly but present the successful results.
4. Use Markdown formatting for readability.
5. Be concise. Do not add information beyond what the agents reported.
6. Do not mention the internal agent names or routing process to the user.
   Present it as a single unified response."""

SYNTHESIS_MAX_TOKENS = 2048


@activity.defn
async def run_synthesis(input_data: dict[str, Any]) -> dict[str, Any]:
    """Synthesize results from multiple sub-agents into one response.

    Args:
        input_data: Dict containing:
            - original_message: str - The user's original message.
            - agent_results: list[dict] - Results from each sub-agent.
              Each dict has "agent" (str) and "response_text" (str).

    Returns:
        Dict with response_text (the synthesized response).
    """
    original_message = input_data["original_message"]
    agent_results = input_data["agent_results"]

    activity.heartbeat("Synthesizing multi-agent results")

    if len(agent_results) == 1:
        return {"response_text": agent_results[0]["response_text"]}

    # Build the synthesis prompt
    results_text = ""
    for i, result in enumerate(agent_results, 1):
        agent_name = result.get("agent", f"agent-{i}")
        response = result.get("response_text", "(no response)")
        stop_reason = result.get("stop_reason", "unknown")
        if stop_reason == "error":
            results_text += f"\n--- Result {i} ({agent_name}) [ERROR] ---\n{response}\n"
        else:
            results_text += f"\n--- Result {i} ({agent_name}) ---\n{response}\n"

    user_prompt = (
        f"Original user request: {original_message}\n\n"
        f"Agent results:{results_text}\n\n"
        "Synthesize these into a single, coherent response for the user."
    )

    from kubani.framework.config import get_llm_config
    from strands import Agent
    from strands.models.openai import OpenAIModel

    llm_config = get_llm_config()

    model = OpenAIModel(
        client_args={
            "api_key": llm_config.api_key or "not-needed",
            "base_url": llm_config.api_url,
        },
        model_id=llm_config.model,
        params={
            "temperature": 0.3,
            "max_tokens": SYNTHESIS_MAX_TOKENS,
        },
    )

    agent = Agent(
        model=model,
        system_prompt=SYNTHESIS_SYSTEM_PROMPT,
        tools=[],
        callback_handler=None,
    )

    try:
        result = await agent.invoke_async(user_prompt)
        response_text = str(result)
        response_text = re.sub(r"<think>\s*</think>\s*", "", response_text).strip()
        return {"response_text": response_text}
    except Exception as e:
        logger.error(f"Synthesis error: {e}", exc_info=True)
        # Fallback: concatenate results
        fallback_parts = []
        for r in agent_results:
            fallback_parts.append(r.get("response_text", ""))
        return {"response_text": "\n\n---\n\n".join(fallback_parts)}
```

---

### Step 4: Kubernetes Specialist Agent

**File:** `kubani/nexus/agents/k8s_agent.py`

The K8s agent activity creates a Strands Agent with K8s MCP tools and Prometheus custom tools. The MCP tools are loaded from the MCP Gateway filtered by the `nexus-k8s` policy. Prometheus tools (`prometheus_query`, `prometheus_query_range`, `prometheus_alerts`) are custom `@tool` functions that query the Prometheus API directly.

```python
"""Kubernetes specialist sub-agent.

Handles all Kubernetes cluster operations: pod diagnostics, deployment
management, log analysis, resource monitoring, event investigation,
and automated remediation.

This agent accesses MCP tools through the MCP Gateway with the
nexus-k8s policy, which allows: kubernetes + prometheus custom tools.

Usage (as Temporal activity):
    result = await workflow.execute_activity(
        "run_k8s_agent_turn",
        args=[{ ... }],
        start_to_close_timeout=timedelta(minutes=5),
    )
"""

from __future__ import annotations

import logging
import re
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)


def _create_k8s_mcp_tools() -> list:
    """Create Strands @tool wrappers for K8s MCP gateway tools.

    These tools call the MCP Gateway with the nexus-k8s policy header.
    The gateway routes to the appropriate backend MCP server.

    Returns:
        List of Strands tool instances.
    """
    import os

    import httpx
    from strands import tool

    gateway_url = os.environ.get("MCP_GATEWAY_URL", "http://localhost:8085")
    policy_name = "nexus-k8s"

    async def _call_gateway(tool_name: str, arguments: dict[str, Any]) -> str:
        """Call the MCP gateway with policy headers.

        Args:
            tool_name: The MCP tool to call.
            arguments: Tool arguments.

        Returns:
            Tool result as a string.
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{gateway_url}/call",
                json={
                    "tool": tool_name,
                    "arguments": arguments,
                },
                headers={"X-Agent-Policy": policy_name},
            )
            if response.status_code == 403:
                return f"Error: Tool '{tool_name}' blocked by policy"
            response.raise_for_status()
            data = response.json()
            if data.get("error"):
                return f"Error: {data['error']}"
            return data.get("result", str(data))

    @tool
    async def kubectl_get(resource: str, namespace: str = "", name: str = "", output_format: str = "wide") -> str:
        """Get Kubernetes resources. Returns resource details in the specified format.

        Args:
            resource: Resource type (pods, deployments, services, nodes, events, etc.).
            namespace: Kubernetes namespace. Empty string for all namespaces.
            name: Specific resource name. Empty string for all resources of this type.
            output_format: Output format (wide, yaml, json, name).
        """
        return await _call_gateway("kubernetes.get", {
            "resource": resource,
            "namespace": namespace,
            "name": name,
            "output_format": output_format,
        })

    @tool
    async def kubectl_describe(resource: str, name: str, namespace: str = "default") -> str:
        """Describe a Kubernetes resource in detail. Shows events, conditions, and status.

        Args:
            resource: Resource type (pod, deployment, service, node, etc.).
            name: Name of the specific resource.
            namespace: Kubernetes namespace.
        """
        return await _call_gateway("kubernetes.describe", {
            "resource": resource,
            "name": name,
            "namespace": namespace,
        })

    @tool
    async def kubectl_logs(pod_name: str, namespace: str = "default", container: str = "", tail_lines: int = 100, previous: bool = False) -> str:
        """Get logs from a Kubernetes pod.

        Args:
            pod_name: Name of the pod.
            namespace: Kubernetes namespace.
            container: Specific container name (for multi-container pods). Empty for default.
            tail_lines: Number of lines from the end of the logs.
            previous: If True, get logs from the previous terminated container.
        """
        return await _call_gateway("kubernetes.logs", {
            "pod_name": pod_name,
            "namespace": namespace,
            "container": container,
            "tail_lines": tail_lines,
            "previous": previous,
        })

    @tool
    async def kubectl_top(resource: str = "nodes", namespace: str = "", name: str = "") -> str:
        """Get resource usage (CPU/memory) for nodes or pods.

        Args:
            resource: Either "nodes" or "pods".
            namespace: Kubernetes namespace (for pods). Empty for all namespaces.
            name: Specific resource name. Empty for all.
        """
        return await _call_gateway("kubernetes.top", {
            "resource": resource,
            "namespace": namespace,
            "name": name,
        })

    @tool
    async def kubectl_events(namespace: str = "", field_selector: str = "") -> str:
        """Get Kubernetes events sorted by timestamp.

        Args:
            namespace: Kubernetes namespace. Empty for all namespaces.
            field_selector: Field selector to filter events (e.g., "type=Warning").
        """
        return await _call_gateway("kubernetes.events", {
            "namespace": namespace,
            "field_selector": field_selector,
        })

    @tool
    async def kubectl_rollout(action: str, resource: str, name: str, namespace: str = "default") -> str:
        """Manage deployment rollouts.

        Args:
            action: Rollout action (status, restart, undo, history).
            resource: Resource type (deployment, statefulset, daemonset).
            name: Name of the resource.
            namespace: Kubernetes namespace.
        """
        return await _call_gateway("kubernetes.rollout", {
            "action": action,
            "resource": resource,
            "name": name,
            "namespace": namespace,
        })

    @tool
    async def kubectl_scale(resource: str, name: str, replicas: int, namespace: str = "default") -> str:
        """Scale a deployment, statefulset, or replicaset.

        Args:
            resource: Resource type (deployment, statefulset, replicaset).
            name: Name of the resource.
            replicas: Desired number of replicas.
            namespace: Kubernetes namespace.
        """
        return await _call_gateway("kubernetes.scale", {
            "resource": resource,
            "name": name,
            "replicas": replicas,
            "namespace": namespace,
        })

    @tool
    async def send_discord_message(channel: str, message: str) -> str:
        """Send a message to a Discord channel.

        Args:
            channel: Discord channel name or ID.
            message: Message text to send (supports Markdown).
        """
        return await _call_gateway("discord.send_message", {
            "channel": channel,
            "content": message,
        })

    @tool
    async def search_memory(query: str, limit: int = 5) -> str:
        """Search the agent's memory for relevant past knowledge.

        Args:
            query: Search query text.
            limit: Maximum number of results.
        """
        return await _call_gateway("memory.search", {
            "query": query,
            "limit": limit,
        })

    return [
        kubectl_get,
        kubectl_describe,
        kubectl_logs,
        kubectl_top,
        kubectl_events,
        kubectl_rollout,
        kubectl_scale,
        send_discord_message,
        search_memory,
    ]


@activity.defn
async def run_k8s_agent_turn(input_data: dict[str, Any]) -> dict[str, Any]:
    """Run a full turn of the Kubernetes specialist agent.

    Creates a Strands Agent with K8s MCP tools and the K8s system prompt,
    runs the agentic loop, and returns the response.

    Args:
        input_data: Dict containing:
            - user_message: str - The task for this agent.
            - conversation_history: list[dict] - Recent conversation.
            - memories: list[str] - Relevant memories.
            - context: str - Results from previous agents (optional).
            - user_id: str - For audit logging.

    Returns:
        Dict with response_text and stop_reason.
    """
    user_message = input_data.get("user_message", "")
    conversation_history = input_data.get("conversation_history", [])
    memories = input_data.get("memories", [])
    context = input_data.get("context", "")
    user_id = input_data.get("user_id", "default")

    activity.heartbeat("Creating K8s agent")
    logger.info(f"K8s agent: user={user_id}, msg={user_message[:100]}")

    from kubani.framework.config import get_llm_config
    from kubani.nexus.agents.registry import SubAgentRegistry
    from strands import Agent
    from strands.models.openai import OpenAIModel

    llm_config = get_llm_config()
    registry = SubAgentRegistry()
    agent_config = registry.get("k8s")

    model = OpenAIModel(
        client_args={
            "api_key": llm_config.api_key or "not-needed",
            "base_url": llm_config.api_url,
        },
        model_id=llm_config.model,
        params={
            "temperature": llm_config.temperature,
            "max_tokens": agent_config.max_tokens,
        },
    )

    tools = _create_k8s_mcp_tools()

    # Build the prompt with context
    prompt_parts = []
    if memories:
        prompt_parts.append(
            "Relevant context from memory:\n" + "\n".join(f"- {m}" for m in memories)
        )
    if conversation_history:
        history_lines = []
        for msg in conversation_history[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")[:500]
            history_lines.append(f"{role}: {content}")
        if history_lines:
            prompt_parts.append("Recent conversation:\n" + "\n".join(history_lines))
    if context:
        prompt_parts.append(f"Context from other agents:\n{context}")
    prompt_parts.append(user_message)
    full_prompt = "\n\n".join(prompt_parts)

    agent = Agent(
        model=model,
        system_prompt=agent_config.system_prompt,
        tools=tools,
        callback_handler=None,
    )

    activity.heartbeat("Running K8s agent loop")

    try:
        result = await agent.invoke_async(full_prompt)
        response_text = str(result)
        response_text = re.sub(r"<think>\s*</think>\s*", "", response_text).strip()
        activity.heartbeat("K8s agent complete")
        logger.info(f"K8s agent complete: {response_text[:200]}")
        return {
            "response_text": response_text,
            "stop_reason": str(result.stop_reason),
        }
    except Exception as e:
        logger.error(f"K8s agent error: {e}", exc_info=True)
        return {
            "response_text": f"The Kubernetes agent encountered an error: {e}",
            "stop_reason": "error",
        }
```

---

### Step 5: Code Specialist Agent

**File:** `kubani/nexus/agents/code_agent.py`

The code agent reuses the existing workspace tools from `kubani/nexus/tools/strands_tools.py`. It has no MCP gateway access -- only local filesystem tools.

```python
"""Code specialist sub-agent.

Handles coding tasks: reading, writing, and editing files, running shell
commands, creating scripts, and registering skills. Operates within a
sandboxed workspace with restricted filesystem access.

This agent uses the existing workspace tools (read_file, write_file,
edit_file, bash, register_skill) from kubani.nexus.tools.strands_tools.
It does NOT have MCP gateway access.

Usage (as Temporal activity):
    result = await workflow.execute_activity(
        "run_code_agent_turn",
        args=[{ ... }],
        start_to_close_timeout=timedelta(minutes=10),
    )
"""

from __future__ import annotations

import logging
import re
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)


@activity.defn
async def run_code_agent_turn(input_data: dict[str, Any]) -> dict[str, Any]:
    """Run a full turn of the Code specialist agent.

    Creates a Strands Agent with workspace tools (read, write, edit, bash,
    register_skill) and the code-focused system prompt.

    Args:
        input_data: Dict containing:
            - user_message: str - The task for this agent.
            - conversation_history: list[dict] - Recent conversation.
            - memories: list[str] - Relevant memories.
            - context: str - Results from previous agents (optional).
            - user_id: str - For workspace resolution.

    Returns:
        Dict with response_text and stop_reason.
    """
    user_message = input_data.get("user_message", "")
    conversation_history = input_data.get("conversation_history", [])
    memories = input_data.get("memories", [])
    context = input_data.get("context", "")
    user_id = input_data.get("user_id", "default")

    activity.heartbeat("Creating Code agent")
    logger.info(f"Code agent: user={user_id}, msg={user_message[:100]}")

    from kubani.framework.config import get_llm_config
    from kubani.nexus.agents.registry import SubAgentRegistry
    from kubani.nexus.tools.core import get_workspace
    from kubani.nexus.tools.strands_tools import create_tools
    from strands import Agent
    from strands.models.openai import OpenAIModel

    llm_config = get_llm_config()
    registry = SubAgentRegistry()
    agent_config = registry.get("code")
    workspace = get_workspace(user_id)
    tools = create_tools(workspace)

    model = OpenAIModel(
        client_args={
            "api_key": llm_config.api_key or "not-needed",
            "base_url": llm_config.api_url,
        },
        model_id=llm_config.model,
        params={
            "temperature": llm_config.temperature,
            "max_tokens": agent_config.max_tokens,
        },
    )

    # Build the prompt with context
    prompt_parts = []
    if memories:
        prompt_parts.append(
            "Relevant context from memory:\n" + "\n".join(f"- {m}" for m in memories)
        )
    if conversation_history:
        history_lines = []
        for msg in conversation_history[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")[:500]
            history_lines.append(f"{role}: {content}")
        if history_lines:
            prompt_parts.append("Recent conversation:\n" + "\n".join(history_lines))
    if context:
        prompt_parts.append(f"Context from other agents:\n{context}")
    prompt_parts.append(user_message)
    full_prompt = "\n\n".join(prompt_parts)

    agent = Agent(
        model=model,
        system_prompt=agent_config.system_prompt,
        tools=tools,
        callback_handler=None,
    )

    activity.heartbeat("Running Code agent loop")

    try:
        result = await agent.invoke_async(full_prompt)
        response_text = str(result)
        response_text = re.sub(r"<think>\s*</think>\s*", "", response_text).strip()
        activity.heartbeat("Code agent complete")
        logger.info(f"Code agent complete: {response_text[:200]}")
        return {
            "response_text": response_text,
            "stop_reason": str(result.stop_reason),
        }
    except Exception as e:
        logger.error(f"Code agent error: {e}", exc_info=True)
        return {
            "response_text": f"The Code agent encountered an error: {e}",
            "stop_reason": "error",
        }
```

---

### Step 6: Research Specialist Agent

**File:** `kubani/nexus/agents/research_agent.py`

The research agent accesses Memory and Qdrant MCP tools through the gateway.

```python
"""Research specialist sub-agent.

Handles information retrieval and synthesis: searching vector memory
(Qdrant), querying past conversations, and synthesizing findings.

This agent accesses MCP tools through the MCP Gateway with the
nexus-research policy, which allows: qdrant + arxiv custom tools.

Usage (as Temporal activity):
    result = await workflow.execute_activity(
        "run_research_agent_turn",
        args=[{ ... }],
        start_to_close_timeout=timedelta(minutes=3),
    )
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx
from temporalio import activity

logger = logging.getLogger(__name__)


def _create_research_mcp_tools() -> list:
    """Create Strands @tool wrappers for research MCP gateway tools.

    Returns:
        List of Strands tool instances.
    """
    from strands import tool

    gateway_url = os.environ.get("MCP_GATEWAY_URL", "http://localhost:8085")
    policy_name = "nexus-research"

    async def _call_gateway(tool_name: str, arguments: dict[str, Any]) -> str:
        """Call the MCP gateway with policy headers."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{gateway_url}/call",
                json={
                    "tool": tool_name,
                    "arguments": arguments,
                },
                headers={"X-Agent-Policy": policy_name},
            )
            if response.status_code == 403:
                return f"Error: Tool '{tool_name}' blocked by policy"
            response.raise_for_status()
            data = response.json()
            if data.get("error"):
                return f"Error: {data['error']}"
            return data.get("result", str(data))

    @tool
    async def search_memory(query: str, user_id: str = "default", limit: int = 10) -> str:
        """Search the agent's memory for relevant past knowledge and conversations.

        Args:
            query: Semantic search query.
            user_id: Filter memories by user.
            limit: Maximum number of results to return.
        """
        return await _call_gateway("memory.search", {
            "query": query,
            "user_id": user_id,
            "limit": limit,
        })

    @tool
    async def store_memory(content: str, user_id: str = "default", metadata: str = "") -> str:
        """Store a new piece of knowledge or insight in memory.

        Args:
            content: The knowledge or insight to store.
            user_id: The user this memory belongs to.
            metadata: Optional JSON string of additional metadata.
        """
        import json

        meta = {}
        if metadata:
            try:
                meta = json.loads(metadata)
            except json.JSONDecodeError:
                meta = {"note": metadata}
        return await _call_gateway("memory.add", {
            "content": content,
            "user_id": user_id,
            "metadata": meta,
        })

    @tool
    async def get_all_memories(user_id: str = "default", limit: int = 50) -> str:
        """Retrieve all stored memories for a user.

        Args:
            user_id: The user to retrieve memories for.
            limit: Maximum number of memories to return.
        """
        return await _call_gateway("memory.get_all", {
            "user_id": user_id,
            "limit": limit,
        })

    @tool
    async def search_vectors(collection: str, query: str, limit: int = 10) -> str:
        """Search a Qdrant vector collection by semantic similarity.

        Args:
            collection: The Qdrant collection name (e.g., "skills", "kubani_memory").
            query: The search query text (will be embedded automatically).
            limit: Maximum number of results.
        """
        return await _call_gateway("qdrant.search", {
            "collection": collection,
            "query": query,
            "limit": limit,
        })

    @tool
    async def list_collections() -> str:
        """List all available Qdrant vector collections."""
        return await _call_gateway("qdrant.list_collections", {})

    @tool
    async def send_discord_message(channel: str, message: str) -> str:
        """Send a message to a Discord channel.

        Args:
            channel: Discord channel name or ID.
            message: Message text to send.
        """
        return await _call_gateway("discord.send_message", {
            "channel": channel,
            "content": message,
        })

    return [
        search_memory,
        store_memory,
        get_all_memories,
        search_vectors,
        list_collections,
        send_discord_message,
    ]


@activity.defn
async def run_research_agent_turn(input_data: dict[str, Any]) -> dict[str, Any]:
    """Run a full turn of the Research specialist agent.

    Args:
        input_data: Dict containing:
            - user_message: str - The task for this agent.
            - conversation_history: list[dict] - Recent conversation.
            - memories: list[str] - Pre-recalled memories.
            - context: str - Results from previous agents (optional).
            - user_id: str - For memory scoping.

    Returns:
        Dict with response_text and stop_reason.
    """
    user_message = input_data.get("user_message", "")
    conversation_history = input_data.get("conversation_history", [])
    memories = input_data.get("memories", [])
    context = input_data.get("context", "")
    user_id = input_data.get("user_id", "default")

    activity.heartbeat("Creating Research agent")
    logger.info(f"Research agent: user={user_id}, msg={user_message[:100]}")

    from kubani.framework.config import get_llm_config
    from kubani.nexus.agents.registry import SubAgentRegistry
    from strands import Agent
    from strands.models.openai import OpenAIModel

    llm_config = get_llm_config()
    registry = SubAgentRegistry()
    agent_config = registry.get("research")

    model = OpenAIModel(
        client_args={
            "api_key": llm_config.api_key or "not-needed",
            "base_url": llm_config.api_url,
        },
        model_id=llm_config.model,
        params={
            "temperature": llm_config.temperature,
            "max_tokens": agent_config.max_tokens,
        },
    )

    tools = _create_research_mcp_tools()

    # Build the prompt with context
    prompt_parts = []
    if memories:
        prompt_parts.append(
            "Pre-recalled memories:\n" + "\n".join(f"- {m}" for m in memories)
        )
    if conversation_history:
        history_lines = []
        for msg in conversation_history[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")[:500]
            history_lines.append(f"{role}: {content}")
        if history_lines:
            prompt_parts.append("Recent conversation:\n" + "\n".join(history_lines))
    if context:
        prompt_parts.append(f"Context from other agents:\n{context}")
    prompt_parts.append(user_message)
    full_prompt = "\n\n".join(prompt_parts)

    agent = Agent(
        model=model,
        system_prompt=agent_config.system_prompt,
        tools=tools,
        callback_handler=None,
    )

    activity.heartbeat("Running Research agent loop")

    try:
        result = await agent.invoke_async(full_prompt)
        response_text = str(result)
        response_text = re.sub(r"<think>\s*</think>\s*", "", response_text).strip()
        activity.heartbeat("Research agent complete")
        logger.info(f"Research agent complete: {response_text[:200]}")
        return {
            "response_text": response_text,
            "stop_reason": str(result.stop_reason),
        }
    except Exception as e:
        logger.error(f"Research agent error: {e}", exc_info=True)
        return {
            "response_text": f"The Research agent encountered an error: {e}",
            "stop_reason": "error",
        }
```

---

I will continue with Steps 7-21 in the next sections of this document. Due to the document's length, the remaining steps are continued below.

---

### Step 7: Per-Agent Container Isolation

**File:** `kubani/nexus/agents/isolation.py`

This module defines container configuration per agent type. In Phase 3, isolation is enforced at two levels: (1) MCP Gateway policies control which tools each agent can access, and (2) Kubernetes NetworkPolicies control network egress per pod. The container isolation module provides configuration that the deployment manifests consume.

```python
"""Per-agent isolation configuration.

Defines resource limits, network access, and tool permissions for each
sub-agent type. This configuration is consumed by:
1. Temporal activity setup (resource hints).
2. Kubernetes deployment manifests (resource limits).
3. MCP Gateway policy selection (tool access).

In Phase 3, all sub-agents run in the same Temporal worker process.
Isolation is enforced by:
- MCP Gateway policies (which tools each agent can call).
- Kubernetes NetworkPolicies (which network endpoints each pod can reach).
- Workspace sandboxing (code agent runs in restricted filesystem).

A future Phase 4 could move each agent to its own container/pod for
stronger isolation, using Temporal's activity-to-worker routing.

Usage:
    from kubani.nexus.agents.isolation import get_agent_isolation

    iso = get_agent_isolation("k8s")
    print(iso.cpu_limit)      # "1000m"
    print(iso.memory_limit)   # "1Gi"
    print(iso.network_access) # ["mcp-gateway", "kubernetes-api"]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentIsolation:
    """Isolation configuration for a sub-agent.

    Attributes:
        agent_name: The sub-agent identifier.
        cpu_request: Kubernetes CPU request (e.g., "200m").
        cpu_limit: Kubernetes CPU limit (e.g., "1000m").
        memory_request: Kubernetes memory request (e.g., "256Mi").
        memory_limit: Kubernetes memory limit (e.g., "1Gi").
        network_access: List of allowed network endpoints.
        filesystem_access: Type of filesystem access ("none", "workspace", "readonly").
        mcp_policy: Name of the MCP gateway policy file.
        max_concurrent: Maximum concurrent instances of this agent type.
    """

    agent_name: str
    cpu_request: str = "200m"
    cpu_limit: str = "1000m"
    memory_request: str = "256Mi"
    memory_limit: str = "1Gi"
    network_access: list[str] = field(default_factory=list)
    filesystem_access: str = "none"
    mcp_policy: str = "default"
    max_concurrent: int = 3


# Pre-defined isolation configurations
_ISOLATION_CONFIGS: dict[str, AgentIsolation] = {
    "k8s": AgentIsolation(
        agent_name="k8s",
        cpu_request="200m",
        cpu_limit="1000m",
        memory_request="256Mi",
        memory_limit="1Gi",
        network_access=[
            "mcp-gateway",
            "kubernetes-api",
            "prometheus",
        ],
        filesystem_access="none",
        mcp_policy="nexus-k8s",
        max_concurrent=3,
    ),
    "workflow": AgentIsolation(
        agent_name="workflow",
        cpu_request="100m",
        cpu_limit="500m",
        memory_request="256Mi",
        memory_limit="512Mi",
        network_access=[
            "mcp-gateway",
        ],
        filesystem_access="none",
        mcp_policy="nexus-workflow",
        max_concurrent=3,
    ),
    "comms": AgentIsolation(
        agent_name="comms",
        cpu_request="100m",
        cpu_limit="500m",
        memory_request="256Mi",
        memory_limit="512Mi",
        network_access=[
            "mcp-gateway",
        ],
        filesystem_access="none",
        mcp_policy="nexus-comms",
        max_concurrent=3,
    ),
    "research": AgentIsolation(
        agent_name="research",
        cpu_request="100m",
        cpu_limit="500m",
        memory_request="256Mi",
        memory_limit="512Mi",
        network_access=[
            "mcp-gateway",
            "internet",  # for ArXiv API
        ],
        filesystem_access="none",
        mcp_policy="nexus-research",
        max_concurrent=3,
    ),
    "code": AgentIsolation(
        agent_name="code",
        cpu_request="200m",
        cpu_limit="2000m",
        memory_request="512Mi",
        memory_limit="2Gi",
        network_access=[],
        filesystem_access="workspace",
        mcp_policy="nexus-code",
        max_concurrent=1,
    ),
    "general": AgentIsolation(
        agent_name="general",
        cpu_request="200m",
        cpu_limit="1000m",
        memory_request="256Mi",
        memory_limit="1Gi",
        network_access=[
            "mcp-gateway",
            "internet",  # for fetch and web_search
        ],
        filesystem_access="workspace",
        mcp_policy="nexus",
        max_concurrent=2,
    ),
    "router": AgentIsolation(
        agent_name="router",
        cpu_request="100m",
        cpu_limit="500m",
        memory_request="128Mi",
        memory_limit="256Mi",
        network_access=[],
        filesystem_access="none",
        mcp_policy="default",
        max_concurrent=5,
    ),
}


def get_agent_isolation(agent_name: str) -> AgentIsolation:
    """Get the isolation configuration for a sub-agent.

    Args:
        agent_name: The sub-agent identifier.

    Returns:
        AgentIsolation configuration. Returns a default if not found.
    """
    if agent_name in _ISOLATION_CONFIGS:
        return _ISOLATION_CONFIGS[agent_name]
    logger.warning(f"No isolation config for agent '{agent_name}', using default")
    return AgentIsolation(agent_name=agent_name)


def list_isolation_configs() -> list[AgentIsolation]:
    """List all isolation configurations.

    Returns:
        List of all AgentIsolation instances.
    """
    return list(_ISOLATION_CONFIGS.values())
```

---

### Step 8: System Prompts

Create the directory and all prompt files.

**File:** `kubani/nexus/agents/prompts/k8s_agent.md`

```markdown
/no_think
You are the Kubernetes specialist agent for Kubani Nexus. You diagnose
and resolve Kubernetes cluster issues.

## Your Capabilities

You have tools to interact with the Kubernetes cluster:
- kubectl_get: List and inspect resources (pods, deployments, services, nodes, events).
- kubectl_describe: Get detailed information about a specific resource.
- kubectl_logs: Read pod logs (current and previous containers).
- kubectl_top: Check CPU and memory usage for nodes and pods.
- kubectl_events: View cluster events filtered by namespace or type.
- kubectl_rollout: Manage deployment rollouts (status, restart, undo).
- kubectl_scale: Scale deployments up or down.
- send_discord_message: Notify team members via Discord.
- search_memory: Search past knowledge for relevant context.

## Cluster Context

The Kubani cluster runs on bare metal with these key namespaces:
- ai-agents: AI monitoring and agent workloads
- nexus: The Nexus agent system (this system)
- vllm: LLM inference servers (GPU workloads)
- temporal: Temporal workflow engine
- database: PostgreSQL, Qdrant, Neo4j, Redis
- flux-system: GitOps reconciliation
- cert-manager: TLS certificate management
- monitoring: Prometheus, Grafana

## Approach

1. Start by gathering information before acting. Use kubectl_get and kubectl_events first.
2. For pod issues, check events, then describe the pod, then check logs.
3. For resource pressure, check kubectl_top for nodes and pods.
4. Explain your findings clearly with specific resource names, timestamps, and error messages.
5. If remediation is needed and safe (e.g., rollout restart), offer to do it.
6. For destructive actions (delete, scale to 0), explain the risk first.

## Response Style

- Be concise and technical.
- Include specific resource names, namespaces, and relevant log excerpts.
- Use Markdown formatting: headers, code blocks for logs, bullet lists for findings.
- If you cannot determine the cause, say so and suggest next steps.
```

**File:** `kubani/nexus/agents/prompts/code_agent.md`

```markdown
/no_think
You are the Code specialist agent for Kubani Nexus. You help users with
coding tasks within a sandboxed workspace.

## Your Capabilities

You have tools for file operations and command execution:
- read_file(path): Read a file from the workspace with line numbers.
- write_file(path, content): Create or overwrite a file.
- edit_file(path, old_text, new_text): Search-and-replace in a file. old_text must be unique.
- bash(command, timeout): Run a shell command in the workspace.
- register_skill(name, file_path, description): Register a Python skill for reuse.

## Rules

1. Always read a file before editing it. Never blindly edit.
2. Use edit_file for surgical changes to existing files. Use write_file for new files.
3. If a bash command is blocked or needs approval, explain what you wanted to do and why.
4. All file paths are relative to the workspace root. You cannot access files outside it.
5. Keep file sizes reasonable (under 1MB per file).
6. When creating scripts, include comments explaining what the code does.
7. When editing, provide enough context in old_text to ensure uniqueness.

## Response Style

- Show what you did: mention file paths, commands run, and outcomes.
- For file creation, briefly summarize the content rather than quoting it all.
- If something failed, explain the error and suggest a fix.
- Be concise. Focus on the task, not on explaining your process.
```

**File:** `kubani/nexus/agents/prompts/research_agent.md`

```markdown
/no_think
You are the Research specialist agent for Kubani Nexus. You retrieve,
analyze, and synthesize information from the agent's memory systems.

## Your Capabilities

You have tools for memory and knowledge retrieval:
- search_memory(query, user_id, limit): Semantic search across stored memories.
- store_memory(content, user_id, metadata): Store new knowledge or insights.
- get_all_memories(user_id, limit): Retrieve all memories for a user.
- search_vectors(collection, query, limit): Search Qdrant vector collections directly.
- list_collections(): List available vector collections.
- send_discord_message(channel, message): Share findings via Discord.

## Available Collections

The Qdrant vector database has these collections:
- nexus_memory: User memories and conversation context.
- skills: Registered skill definitions and metadata.
- kubani_memory: General knowledge base.
- learnings: Agent learning outcomes and patterns.

## Approach

1. Start with a semantic search to find relevant memories or knowledge.
2. If the initial search is too broad, refine with more specific queries.
3. Synthesize findings into a clear, structured summary.
4. When storing new memories, include relevant metadata for future retrieval.
5. If you find no relevant information, say so clearly rather than guessing.

## Response Style

- Present findings in a structured format with headers and bullet points.
- Quote relevant excerpts from memories when they add value.
- Distinguish between facts from memory and your own analysis.
- If multiple memories conflict, note the discrepancy.
- Be thorough but concise.
```

**File:** `kubani/nexus/agents/prompts/general_agent.md`

```markdown
/no_think
You are Nexus, the Kubani AI assistant. You handle general conversation,
questions about the Kubani system, greetings, and help requests.

## Your Capabilities

You have basic workspace tools:
- read_file(path): Read a file from the workspace.
- write_file(path, content): Create or overwrite a file.
- edit_file(path, old_text, new_text): Edit a file.
- bash(command, timeout): Run a shell command.
- register_skill(name, file_path, description): Register a skill.

## About Kubani

Kubani is an AI agent platform running on a bare-metal Kubernetes cluster.
It includes:
- Nexus: The conversational AI agent (you).
- MCP Servers: Standardized tool interfaces for Temporal, Qdrant, Memory, Discord.
- Registry: Metadata registry for agents, skills, and models.
- Learning System: Continuous learning with Critic, Reflection, and Skill Synthesizer agents.
- Syndicates: Multi-agent orchestration groups.

## Response Style

- Be friendly and helpful.
- For questions about Kubani, provide accurate information based on your knowledge.
- For greetings, respond naturally without being verbose.
- If the user's request would be better handled by a specialist (K8s, code, research),
  let them know you can help with that or suggest they ask more specifically.
- Use Markdown formatting for structured responses.
- Be concise. Most general responses should be 1-3 paragraphs.
```

---

### Step 9: Modified Workflow

**File:** `kubani/nexus/orchestrator/workflow.py` (full replacement)

This is the complete updated workflow that routes to sub-agents, supports multi-agent execution, and handles result synthesis.

```python
"""Nexus Orchestrator Temporal Workflow — Swarm Architecture.

This is the core 'always-on' workflow that represents the Nexus agent's
lifecycle. Phase 3 evolves it from a monolithic agent into an orchestrator
that delegates to specialized sub-agents.

Agentic loop (Swarm):
    1. Start -> IDLE
    2. Receive user message signal -> PROCESSING
    3. Recall memories
    4. Route intent (classify which sub-agent(s) should handle)
    5. Dispatch to sub-agent activity(ies):
       - Sequential: run agents one after another, passing context
       - Parallel: run agents concurrently (when independent)
    6. Synthesize results (if multi-agent)
    7. Publish response -> IDLE
    8. Wait for next signal -> goto 2
    9. After N iterations -> continue-as-new
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from kubani.nexus.models.messages import (
        AgentMessage,
        ConversationMessage,
        MessageRole,
        MessageSource,
        UserMessage,
    )
    from kubani.nexus.models.state import (
        ExecutionPlan,
        NexusStatus,
        NexusWorkflowState,
        PlanStep,
    )

logger = logging.getLogger(__name__)

LLM_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=3,
    non_retryable_error_types=["ValidationError"],
)

INFRA_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=5,
)

ROUTER_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
)

MAX_ITERATIONS_BEFORE_CONTINUE = 100

# Feature flag: set NEXUS_SWARM_MODE=false to revert to monolithic agent
SWARM_MODE = os.environ.get("NEXUS_SWARM_MODE", "true").lower() == "true"

# Map agent names to their activity function names
AGENT_ACTIVITY_MAP = {
    "k8s": "run_k8s_agent_turn",
    "code": "run_code_agent_turn",
    "research": "run_research_agent_turn",
    "general": "run_agent_turn",
}

# Map agent names to their timeouts
AGENT_TIMEOUT_MAP = {
    "k8s": timedelta(minutes=5),
    "code": timedelta(minutes=10),
    "research": timedelta(minutes=3),
    "general": timedelta(minutes=5),
}


@workflow.defn
class NexusOrchestratorWorkflow:
    """The core Nexus agent workflow with swarm architecture.

    Routes user messages to specialized sub-agents based on intent
    classification. Supports multi-agent tasks with sequential or
    parallel execution and result synthesis.
    """

    def __init__(self) -> None:
        self._state = NexusWorkflowState(user_id="default")
        self._pending_messages: list[dict[str, Any]] = []
        self._iteration_count = 0
        self._should_continue_as_new = False

    # =================================================================
    # Signals
    # =================================================================

    @workflow.signal
    async def user_message(self, message_data: dict[str, Any]) -> None:
        """Signal handler for incoming user messages."""
        self._pending_messages.append(message_data)

    @workflow.signal
    async def approval_decision(self, decision_data: dict[str, Any]) -> None:
        """Signal handler for HITL approval decisions."""
        self._pending_messages.append({
            **decision_data,
            "_type": "approval_decision",
        })

    # =================================================================
    # Queries
    # =================================================================

    @workflow.query
    def get_state(self) -> dict[str, Any]:
        """Query handler for the current workflow state."""
        return self._state.to_dict()

    @workflow.query
    def get_status(self) -> str:
        """Query handler for just the status string."""
        return self._state.status.value

    @workflow.query
    def get_current_plan(self) -> dict[str, Any] | None:
        """Query handler for the current execution plan."""
        if self._state.current_plan:
            return self._state.current_plan.model_dump(mode="json")
        return None

    # =================================================================
    # Main Workflow Loop
    # =================================================================

    @workflow.run
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Main workflow execution loop."""
        self._state.user_id = input_data.get("user_id", "default")
        self._state.conversation_id = input_data.get("conversation_id", "")

        restored = input_data.get("restored_history", [])
        for msg_data in restored:
            self._state.add_message(ConversationMessage.model_validate(msg_data))

        workflow.logger.info(
            f"Nexus workflow started for user {self._state.user_id}"
        )

        while not self._should_continue_as_new:
            await workflow.wait_condition(lambda: len(self._pending_messages) > 0)

            while self._pending_messages:
                message_data = self._pending_messages.pop(0)

                if message_data.get("_type") == "approval_decision":
                    continue

                await self._process_message(message_data)

                self._iteration_count += 1
                if self._iteration_count >= MAX_ITERATIONS_BEFORE_CONTINUE:
                    self._should_continue_as_new = True
                    break

        workflow.logger.info("Continuing as new to reset history")
        workflow.continue_as_new(
            {
                "user_id": self._state.user_id,
                "conversation_id": self._state.conversation_id,
                "restored_history": [
                    msg.model_dump(mode="json")
                    for msg in self._state.conversation_history[-20:]
                ],
            }
        )

    # =================================================================
    # Message Processing
    # =================================================================

    async def _process_message(self, message_data: dict[str, Any]) -> None:
        """Process a single user message using the swarm or monolithic path."""
        try:
            user_msg = UserMessage.from_dict(message_data)
        except Exception:
            workflow.logger.error(f"Invalid message data: {message_data}")
            return

        self._state.status = NexusStatus.PROCESSING
        self._state.conversation_id = user_msg.conversation_id

        self._state.add_message(ConversationMessage(
            role=MessageRole.USER,
            content=user_msg.text,
            source=user_msg.source,
        ))

        await workflow.execute_activity(
            "persist_message",
            args=[{
                "conversation_id": user_msg.conversation_id,
                "user_id": user_msg.user_id,
                "role": "user",
                "content": user_msg.text,
                "source": user_msg.source.value,
            }],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=INFRA_RETRY_POLICY,
        )

        memories_result = await workflow.execute_activity(
            "recall_memories_activity",
            args=[{
                "query": user_msg.text,
                "user_id": user_msg.user_id,
                "limit": 5,
            }],
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=INFRA_RETRY_POLICY,
        )
        memories = memories_result.get("memories", [])

        if SWARM_MODE:
            response_text = await self._run_swarm(user_msg, memories)
        else:
            response_text = await self._run_monolithic(user_msg, memories)

        await self._publish_and_persist_response(
            user_msg.conversation_id, user_msg.user_id, response_text
        )

        await workflow.execute_activity(
            "store_memory_activity",
            args=[{
                "content": f"User asked: {user_msg.text}\nI responded: {response_text[:200]}",
                "user_id": user_msg.user_id,
                "metadata": {"conversation_id": user_msg.conversation_id},
            }],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=INFRA_RETRY_POLICY,
        )

        self._state.current_plan = None
        self._state.current_goal = None
        self._state.tool_call_history = []
        self._state.status = NexusStatus.IDLE

    # =================================================================
    # Swarm Path (Phase 3)
    # =================================================================

    async def _run_swarm(
        self, user_msg: UserMessage, memories: list[str]
    ) -> str:
        """Run the swarm architecture: route, dispatch, synthesize.

        Args:
            user_msg: The user message being processed.
            memories: Relevant memories from the memory system.

        Returns:
            The final response text.
        """
        # Step 1: Route intent
        self._state.status = NexusStatus.PLANNING

        from kubani.nexus.agents.registry import SubAgentRegistry

        registry = SubAgentRegistry()

        routing = await workflow.execute_activity(
            "route_intent",
            args=[{
                "user_message": user_msg.text,
                "agent_descriptions": registry.get_router_description(),
                "agent_names": registry.get_names(),
                "conversation_history": [
                    msg.model_dump(mode="json")
                    for msg in self._state.conversation_history[-10:]
                ],
            }],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=ROUTER_RETRY_POLICY,
        )

        agents = routing.get("agents", ["general"])
        rewritten_tasks = routing.get("rewritten_tasks", {})
        is_parallel = routing.get("parallel", False)

        workflow.logger.info(
            f"Routed to agents: {agents}, parallel={is_parallel}"
        )

        # Step 2: Dispatch to sub-agents
        self._state.status = NexusStatus.EXECUTING

        conversation_history = [
            msg.model_dump(mode="json")
            for msg in self._state.conversation_history
        ]

        if len(agents) == 1:
            # Single agent — simple dispatch
            agent_name = agents[0]
            task = rewritten_tasks.get(agent_name, user_msg.text)
            result = await self._dispatch_agent(
                agent_name, task, conversation_history, memories, user_msg.user_id, ""
            )
            return result.get("response_text", "Done.")

        # Multi-agent execution
        if is_parallel:
            return await self._run_parallel_agents(
                agents, rewritten_tasks, conversation_history, memories,
                user_msg.user_id, user_msg.text,
            )
        else:
            return await self._run_sequential_agents(
                agents, rewritten_tasks, conversation_history, memories,
                user_msg.user_id, user_msg.text,
            )

    async def _run_sequential_agents(
        self,
        agents: list[str],
        rewritten_tasks: dict[str, str],
        conversation_history: list[dict],
        memories: list[str],
        user_id: str,
        original_message: str,
    ) -> str:
        """Run multiple agents sequentially, passing context forward.

        Each agent receives the results of all previous agents as context.

        Returns:
            Synthesized response text.
        """
        agent_results = []
        accumulated_context = ""

        for agent_name in agents:
            task = rewritten_tasks.get(agent_name, original_message)
            result = await self._dispatch_agent(
                agent_name, task, conversation_history, memories,
                user_id, accumulated_context,
            )
            agent_results.append({
                "agent": agent_name,
                "response_text": result.get("response_text", ""),
                "stop_reason": result.get("stop_reason", "unknown"),
            })
            accumulated_context += (
                f"\n\n[{agent_name} agent result]:\n"
                + result.get("response_text", "")
            )

        # Synthesize
        synthesis = await workflow.execute_activity(
            "run_synthesis",
            args=[{
                "original_message": original_message,
                "agent_results": agent_results,
            }],
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=LLM_RETRY_POLICY,
        )
        return synthesis.get("response_text", "Done.")

    async def _run_parallel_agents(
        self,
        agents: list[str],
        rewritten_tasks: dict[str, str],
        conversation_history: list[dict],
        memories: list[str],
        user_id: str,
        original_message: str,
    ) -> str:
        """Run multiple agents in parallel.

        All agents run concurrently with no shared context between them.

        Returns:
            Synthesized response text.
        """
        # Start all agent activities
        handles = []
        for agent_name in agents:
            task = rewritten_tasks.get(agent_name, original_message)
            activity_name = AGENT_ACTIVITY_MAP.get(agent_name, "run_agent_turn")
            timeout = AGENT_TIMEOUT_MAP.get(agent_name, timedelta(minutes=5))

            handle = workflow.start_activity(
                activity_name,
                args=[{
                    "user_message": task,
                    "conversation_history": conversation_history,
                    "memories": memories,
                    "context": "",
                    "user_id": user_id,
                }],
                start_to_close_timeout=timeout,
                heartbeat_timeout=timedelta(minutes=2),
                retry_policy=LLM_RETRY_POLICY,
            )
            handles.append((agent_name, handle))

        # Collect results
        agent_results = []
        for agent_name, handle in handles:
            try:
                result = await handle
                agent_results.append({
                    "agent": agent_name,
                    "response_text": result.get("response_text", ""),
                    "stop_reason": result.get("stop_reason", "unknown"),
                })
            except Exception as e:
                workflow.logger.error(f"Agent {agent_name} failed: {e}")
                agent_results.append({
                    "agent": agent_name,
                    "response_text": f"Error: {e}",
                    "stop_reason": "error",
                })

        # Synthesize
        synthesis = await workflow.execute_activity(
            "run_synthesis",
            args=[{
                "original_message": original_message,
                "agent_results": agent_results,
            }],
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=LLM_RETRY_POLICY,
        )
        return synthesis.get("response_text", "Done.")

    async def _dispatch_agent(
        self,
        agent_name: str,
        task: str,
        conversation_history: list[dict],
        memories: list[str],
        user_id: str,
        context: str,
    ) -> dict[str, Any]:
        """Dispatch a task to a specific sub-agent activity.

        Args:
            agent_name: The sub-agent to invoke.
            task: The task description for this agent.
            conversation_history: Recent conversation messages.
            memories: Relevant memories.
            user_id: The user ID.
            context: Results from previous agents (for sequential execution).

        Returns:
            Dict with response_text and stop_reason.
        """
        activity_name = AGENT_ACTIVITY_MAP.get(agent_name, "run_agent_turn")
        timeout = AGENT_TIMEOUT_MAP.get(agent_name, timedelta(minutes=5))

        workflow.logger.info(f"Dispatching to {agent_name} via {activity_name}")

        result = await workflow.execute_activity(
            activity_name,
            args=[{
                "user_message": task,
                "conversation_history": conversation_history,
                "memories": memories,
                "context": context,
                "user_id": user_id,
            }],
            start_to_close_timeout=timeout,
            heartbeat_timeout=timedelta(minutes=2),
            retry_policy=LLM_RETRY_POLICY,
        )

        return result

    # =================================================================
    # Monolithic Path (Fallback / Phase 2 compatibility)
    # =================================================================

    async def _run_monolithic(
        self, user_msg: UserMessage, memories: list[str]
    ) -> str:
        """Run the monolithic agentic loop (Phase 2 behavior).

        This is the fallback path when NEXUS_SWARM_MODE=false.
        Uses the original run_agent_turn activity with all tools.
        """
        self._state.status = NexusStatus.PROCESSING

        result = await workflow.execute_activity(
            "run_agent_turn",
            args=[{
                "user_message": user_msg.text,
                "conversation_history": [
                    msg.model_dump(mode="json")
                    for msg in self._state.conversation_history
                ],
                "memories": memories,
                "user_id": user_msg.user_id,
            }],
            start_to_close_timeout=timedelta(minutes=10),
            heartbeat_timeout=timedelta(minutes=2),
            retry_policy=LLM_RETRY_POLICY,
        )

        return result.get("response_text", "Done.")

    # =================================================================
    # Helpers
    # =================================================================

    async def _publish_and_persist_response(
        self, conversation_id: str, user_id: str, text: str
    ) -> None:
        """Publish a response via pub/sub and persist it to the database."""
        self._state.add_message(ConversationMessage(
            role=MessageRole.ASSISTANT,
            content=text,
            source=MessageSource.SYSTEM,
        ))

        await workflow.execute_activity(
            "persist_message",
            args=[{
                "conversation_id": conversation_id,
                "user_id": user_id,
                "role": "assistant",
                "content": text,
                "source": "system",
            }],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=INFRA_RETRY_POLICY,
        )

        await workflow.execute_activity(
            "publish_response_activity",
            args=[{
                "conversation_id": conversation_id,
                "text": text,
            }],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=INFRA_RETRY_POLICY,
        )
```

---

### Step 10: Modified Worker

**File:** `kubani/nexus/orchestrator/worker.py` (full replacement)

Registers all new activities alongside the existing ones.

```python
"""Nexus Orchestrator Temporal Worker — Swarm Architecture.

Entry point for the Nexus syndicate's Temporal worker. Registers the
NexusOrchestratorWorkflow and all activities including the new sub-agent
activities from Phase 3.

Usage:
    python -m kubani.nexus.orchestrator.worker
"""

from __future__ import annotations

import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

TEMPORAL_NAMESPACE = "nexus"
TASK_QUEUE = "nexus-orchestrator"


def get_temporal_settings() -> tuple[str, str]:
    """Get Temporal connection settings from environment."""
    host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", TEMPORAL_NAMESPACE)
    return host, namespace


def get_activities() -> list:
    """Get all activities needed by the Nexus workflows."""
    from kubani.nexus.orchestrator.activities import (
        execute_skill_activity,
        generate_response,
        log_action_activity,
        notify_discord_activity,
        persist_message,
        plan_response,
        publish_response_activity,
        recall_memories_activity,
        run_agent_turn,
        store_memory_activity,
    )

    # Phase 3: Sub-agent activities
    from kubani.nexus.agents.code_agent import run_code_agent_turn
    from kubani.nexus.agents.k8s_agent import run_k8s_agent_turn
    from kubani.nexus.agents.orchestrator import run_synthesis
    from kubani.nexus.agents.research_agent import run_research_agent_turn
    from kubani.nexus.agents.router import route_intent

    return [
        # Phase 3: Swarm activities
        route_intent,
        run_k8s_agent_turn,
        run_code_agent_turn,
        run_research_agent_turn,
        run_synthesis,
        # Phase 1-2: Monolithic agent (kept as fallback + general agent)
        run_agent_turn,
        # Legacy planning (backward compatibility)
        plan_response,
        execute_skill_activity,
        generate_response,
        # Infrastructure
        persist_message,
        log_action_activity,
        publish_response_activity,
        recall_memories_activity,
        store_memory_activity,
        notify_discord_activity,
    ]


def get_workflows() -> list:
    """Get all workflows for the Nexus syndicate."""
    from kubani.nexus.orchestrator.workflow import NexusOrchestratorWorkflow

    return [NexusOrchestratorWorkflow]


async def run_worker() -> None:
    """Run the Nexus Orchestrator worker."""
    temporal_host, temporal_namespace = get_temporal_settings()

    logger.info(f"Connecting to Temporal at {temporal_host}")
    logger.info(f"Namespace: {temporal_namespace}")
    logger.info(f"Task queue: {TASK_QUEUE}")

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    workflows = get_workflows()
    activities = get_activities()

    logger.info(
        f"Registering {len(workflows)} workflows: "
        f"{[w.__name__ for w in workflows]}"
    )
    logger.info(f"Registering {len(activities)} activities")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=workflows,
        activities=activities,
    )

    logger.info("Starting Nexus Orchestrator worker (swarm mode)...")

    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        logger.info("Worker shutdown complete")


async def start_nexus_workflow(
    user_id: str = "default",
    conversation_id: str = "",
) -> str:
    """Start the Nexus orchestrator workflow."""
    temporal_host, temporal_namespace = get_temporal_settings()

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    from kubani.nexus.orchestrator.workflow import NexusOrchestratorWorkflow

    workflow_id = f"nexus-{user_id}"

    handle = await client.start_workflow(
        NexusOrchestratorWorkflow.run,
        {
            "user_id": user_id,
            "conversation_id": conversation_id,
        },
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    logger.info(f"Started Nexus workflow: {workflow_id}")
    return workflow_id


def main() -> None:
    """CLI entry point."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
```

---

### Step 11: MCP Gateway Policies

**File:** `kubani/mcp/registry/policies/nexus-k8s.json`

```json
{
  "allowedServers": [
    "kubernetes"
  ],
  "customTools": ["prometheus_query", "prometheus_query_range", "prometheus_alerts"],
  "requireApproval": [
    "kubernetes.delete",
    "kubernetes.scale",
    "kubernetes.rollout.undo"
  ],
  "auditLog": true,
  "namespaceRestrictions": {
    "deny": [
      "kube-system",
      "flux-system"
    ]
  },
  "rateLimits": {
    "maxCallsPerMinute": 60,
    "maxConcurrent": 5
  }
}
```

**File:** `kubani/mcp/registry/policies/nexus-workflow.json`

```json
{
  "allowedServers": [
    "temporal"
  ],
  "requireApproval": [
    "workflows.terminate",
    "workflows.cancel"
  ],
  "auditLog": true,
  "rateLimits": {
    "maxCallsPerMinute": 30,
    "maxConcurrent": 3
  }
}
```

**File:** `kubani/mcp/registry/policies/nexus-comms.json`

```json
{
  "allowedServers": [
    "discord"
  ],
  "requireApproval": [
    "channels.create",
    "channels.delete",
    "webhooks.create",
    "webhooks.delete"
  ],
  "auditLog": true,
  "rateLimits": {
    "maxCallsPerMinute": 30,
    "maxConcurrent": 3
  }
}
```

**File:** `kubani/mcp/registry/policies/nexus-research.json`

```json
{
  "allowedServers": [
    "qdrant"
  ],
  "customTools": ["arxiv_search", "arxiv_get_paper"],
  "requireApproval": [
    "collections.delete"
  ],
  "auditLog": true,
  "rateLimits": {
    "maxCallsPerMinute": 30,
    "maxConcurrent": 3
  }
}
```

**File:** `kubani/mcp/registry/policies/nexus-code.json`

```json
{
  "allowedServers": [],
  "requireApproval": [],
  "auditLog": true,
  "description": "Code agent has no MCP access. Uses workspace tools only.",
  "rateLimits": {
    "maxCallsPerMinute": 0,
    "maxConcurrent": 0
  }
}
```

**Note:** The `nexus.json` policy from Phase 1 (Memory + Skills) is used by the General (PI) agent fallback.

---

### Step 12: Kubernetes Network Policies

**File:** `infrastructure/gitops/apps/nexus/networkpolicy-orchestrator.yaml`

This NetworkPolicy allows the orchestrator pod to reach the MCP gateway, Temporal, Redis, and PostgreSQL. It denies direct Kubernetes API access (the K8s agent tools go through the MCP gateway, which itself has cluster access).

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: nexus-orchestrator-netpol
  namespace: nexus
  labels:
    app.kubernetes.io/name: nexus-orchestrator
    app.kubernetes.io/part-of: kubani
spec:
  podSelector:
    matchLabels:
      app: nexus-orchestrator
  policyTypes:
    - Egress
  egress:
    # Allow DNS resolution
    - to:
        - namespaceSelector: {}
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    # Allow MCP Gateway
    - to:
        - podSelector:
            matchLabels:
              app: mcp-gateway
      ports:
        - protocol: TCP
          port: 8085
    # Allow Temporal
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: temporal
      ports:
        - protocol: TCP
          port: 7233
    # Allow Redis
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: database
      ports:
        - protocol: TCP
          port: 6379
    # Allow PostgreSQL
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: database
      ports:
        - protocol: TCP
          port: 5432
    # Allow vLLM (LLM API)
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: vllm
      ports:
        - protocol: TCP
          port: 8000
    # Allow external HTTPS (for LLM API via ingress)
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
      ports:
        - protocol: TCP
          port: 443
```

---

## 5. Testing

### 5.1 Unit Tests for the Router

Test that the router correctly classifies messages and handles edge cases.

**File:** `tests/unit/nexus/test_router.py`

```python
"""Unit tests for the intent router."""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from kubani.nexus.agents.router import _extract_routing_json


class TestExtractRoutingJson:
    """Tests for _extract_routing_json parsing logic."""

    def test_valid_single_agent(self):
        raw = json.dumps({
            "agents": ["k8s"],
            "reasoning": "Kubernetes question",
            "parallel": False,
            "rewritten_tasks": {"k8s": "Check pod status"},
        })
        result = _extract_routing_json(raw, ["k8s", "code", "research", "general"])
        assert result["agents"] == ["k8s"]
        assert result["parallel"] is False

    def test_valid_multi_agent(self):
        raw = json.dumps({
            "agents": ["k8s", "code"],
            "reasoning": "Need data then write report",
            "parallel": False,
            "rewritten_tasks": {
                "k8s": "Get cluster status",
                "code": "Write report",
            },
        })
        result = _extract_routing_json(raw, ["k8s", "code", "research", "general"])
        assert result["agents"] == ["k8s", "code"]

    def test_code_fences(self):
        raw = '```json\n{"agents": ["research"], "reasoning": "search", "parallel": false, "rewritten_tasks": {"research": "find info"}}\n```'
        result = _extract_routing_json(raw, ["k8s", "code", "research", "general"])
        assert result["agents"] == ["research"]

    def test_invalid_agent_name(self):
        raw = json.dumps({
            "agents": ["nonexistent"],
            "reasoning": "bad",
            "parallel": False,
            "rewritten_tasks": {},
        })
        result = _extract_routing_json(raw, ["k8s", "code", "research", "general"])
        assert result["agents"] == ["general"]

    def test_invalid_json(self):
        result = _extract_routing_json("not json at all", ["k8s", "code", "general"])
        assert result["agents"] == ["general"]

    def test_thinking_tags_stripped(self):
        raw = '<think>hmm let me think</think>{"agents": ["k8s"], "reasoning": "k8s question", "parallel": false, "rewritten_tasks": {"k8s": "check pods"}}'
        result = _extract_routing_json(raw, ["k8s", "code", "research", "general"])
        assert result["agents"] == ["k8s"]

    def test_missing_rewritten_tasks(self):
        raw = json.dumps({
            "agents": ["k8s"],
            "reasoning": "k8s question",
            "parallel": False,
        })
        result = _extract_routing_json(raw, ["k8s", "code", "research", "general"])
        assert "k8s" in result["rewritten_tasks"]
```

### 5.2 Unit Tests for the Registry

```python
"""Unit tests for the sub-agent registry."""

from kubani.nexus.agents.registry import AgentConfig, SubAgentRegistry


class TestSubAgentRegistry:
    """Tests for SubAgentRegistry."""

    def test_default_agents_registered(self):
        registry = SubAgentRegistry()
        names = registry.get_names()
        assert "k8s" in names
        assert "code" in names
        assert "research" in names
        assert "general" in names

    def test_get_existing_agent(self):
        registry = SubAgentRegistry()
        config = registry.get("k8s")
        assert config is not None
        assert config.name == "k8s"
        assert config.tool_type == "k8s_mcp"

    def test_get_nonexistent_agent(self):
        registry = SubAgentRegistry()
        config = registry.get("nonexistent")
        assert config is None

    def test_register_custom_agent(self):
        registry = SubAgentRegistry()
        custom = AgentConfig(
            name="custom",
            display_name="Custom Agent",
            description="A custom agent",
            prompt_file="custom.md",
            tool_type="workspace",
        )
        registry.register(custom)
        assert registry.get("custom") is not None

    def test_router_description_contains_all_agents(self):
        registry = SubAgentRegistry()
        desc = registry.get_router_description()
        assert "k8s" in desc
        assert "code" in desc
        assert "research" in desc
        assert "general" in desc
```

### 5.3 Integration Test: End-to-End Swarm Flow

This test requires a running Temporal server and LLM endpoint. It verifies the full message flow from signal to response.

```python
"""Integration test for the swarm architecture.

Requires:
- Temporal running at localhost:7233
- vLLM running at configured endpoint
- Redis running at localhost:6379
- PostgreSQL running at configured endpoint

Run with: pytest tests/integration/nexus/test_swarm.py -v
"""

import asyncio
import os
import pytest
from temporalio.client import Client
from temporalio.worker import Worker

from kubani.nexus.orchestrator.worker import get_activities, get_workflows


@pytest.fixture
async def temporal_client():
    host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
    client = await Client.connect(host, namespace=namespace)
    yield client


@pytest.fixture
async def worker(temporal_client):
    w = Worker(
        temporal_client,
        task_queue="nexus-test",
        workflows=get_workflows(),
        activities=get_activities(),
    )
    task = asyncio.create_task(w.run())
    yield w
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.integration
async def test_k8s_routing(temporal_client, worker):
    """Test that a K8s question is routed to the K8s agent."""
    from kubani.nexus.orchestrator.workflow import NexusOrchestratorWorkflow

    handle = await temporal_client.start_workflow(
        NexusOrchestratorWorkflow.run,
        {"user_id": "test", "conversation_id": "test-conv"},
        id="nexus-test-k8s",
        task_queue="nexus-test",
    )

    await handle.signal("user_message", {
        "source": "test",
        "user_id": "test",
        "conversation_id": "test-conv",
        "text": "What pods are running in the ai-agents namespace?",
    })

    # Wait for processing
    await asyncio.sleep(30)

    state = await handle.query("get_state")
    assert state["status"] == "idle"
    # Verify a response was generated
    history = state.get("conversation_history", [])
    assert len(history) >= 2  # user + assistant


@pytest.mark.integration
async def test_general_routing(temporal_client, worker):
    """Test that a greeting is routed to the general agent."""
    from kubani.nexus.orchestrator.workflow import NexusOrchestratorWorkflow

    handle = await temporal_client.start_workflow(
        NexusOrchestratorWorkflow.run,
        {"user_id": "test", "conversation_id": "test-conv-2"},
        id="nexus-test-general",
        task_queue="nexus-test",
    )

    await handle.signal("user_message", {
        "source": "test",
        "user_id": "test",
        "conversation_id": "test-conv-2",
        "text": "Hello, how are you?",
    })

    await asyncio.sleep(15)

    state = await handle.query("get_state")
    assert state["status"] == "idle"
```

### 5.4 Testing Each Sub-Agent Independently

Each sub-agent activity can be tested in isolation by calling it directly:

```python
"""Test individual sub-agent activities."""

import pytest
from unittest.mock import patch, AsyncMock


@pytest.mark.integration
async def test_k8s_agent_direct():
    """Test the K8s agent activity directly."""
    from kubani.nexus.agents.k8s_agent import run_k8s_agent_turn

    result = await run_k8s_agent_turn({
        "user_message": "List all pods in the nexus namespace",
        "conversation_history": [],
        "memories": [],
        "context": "",
        "user_id": "test",
    })

    assert "response_text" in result
    assert result["stop_reason"] != "error"


@pytest.mark.integration
async def test_code_agent_direct():
    """Test the Code agent activity directly."""
    from kubani.nexus.agents.code_agent import run_code_agent_turn

    result = await run_code_agent_turn({
        "user_message": "Create a file called hello.py that prints Hello World",
        "conversation_history": [],
        "memories": [],
        "context": "",
        "user_id": "test",
    })

    assert "response_text" in result
    assert result["stop_reason"] != "error"


@pytest.mark.integration
async def test_research_agent_direct():
    """Test the Research agent activity directly."""
    from kubani.nexus.agents.research_agent import run_research_agent_turn

    result = await run_research_agent_turn({
        "user_message": "Search memory for any previous cluster health checks",
        "conversation_history": [],
        "memories": [],
        "context": "",
        "user_id": "test",
    })

    assert "response_text" in result
    assert result["stop_reason"] != "error"
```

### 5.5 Testing the Feature Flag Rollback

```python
"""Test that NEXUS_SWARM_MODE=false reverts to monolithic behavior."""

import os
import pytest


def test_swarm_mode_flag():
    """Verify the feature flag controls the code path."""
    os.environ["NEXUS_SWARM_MODE"] = "false"

    # Re-import to pick up the flag
    import importlib
    from kubani.nexus.orchestrator import workflow
    importlib.reload(workflow)

    assert workflow.SWARM_MODE is False

    # Cleanup
    os.environ["NEXUS_SWARM_MODE"] = "true"
    importlib.reload(workflow)
    assert workflow.SWARM_MODE is True
```

---

## 6. Rollback

### 6.1 Feature Flag Rollback (Instant)

Set the environment variable `NEXUS_SWARM_MODE=false` on the orchestrator deployment. This causes the workflow to skip the router and sub-agent dispatch, falling back to the original `run_agent_turn` activity with the monolithic agent.

```bash
kubectl set env deployment/nexus-orchestrator \
  NEXUS_SWARM_MODE=false \
  -n nexus
```

The next user message will use the Phase 2 monolithic path. No workflow restart is needed because the flag is checked per-message in `_process_message`.

### 6.2 Code Rollback

If the feature flag is insufficient, revert the three modified files to their Phase 2 versions:

```bash
# Revert workflow to Phase 2
git checkout HEAD~1 -- kubani/nexus/orchestrator/workflow.py

# Revert worker to Phase 2
git checkout HEAD~1 -- kubani/nexus/orchestrator/worker.py

# Rebuild and deploy
docker build -t registry.almckay.io/kubani-nexus-orchestrator:rollback .
docker push registry.almckay.io/kubani-nexus-orchestrator:rollback
kubectl set image deployment/nexus-orchestrator \
  orchestrator=registry.almckay.io/kubani-nexus-orchestrator:rollback \
  -n nexus
```

The new files (`kubani/nexus/agents/`) are inert -- they are not imported unless the worker registers them. Reverting the worker removes all new activity registrations.

### 6.3 Full Rollback Checklist

1. Set `NEXUS_SWARM_MODE=false` (immediate mitigation).
2. Revert `kubani/nexus/orchestrator/workflow.py` to Phase 2 version.
3. Revert `kubani/nexus/orchestrator/worker.py` to Phase 2 version.
4. Rebuild and push the orchestrator image.
5. Deploy the rollback image.
6. Verify the workflow is processing messages with `kubectl logs`.
7. The new files in `kubani/nexus/agents/` can be left in place (unused) or removed.
8. The new MCP policy files can be left in place (unused by any agent).
9. The NetworkPolicy can be left in place (does not affect Phase 2 behavior).

---

## Implementation Order

Execute the steps in this order:

| Order | Step | Files | Depends On |
|-------|------|-------|------------|
| 1 | Sub-Agent Registry | `kubani/nexus/agents/__init__.py`, `registry.py` | Nothing |
| 2 | System Prompts | `kubani/nexus/agents/prompts/*.md` | Nothing |
| 3 | Intent Router | `kubani/nexus/agents/router.py` | Step 1 |
| 4 | Orchestrator Synthesis | `kubani/nexus/agents/orchestrator.py` | Nothing |
| 5 | K8s Agent | `kubani/nexus/agents/k8s_agent.py` | Step 1 |
| 6 | Code Agent | `kubani/nexus/agents/code_agent.py` | Step 1 |
| 7 | Research Agent | `kubani/nexus/agents/research_agent.py` | Step 1 |
| 8 | Isolation Config | `kubani/nexus/agents/isolation.py` | Nothing |
| 9 | MCP Policies | `kubani/mcp/registry/policies/nexus-*.json` | Nothing |
| 10 | Modified Worker | `kubani/nexus/orchestrator/worker.py` | Steps 3-7 |
| 11 | Modified Workflow | `kubani/nexus/orchestrator/workflow.py` | Steps 3-4, 10 |
| 12 | Network Policies | `infrastructure/gitops/apps/nexus/networkpolicy-*.yaml` | Nothing |
| 13 | Unit Tests | `tests/unit/nexus/` | Steps 1-3 |
| 14 | Integration Tests | `tests/integration/nexus/` | Steps 10-11 |

**Estimated effort:** 3-5 days for a developer familiar with the codebase.

**Verification after each step:**

- Steps 1-2: `python -c "from kubani.nexus.agents.registry import SubAgentRegistry; r = SubAgentRegistry(); print(r.get_names())"`
- Step 3: Unit tests for router JSON parsing pass.
- Steps 5-7: Each agent activity can be called directly in a test script.
- Step 10: Worker starts without import errors: `python -m kubani.nexus.orchestrator.worker`
- Step 11: Full integration test with a running Temporal and LLM endpoint.
