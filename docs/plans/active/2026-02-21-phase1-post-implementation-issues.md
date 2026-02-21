# Phase 1 MCP Integration — Post-Implementation Issues

**Date:** 2026-02-21
**Status:** Active
**Branch:** `feature/20260221-phase-1`

## Context

Phase 1 MCP integration is working end-to-end: UI → UI Server → Gateway → Temporal → Orchestrator → LLM → Redis → UI. The agent responds correctly with workspace tools + web_search. However, MCP SSE clients (Memory, Skills, Fetch) are not yet available to the agent at runtime due to an event loop conflict.

## Issue 1: MCP SSE Clients Fail Inside Temporal Activity

**Severity:** Medium — agent works without MCP tools, but Memory/Skills/Fetch are unavailable

**Symptom:** Strands `MCPClient.start()` fails during `Agent()` constructor with:
```
ToolProviderException: Failed to start MCP client: the client initialization failed
```

**Root Cause:** The MCP SSE client (`mcp.client.sse.sse_client()`) uses httpx/anyio to maintain a persistent SSE connection. When started inside a Temporal activity (which runs within Temporal's async worker event loop), the SSE client's async context manager conflicts with the existing event loop state.

The 421 "Invalid Host Header" issue is fixed (Memory MCP server now accepts `.cluster.local` FQDN patterns), and direct HTTP connectivity from the orchestrator pod to both MCP servers returns 200. The issue is purely about starting SSE clients within the Temporal activity's event loop context.

**Current Workaround:** Graceful fallback in `activities.py` — if `Agent(tools=[...mcp_clients])` raises `ValueError`, we retry with workspace tools only. The agent functions but without Memory, Skills, and Fetch tools.

**Potential Fixes:**
1. **Run MCP clients in a separate thread with their own event loop** — create a dedicated thread/event loop for SSE connections, bridge tool calls across threads.
2. **Switch MCP transport from SSE to Streamable HTTP** — the newer MCP transport may behave better since it doesn't maintain persistent connections.
3. **Pre-start MCP clients at worker level** — start SSE connections once when the Temporal worker boots (not per-activity), and reuse them across activity invocations. Requires careful lifecycle management.
4. **Use HTTP-based tool proxying** — instead of SSE MCP clients, call the MCP servers via direct HTTP POST to their tool endpoints, bypassing the SSE transport entirely.

## Issue 2: Flux GitOps Sync Pending

**Severity:** Low — cluster is running correctly, just not synced from Git

**Details:** The Nexus orchestrator deployment YAML (`infrastructure/gitops/apps/nexus/`) is not yet on the `main` branch. Flux reconciles from `main`, so these changes need to be merged for GitOps to manage them. Currently deployed via manual `kubectl apply`.

The memory MCP server deployment change (`MCP_ALLOWED_HOSTS` update) is also only on this branch. Flux will revert it on the next reconciliation from `main` unless merged first.

**Fix:** Merge `feature/20260221-phase-1` to `main` after review.

## What's Working

- Memory MCP server accepts `.cluster.local` FQDN Host headers (421 fix)
- Skills MCP server already had correct allowed hosts
- Orchestrator connects to correct Temporal namespace (`nexus`)
- LLM config resolves correctly (`LLM_API_URL` env var)
- Agent responds via full chain: UI → Gateway → Temporal → Orchestrator → LLM → Redis → UI
- Graceful MCP fallback — agent works with workspace tools when MCP fails
- Memory storage works (Qdrant embeddings stored after each conversation)

## Files Changed in This Session

| File | Change |
|------|--------|
| `infrastructure/gitops/apps/ai-agents/memory-mcp-server/deployment.yaml` | Added `.cluster.local` patterns to `MCP_ALLOWED_HOSTS` |
| `infrastructure/gitops/apps/nexus/orchestrator-deployment.yaml` | Fixed `TEMPORAL_NAMESPACE`, `LLM_API_URL`, removed disabled flags, bumped to `v0.6.3-pi` |
| `kubani/nexus/orchestrator/activities.py` | Replaced pre-start logic with try/except fallback for MCP client init |
