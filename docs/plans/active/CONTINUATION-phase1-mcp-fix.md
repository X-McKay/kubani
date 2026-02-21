# Phase 1 MCP Integration — Continuation Prompt

## What We're Doing

Executing the Phase 1 plan (`docs/plans/active/2026-02-20-phase1-mcp-native-tools.md`) which evolves the Nexus orchestrator from a coding-only agent into a PI (Personal Intelligence) agent with Memory MCP, Skills MCP, Fetch MCP, and DuckDuckGo web search tools.

**Branch:** `feature/20260221-phase-1`

## What's Been Implemented (All 7 Plan Steps Complete)

All code changes are in place and unit tests pass:

1. **`kubani/nexus/tools/mcp_clients.py`** — Creates Strands `MCPClient` instances for Memory (SSE), Skills (SSE), and Fetch (stdio). Respects `config.mcp.memory_enabled` / `skills_enabled` flags.

2. **`kubani/nexus/tools/extra_tools.py`** — DuckDuckGo `web_search` `@tool` function.

3. **`kubani/nexus/tools/strands_tools.py`** — Modified to include `web_search` from extra_tools when `include_extras=True`.

4. **`kubani/nexus/orchestrator/activities.py`** — `run_agent_turn` now creates MCP clients, pre-starts them with a 10s timeout (to prevent hangs), combines them with workspace tools, and passes them to `Agent(tools=...)`. System prompt updated for PI agent. MCP clients cleaned up in `finally` block via `client.stop(None, None, None)`.

5. **`kubani/nexus/orchestrator/Dockerfile`** — Added `duckduckgo-search mcp-server-fetch` to pip install.

6. **`infrastructure/gitops/apps/nexus/orchestrator-deployment.yaml`** — Added `MCP_MEMORY_URL` and `MCP_SKILLS_URL` env vars. Image tag is `v0.6.2-pi`. **NOTE:** Also has `MCP_MEMORY_ENABLED=false` and `MCP_SKILLS_ENABLED=false` — these should be REMOVED once the 421 issue is fixed.

7. **`kubani/mcp/registry/registry.json`** — Added `nexus` policy. `kubani/mcp/registry/policies/nexus.json` created.

## The Blocking Issue: MCP SSE 421 "Invalid Host Header"

### Root Cause

Both MCP servers (Memory and Skills) use the MCP SDK's `TransportSecuritySettings` with `enable_dns_rebinding_protection=True` and an `allowed_hosts` list. The servers reject connections where the HTTP `Host` header doesn't match their allowed hosts list, returning HTTP 421.

### The Host Header Mismatch

The **orchestrator** (in `nexus` namespace) connects to MCP servers using FQDN:
- `http://memory-mcp.ai-agents.svc.cluster.local:8083/sse`
- `http://skills-mcp-server.ai-agents.svc.cluster.local:8085/sse`

The HTTP `Host` header sent is: `memory-mcp.ai-agents.svc.cluster.local:8083`

But the **memory MCP server's** `MCP_ALLOWED_HOSTS` env var is:
```
memory-mcp.ai-agents.svc,memory-mcp.ai-agents.svc:*,memory-mcp.almckay.io,memory-mcp.almckay.io:*,localhost,localhost:*,127.0.0.1,127.0.0.1:*,10.*:*,100.*:*
```

**Missing:** `memory-mcp.ai-agents.svc.cluster.local` and `memory-mcp.ai-agents.svc.cluster.local:*`

The **skills MCP server's** `MCP_ALLOWED_HOSTS` already includes `*.svc.cluster.local:*` patterns, so it may actually work. Need to verify.

### How the Allowed Hosts Are Used

In `kubani/mcp/servers/memory/src/memory_mcp/server.py` lines 255-272:
```python
allowed_hosts_env = os.environ.get("MCP_ALLOWED_HOSTS", "")
allowed_hosts = ["localhost:*", "127.0.0.1:*"]
if allowed_hosts_env:
    allowed_hosts.extend(h.strip() for h in allowed_hosts_env.split(",") if h.strip())

mcp = FastMCP(
    name="Memory MCP Server",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
    ),
)
```

The `TransportSecuritySettings` from the MCP SDK validates incoming request Host headers against the `allowed_hosts` list. Wildcard `*` matches any port. The list is used by `mcp.server.sse` to reject requests with non-matching Host headers with HTTP 421.

### Secondary Issue: SSE Client Hangs

When the MCP server returns 421, the `mcp.client.sse.sse_client()` async context manager may hang rather than raise an exception cleanly. This causes `MCPClient.start()` to block indefinitely. The timeout wrapper in `activities.py` (using `asyncio.wait_for` with `run_in_executor`) was added to prevent this, but hasn't been tested yet because the image deployed (`v0.6.1-pi`) is the version BEFORE that fix.

## What Needs to Be Fixed

### Fix 1: Update MCP Server Allowed Hosts (the actual fix)

Update the `MCP_ALLOWED_HOSTS` env var in the **memory MCP server deployment** to include the FQDN patterns:

File: `infrastructure/gitops/apps/ai-agents/memory-mcp-server/deployment.yaml` (line 53)

Add to `MCP_ALLOWED_HOSTS`:
- `memory-mcp.ai-agents.svc.cluster.local`
- `memory-mcp.ai-agents.svc.cluster.local:*`

Or simplify with wildcard patterns like the skills server already has: `*.svc.cluster.local,*.svc.cluster.local:*`

Then apply the deployment update to the cluster.

### Fix 2: Verify Skills MCP Server

The skills MCP server's `MCP_ALLOWED_HOSTS` (line 54 of `infrastructure/gitops/apps/ai-agents/skills-mcp-server/deployment.yaml`) already includes `*.svc.cluster.local:*` patterns. Verify it actually works by testing connectivity from the orchestrator pod.

### Fix 3: Clean Up Orchestrator Deployment

After Fixes 1-2 are applied and verified:

1. Remove the `MCP_MEMORY_ENABLED=false` and `MCP_SKILLS_ENABLED=false` env vars from `infrastructure/gitops/apps/nexus/orchestrator-deployment.yaml`
2. Optionally simplify the MCP URLs to use short service names: `http://memory-mcp.ai-agents.svc:8083` (which already matches the allowed hosts)
3. Rebuild and deploy the orchestrator image

### Fix 4: Test End-to-End via Kubani UI

1. Navigate to `https://kubani.almckay.io/chat`
2. Select "Nexus Agent" from the dropdown
3. Send: "Hello! What tools do you have available?"
4. Verify the agent responds listing its available tools
5. Test web_search: "Search the web for the latest Kubernetes news"
6. Test fetch: "Fetch https://kubernetes.io/docs/ and summarize it"

## Current Cluster State

- **Orchestrator pod:** Running `v0.6.1-pi` (the version WITHOUT timeout fix, WITHOUT disabled MCP flags). This version will hang on `MCPClient.start()` when MCP servers return 421.
- **Memory MCP:** Running in `ai-agents` namespace, service `memory-mcp:8083`
- **Skills MCP:** Running in `ai-agents` namespace, service `skills-mcp-server:8085`
- **Gateway:** Running in `nexus` namespace, healthy
- **Local git state:** `v0.6.2-pi` Dockerfile built and pushed but NOT deployed (user rejected the apply). Local yaml has the disable flags which should be removed.

## Key Files

| File | Purpose |
|------|---------|
| `kubani/nexus/tools/mcp_clients.py` | MCP client factory (SSE + stdio) |
| `kubani/nexus/tools/extra_tools.py` | DuckDuckGo web_search tool |
| `kubani/nexus/tools/strands_tools.py` | Tool aggregation |
| `kubani/nexus/orchestrator/activities.py` | Temporal activity with Strands Agent |
| `kubani/nexus/orchestrator/Dockerfile` | Docker build for orchestrator |
| `infrastructure/gitops/apps/nexus/orchestrator-deployment.yaml` | K8s deployment for orchestrator |
| `infrastructure/gitops/apps/ai-agents/memory-mcp-server/deployment.yaml` | Memory MCP deployment (FIX NEEDED) |
| `infrastructure/gitops/apps/ai-agents/skills-mcp-server/deployment.yaml` | Skills MCP deployment (verify) |
| `kubani/mcp/servers/memory/src/memory_mcp/server.py` | Memory MCP server code |
| `kubani/mcp/servers/skills/src/skills_mcp/server.py` | Skills MCP server code |

## Strands SDK Notes

- `MCPClient(transport_callable)` — constructor takes a lambda returning an async context manager
- `MCPClient.start()` — eagerly connects and discovers tools. If this fails, `Agent()` constructor crashes with `ValueError`
- `MCPClient.stop(exc_type, exc_val, exc_tb)` — cleanup. No `close()` method exists
- `Agent(tools=[...])` — accepts both `@tool` functions and `MCPClient` instances in the same list
- `agent.invoke_async(prompt)` — async execution of the agent loop
