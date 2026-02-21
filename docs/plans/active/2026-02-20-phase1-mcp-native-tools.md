# Phase 1: Nexus PI Agent — Memory, Skills, Fetch & Web Search

**Status:** Active
**Created:** 2026-02-20
**Updated:** 2026-02-21
**Author:** Generated with Claude Code
**Scope:** Evolve Nexus from a coding-only agent into a focused PI (Personal Intelligence) agent with memory, skill discovery, web fetch, and web search. Cluster operations, workflows, comms, and research are deferred to specialized sub-agents in Phase 3.

---

## 1. Context

Nexus is a conversational AI agent built on Temporal + Strands Agent SDK. It currently has exactly 5 workspace tools (`read_file`, `write_file`, `edit_file`, `bash`, `register_skill`) and zero access to any MCP servers or external data sources.

All MCP servers are already deployed and running in the `ai-agents` namespace. However, rather than giving Nexus access to *all* of them (which inflates token overhead and fights the Phase 3 swarm architecture), we scope Phase 1 to the tools that define a PI agent:

| Server | Transport | Purpose |
|--------|-----------|---------|
| `memory-mcp-server` | SSE | Store/query knowledge, learnings, and context |
| `skills-mcp-server` | SSE | Discover and execute registered Kubani skills |
| `mcp-server-fetch` | stdio (in-process) | Read any URL as markdown (the "curl" equivalent) |

Plus one custom `@tool`:
- **`web_search`** — DuckDuckGo internet search (no API key needed)

**Deferred to Phase 3 sub-agents:**

| Sub-Agent | MCP Servers / Tools |
|-----------|-------------------|
| K8s Agent | K8s MCP, Prometheus queries |
| Workflow Agent | Temporal MCP |
| Comms Agent | Discord MCP |
| Research Agent | Qdrant MCP, ArXiv search |

**The key insight:** Strands Agent SDK has a built-in `MCPClient` (`strands.tools.mcp.MCPClient`) that auto-discovers tools from MCP servers. We pass `MCPClient` instances directly to `Agent(tools=[...])`. No manual `@tool` wrappers needed.

This approach keeps the tool count low (~10-15 tools total), the system prompt tight, and aligns Phase 1 directly with the Phase 3 swarm trajectory instead of building up tool sprawl and ripping it out later.

---

## 2. Root Cause Analysis

The exact chain of failure when a user asks "How are the pods in the ai-agents namespace?":

1. User sends message via WebSocket or Discord.
2. Gateway receives message, signals Temporal workflow.
3. Workflow dispatches `run_agent_turn` activity.
4. Activity creates a Strands `Agent` with 5 workspace tools.
5. Agent receives user message and the system prompt (which says "You are a coding agent").
6. The LLM sees it has `bash` available and attempts: `kubectl get pods -n ai-agents`.
7. The bash tool calls `analyze_bash_command("kubectl get pods -n ai-agents")`.
8. In `security.py`, line 72: the regex `r"\bkubectl\b"` matches → `"approve"`.
9. The bash tool returns `ToolResult(success=False, error="NEEDS_APPROVAL: kubernetes operations")`.
10. The Strands agent tells the user: "I can't run kubectl because it requires approval."
11. **There is no approval mechanism in the Strands agent loop.** The error is terminal.

Even if kubectl were allowed, the orchestrator container has neither kubectl installed nor a kubeconfig mounted.

**Phase 1 fix:** Give Nexus memory and skills so it can learn, remember, and leverage registered skills. For cluster-specific questions, Nexus can honestly say "I don't have direct cluster access yet" — Phase 3 adds a dedicated K8s agent for that.

---

## 3. Architecture

### After (Phase 1)

```
User Message
    |
    v
Temporal Workflow --> run_agent_turn activity
    |
    v
Strands Agent (Nexus PI)
|-- Workspace Tools (5 existing @tool functions)
|   read_file, write_file, edit_file, bash, register_skill
|-- MCPClient: Memory MCP (SSE) --> memory-mcp.ai-agents.svc:8083/sse
|   Auto-discovers: store_learning, query_knowledge, etc.
|-- MCPClient: Skills MCP (SSE) --> skills-mcp-server.ai-agents.svc:8085/sse
|   Auto-discovers: skills.list, skills.get, skills.execute, etc.
|-- MCPClient: Fetch (stdio, in-process) --> python -m mcp_server_fetch
|   Auto-discovers: fetch(url, max_length, start_index, raw)
|-- Custom @tool: web_search (DuckDuckGo)
```

### Key Design Decisions

- **Focused toolset.** Only memory, skills, fetch, and web search. K8s, Temporal, Discord, Qdrant, ArXiv, and Prometheus are deferred to Phase 3 sub-agents. This keeps token overhead low and aligns with the swarm architecture.
- **MCPClient auto-discovery** replaces hand-written `@tool` wrappers. Zero boilerplate.
- **Fetch MCP via stdio** runs `mcp-server-fetch` in-process using `python -m mcp_server_fetch`. No deployment needed. The package is pip-installed in the container image.
- **SSE URLs must include `/sse` suffix.** The `mcp` library's `sse_client()` expects the full endpoint URL. The base URLs in config do NOT include `/sse`, so `create_mcp_clients()` appends it.
- **MCPClient cleanup.** MCP clients are explicitly closed in a `finally` block to prevent SSE connection leaks on activity timeout/cancellation.
- **No changes to `kubani/framework/mcp/client.py`** — Nexus uses Strands SDK's MCPClient, not the custom framework MCPClient.

---

## 4. Step-by-Step Implementation

### Step 1: Create `kubani/nexus/tools/mcp_clients.py`

New file (~50 lines) that creates Strands `MCPClient` instances for Memory, Skills, and Fetch.

**File:** `kubani/nexus/tools/mcp_clients.py`

```python
"""MCP client factory for the Nexus PI agent.

Creates Strands MCPClient instances for Memory, Skills, and Fetch.
These are passed directly to Agent(tools=[...]) which auto-discovers
all tools from each server.

Uses strands.tools.mcp.MCPClient -- NOT the custom
kubani.framework.mcp.client.MCPClient.
"""
from __future__ import annotations

import logging

from strands.tools.mcp import MCPClient

logger = logging.getLogger(__name__)


def create_mcp_clients() -> list[MCPClient]:
    """Create MCPClient instances for PI agent MCP servers.

    Returns:
        List of MCPClient instances. Each auto-discovers tools
        when passed to Agent(tools=[...]).
    """
    from kubani.framework.config import get_config

    config = get_config()
    clients: list[MCPClient] = []

    # SSE-based MCP servers (already deployed on cluster).
    # sse_client() expects the full endpoint URL including /sse.
    sse_servers = {
        "memory": config.mcp.memory_url,
        "skills": config.mcp.skills_url,
    }

    for name, base_url in sse_servers.items():
        if not base_url:
            logger.warning(f"MCP server '{name}' URL not configured, skipping")
            continue
        try:
            from mcp.client.sse import sse_client

            sse_url = base_url.rstrip("/") + "/sse"
            client = MCPClient(lambda u=sse_url: sse_client(u))
            clients.append(client)
            logger.info(f"Created MCPClient for {name} at {sse_url}")
        except Exception as e:
            logger.warning(f"Failed to create MCPClient for {name}: {e}")

    # Stdio-based: Fetch MCP (in-process, no deployment needed).
    # Uses pip-installed mcp-server-fetch, not uvx.
    try:
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client

        fetch_client = MCPClient(lambda: stdio_client(
            StdioServerParameters(command="python", args=["-m", "mcp_server_fetch"])
        ))
        clients.append(fetch_client)
        logger.info("Created MCPClient for fetch (stdio)")
    except Exception as e:
        logger.warning(f"Failed to create fetch MCPClient: {e}")

    return clients
```

**Notes:**
- `MCPClient` connects lazily — no network calls at creation time.
- The `lambda u=sse_url:` pattern captures the URL by value, avoiding late-binding closure issues.
- Fetch uses `python -m mcp_server_fetch` (pip-installed), not `uvx` (not in container).

---

### Step 2: Create `kubani/nexus/tools/extra_tools.py`

New file (~50 lines) with the single custom `@tool`: `web_search`.

**File:** `kubani/nexus/tools/extra_tools.py`

```python
"""Extra tools for the Nexus PI agent.

Custom @tool functions for capabilities without MCP servers:
- web_search: DuckDuckGo internet search (no API key needed)

Usage:
    from kubani.nexus.tools.extra_tools import create_extra_tools
    extras = create_extra_tools()
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from strands import tool

logger = logging.getLogger(__name__)


def _format_result(data: Any) -> str:
    if data is None:
        return "No data returned."
    if isinstance(data, (dict, list)):
        return json.dumps(data, indent=2, default=str)
    return str(data)


def create_extra_tools() -> list:
    """Create custom @tool instances for the PI agent.

    Returns:
        List of Strands tool instances.
    """

    @tool
    def web_search(query: str, max_results: int = 5) -> str:
        """Search the web using DuckDuckGo. Returns titles, URLs, and snippets.

        Use this tool when the user asks to look something up, find information,
        or when you need current data that isn't in your training set.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return. Default 5, max 20.
        """
        try:
            from duckduckgo_search import DDGS

            max_results = min(max_results, 20)
            with DDGS() as ddgs:
                raw_results = list(ddgs.text(query, max_results=max_results))

            if not raw_results:
                return f"No web results found for query: {query}"

            results = []
            for r in raw_results:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", r.get("link", "")),
                    "snippet": r.get("body", r.get("snippet", "")),
                })
            return _format_result(results)
        except ImportError:
            return "Error: duckduckgo-search package not installed."
        except Exception as e:
            return f"Error searching the web: {e}"

    return [web_search]
```

**Notes:**
- `web_search` is defined as sync (not `async`) because `DDGS().text()` is synchronous. Strands runs sync tools in a thread executor, avoiding event loop blocking.
- Single tool, ~50 lines total. Clean and focused.

---

### Step 3: Modify `kubani/nexus/tools/strands_tools.py`

Update `create_tools()` to optionally include extra tools.

**Change the signature:**

```python
def create_tools(workspace: Path, include_extras: bool = True) -> list:
```

**Change the return statement:**

```python
    tools = [read_file, write_file, edit_file, bash, register_skill]

    if include_extras:
        try:
            from kubani.nexus.tools.extra_tools import create_extra_tools
            extras = create_extra_tools()
            tools.extend(extras)
            logger.info(f"Loaded {len(extras)} extra tools")
        except Exception as e:
            logger.warning(f"Failed to load extra tools: {e}")

    return tools
```

---

### Step 4: Modify `kubani/nexus/orchestrator/activities.py`

Two changes: (a) new system prompt, (b) create MCP clients with cleanup.

**New system prompt:**

```python
AGENT_SYSTEM_PROMPT = """/no_think
You are Nexus, the Kubani platform's personal intelligence assistant. You help
users with coding tasks, research, knowledge management, and skill discovery.

You have access to the following tool categories:

WORKSPACE: read_file, write_file, edit_file, bash, register_skill
  Use these for coding tasks and file operations.

MEMORY (via MCP): Store and query knowledge, learnings, and context.
  Use these to remember information across conversations and retrieve
  relevant context from past interactions.

SKILLS (via MCP): Discover and execute registered Kubani skills.
  Use these to find and run pre-built capabilities.

FETCH (via MCP): Read any URL and get its content as markdown.
  Use this to read documentation, web pages, or API responses.

WEB SEARCH: web_search for DuckDuckGo internet searches.
  Use this to find current information on the web.

When you have completed the task or have the answer, respond directly
with your final message to the user. Do not call any tools when you
are ready to respond.

Important:
- For cluster operations (pod status, deployments, etc.), let the user
  know that dedicated cluster tools are coming soon. You can still help
  with Kubernetes YAML files, Helm charts, and documentation.
- For web lookups, use fetch to read URLs or web_search to search.
- Always read a file before editing it.
- Use edit_file for surgical changes, write_file for creating new files.
- Be concise in your responses."""
```

**Modified `run_agent_turn`:**

```python
@activity.defn
async def run_agent_turn(input_data: dict[str, Any]) -> dict[str, Any]:
    user_message = input_data.get("user_message", "")
    conversation_history = input_data.get("conversation_history", [])
    memories = input_data.get("memories", [])
    user_id = input_data.get("user_id", "default")

    activity.heartbeat("Creating Strands agent")
    logger.info(f"run_agent_turn: user={user_id}, msg={user_message[:100]}")

    from kubani.framework.config import get_llm_config
    from kubani.nexus.tools.core import get_workspace
    from kubani.nexus.tools.mcp_clients import create_mcp_clients
    from kubani.nexus.tools.strands_tools import create_tools
    from strands import Agent
    from strands.models.openai import OpenAIModel

    llm_config = get_llm_config()
    workspace = get_workspace(user_id)
    workspace_tools = create_tools(workspace)
    mcp_clients = create_mcp_clients()

    model = OpenAIModel(
        client_args={
            "api_key": llm_config.api_key or "not-needed",
            "base_url": llm_config.api_url,
        },
        model_id=llm_config.model,
        params={
            "temperature": llm_config.temperature,
            "max_tokens": llm_config.max_tokens,
        },
    )

    # Build the prompt with context
    prompt_parts = []
    if memories:
        mem_text = "Relevant context from memory:\n" + "\n".join(f"- {m}" for m in memories)
        prompt_parts.append(mem_text)

    if conversation_history:
        history_lines = []
        for msg in conversation_history[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")[:500]
            history_lines.append(f"{role}: {content}")
        if history_lines:
            prompt_parts.append("Recent conversation:\n" + "\n".join(history_lines))

    prompt_parts.append(user_message)
    full_prompt = "\n\n".join(prompt_parts)

    # Combine workspace tools + web_search with MCP clients.
    # MCPClient instances are passed alongside @tool functions —
    # Strands Agent auto-discovers tools from each MCPClient.
    all_tools = [*workspace_tools, *mcp_clients]

    agent = Agent(
        model=model,
        system_prompt=AGENT_SYSTEM_PROMPT,
        tools=all_tools,
        callback_handler=None,
    )

    activity.heartbeat("Running Strands agent loop")

    try:
        result = await agent.invoke_async(full_prompt)
        response_text = str(result)

        import re
        response_text = re.sub(r"<think>\s*</think>\s*", "", response_text).strip()

        activity.heartbeat("Agent loop complete")
        logger.info(f"run_agent_turn complete: stop_reason={result.stop_reason}, response={response_text[:200]}")

        return {
            "response_text": response_text,
            "stop_reason": str(result.stop_reason),
        }
    except Exception as e:
        logger.error(f"Strands agent error: {e}", exc_info=True)
        return {
            "response_text": f"I encountered an error while processing your request: {e}",
            "stop_reason": "error",
        }
    finally:
        # Clean up MCP client connections to prevent SSE leaks
        # on activity timeout or cancellation.
        for client in mcp_clients:
            try:
                client.close()
            except Exception:
                pass
```

---

### Step 5: Update orchestrator deployment env vars

**File:** `infrastructure/gitops/apps/nexus/orchestrator-deployment.yaml`

Add MCP URL environment variables after `LOG_LEVEL`:

```yaml
        - name: LOG_LEVEL
          value: "INFO"
        # MCP server URLs (PI agent servers only)
        - name: MCP_MEMORY_URL
          value: "http://memory-mcp.ai-agents.svc.cluster.local:8083"
        - name: MCP_SKILLS_URL
          value: "http://skills-mcp-server.ai-agents.svc.cluster.local:8085"
        resources:
```

Only Memory and Skills — Fetch runs in-process via stdio, web_search needs no config.

---

### Step 6: Update Dockerfile

**File:** `kubani/nexus/orchestrator/Dockerfile`

Add new pip dependencies:

```dockerfile
RUN pip install --no-cache-dir -e ".[events,skills]" \
    && pip install --no-cache-dir asyncpg duckduckgo-search mcp-server-fetch
```

- `duckduckgo-search` — for the `web_search` tool
- `mcp-server-fetch` — for the in-process Fetch MCP server (run via `python -m mcp_server_fetch`)

---

### Step 7: Create Nexus MCP policy

**File:** `kubani/mcp/registry/policies/nexus.json`

```json
{
  "allowedServers": [
    "memory",
    "skills"
  ],
  "requireApproval": [],
  "auditLog": true,
  "readOnly": false,
  "notes": "Phase 1 PI agent. Memory and Skills are read-write. K8s, Temporal, Discord, Qdrant deferred to Phase 3 sub-agents."
}
```

Also add a `"nexus"` entry to the `"policies"` section in `kubani/mcp/registry/registry.json`.

**Note:** This policy is defense-in-depth — nothing enforces it in Phase 1. It documents intent and will be enforced when the MCP Gateway is built in Phase 2.

---

## 5. File Summary

### New files (3)

| File | Lines | Purpose |
|------|-------|---------|
| `kubani/nexus/tools/mcp_clients.py` | ~50 | Strands MCPClient factory for Memory, Skills (SSE) + Fetch (stdio) |
| `kubani/nexus/tools/extra_tools.py` | ~50 | DuckDuckGo `web_search` @tool |
| `kubani/mcp/registry/policies/nexus.json` | ~10 | MCP access policy for Nexus PI agent |

### Modified files (3)

| File | Change |
|------|--------|
| `kubani/nexus/tools/strands_tools.py` | Add `include_extras` param, load extra tools |
| `kubani/nexus/orchestrator/activities.py` | New PI agent system prompt + MCP clients with cleanup |
| `kubani/nexus/orchestrator/Dockerfile` | Add `duckduckgo-search` and `mcp-server-fetch` deps |

### Infrastructure (1)

| File | Change |
|------|--------|
| `infrastructure/gitops/apps/nexus/orchestrator-deployment.yaml` | Add `MCP_MEMORY_URL` and `MCP_SKILLS_URL` env vars |

### What is NOT changed

| File | Why |
|------|-----|
| `kubani/framework/config.py` | No new config fields needed — Memory and Skills URLs already exist |
| `kubani/framework/mcp/client.py` | We use Strands MCPClient, not the framework MCPClient |
| `kubani/nexus/tools/core.py` | Workspace tools unchanged |
| `kubani/nexus/tools/security.py` | Security barrier unchanged |
| Any RBAC or kustomization manifests | No new K8s resources to deploy |

**Total: 3 new files + 3 modified files + 1 infra update = 7 changes**

---

## 6. Dependencies

Add to the orchestrator's Dockerfile pip install:

```
duckduckgo-search>=6.0.0
mcp-server-fetch
```

Already present as transitive dependencies: `httpx`, `mcp`, `strands-agents`.

No longer needed (deferred to Phase 3): `arxiv`, Prometheus tools.

---

## 7. Testing

### Unit: Tool creation (no network)

```bash
# Extra tools create without error
python -c "
from kubani.nexus.tools.extra_tools import create_extra_tools
tools = create_extra_tools()
print(f'Extra tools: {len(tools)}')
assert len(tools) == 1
print(f'  {tools[0].tool_name}')
print('OK')
"

# MCP clients create without error (lazy, no connection)
python -c "
from kubani.nexus.tools.mcp_clients import create_mcp_clients
clients = create_mcp_clients()
print(f'MCP clients: {len(clients)}')
assert len(clients) == 3  # memory, skills, fetch
print('OK')
"

# Combined workspace + extras
python -c "
from pathlib import Path
from kubani.nexus.tools.strands_tools import create_tools
tools = create_tools(Path('/tmp/test'), include_extras=True)
print(f'Total tools: {len(tools)}')
assert len(tools) == 6  # 5 workspace + 1 web_search
print('OK')
"
```

### Integration: Live test

```bash
# After deployment, test via UI or API:
curl -X POST http://localhost:8000/api/v1/conversations/test/messages \
  -H "Content-Type: application/json" \
  -d '{"text": "Search the web for Strands Agent SDK documentation", "source": "test"}'
```

Expected: web search results instead of "I can't do that."

```bash
# Test fetch
curl -X POST http://localhost:8000/api/v1/conversations/test/messages \
  -H "Content-Type: application/json" \
  -d '{"text": "Fetch and summarize https://strandsagents.com/latest/", "source": "test"}'
```

### System prompt verification

```bash
python -c "
from kubani.nexus.orchestrator.activities import AGENT_SYSTEM_PROMPT
assert 'Nexus' in AGENT_SYSTEM_PROMPT
assert 'personal intelligence' in AGENT_SYSTEM_PROMPT
assert 'web_search' in AGENT_SYSTEM_PROMPT
assert 'cluster tools are coming soon' in AGENT_SYSTEM_PROMPT
print('OK')
"
```

---

## 8. Deployment

1. Build and push the image:
   ```bash
   docker build -f kubani/nexus/orchestrator/Dockerfile \
     -t registry.almckay.io/kubani-nexus-orchestrator:v0.6.0-pi .
   docker push registry.almckay.io/kubani-nexus-orchestrator:v0.6.0-pi
   ```
2. Commit manifest changes and let Flux reconcile (or `kubectl apply` directly).
3. Verify:
   ```bash
   kubectl rollout status deployment/nexus-orchestrator -n nexus
   kubectl logs deployment/nexus-orchestrator -n nexus --tail=50 | grep -i "mcp\|tools\|loaded"
   ```

---

## 9. Rollback

**Immediate:** `kubectl rollout undo deployment/nexus-orchestrator -n nexus`

**Disable MCP tools at runtime** (without revert): Set `NEXUS_DISABLE_MCP_TOOLS=true` env var and check it in `run_agent_turn` before creating MCP clients.

**Full revert:** `git revert HEAD && git push`

---

## 10. Security

- **Memory and Skills are read-write by design.** The PI agent needs to store learnings and execute skills.
- **Fetch is read-only.** It can only GET URLs. The `mcp-server-fetch` server does not support POST/PUT/DELETE.
- **Web search is read-only.** DuckDuckGo text search only.
- **Bash security barrier unchanged.** kubectl and other medium/high-risk commands are still blocked.
- **MCP policy.** `nexus.json` documents allowed servers (defense-in-depth for Phase 2 gateway).
- **No cluster API access.** Nexus has no K8s ServiceAccount, kubeconfig, or kubectl. Cluster operations are deferred to the Phase 3 K8s agent.

---

## 11. Future Phases

### Phase 2: MCP Gateway + Enhanced Sandbox
- Centralized policy enforcement, audit logging, rate limiting
- Container-based sandbox for code execution
- HITL approval flow for write operations

### Phase 3: Agent Swarm Architecture
Specialized sub-agents with focused toolsets:

| Sub-Agent | MCP Servers | Custom Tools |
|-----------|-------------|--------------|
| **K8s Agent** | K8s MCP | Prometheus queries |
| **Workflow Agent** | Temporal MCP | — |
| **Comms Agent** | Discord MCP | — |
| **Research Agent** | Qdrant MCP | ArXiv search |

Nexus becomes the orchestrator/router that delegates to sub-agents based on intent classification. Each sub-agent has its own container isolation and network policies (least privilege).
