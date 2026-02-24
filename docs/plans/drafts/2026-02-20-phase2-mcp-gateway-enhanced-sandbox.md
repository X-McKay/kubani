# Phase 2: MCP Gateway + Enhanced Sandbox

**Status:** Draft
**Created:** 2026-02-20
**Author:** Kubani Development Team
**Depends on:** Phase 1 (Nexus PI Agent — Memory, Skills, Fetch, web_search — assumed complete)

---

## Table of Contents

1. [Context and Motivation](#1-context-and-motivation)
2. [Architecture Overview](#2-architecture-overview)
3. [Prerequisites](#3-prerequisites)
4. [Step-by-Step Implementation](#4-step-by-step-implementation)
   - 4.1 [Gateway Policy Engine](#41-gateway-policy-engine)
   - 4.2 [Gateway Audit Logger](#42-gateway-audit-logger)
   - 4.3 [Gateway Router](#43-gateway-router)
   - 4.4 [Gateway Server](#44-gateway-server)
   - 4.5 [Gateway Dockerfile](#45-gateway-dockerfile)
   - 4.6 [Framework Config Changes](#46-framework-config-changes)
   - 4.7 [Dynamic Tool Loader](#47-dynamic-tool-loader)
   - 4.8 [Modified Strands Tools](#48-modified-strands-tools)
   - 4.9 [Modified Activities](#49-modified-activities)
   - 4.10 [Container-Based Sandbox](#410-container-based-sandbox)
   - 4.11 [Sandbox Dockerfile](#411-sandbox-dockerfile)
   - 4.12 [HITL Approval Flow](#412-hitl-approval-flow)
   - 4.13 [Kubernetes Manifests](#413-kubernetes-manifests)
   - 4.14 [Nexus Policy File](#414-nexus-policy-file)
5. [Testing](#5-testing)
6. [Rollback Plan](#6-rollback-plan)
7. [Implementation Order](#7-implementation-order)

---

## 1. Context and Motivation

### What Phase 1 Delivered

Phase 1 evolved Nexus into a focused PI (Personal Intelligence) agent with:

- **Memory MCP** (SSE) — store/query knowledge, learnings, and context
- **Skills MCP** (SSE) — discover and execute registered Kubani skills
- **Fetch MCP** (stdio, in-process) — read any URL as markdown
- **web_search** (DuckDuckGo `@tool`) — internet search
- **5 workspace tools** (read/write/edit/bash/register_skill) — unchanged

This keeps the tool count low (~10-15 tools) and aligns with the Phase 3 swarm architecture where K8s, Temporal, Discord, Qdrant, ArXiv, and Prometheus are handled by specialized sub-agents. However, Phase 1 has several limitations:

1. **No centralized policy enforcement**: The `nexus.json` policy file is defense-in-depth documentation only — nothing enforces it at runtime. Any code with the MCP server URLs can call any tool.
2. **No audit trail**: Tool calls are not logged. There is no way to answer "what tool calls did Nexus make in the last hour?"
3. **No rate limiting**: A runaway agent loop could flood an MCP server with thousands of calls per second.
4. **Subprocess sandbox is weak**: The current sandbox uses `asyncio.create_subprocess_exec` with environment variable stripping. This provides no filesystem, network, or process isolation. A malicious skill can read any file on the host, make network calls, and consume unbounded resources.
5. **Static tool lists**: Adding or removing an MCP server requires a code change and redeployment. There is no way for an agent to discover available tools at runtime.
6. **No sub-agent support**: When Phase 3 adds specialized sub-agents (K8s Agent, Research Agent, etc.), each will need its own MCP access with different policies. Without a gateway, this means duplicating client setup and policy logic per agent.

### What Phase 2 Solves

Phase 2 introduces a **MCP Gateway** service that sits between all agents and all MCP backend servers. The gateway:

- Acts as a single entry point for all MCP tool calls (Nexus PI agent today, Phase 3 sub-agents tomorrow)
- Enforces per-agent policies (which servers, which tools, which namespaces)
- Rate limits tool calls per agent per tool
- Logs every tool call to PostgreSQL for audit
- Returns `approval_required` for restricted operations (integrating with the Temporal HITL flow)
- Exposes a `/tools` endpoint that returns the full tool manifest for dynamic discovery

Phase 2 also:

- Replaces the subprocess sandbox with **Docker container isolation** for code execution
- Adds **dynamic tool loading** so agents discover available tools from the gateway at startup (Nexus PI today, sub-agents in Phase 3)
- Implements a proper **HITL approval flow** that pauses the Temporal workflow until a human approves or rejects
- **Routes ALL MCP servers** through the gateway (Memory, Skills, K8s, Temporal, Discord, Qdrant) — even though the PI agent only uses Memory and Skills, the gateway manages all servers so Phase 3 sub-agents can access them through the same gateway

---

## 2. Architecture Overview

### Before (Phase 1 — PI Agent)

```
                        ┌──────────────────┐
                        │  Nexus PI Agent  │
                        │  (Strands)       │
                        │                  │
                        │  5 workspace     │
                        │  tools           │
                        │  + web_search    │
                        └─┬──────┬─────┬──┘
                          │      │     │
               SSE ───────┘      │     └────── stdio (in-process)
               (no policy,       │              (no policy, no audit)
                no audit)        │
           ┌─────────────────────┘
           ▼                 ▼                  ▼
      ┌──────────┐  ┌──────────┐  ┌──────────────────┐
      │ Memory   │  │ Skills   │  │ Fetch MCP        │
      │ MCP      │  │ MCP      │  │ (mcp-server-     │
      │ (SSE)    │  │ (SSE)    │  │  fetch, stdio)   │
      └──────────┘  └──────────┘  └──────────────────┘

      NOT connected (deferred to Phase 3 sub-agents):
      K8s MCP, Temporal MCP, Discord MCP, Qdrant MCP
```

### After (Phase 2)

```
      ┌──────────────────┐        ┌──────────────────────┐
      │  Nexus Agent     │        │  Future Agent X      │
      │  (Strands)       │        │                      │
      │                  │        │                      │
      │  Dynamic tools   │        │  Dynamic tools       │
      │  from gateway    │        │  from gateway        │
      └────────┬─────────┘        └──────────┬───────────┘
               │  Single SSE connection       │
               │  (all tools multiplexed)     │
               ▼                              ▼
      ┌───────────────────────────────────────────────────┐
      │              MCP Gateway (FastAPI)                 │
      │                                                   │
      │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐ │
      │  │ Policy │  │ Router │  │ Audit  │  │ Rate   │ │
      │  │ Engine │  │        │  │ Logger │  │ Limiter│ │
      │  └────────┘  └────────┘  └────────┘  └────────┘ │
      │                                                   │
      │  GET /tools — tool manifest                      │
      │  POST /call  — tool invocation                   │
      │  GET /health — health check                      │
      └──┬──────┬──────┬──────┬──────┬──────┬────────────┘
         │      │      │      │      │      │
         ▼      ▼      ▼      ▼      ▼      ▼
      ┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐
      │K8s   ││Tempo-││Disco-││Memor-││Qdrant││Skills│
      │MCP   ││ral   ││rd    ││y     ││MCP   ││MCP   │
      └──────┘└──────┘└──────┘└──────┘└──────┘└──────┘

      ┌───────────────────────────────────────────────────┐
      │           Container Sandbox (Docker)               │
      │                                                   │
      │  ┌─────────────────────────────────────────────┐ │
      │  │  Isolated container per execution            │ │
      │  │  - No host network                          │ │
      │  │  - CPU/memory limits                        │ │
      │  │  - Read-only root filesystem                │ │
      │  │  - /workspace volume mount                  │ │
      │  └─────────────────────────────────────────────┘ │
      └───────────────────────────────────────────────────┘
```

### HITL Approval Flow

```
  Nexus Agent calls tool      MCP Gateway checks policy
  via gateway                 ─────────────────────────►
       │                                │
       │                    ┌───────────┴──────────┐
       │                    │ requireApproval list  │
       │                    │ matches this tool?    │
       │                    └───────────┬──────────┘
       │                           YES  │  NO
       │                    ┌───────────┤  └──► Route to backend
       │                    ▼           │       return result
       │            Return JSON:        │
       │            {                   │
       │              "approval_required": true,
       │              "approval_id": "abc-123",
       │              "tool_name": "pods.delete",
       │              "args": {...}
       │            }
       │                    │
       ▼                    ▼
  Activity receives     Gateway logs approval
  approval_required     request to DB
  result                    │
       │                    ▼
       ▼              Discord/UI notification
  Workflow sets            sent to approvers
  state to                  │
  WAITING_APPROVAL          │
       │                    │
       ▼                    ▼
  workflow.wait_condition   Human clicks
  (approval signal)        Approve/Reject
       │                    │
       │◄───────────────────┘
       │  approval_decision signal
       ▼
  If approved: retry tool call with approval token
  If rejected: return rejection to agent
```

---

## 3. Prerequisites

Before starting Phase 2 implementation:

1. **Phase 1 complete**: Nexus PI agent has Memory MCP, Skills MCP, Fetch MCP, and web_search working end-to-end.
2. **Docker available on orchestrator nodes**: The Kubernetes nodes running the Nexus orchestrator must have Docker (or a compatible container runtime) accessible to the orchestrator pod. Alternatively, you can use the Kubernetes API to create ephemeral pods (Job-based sandbox), which avoids Docker-in-Docker. This plan uses the Docker SDK approach for local dev and outlines the K8s Job alternative for production.
3. **PostgreSQL database**: The existing `nexus` database (at `postgresql://nexus:...@postgresql.database.svc.cluster.local:5432/nexus`) must be accessible. We add an `audit_log` table to it.
4. **Registry image**: The container registry at `registry.almckay.io` must be accessible for pushing the gateway image and the sandbox base image.

### Python dependencies to add

Add to `pyproject.toml` under `[project.dependencies]`:
- `docker>=7.0.0` (for container sandbox)

No other new dependencies needed. FastAPI, Pydantic, httpx, asyncpg are already available.

---

## 4. Step-by-Step Implementation

### Implementation order summary

Build bottom-up: policy engine, audit, router, server, then Dockerfile, config, dynamic loader, modified activities, container sandbox, HITL flow, K8s manifests.

---

### 4.1 Gateway Policy Engine

**File:** `kubani/mcp/gateway/policy.py`

This module loads policy JSON files from `kubani/mcp/registry/policies/` and evaluates whether a given agent+tool combination is allowed, denied, or requires approval.

```python
"""MCP Gateway policy enforcement.

Loads per-agent policies from the MCP registry and evaluates tool call
permissions. Three possible outcomes:

- allow: the tool call is permitted, route it to the backend.
- deny: the tool call is forbidden for this agent.
- approval_required: the tool call needs human approval before execution.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default path to the registry directory containing policy files
REGISTRY_DIR = Path(__file__).resolve().parent.parent / "registry"


class PolicyDecision:
    """Result of a policy evaluation."""

    ALLOW = "allow"
    DENY = "deny"
    APPROVAL_REQUIRED = "approval_required"

    def __init__(
        self,
        action: str,
        reason: str = "",
        policy_name: str = "default",
    ):
        self.action = action
        self.reason = reason
        self.policy_name = policy_name

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "policy_name": self.policy_name,
        }


class PolicyEngine:
    """Evaluates tool call permissions against loaded policies.

    Loads the registry.json and per-agent policy files at construction
    time. Policies are cached in memory and can be reloaded.
    """

    def __init__(self, registry_dir: Path | None = None):
        self._registry_dir = registry_dir or REGISTRY_DIR
        self._registry: dict[str, Any] = {}
        self._policies: dict[str, dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        """Load or reload all policies from disk."""
        registry_file = self._registry_dir / "registry.json"
        if registry_file.exists():
            with open(registry_file) as f:
                self._registry = json.load(f)
            # Extract inline policies from registry.json
            self._policies = self._registry.get("policies", {})
        else:
            logger.warning(f"Registry file not found: {registry_file}")
            self._registry = {}
            self._policies = {}

        # Load individual policy files from policies/ directory
        policies_dir = self._registry_dir / "policies"
        if policies_dir.is_dir():
            for policy_file in policies_dir.glob("*.json"):
                policy_name = policy_file.stem  # e.g. "nexus" from "nexus.json"
                with open(policy_file) as f:
                    self._policies[policy_name] = json.load(f)

        logger.info(
            f"Loaded {len(self._policies)} policies: "
            f"{', '.join(self._policies.keys())}"
        )

    def get_server_for_tool(self, tool_name: str) -> str | None:
        """Look up which backend server owns a tool by matching capabilities.

        The registry.json maps server names to their capabilities list.
        A tool name like "pods_list" is matched against capability
        "pods.list" by replacing underscores with dots.

        Args:
            tool_name: The tool name as exposed by the MCP server
                       (e.g. "pods_list", "send_message").

        Returns:
            Server name string, or None if not found.
        """
        servers = self._registry.get("servers", {})
        # Normalize: MCP tools use underscores, capabilities use dots
        capability_name = tool_name.replace("_", ".")
        for server_name, server_config in servers.items():
            capabilities = server_config.get("capabilities", [])
            for cap in capabilities:
                if cap == capability_name:
                    return server_name
                # Also match partial prefixes: "pods.list" matches tool "list_pods_in_namespace"
                # We do exact match only — partial matching leads to ambiguity
        return None

    def evaluate(
        self,
        agent_id: str,
        tool_name: str,
        server_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        """Evaluate whether an agent is allowed to call a tool.

        Checks in order:
        1. Is the server in the agent's allowedServers list?
        2. Does the tool capability appear in the requireApproval list?
        3. Are there namespace restrictions that apply?

        Args:
            agent_id: The calling agent's identifier (e.g. "nexus").
            tool_name: The tool being called (e.g. "pods_delete").
            server_name: The backend server that owns the tool.
            arguments: The tool call arguments (used for namespace checks).

        Returns:
            PolicyDecision with action, reason, and policy_name.
        """
        # Look up agent-specific policy, fall back to default
        policy = self._policies.get(agent_id, self._policies.get("default", {}))
        policy_name = agent_id if agent_id in self._policies else "default"

        # Check 1: Is the server allowed?
        allowed_servers = policy.get("allowedServers", [])
        if allowed_servers and server_name not in allowed_servers:
            return PolicyDecision(
                action=PolicyDecision.DENY,
                reason=f"Server '{server_name}' not in allowed list for agent '{agent_id}'",
                policy_name=policy_name,
            )

        # Check 2: Is the agent read-only?
        if policy.get("readOnly", False):
            # Read-only agents can only call tools on read-only servers
            servers = self._registry.get("servers", {})
            server_config = servers.get(server_name, {})
            if not server_config.get("readOnly", False):
                return PolicyDecision(
                    action=PolicyDecision.DENY,
                    reason=f"Agent '{agent_id}' is read-only but server '{server_name}' is read-write",
                    policy_name=policy_name,
                )

        # Check 3: Does this tool require approval?
        require_approval = policy.get("requireApproval", [])
        capability_name = tool_name.replace("_", ".")
        for approval_pattern in require_approval:
            if approval_pattern == "*":
                return PolicyDecision(
                    action=PolicyDecision.APPROVAL_REQUIRED,
                    reason=f"All tools require approval for agent '{agent_id}'",
                    policy_name=policy_name,
                )
            if approval_pattern == capability_name:
                return PolicyDecision(
                    action=PolicyDecision.APPROVAL_REQUIRED,
                    reason=f"Tool '{tool_name}' requires approval per policy '{policy_name}'",
                    policy_name=policy_name,
                )

        # Check 4: Namespace restrictions
        namespace_restrictions = policy.get("namespaceRestrictions", {})
        if namespace_restrictions and arguments:
            namespace = arguments.get("namespace", "")
            deny_namespaces = namespace_restrictions.get("deny", [])
            if namespace in deny_namespaces:
                return PolicyDecision(
                    action=PolicyDecision.DENY,
                    reason=f"Namespace '{namespace}' is denied for agent '{agent_id}'",
                    policy_name=policy_name,
                )

        return PolicyDecision(
            action=PolicyDecision.ALLOW,
            reason="Allowed by policy",
            policy_name=policy_name,
        )

    def get_allowed_servers(self, agent_id: str) -> list[str]:
        """Get the list of allowed servers for an agent.

        Args:
            agent_id: The agent identifier.

        Returns:
            List of server name strings.
        """
        policy = self._policies.get(agent_id, self._policies.get("default", {}))
        return policy.get("allowedServers", [])

    def get_server_config(self, server_name: str) -> dict[str, Any] | None:
        """Get the configuration for a backend server.

        Args:
            server_name: The server name from registry.json.

        Returns:
            Server config dict, or None if not found.
        """
        return self._registry.get("servers", {}).get(server_name)
```

---

### 4.2 Gateway Audit Logger

**File:** `kubani/mcp/gateway/audit.py`

Logs every tool call to PostgreSQL for observability and compliance. The `audit_log` table is created automatically on first use.

```python
"""MCP Gateway audit logging.

Records every tool call that passes through the gateway to a PostgreSQL
table. This provides a complete audit trail of what tools were called,
by which agent, with what arguments, and what the result was.

The audit_log table is created automatically on first connection if it
does not exist.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# SQL to create the audit table
CREATE_AUDIT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS mcp_audit_log (
    id              BIGSERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    agent_id        TEXT NOT NULL,
    tool_name       TEXT NOT NULL,
    server_name     TEXT NOT NULL,
    arguments       JSONB,
    policy_decision TEXT NOT NULL,
    policy_name     TEXT NOT NULL DEFAULT 'default',
    approval_id     TEXT,
    result_success  BOOLEAN,
    result_error    TEXT,
    duration_ms     INTEGER,
    metadata        JSONB
);

CREATE INDEX IF NOT EXISTS idx_audit_agent_id ON mcp_audit_log (agent_id);
CREATE INDEX IF NOT EXISTS idx_audit_tool_name ON mcp_audit_log (tool_name);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON mcp_audit_log (timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_approval_id ON mcp_audit_log (approval_id);
"""

# SQL to insert an audit record
INSERT_AUDIT_SQL = """
INSERT INTO mcp_audit_log (
    agent_id, tool_name, server_name, arguments,
    policy_decision, policy_name, approval_id,
    result_success, result_error, duration_ms, metadata
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
RETURNING id;
"""

# SQL to query recent audit records
QUERY_RECENT_SQL = """
SELECT id, timestamp, agent_id, tool_name, server_name,
       arguments, policy_decision, policy_name, approval_id,
       result_success, result_error, duration_ms, metadata
FROM mcp_audit_log
ORDER BY timestamp DESC
LIMIT $1;
"""

# SQL to query audit records for a specific agent
QUERY_BY_AGENT_SQL = """
SELECT id, timestamp, agent_id, tool_name, server_name,
       arguments, policy_decision, policy_name, approval_id,
       result_success, result_error, duration_ms, metadata
FROM mcp_audit_log
WHERE agent_id = $1
ORDER BY timestamp DESC
LIMIT $2;
"""


class AuditLogger:
    """Logs MCP tool calls to PostgreSQL.

    Manages a connection pool and provides methods to log and query
    audit records. The audit table is created automatically on
    initialization.
    """

    def __init__(self, db_url: str | None = None):
        self._db_url = db_url or os.environ.get(
            "NEXUS_DATABASE_URL",
            "postgresql://kubani:kubani@localhost:5432/kubani_nexus",
        )
        self._pool = None

    async def initialize(self) -> None:
        """Create the connection pool and ensure the audit table exists."""
        import asyncpg

        self._pool = await asyncpg.create_pool(self._db_url, min_size=2, max_size=10)
        async with self._pool.acquire() as conn:
            await conn.execute(CREATE_AUDIT_TABLE_SQL)
        logger.info("Audit logger initialized, table ensured")

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def log_call(
        self,
        agent_id: str,
        tool_name: str,
        server_name: str,
        arguments: dict[str, Any] | None,
        policy_decision: str,
        policy_name: str = "default",
        approval_id: str | None = None,
        result_success: bool | None = None,
        result_error: str | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Log a tool call to the audit table.

        Args:
            agent_id: The calling agent's identifier.
            tool_name: The tool that was called.
            server_name: The backend server that handled the call.
            arguments: The tool call arguments (sanitized — no secrets).
            policy_decision: The policy engine's decision (allow/deny/approval_required).
            policy_name: Which policy was applied.
            approval_id: If approval was required, the approval request ID.
            result_success: Whether the tool call succeeded (None if not yet executed).
            result_error: Error message if the call failed.
            duration_ms: How long the call took in milliseconds.
            metadata: Additional structured metadata.

        Returns:
            The audit record ID.
        """
        if self._pool is None:
            logger.warning("Audit logger not initialized, skipping log")
            return -1

        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    INSERT_AUDIT_SQL,
                    agent_id,
                    tool_name,
                    server_name,
                    json.dumps(arguments) if arguments else None,
                    policy_decision,
                    policy_name,
                    approval_id,
                    result_success,
                    result_error,
                    duration_ms,
                    json.dumps(metadata) if metadata else None,
                )
                return row["id"]
        except Exception as e:
            logger.error(f"Failed to log audit record: {e}")
            return -1

    async def update_result(
        self,
        audit_id: int,
        result_success: bool,
        result_error: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Update an existing audit record with the call result.

        Used when a call is logged before execution (e.g., for approval
        flow) and the result arrives later.

        Args:
            audit_id: The audit record ID to update.
            result_success: Whether the call succeeded.
            result_error: Error message if the call failed.
            duration_ms: How long the call took.
        """
        if self._pool is None:
            return

        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE mcp_audit_log
                    SET result_success = $1, result_error = $2, duration_ms = $3
                    WHERE id = $4
                    """,
                    result_success,
                    result_error,
                    duration_ms,
                    audit_id,
                )
        except Exception as e:
            logger.error(f"Failed to update audit record {audit_id}: {e}")

    async def query_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Query recent audit records.

        Args:
            limit: Maximum number of records to return.

        Returns:
            List of audit record dicts, newest first.
        """
        if self._pool is None:
            return []

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(QUERY_RECENT_SQL, limit)
            return [dict(row) for row in rows]

    async def query_by_agent(
        self, agent_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Query audit records for a specific agent.

        Args:
            agent_id: The agent to query for.
            limit: Maximum number of records to return.

        Returns:
            List of audit record dicts, newest first.
        """
        if self._pool is None:
            return []

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(QUERY_BY_AGENT_SQL, agent_id, limit)
            return [dict(row) for row in rows]
```

---

### 4.3 Gateway Router

**File:** `kubani/mcp/gateway/router.py`

Routes tool calls from the gateway to the correct backend MCP server. Handles both SSE (most servers) and stdio (Kubernetes MCP) transports. Maintains a mapping of tool names to servers.

```python
"""MCP Gateway tool call router.

Maintains a mapping of tool names to backend MCP servers and routes
tool calls to the correct backend. Supports SSE transport (the common
case) and provides connection management.

The router builds its tool-to-server mapping by querying each backend
server's list_tools endpoint at startup. This mapping is cached and
refreshed periodically.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from kubani.framework.mcp.client import MCPResponse, MCPServerClient

logger = logging.getLogger(__name__)


class ToolDefinition:
    """Metadata about a tool from a backend server."""

    def __init__(
        self,
        name: str,
        description: str,
        server_name: str,
        server_url: str,
        input_schema: dict[str, Any] | None = None,
    ):
        self.name = name
        self.description = description
        self.server_name = server_name
        self.server_url = server_url
        self.input_schema = input_schema or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "server_name": self.server_name,
            "input_schema": self.input_schema,
        }


class GatewayRouter:
    """Routes tool calls to the correct backend MCP server.

    At startup, queries all configured backend servers for their
    available tools and builds a name-to-server mapping. This mapping
    is used to route incoming tool calls.

    Attributes:
        _servers: Dict of server_name -> MCPServerClient instances.
        _tool_map: Dict of tool_name -> ToolDefinition.
    """

    def __init__(self) -> None:
        self._servers: dict[str, MCPServerClient] = {}
        self._tool_map: dict[str, ToolDefinition] = {}
        self._last_refresh: float = 0.0
        self._refresh_interval: float = 300.0  # 5 minutes

    def register_server(
        self, name: str, url: str, timeout: float = 30.0
    ) -> None:
        """Register a backend MCP server.

        Args:
            name: Server name (e.g., "temporal", "discord").
            url: Server SSE URL (e.g., "http://temporal-mcp:8081").
            timeout: Connection timeout in seconds.
        """
        self._servers[name] = MCPServerClient(name=name, url=url, timeout=timeout)
        logger.info(f"Registered backend server: {name} at {url}")

    async def refresh_tool_map(self) -> dict[str, ToolDefinition]:
        """Query all backend servers for their tools and rebuild the map.

        Returns:
            The refreshed tool map.
        """
        new_map: dict[str, ToolDefinition] = {}
        tasks = {}

        for server_name, client in self._servers.items():
            tasks[server_name] = asyncio.create_task(
                self._discover_server_tools(server_name, client)
            )

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        for server_name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.warning(
                    f"Failed to discover tools for {server_name}: {result}"
                )
                continue
            for tool_def in result:
                if tool_def.name in new_map:
                    logger.warning(
                        f"Duplicate tool name '{tool_def.name}' from "
                        f"{server_name} (already registered from "
                        f"{new_map[tool_def.name].server_name}). "
                        f"Keeping the first registration."
                    )
                    continue
                new_map[tool_def.name] = tool_def

        self._tool_map = new_map
        self._last_refresh = time.monotonic()
        logger.info(
            f"Refreshed tool map: {len(new_map)} tools from "
            f"{len(self._servers)} servers"
        )
        return new_map

    async def _discover_server_tools(
        self, server_name: str, client: MCPServerClient
    ) -> list[ToolDefinition]:
        """Query a single server for its tools.

        Args:
            server_name: The server's name.
            client: The MCPServerClient to query.

        Returns:
            List of ToolDefinition objects.
        """
        try:
            async with client._connect() as session:
                result = await session.list_tools()
                tools = []
                for tool in result.tools:
                    tool_def = ToolDefinition(
                        name=tool.name,
                        description=tool.description or "",
                        server_name=server_name,
                        server_url=client.url,
                        input_schema=tool.inputSchema if hasattr(tool, "inputSchema") else {},
                    )
                    tools.append(tool_def)
                return tools
        except Exception as e:
            logger.warning(f"Failed to list tools for {server_name}: {e}")
            return []

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> MCPResponse:
        """Route a tool call to the correct backend server.

        Args:
            tool_name: The tool to call.
            arguments: The tool arguments.

        Returns:
            MCPResponse from the backend server.
        """
        tool_def = self._tool_map.get(tool_name)
        if tool_def is None:
            return MCPResponse(
                success=False,
                data=None,
                error=f"Unknown tool: {tool_name}. "
                f"Available tools: {', '.join(sorted(self._tool_map.keys())[:20])}",
            )

        client = self._servers.get(tool_def.server_name)
        if client is None:
            return MCPResponse(
                success=False,
                data=None,
                error=f"Backend server '{tool_def.server_name}' not available",
            )

        return await client.call_tool(tool_name, **arguments)

    def get_tool_manifest(
        self, allowed_servers: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Get the complete tool manifest, optionally filtered by server.

        Args:
            allowed_servers: If provided, only include tools from these servers.

        Returns:
            List of tool definition dicts.
        """
        result = []
        for tool_def in self._tool_map.values():
            if allowed_servers and tool_def.server_name not in allowed_servers:
                continue
            result.append(tool_def.to_dict())
        return result

    def get_server_for_tool(self, tool_name: str) -> str | None:
        """Look up which server owns a tool.

        Args:
            tool_name: The tool name.

        Returns:
            Server name, or None.
        """
        tool_def = self._tool_map.get(tool_name)
        return tool_def.server_name if tool_def else None

    @property
    def tool_count(self) -> int:
        """Number of registered tools."""
        return len(self._tool_map)

    @property
    def server_count(self) -> int:
        """Number of registered backend servers."""
        return len(self._servers)

    def needs_refresh(self) -> bool:
        """Check if the tool map should be refreshed."""
        return (time.monotonic() - self._last_refresh) > self._refresh_interval
```

---

### 4.4 Gateway Server

**File:** `kubani/mcp/gateway/server.py`

The main FastAPI application that ties together the router, policy engine, and audit logger.

```python
"""MCP Gateway Server.

A centralized gateway that sits between agents and all MCP backend
servers. Provides:

- Tool discovery: GET /tools returns all available tools
- Tool invocation: POST /call routes and executes tool calls
- Policy enforcement: per-agent allow/deny/approval_required
- Rate limiting: per-agent per-tool rate limits
- Audit logging: every call logged to PostgreSQL

Usage:
    uvicorn kubani.mcp.gateway.server:app --host 0.0.0.0 --port 8090
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =========================================================================
# Request/Response Models
# =========================================================================


class ToolCallRequest(BaseModel):
    """Request to call a tool through the gateway."""

    agent_id: str = Field(description="The calling agent's identifier")
    tool_name: str = Field(description="The tool to call")
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="Tool arguments"
    )
    approval_token: str | None = Field(
        default=None,
        description="Approval token for previously-approved restricted calls",
    )


class ToolCallResponse(BaseModel):
    """Response from a tool call through the gateway."""

    success: bool
    data: Any = None
    error: str | None = None
    approval_required: bool = False
    approval_id: str | None = None
    approval_reason: str | None = None
    audit_id: int | None = None
    duration_ms: int = 0


class ToolManifestEntry(BaseModel):
    """A single tool in the manifest."""

    name: str
    description: str
    server_name: str
    input_schema: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    tool_count: int
    server_count: int
    uptime_seconds: int


# =========================================================================
# Rate Limiter
# =========================================================================


class RateLimiter:
    """Simple in-memory sliding window rate limiter.

    Limits each agent+tool combination to a maximum number of calls
    within a time window.
    """

    def __init__(
        self, max_calls: int = 60, window_seconds: float = 60.0
    ):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._calls: dict[str, list[float]] = defaultdict(list)

    def check(self, agent_id: str, tool_name: str) -> bool:
        """Check if the call is within rate limits.

        Args:
            agent_id: The calling agent.
            tool_name: The tool being called.

        Returns:
            True if the call is allowed, False if rate-limited.
        """
        key = f"{agent_id}:{tool_name}"
        now = time.monotonic()
        cutoff = now - self.window_seconds

        # Remove expired entries
        self._calls[key] = [t for t in self._calls[key] if t > cutoff]

        if len(self._calls[key]) >= self.max_calls:
            return False

        self._calls[key].append(now)
        return True


# =========================================================================
# Approval Store
# =========================================================================


class PendingApproval:
    """A tool call waiting for human approval."""

    def __init__(
        self,
        approval_id: str,
        agent_id: str,
        tool_name: str,
        server_name: str,
        arguments: dict[str, Any],
        audit_id: int,
    ):
        self.approval_id = approval_id
        self.agent_id = agent_id
        self.tool_name = tool_name
        self.server_name = server_name
        self.arguments = arguments
        self.audit_id = audit_id
        self.created_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "agent_id": self.agent_id,
            "tool_name": self.tool_name,
            "server_name": self.server_name,
            "arguments": self.arguments,
            "audit_id": self.audit_id,
            "created_at": self.created_at,
        }


# =========================================================================
# Application State
# =========================================================================


class GatewayState:
    """Shared state for the MCP Gateway."""

    def __init__(self) -> None:
        from kubani.mcp.gateway.audit import AuditLogger
        from kubani.mcp.gateway.policy import PolicyEngine
        from kubani.mcp.gateway.router import GatewayRouter

        self.router = GatewayRouter()
        self.policy = PolicyEngine()
        self.audit = AuditLogger()
        self.rate_limiter = RateLimiter(max_calls=120, window_seconds=60.0)
        self.pending_approvals: dict[str, PendingApproval] = {}
        self.start_time = time.monotonic()

    async def initialize(self) -> None:
        """Initialize all components."""
        # Initialize audit logger (creates table if needed)
        await self.audit.initialize()

        # Register backend servers from environment or config
        self._register_servers_from_env()

        # Discover tools from all backends
        await self.router.refresh_tool_map()

        logger.info(
            f"MCP Gateway initialized: {self.router.tool_count} tools "
            f"from {self.router.server_count} servers"
        )

    def _register_servers_from_env(self) -> None:
        """Register backend MCP servers from environment variables.

        Environment variables follow the pattern:
            MCP_GATEWAY_SERVER_{NAME}_URL=http://...

        Falls back to well-known defaults for the standard servers.
        """
        # Well-known server defaults (in-cluster URLs)
        defaults = {
            "temporal": os.environ.get(
                "MCP_GATEWAY_SERVER_TEMPORAL_URL",
                "http://temporal-mcp-server.ai-agents.svc.cluster.local:8081",
            ),
            "memory": os.environ.get(
                "MCP_GATEWAY_SERVER_MEMORY_URL",
                "http://memory-mcp-server.ai-agents.svc.cluster.local:8083",
            ),
            "discord": os.environ.get(
                "MCP_GATEWAY_SERVER_DISCORD_URL",
                "http://discord-mcp-server.ai-agents.svc.cluster.local:8084",
            ),
            "qdrant": os.environ.get(
                "MCP_GATEWAY_SERVER_QDRANT_URL",
                "http://qdrant-mcp-server.ai-agents.svc.cluster.local:8082",
            ),
            "skills": os.environ.get(
                "MCP_GATEWAY_SERVER_SKILLS_URL",
                "http://skills-mcp-server.ai-agents.svc.cluster.local:8086",
            ),
        }

        for name, url in defaults.items():
            if url:
                self.router.register_server(name, url)

    async def cleanup(self) -> None:
        """Clean up resources."""
        await self.audit.close()


# Global state
_state = GatewayState()


# =========================================================================
# Application Lifecycle
# =========================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown."""
    await _state.initialize()
    yield
    await _state.cleanup()


# =========================================================================
# Application Factory
# =========================================================================


def create_app() -> FastAPI:
    """Create the MCP Gateway FastAPI application."""
    application = FastAPI(
        title="Kubani MCP Gateway",
        description="Centralized gateway for MCP tool routing, policy, and audit",
        version="0.1.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(_create_tools_router())
    application.include_router(_create_call_router())
    application.include_router(_create_approvals_router())
    application.include_router(_create_health_router())

    return application


# =========================================================================
# Tool Discovery Routes
# =========================================================================


def _create_tools_router():
    from fastapi import APIRouter

    router = APIRouter(tags=["tools"])

    @router.get("/tools", response_model=list[ToolManifestEntry])
    async def get_tools(
        agent_id: str = Query(
            default="default",
            description="Agent ID to filter tools by policy",
        ),
    ) -> list[ToolManifestEntry]:
        """Get the complete tool manifest filtered by agent policy.

        Returns all tools that the specified agent is allowed to access
        based on its policy's allowedServers list.
        """
        if _state.router.needs_refresh():
            await _state.router.refresh_tool_map()

        allowed_servers = _state.policy.get_allowed_servers(agent_id)
        manifest = _state.router.get_tool_manifest(
            allowed_servers=allowed_servers if allowed_servers else None
        )
        return [ToolManifestEntry(**entry) for entry in manifest]

    @router.post("/tools/refresh")
    async def refresh_tools() -> dict[str, int]:
        """Force refresh the tool map from all backend servers."""
        await _state.router.refresh_tool_map()
        return {"tool_count": _state.router.tool_count}

    return router


# =========================================================================
# Tool Call Routes
# =========================================================================


def _create_call_router():
    from fastapi import APIRouter

    router = APIRouter(tags=["call"])

    @router.post("/call", response_model=ToolCallResponse)
    async def call_tool(request: ToolCallRequest) -> ToolCallResponse:
        """Call a tool through the gateway.

        The gateway:
        1. Looks up the tool's backend server.
        2. Checks rate limits.
        3. Evaluates the agent's policy.
        4. If allowed, routes the call to the backend.
        5. Logs the call to the audit table.
        6. Returns the result.

        If the policy says "approval_required", the call is NOT executed.
        Instead, the gateway returns a response with approval_required=True
        and an approval_id. The caller must re-submit with an
        approval_token after a human approves.
        """
        start_time = time.monotonic()

        # Step 1: Look up the backend server for this tool
        server_name = _state.router.get_server_for_tool(request.tool_name)
        if server_name is None:
            return ToolCallResponse(
                success=False,
                error=f"Unknown tool: {request.tool_name}",
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

        # Step 2: Rate limit check
        if not _state.rate_limiter.check(request.agent_id, request.tool_name):
            audit_id = await _state.audit.log_call(
                agent_id=request.agent_id,
                tool_name=request.tool_name,
                server_name=server_name,
                arguments=request.arguments,
                policy_decision="rate_limited",
                result_success=False,
                result_error="Rate limit exceeded",
            )
            return ToolCallResponse(
                success=False,
                error="Rate limit exceeded. Try again in a few seconds.",
                audit_id=audit_id,
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

        # Step 3: Policy evaluation
        decision = _state.policy.evaluate(
            agent_id=request.agent_id,
            tool_name=request.tool_name,
            server_name=server_name,
            arguments=request.arguments,
        )

        # Step 3a: Check for approval token on previously-approved calls
        if (
            decision.action == "approval_required"
            and request.approval_token is not None
        ):
            pending = _state.pending_approvals.get(request.approval_token)
            if pending and pending.tool_name == request.tool_name:
                # Approval token is valid — proceed with the call
                decision.action = "allow"
                decision.reason = f"Approved via token {request.approval_token}"
                del _state.pending_approvals[request.approval_token]
            else:
                return ToolCallResponse(
                    success=False,
                    error="Invalid or expired approval token",
                    duration_ms=int((time.monotonic() - start_time) * 1000),
                )

        # Step 3b: Handle denial
        if decision.action == "deny":
            audit_id = await _state.audit.log_call(
                agent_id=request.agent_id,
                tool_name=request.tool_name,
                server_name=server_name,
                arguments=request.arguments,
                policy_decision="deny",
                policy_name=decision.policy_name,
                result_success=False,
                result_error=decision.reason,
            )
            return ToolCallResponse(
                success=False,
                error=decision.reason,
                audit_id=audit_id,
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

        # Step 3c: Handle approval required
        if decision.action == "approval_required":
            approval_id = str(uuid.uuid4())
            audit_id = await _state.audit.log_call(
                agent_id=request.agent_id,
                tool_name=request.tool_name,
                server_name=server_name,
                arguments=request.arguments,
                policy_decision="approval_required",
                policy_name=decision.policy_name,
                approval_id=approval_id,
            )
            _state.pending_approvals[approval_id] = PendingApproval(
                approval_id=approval_id,
                agent_id=request.agent_id,
                tool_name=request.tool_name,
                server_name=server_name,
                arguments=request.arguments,
                audit_id=audit_id,
            )
            return ToolCallResponse(
                success=False,
                approval_required=True,
                approval_id=approval_id,
                approval_reason=decision.reason,
                audit_id=audit_id,
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

        # Step 4: Route the call to the backend
        result = await _state.router.call_tool(
            request.tool_name, request.arguments
        )

        duration_ms = int((time.monotonic() - start_time) * 1000)

        # Step 5: Log to audit
        audit_id = await _state.audit.log_call(
            agent_id=request.agent_id,
            tool_name=request.tool_name,
            server_name=server_name,
            arguments=request.arguments,
            policy_decision="allow",
            policy_name=decision.policy_name,
            result_success=result.success,
            result_error=result.error,
            duration_ms=duration_ms,
        )

        # Step 6: Return the result
        return ToolCallResponse(
            success=result.success,
            data=result.data,
            error=result.error,
            audit_id=audit_id,
            duration_ms=duration_ms,
        )

    return router


# =========================================================================
# Approval Routes
# =========================================================================


def _create_approvals_router():
    from fastapi import APIRouter

    router = APIRouter(prefix="/approvals", tags=["approvals"])

    @router.get("")
    async def list_pending_approvals() -> list[dict[str, Any]]:
        """List all pending approval requests."""
        return [pa.to_dict() for pa in _state.pending_approvals.values()]

    @router.post("/{approval_id}/approve")
    async def approve(approval_id: str) -> dict[str, str]:
        """Approve a pending tool call.

        After approval, the caller can re-submit the tool call with the
        approval_id as the approval_token.
        """
        pending = _state.pending_approvals.get(approval_id)
        if pending is None:
            raise HTTPException(status_code=404, detail="Approval not found")

        # Don't remove yet — the caller needs to re-submit with the token.
        # The token is consumed when the call is retried.
        await _state.audit.update_result(
            pending.audit_id,
            result_success=True,
            result_error=None,
        )

        return {"status": "approved", "approval_id": approval_id}

    @router.post("/{approval_id}/reject")
    async def reject(
        approval_id: str, reason: str = Query(default="Rejected by operator")
    ) -> dict[str, str]:
        """Reject a pending tool call."""
        pending = _state.pending_approvals.pop(approval_id, None)
        if pending is None:
            raise HTTPException(status_code=404, detail="Approval not found")

        await _state.audit.update_result(
            pending.audit_id,
            result_success=False,
            result_error=f"Rejected: {reason}",
        )

        return {"status": "rejected", "approval_id": approval_id}

    return router


# =========================================================================
# Health Routes
# =========================================================================


def _create_health_router():
    from fastapi import APIRouter

    router = APIRouter(tags=["health"])

    @router.get("/health", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        return HealthResponse(
            status="healthy",
            tool_count=_state.router.tool_count,
            server_count=_state.router.server_count,
            uptime_seconds=int(time.monotonic() - _state.start_time),
        )

    @router.get("/audit")
    async def get_audit_log(
        limit: int = Query(default=50, le=500),
        agent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query the audit log."""
        if agent_id:
            return await _state.audit.query_by_agent(agent_id, limit)
        return await _state.audit.query_recent(limit)

    return router


# =========================================================================
# Module-level app instance
# =========================================================================

app = create_app()
```

Also create the package `__init__.py`:

**File:** `kubani/mcp/gateway/__init__.py`

```python
"""MCP Gateway — centralized tool routing, policy, and audit."""
```

---

### 4.5 Gateway Dockerfile

**File:** `kubani/mcp/gateway/Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy workspace root for installable package
COPY pyproject.toml README.md ./
COPY kubani/ kubani/

# Install the kubani package plus gateway dependencies
RUN pip install --no-cache-dir -e "." \
    && pip install --no-cache-dir uvicorn[standard] fastapi asyncpg

# Run as non-root user
RUN useradd -m -u 1000 appuser
USER appuser

EXPOSE 8090

CMD ["uvicorn", "kubani.mcp.gateway.server:app", "--host", "0.0.0.0", "--port", "8090"]
```

---

### 4.6 Framework Config Changes

**File:** `kubani/framework/config.py`

Add gateway configuration to `MCPServerConfig`. This is a minimal, surgical change.

**What to change:** Add two new fields to the `MCPServerConfig` class after the existing `skills_url` and `skills_enabled` fields.

Add the following two fields to the `MCPServerConfig` class (after line 109 in the current file):

```python
    # MCP Gateway
    gateway_url: str = Field(
        default="http://localhost:8090",
        description="MCP Gateway URL",
    )
    gateway_enabled: bool = Field(
        default=False,
        description="Route tool calls through MCP Gateway instead of direct connections",
    )
```

**Why `gateway_enabled` defaults to False:** This allows Phase 1 direct connections to continue working. Phase 2 is opt-in by setting `MCP_GATEWAY_ENABLED=true` or `gateway_enabled: true` in config YAML.

Also add a convenience function at the bottom of the file (after `get_embeddings_config`):

```python
def get_gateway_config() -> tuple[str, bool]:
    """Get MCP Gateway URL and enabled flag."""
    config = get_config().mcp
    return config.gateway_url, config.gateway_enabled
```

---

### 4.7 Dynamic Tool Loader

**File:** `kubani/nexus/tools/dynamic_loader.py`

This module queries the MCP Gateway's `/tools` endpoint and dynamically generates Strands `@tool` functions for each available tool.

```python
"""Dynamic tool loader for the Nexus agent.

Queries the MCP Gateway's /tools endpoint to discover available tools,
then dynamically generates Strands @tool functions for each tool.
This replaces the static MCP tool wrappers from Phase 1.

The generated tools call back through the gateway's /call endpoint,
which handles policy enforcement, rate limiting, and audit logging.

Usage:
    from kubani.nexus.tools.dynamic_loader import load_gateway_tools

    tools = await load_gateway_tools(agent_id="nexus")
    agent = Agent(model=model, tools=tools, system_prompt=prompt)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from strands import tool

logger = logging.getLogger(__name__)

# Cache for loaded tools to avoid re-querying on every agent turn
_cached_tools: list | None = None
_cached_manifest: list[dict[str, Any]] | None = None


async def load_gateway_tools(
    gateway_url: str,
    agent_id: str = "nexus",
    timeout: float = 15.0,
) -> list:
    """Query the gateway and generate Strands tools dynamically.

    Each tool returned by the gateway becomes a Strands @tool function
    that calls gateway /call endpoint when invoked.

    Args:
        gateway_url: The MCP Gateway base URL (e.g., "http://localhost:8090").
        agent_id: The agent identifier for policy filtering.
        timeout: HTTP request timeout.

    Returns:
        List of Strands tool callables.
    """
    global _cached_tools, _cached_manifest

    manifest = await _fetch_manifest(gateway_url, agent_id, timeout)

    # Check if manifest has changed
    if _cached_manifest == manifest and _cached_tools is not None:
        logger.debug("Using cached dynamic tools (manifest unchanged)")
        return _cached_tools

    tools = []
    for entry in manifest:
        tool_fn = _create_tool_function(
            gateway_url=gateway_url,
            agent_id=agent_id,
            tool_name=entry["name"],
            tool_description=entry["description"],
            input_schema=entry.get("input_schema", {}),
            timeout=timeout,
        )
        tools.append(tool_fn)

    _cached_tools = tools
    _cached_manifest = manifest
    logger.info(f"Loaded {len(tools)} dynamic tools from gateway for agent '{agent_id}'")
    return tools


async def _fetch_manifest(
    gateway_url: str, agent_id: str, timeout: float
) -> list[dict[str, Any]]:
    """Fetch the tool manifest from the gateway.

    Args:
        gateway_url: Gateway base URL.
        agent_id: Agent ID for filtering.
        timeout: Request timeout.

    Returns:
        List of tool definition dicts.
    """
    url = f"{gateway_url.rstrip('/')}/tools"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params={"agent_id": agent_id},
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Failed to fetch tool manifest from {url}: {e}")
        return []


def _create_tool_function(
    gateway_url: str,
    agent_id: str,
    tool_name: str,
    tool_description: str,
    input_schema: dict[str, Any],
    timeout: float,
):
    """Create a single Strands @tool function for a gateway tool.

    The generated function accepts **kwargs matching the tool's input
    schema and calls the gateway's /call endpoint.

    Args:
        gateway_url: Gateway base URL.
        agent_id: Agent ID for the call.
        tool_name: The tool's name.
        tool_description: The tool's description (used in docstring).
        input_schema: JSON Schema for the tool's input.
        timeout: Request timeout.

    Returns:
        A Strands tool callable.
    """
    call_url = f"{gateway_url.rstrip('/')}/call"

    @tool(name=tool_name)
    async def gateway_tool(**kwargs: Any) -> str:
        """Dynamically generated tool that calls through the MCP Gateway."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    call_url,
                    json={
                        "agent_id": agent_id,
                        "tool_name": tool_name,
                        "arguments": kwargs,
                    },
                    timeout=timeout,
                )
                response.raise_for_status()
                result = response.json()

                if result.get("approval_required"):
                    approval_id = result.get("approval_id", "unknown")
                    reason = result.get("approval_reason", "Policy restriction")
                    return (
                        f"APPROVAL_REQUIRED: This operation ({tool_name}) "
                        f"needs human approval. Reason: {reason}. "
                        f"Approval ID: {approval_id}. "
                        f"The request has been sent to operators for review."
                    )

                if not result.get("success"):
                    error = result.get("error", "Unknown error")
                    return f"Error: {error}"

                data = result.get("data")
                if data is None:
                    return "Success (no data returned)"
                if isinstance(data, str):
                    return data
                import json
                return json.dumps(data, indent=2, default=str)

        except httpx.HTTPStatusError as e:
            return f"Error: Gateway returned HTTP {e.response.status_code}: {e.response.text}"
        except httpx.ConnectError:
            return f"Error: Cannot connect to MCP Gateway at {call_url}"
        except Exception as e:
            return f"Error: {e}"

    # Override the docstring with the actual tool description
    gateway_tool.__doc__ = tool_description
    # Attach the input schema for Strands to use
    if input_schema and "properties" in input_schema:
        gateway_tool.__tool_input_schema__ = input_schema

    return gateway_tool


def clear_cache() -> None:
    """Clear the cached tools. Call this to force re-discovery."""
    global _cached_tools, _cached_manifest
    _cached_tools = None
    _cached_manifest = None
```

---

### 4.8 Modified Strands Tools

**File:** `kubani/nexus/tools/strands_tools.py`

Add a `create_dynamic_tools` function that combines the existing core tools with dynamically loaded gateway tools. The existing `create_tools` function is kept unchanged for backward compatibility.

**What to change:** Add the following function after the existing `create_tools` function (after line 111).

```python
async def create_dynamic_tools(
    workspace: Path,
    gateway_url: str,
    agent_id: str = "nexus",
) -> list:
    """Create the full tool list: core tools + dynamic gateway tools.

    This is the Phase 2 replacement for create_tools(). It combines the
    5 core workspace tools (read_file, write_file, edit_file, bash,
    register_skill) with dynamically loaded MCP tools from the gateway.

    Args:
        workspace: The user's workspace directory.
        gateway_url: The MCP Gateway base URL.
        agent_id: The agent identifier for gateway policy filtering.

    Returns:
        List of Strands tool instances (core + gateway).
    """
    from kubani.nexus.tools.dynamic_loader import load_gateway_tools

    # Get the 5 core tools (unchanged from Phase 1)
    core = create_tools(workspace)

    # Load dynamic tools from the gateway
    try:
        gateway_tools = await load_gateway_tools(
            gateway_url=gateway_url,
            agent_id=agent_id,
        )
        logger.info(
            f"Created {len(core)} core tools + {len(gateway_tools)} gateway tools"
        )
        return core + gateway_tools
    except Exception as e:
        logger.warning(
            f"Failed to load gateway tools, falling back to core only: {e}"
        )
        return core
```

Also add the import at the top of the file (the `logging` import is already there, just ensure it exists):

```python
# No new imports needed — logging and Path are already imported.
```

---

### 4.9 Modified Activities

**File:** `kubani/nexus/orchestrator/activities.py`

Modify the `run_agent_turn` activity to use dynamic tools from the gateway when `MCP_GATEWAY_ENABLED=true`. The change is surgical: only the tool creation line changes.

**What to change:** Replace lines 93-99 (the tool creation block) with a gateway-aware version. Here is the complete replacement for the `run_agent_turn` function (all other activities remain unchanged):

Replace the existing `run_agent_turn` function (lines 64-163) with:

```python
@activity.defn
async def run_agent_turn(input_data: dict[str, Any]) -> dict[str, Any]:
    """Run a full agentic turn using the Strands Agent SDK.

    Creates a Strands Agent with OpenAIModel pointing to vLLM and the
    core workspace tools (plus dynamic gateway tools if MCP Gateway is
    enabled). The agent handles the full LLM<>Tool loop internally and
    returns when the LLM produces a text response without tool calls.

    Args:
        input_data: Dict containing:
            - user_message: str -- the user's message
            - conversation_history: list[dict] -- recent conversation
            - memories: list[str] -- relevant memories
            - user_id: str -- for workspace resolution

    Returns:
        Dict with response_text and stop_reason.
    """
    user_message = input_data.get("user_message", "")
    conversation_history = input_data.get("conversation_history", [])
    memories = input_data.get("memories", [])
    user_id = input_data.get("user_id", "default")

    activity.heartbeat("Creating Strands agent")
    logger.info(f"run_agent_turn: user={user_id}, msg={user_message[:100]}")

    import os
    import re

    from kubani.framework.config import get_llm_config
    from kubani.nexus.tools.core import get_workspace
    from strands import Agent
    from strands.models.openai import OpenAIModel

    llm_config = get_llm_config()
    workspace = get_workspace(user_id)

    # Decide whether to use gateway-based dynamic tools or static core tools
    gateway_enabled = os.environ.get("MCP_GATEWAY_ENABLED", "false").lower() == "true"
    gateway_url = os.environ.get("MCP_GATEWAY_URL", "http://localhost:8090")

    if gateway_enabled:
        from kubani.nexus.tools.strands_tools import create_dynamic_tools

        tools = await create_dynamic_tools(
            workspace=workspace,
            gateway_url=gateway_url,
            agent_id="nexus",
        )
    else:
        from kubani.nexus.tools.strands_tools import create_tools

        tools = create_tools(workspace)

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

    # Add memories if available
    if memories:
        mem_text = "Relevant context from memory:\n" + "\n".join(f"- {m}" for m in memories)
        prompt_parts.append(mem_text)

    # Add conversation history summary (last 10 messages)
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

    agent = Agent(
        model=model,
        system_prompt=AGENT_SYSTEM_PROMPT,
        tools=tools,
        callback_handler=None,  # No streaming callbacks in activity
    )

    activity.heartbeat("Running Strands agent loop")

    try:
        result = await agent.invoke_async(full_prompt)
        response_text = str(result)

        # Strip Qwen3 empty thinking tags (appear even with /no_think prefix)
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
```

The key change is the `if gateway_enabled:` block near the top of the function. When `MCP_GATEWAY_ENABLED=true`, the activity uses `create_dynamic_tools()` which includes both core tools and gateway-discovered MCP tools. When false, it falls back to the Phase 1 behavior using `create_tools()`.

---

### 4.10 Container-Based Sandbox

**File:** `kubani/nexus/sandbox/container.py`

Replaces subprocess-based isolation with Docker container isolation.

```python
"""Container-based execution sandbox.

Uses Docker containers for isolated skill execution, providing:
- Filesystem isolation (read-only root, writable /workspace)
- Network isolation (no host network access)
- Resource limits (CPU, memory, execution time)
- Process isolation (separate PID namespace)

This is the Phase 2 replacement for the subprocess-based sandbox in
executor.py. The subprocess sandbox is kept as a fallback for
environments where Docker is not available (e.g., local development
without Docker).

Usage:
    from kubani.nexus.sandbox.container import execute_in_container

    result = await execute_in_container(
        skill_name="web/fetch-url",
        skill_content="import requests; ...",
        inputs={"url": "https://example.com"},
        timeout_seconds=30,
    )

Prerequisites:
    - Docker daemon accessible (either local socket or TCP)
    - Sandbox base image built and available: registry.almckay.io/kubani-sandbox:latest
    - The 'docker' Python package installed: pip install docker>=7.0.0
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from kubani.nexus.models.skills import SkillExecutionResult

logger = logging.getLogger(__name__)

# Container resource limits
DEFAULT_MEMORY_LIMIT = "256m"  # 256MB RAM
DEFAULT_CPU_PERIOD = 100000  # microseconds
DEFAULT_CPU_QUOTA = 50000  # 50% of one CPU core
DEFAULT_PIDS_LIMIT = 64  # max processes in the container

# Sandbox image
SANDBOX_IMAGE = os.environ.get(
    "SANDBOX_IMAGE", "registry.almckay.io/kubani-sandbox:latest"
)


async def execute_in_container(
    skill_name: str,
    skill_content: str,
    inputs: dict[str, Any],
    timeout_seconds: int = 60,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    network_enabled: bool = False,
) -> SkillExecutionResult:
    """Execute skill code in an isolated Docker container.

    Creates a temporary workspace directory with the skill code and
    inputs, mounts it into a Docker container, and runs the skill.

    Args:
        skill_name: Name of the skill (for logging).
        skill_content: Python source code to execute.
        inputs: Input data passed as JSON file.
        timeout_seconds: Maximum execution time.
        memory_limit: Docker memory limit string (e.g., "256m").
        network_enabled: Whether the container has network access.

    Returns:
        SkillExecutionResult with output, exit code, and timing.
    """
    start_time = time.monotonic()

    # Run blocking Docker operations in a thread pool
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        _run_container_sync,
        skill_name,
        skill_content,
        inputs,
        timeout_seconds,
        memory_limit,
        network_enabled,
    )

    result.duration_ms = int((time.monotonic() - start_time) * 1000)
    return result


def _run_container_sync(
    skill_name: str,
    skill_content: str,
    inputs: dict[str, Any],
    timeout_seconds: int,
    memory_limit: str,
    network_enabled: bool,
) -> SkillExecutionResult:
    """Synchronous Docker container execution (runs in thread pool).

    This function is blocking and should be called via run_in_executor.

    Args:
        skill_name: Name of the skill.
        skill_content: Python source code.
        inputs: Input data dict.
        timeout_seconds: Execution timeout.
        memory_limit: Docker memory limit.
        network_enabled: Whether to allow network access.

    Returns:
        SkillExecutionResult with the execution outcome.
    """
    try:
        import docker
        from docker.errors import ContainerError, ImageNotFound
    except ImportError:
        return SkillExecutionResult(
            skill_name=skill_name,
            success=False,
            error="Docker SDK not installed. Run: pip install docker>=7.0.0",
            exit_code=-1,
        )

    try:
        client = docker.from_env()
    except docker.errors.DockerException as e:
        return SkillExecutionResult(
            skill_name=skill_name,
            success=False,
            error=f"Cannot connect to Docker daemon: {e}",
            exit_code=-1,
        )

    # Create temporary workspace with skill code and inputs
    with tempfile.TemporaryDirectory(prefix="nexus-container-") as workspace:
        workspace_path = Path(workspace)

        # Write skill code
        skill_file = workspace_path / "run.py"
        skill_file.write_text(skill_content)

        # Write inputs
        inputs_file = workspace_path / "inputs.json"
        inputs_file.write_text(json.dumps(inputs))

        # Write the wrapper script that executes the skill
        wrapper = workspace_path / "_wrapper.py"
        wrapper.write_text(
            """import json
import sys

# Load inputs
with open("/workspace/inputs.json") as f:
    inputs = json.load(f)

# Import and run the skill
sys.path.insert(0, "/workspace")
from run import *

# If there's a main() function, call it
if "main" in dir():
    result = main(inputs)
    if result is not None:
        print(json.dumps(result) if isinstance(result, (dict, list)) else str(result))
"""
        )

        # Container configuration
        container_config = {
            "image": SANDBOX_IMAGE,
            "command": ["python3", "/workspace/_wrapper.py"],
            "volumes": {
                str(workspace_path): {
                    "bind": "/workspace",
                    "mode": "rw",
                }
            },
            "working_dir": "/workspace",
            "mem_limit": memory_limit,
            "cpu_period": DEFAULT_CPU_PERIOD,
            "cpu_quota": DEFAULT_CPU_QUOTA,
            "pids_limit": DEFAULT_PIDS_LIMIT,
            "network_mode": "bridge" if network_enabled else "none",
            "read_only": False,  # /workspace needs to be writable
            "detach": True,
            "remove": False,  # We remove after reading logs
            "environment": {
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
            },
            "security_opt": ["no-new-privileges"],
        }

        container = None
        try:
            # Pull image if not present
            try:
                client.images.get(SANDBOX_IMAGE)
            except ImageNotFound:
                logger.info(f"Pulling sandbox image: {SANDBOX_IMAGE}")
                client.images.pull(SANDBOX_IMAGE)

            # Run the container
            container = client.containers.run(**container_config)

            # Wait for completion with timeout
            exit_info = container.wait(timeout=timeout_seconds)
            exit_code = exit_info.get("StatusCode", -1)

            # Capture output
            stdout = container.logs(stdout=True, stderr=False).decode(
                "utf-8", errors="replace"
            )[:1_048_576]
            stderr = container.logs(stdout=False, stderr=True).decode(
                "utf-8", errors="replace"
            )[:1_048_576]

            return SkillExecutionResult(
                skill_name=skill_name,
                success=exit_code == 0,
                output=stdout,
                error=stderr if exit_code != 0 else None,
                exit_code=exit_code,
                logs=stderr,
            )

        except docker.errors.ContainerError as e:
            return SkillExecutionResult(
                skill_name=skill_name,
                success=False,
                error=f"Container error: {e}",
                exit_code=e.exit_status if hasattr(e, "exit_status") else -1,
            )
        except Exception as e:
            error_msg = str(e)
            if "timed out" in error_msg.lower() or "read timeout" in error_msg.lower():
                error_msg = f"Execution timed out after {timeout_seconds}s"
            return SkillExecutionResult(
                skill_name=skill_name,
                success=False,
                error=error_msg,
                exit_code=-1,
            )
        finally:
            if container:
                try:
                    container.stop(timeout=5)
                except Exception:
                    pass
                try:
                    container.remove(force=True)
                except Exception:
                    pass


def is_docker_available() -> bool:
    """Check if Docker is available on this host.

    Returns:
        True if Docker is accessible, False otherwise.
    """
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False
```

---

### 4.11 Sandbox Dockerfile

**File:** `kubani/nexus/sandbox/Dockerfile`

The base image for the container sandbox. Includes Python and common data science libraries but no secrets, credentials, or host access.

```dockerfile
FROM python:3.12-slim

# Install commonly needed packages for skills
RUN pip install --no-cache-dir \
    httpx \
    requests \
    beautifulsoup4 \
    lxml \
    pyyaml \
    jinja2 \
    && rm -rf /root/.cache

# Create workspace directory
RUN mkdir -p /workspace && chmod 777 /workspace

# Run as non-root user
RUN useradd -m -u 1000 sandbox
USER sandbox

WORKDIR /workspace

# Default command (overridden by container.py)
CMD ["python3", "-c", "print('sandbox ready')"]
```

Build with:
```bash
docker build -t registry.almckay.io/kubani-sandbox:latest -f kubani/nexus/sandbox/Dockerfile .
docker push registry.almckay.io/kubani-sandbox:latest
```

---

### 4.12 HITL Approval Flow

This section describes how the gateway's `approval_required` response integrates with the Temporal workflow.

#### Flow Description

1. The Strands agent calls a gateway tool (e.g., `pods_delete`).
2. The dynamic tool function (`dynamic_loader.py`) POSTs to the gateway's `/call` endpoint.
3. The gateway's policy engine determines this tool requires approval.
4. The gateway returns `{"approval_required": true, "approval_id": "abc-123", ...}`.
5. The dynamic tool function returns a string to the Strands agent: `"APPROVAL_REQUIRED: This operation (pods_delete) needs human approval. Approval ID: abc-123."`.
6. The Strands agent sees this string as a tool result and generates a text response like: "I need to delete pod X, but this requires human approval. I've submitted the request (ID: abc-123) and will proceed once it's approved."
7. The agent turn completes normally (the `run_agent_turn` activity returns).
8. The workflow publishes this response to the user.
9. Meanwhile, the gateway has the pending approval stored in memory. Operators can see it at `GET /approvals` or receive a notification via the Nexus conversational gateway's approval UI.
10. When a human approves via the Nexus gateway's existing `/api/nexus/approvals/{id}/decide` endpoint, that endpoint also signals the Temporal workflow with the `approval_decision` signal.
11. The workflow receives the signal in its `_pending_messages` queue.
12. On the next user message (or via a periodic check), the workflow can inform the agent that the approval was granted.

#### Connecting the Nexus Gateway Approvals to the MCP Gateway

The Nexus conversational gateway (`kubani/nexus/gateway/app.py`) already has an approvals router. We need to modify it to also proxy approval decisions to the MCP Gateway.

**Changes to `kubani/nexus/gateway/app.py`:**

Replace the `decide_approval` endpoint in `_create_approvals_router` with:

```python
    @router.post("/approvals/{approval_id}/decide")
    async def decide_approval(
        approval_id: int | str, request: ApprovalRequest
    ) -> dict[str, str]:
        """Approve or reject a pending approval request.

        Handles both database-backed approvals (integer IDs from the
        Nexus DB) and MCP Gateway approvals (UUID string IDs).
        """
        approval_id_str = str(approval_id)

        # Check if this is an MCP Gateway approval (UUID format)
        import re

        is_gateway_approval = bool(
            re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-", approval_id_str)
        )

        if is_gateway_approval:
            # Forward to MCP Gateway
            mcp_gateway_url = os.environ.get(
                "MCP_GATEWAY_URL", "http://mcp-gateway.nexus.svc.cluster.local:8090"
            )
            import httpx

            async with httpx.AsyncClient() as client:
                if request.approved:
                    resp = await client.post(
                        f"{mcp_gateway_url}/approvals/{approval_id_str}/approve",
                        timeout=10.0,
                    )
                else:
                    resp = await client.post(
                        f"{mcp_gateway_url}/approvals/{approval_id_str}/reject",
                        params={"reason": request.reason},
                        timeout=10.0,
                    )
                resp.raise_for_status()
        else:
            # Handle as a database approval (existing behavior)
            from kubani.nexus.db import resolve_approval

            await resolve_approval(
                _state.db_pool,
                int(approval_id_str),
                request.approved,
                decided_by="ui-user",
                reason=request.reason,
            )

        # Signal the workflow about the decision
        try:
            await _state.signal_workflow(
                "default",
                "approval_decision",
                {
                    "approval_id": approval_id_str,
                    "approved": request.approved,
                    "reason": request.reason,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to signal approval decision: {e}")

        status = "approved" if request.approved else "rejected"
        return {"status": status, "approval_id": approval_id_str}
```

---

### 4.13 Kubernetes Manifests

#### 4.13.1 MCP Gateway Deployment

**File:** `infrastructure/gitops/apps/nexus/mcp-gateway-deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-gateway
  namespace: nexus
  labels:
    app: mcp-gateway
    app.kubernetes.io/name: mcp-gateway
    app.kubernetes.io/part-of: kubani
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mcp-gateway
  template:
    metadata:
      labels:
        app: mcp-gateway
    spec:
      containers:
      - name: mcp-gateway
        image: registry.almckay.io/kubani-mcp-gateway:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 8090
          name: http
        env:
        - name: NEXUS_DATABASE_URL
          value: "postgresql://nexus:nexus_password_123@postgresql.database.svc.cluster.local:5432/nexus"
        - name: MCP_GATEWAY_SERVER_TEMPORAL_URL
          value: "http://temporal-mcp-server.ai-agents.svc.cluster.local:8081"
        - name: MCP_GATEWAY_SERVER_MEMORY_URL
          value: "http://memory-mcp-server.ai-agents.svc.cluster.local:8083"
        - name: MCP_GATEWAY_SERVER_DISCORD_URL
          value: "http://discord-mcp-server.ai-agents.svc.cluster.local:8084"
        - name: MCP_GATEWAY_SERVER_QDRANT_URL
          value: "http://qdrant-mcp-server.ai-agents.svc.cluster.local:8082"
        - name: MCP_GATEWAY_SERVER_SKILLS_URL
          value: "http://skills-mcp-server.ai-agents.svc.cluster.local:8086"
        - name: LOG_LEVEL
          value: "INFO"
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8090
          initialDelaySeconds: 15
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8090
          initialDelaySeconds: 5
          periodSeconds: 5
```

#### 4.13.2 MCP Gateway Service

**File:** `infrastructure/gitops/apps/nexus/mcp-gateway-service.yaml`

```yaml
apiVersion: v1
kind: Service
metadata:
  name: mcp-gateway
  namespace: nexus
  labels:
    app: mcp-gateway
spec:
  type: ClusterIP
  ports:
  - port: 8090
    targetPort: 8090
    protocol: TCP
    name: http
  selector:
    app: mcp-gateway
```

#### 4.13.3 Updated Orchestrator Deployment

**File:** `infrastructure/gitops/apps/nexus/orchestrator-deployment.yaml`

Add the following environment variables to the existing orchestrator deployment (add after the existing `LOG_LEVEL` env var):

```yaml
        - name: MCP_GATEWAY_ENABLED
          value: "true"
        - name: MCP_GATEWAY_URL
          value: "http://mcp-gateway.nexus.svc.cluster.local:8090"
```

#### 4.13.4 Updated Kustomization

**File:** `infrastructure/gitops/apps/nexus/kustomization.yaml`

Add the new resources:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: nexus
resources:
  - namespace.yaml
  - secret.yaml
  - gateway-deployment.yaml
  - gateway-service.yaml
  - gateway-ingress.yaml
  - orchestrator-deployment.yaml
  - mcp-gateway-deployment.yaml
  - mcp-gateway-service.yaml
```

---

### 4.14 Nexus Policy File

**File:** `kubani/mcp/registry/policies/nexus.json`

This is the per-agent policy for Nexus that the gateway uses. Create this file:

```json
{
  "allowedServers": [
    "temporal",
    "discord",
    "memory",
    "qdrant",
    "skills"
  ],
  "requireApproval": [
    "pods.delete",
    "deployments.scale",
    "resources.delete",
    "resources.create",
    "channels.delete",
    "webhooks.delete",
    "workflows.terminate",
    "collections.delete",
    "helm.install",
    "helm.uninstall"
  ],
  "auditLog": true,
  "namespaceRestrictions": {
    "deny": [
      "kube-system",
      "flux-system",
      "cert-manager"
    ]
  }
}
```

---

## 5. Testing

### 5.1 Unit Tests for Policy Engine

**File:** `tests/unit/mcp_gateway/test_policy.py`

```python
"""Tests for the MCP Gateway policy engine."""

import json
import tempfile
from pathlib import Path

import pytest

from kubani.mcp.gateway.policy import PolicyDecision, PolicyEngine


@pytest.fixture
def policy_dir(tmp_path):
    """Create a temporary registry directory with test policies."""
    registry = {
        "version": "1.0",
        "servers": {
            "kubernetes": {
                "name": "kubernetes-mcp-server",
                "transport": "sse",
                "capabilities": ["pods.list", "pods.get", "pods.delete"],
                "readOnly": False,
            },
            "discord": {
                "name": "discord-mcp-server",
                "transport": "sse",
                "capabilities": ["messages.send", "channels.delete"],
                "readOnly": False,
            },
            "cloudflare-docs": {
                "name": "cloudflare-docs-mcp",
                "transport": "sse",
                "capabilities": ["docs.search"],
                "readOnly": True,
            },
        },
        "policies": {
            "default": {
                "allowedServers": ["kubernetes", "discord", "cloudflare-docs"],
                "requireApproval": ["pods.delete", "channels.delete"],
                "auditLog": True,
            },
        },
    }
    registry_file = tmp_path / "registry.json"
    registry_file.write_text(json.dumps(registry))

    # Create policies directory with agent-specific policy
    policies_dir = tmp_path / "policies"
    policies_dir.mkdir()
    nexus_policy = {
        "allowedServers": ["kubernetes", "discord"],
        "requireApproval": ["pods.delete"],
        "namespaceRestrictions": {"deny": ["kube-system"]},
    }
    (policies_dir / "nexus.json").write_text(json.dumps(nexus_policy))

    readonly_policy = {
        "allowedServers": ["cloudflare-docs"],
        "requireApproval": ["*"],
        "readOnly": True,
    }
    (policies_dir / "readonly-agent.json").write_text(json.dumps(readonly_policy))

    return tmp_path


def test_allow_basic_tool(policy_dir):
    engine = PolicyEngine(registry_dir=policy_dir)
    decision = engine.evaluate("default", "pods_list", "kubernetes")
    assert decision.action == PolicyDecision.ALLOW


def test_deny_server_not_allowed(policy_dir):
    engine = PolicyEngine(registry_dir=policy_dir)
    decision = engine.evaluate("nexus", "docs_search", "cloudflare-docs")
    assert decision.action == PolicyDecision.DENY
    assert "not in allowed list" in decision.reason


def test_approval_required(policy_dir):
    engine = PolicyEngine(registry_dir=policy_dir)
    decision = engine.evaluate("nexus", "pods_delete", "kubernetes")
    assert decision.action == PolicyDecision.APPROVAL_REQUIRED


def test_namespace_denied(policy_dir):
    engine = PolicyEngine(registry_dir=policy_dir)
    decision = engine.evaluate(
        "nexus", "pods_list", "kubernetes",
        arguments={"namespace": "kube-system"},
    )
    assert decision.action == PolicyDecision.DENY
    assert "kube-system" in decision.reason


def test_namespace_allowed(policy_dir):
    engine = PolicyEngine(registry_dir=policy_dir)
    decision = engine.evaluate(
        "nexus", "pods_list", "kubernetes",
        arguments={"namespace": "ai-agents"},
    )
    assert decision.action == PolicyDecision.ALLOW


def test_wildcard_approval(policy_dir):
    engine = PolicyEngine(registry_dir=policy_dir)
    decision = engine.evaluate("readonly-agent", "docs_search", "cloudflare-docs")
    assert decision.action == PolicyDecision.APPROVAL_REQUIRED


def test_readonly_agent_denied_on_readwrite_server(policy_dir):
    # readonly-agent only allows cloudflare-docs, so kubernetes is denied
    engine = PolicyEngine(registry_dir=policy_dir)
    decision = engine.evaluate("readonly-agent", "pods_list", "kubernetes")
    assert decision.action == PolicyDecision.DENY


def test_fallback_to_default_policy(policy_dir):
    engine = PolicyEngine(registry_dir=policy_dir)
    decision = engine.evaluate("unknown-agent", "pods_list", "kubernetes")
    assert decision.action == PolicyDecision.ALLOW
    assert decision.policy_name == "default"


def test_get_allowed_servers(policy_dir):
    engine = PolicyEngine(registry_dir=policy_dir)
    servers = engine.get_allowed_servers("nexus")
    assert "kubernetes" in servers
    assert "discord" in servers
    assert "cloudflare-docs" not in servers
```

### 5.2 Unit Tests for Audit Logger

**File:** `tests/unit/mcp_gateway/test_audit.py`

```python
"""Tests for the MCP Gateway audit logger.

These tests require a PostgreSQL database. Skip with:
    pytest -m "not integration"
"""

import pytest

from kubani.mcp.gateway.audit import AuditLogger


@pytest.fixture
async def audit_logger():
    """Create an audit logger with test database."""
    import os

    db_url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://kubani:kubani@localhost:5432/kubani_nexus_test",
    )
    logger = AuditLogger(db_url=db_url)
    await logger.initialize()
    yield logger
    # Clean up test data
    if logger._pool:
        async with logger._pool.acquire() as conn:
            await conn.execute("DELETE FROM mcp_audit_log WHERE agent_id LIKE 'test-%'")
    await logger.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_log_and_query(audit_logger):
    audit_id = await audit_logger.log_call(
        agent_id="test-agent",
        tool_name="pods_list",
        server_name="kubernetes",
        arguments={"namespace": "default"},
        policy_decision="allow",
        result_success=True,
        duration_ms=42,
    )
    assert audit_id > 0

    records = await audit_logger.query_by_agent("test-agent", limit=1)
    assert len(records) == 1
    assert records[0]["tool_name"] == "pods_list"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_result(audit_logger):
    audit_id = await audit_logger.log_call(
        agent_id="test-agent-update",
        tool_name="pods_delete",
        server_name="kubernetes",
        arguments={},
        policy_decision="approval_required",
        approval_id="test-approval-123",
    )

    await audit_logger.update_result(
        audit_id,
        result_success=True,
        duration_ms=100,
    )

    records = await audit_logger.query_by_agent("test-agent-update", limit=1)
    assert records[0]["result_success"] is True
```

### 5.3 Unit Tests for Dynamic Loader

**File:** `tests/unit/nexus/test_dynamic_loader.py`

```python
"""Tests for the dynamic tool loader."""

import json

import pytest
import respx
from httpx import Response

from kubani.nexus.tools.dynamic_loader import (
    _fetch_manifest,
    clear_cache,
    load_gateway_tools,
)


@pytest.fixture(autouse=True)
def reset_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_manifest():
    manifest = [
        {"name": "pods_list", "description": "List pods", "server_name": "kubernetes", "input_schema": {}},
        {"name": "send_message", "description": "Send Discord message", "server_name": "discord", "input_schema": {}},
    ]
    respx.get("http://test-gateway:8090/tools").mock(
        return_value=Response(200, json=manifest)
    )

    result = await _fetch_manifest("http://test-gateway:8090", "nexus", 5.0)
    assert len(result) == 2
    assert result[0]["name"] == "pods_list"


@pytest.mark.asyncio
@respx.mock
async def test_load_gateway_tools():
    manifest = [
        {"name": "pods_list", "description": "List pods", "server_name": "kubernetes", "input_schema": {}},
    ]
    respx.get("http://test-gateway:8090/tools").mock(
        return_value=Response(200, json=manifest)
    )

    tools = await load_gateway_tools("http://test-gateway:8090", "nexus")
    assert len(tools) == 1


@pytest.mark.asyncio
@respx.mock
async def test_gateway_tool_call():
    manifest = [
        {"name": "pods_list", "description": "List pods", "server_name": "kubernetes", "input_schema": {}},
    ]
    respx.get("http://test-gateway:8090/tools").mock(
        return_value=Response(200, json=manifest)
    )
    respx.post("http://test-gateway:8090/call").mock(
        return_value=Response(200, json={
            "success": True,
            "data": [{"name": "pod-1"}, {"name": "pod-2"}],
        })
    )

    tools = await load_gateway_tools("http://test-gateway:8090", "nexus")
    result = await tools[0](namespace="default")
    assert "pod-1" in result


@pytest.mark.asyncio
@respx.mock
async def test_gateway_tool_approval_required():
    manifest = [
        {"name": "pods_delete", "description": "Delete a pod", "server_name": "kubernetes", "input_schema": {}},
    ]
    respx.get("http://test-gateway:8090/tools").mock(
        return_value=Response(200, json=manifest)
    )
    respx.post("http://test-gateway:8090/call").mock(
        return_value=Response(200, json={
            "success": False,
            "approval_required": True,
            "approval_id": "abc-123",
            "approval_reason": "Tool requires approval",
        })
    )

    tools = await load_gateway_tools("http://test-gateway:8090", "nexus")
    result = await tools[0](name="pod-1", namespace="default")
    assert "APPROVAL_REQUIRED" in result
    assert "abc-123" in result


@pytest.mark.asyncio
@respx.mock
async def test_fetch_manifest_failure():
    respx.get("http://test-gateway:8090/tools").mock(
        return_value=Response(500, text="Internal Server Error")
    )

    result = await _fetch_manifest("http://test-gateway:8090", "nexus", 5.0)
    assert result == []


@pytest.mark.asyncio
@respx.mock
async def test_caching():
    manifest = [
        {"name": "test_tool", "description": "Test", "server_name": "test", "input_schema": {}},
    ]
    route = respx.get("http://test-gateway:8090/tools").mock(
        return_value=Response(200, json=manifest)
    )

    tools1 = await load_gateway_tools("http://test-gateway:8090", "nexus")
    tools2 = await load_gateway_tools("http://test-gateway:8090", "nexus")

    # Should only fetch once (cached)
    assert route.call_count == 1
    assert tools1 is tools2
```

### 5.4 Integration Test for Gateway Server

**File:** `tests/integration/gateway/test_mcp_gateway.py`

```python
"""Integration tests for the MCP Gateway server.

Requires the gateway to be running locally:
    uvicorn kubani.mcp.gateway.server:app --port 8090

Or run with pytest fixtures that start the server.
"""

import pytest
import httpx


GATEWAY_URL = "http://localhost:8090"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{GATEWAY_URL}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["tool_count"] >= 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_tools():
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GATEWAY_URL}/tools", params={"agent_id": "nexus"}
        )
        assert resp.status_code == 200
        tools = resp.json()
        assert isinstance(tools, list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_call_unknown_tool():
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GATEWAY_URL}/call",
            json={
                "agent_id": "nexus",
                "tool_name": "nonexistent_tool",
                "arguments": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "Unknown tool" in data["error"]
```

### 5.5 Container Sandbox Test

**File:** `tests/unit/sandbox/test_container.py`

```python
"""Tests for container-based sandbox.

Requires Docker to be available. Skip with:
    pytest -m "not docker"
"""

import pytest

from kubani.nexus.sandbox.container import execute_in_container, is_docker_available


@pytest.mark.skipif(not is_docker_available(), reason="Docker not available")
@pytest.mark.asyncio
async def test_simple_execution():
    result = await execute_in_container(
        skill_name="test/hello",
        skill_content='def main(inputs):\n    return {"message": f"Hello, {inputs.get(\'name\', \'World\')}!"}',
        inputs={"name": "Kubani"},
        timeout_seconds=30,
    )
    assert result.success
    assert "Kubani" in result.output


@pytest.mark.skipif(not is_docker_available(), reason="Docker not available")
@pytest.mark.asyncio
async def test_timeout():
    result = await execute_in_container(
        skill_name="test/slow",
        skill_content="import time\ndef main(inputs):\n    time.sleep(60)\n    return {}",
        inputs={},
        timeout_seconds=5,
    )
    assert not result.success
    assert "timed out" in result.error.lower() or result.exit_code != 0


@pytest.mark.skipif(not is_docker_available(), reason="Docker not available")
@pytest.mark.asyncio
async def test_no_network_by_default():
    result = await execute_in_container(
        skill_name="test/network",
        skill_content=(
            "import urllib.request\n"
            "def main(inputs):\n"
            "    try:\n"
            "        urllib.request.urlopen('https://example.com', timeout=5)\n"
            "        return {'network': True}\n"
            "    except Exception as e:\n"
            "        return {'network': False, 'error': str(e)}\n"
        ),
        inputs={},
        timeout_seconds=15,
        network_enabled=False,
    )
    # Should succeed but network should be blocked
    assert result.success
    assert "False" in result.output or "error" in result.output
```

### 5.6 Running Tests

```bash
# Unit tests (no external services needed)
pytest tests/unit/mcp_gateway/ -v
pytest tests/unit/nexus/test_dynamic_loader.py -v
pytest tests/unit/sandbox/test_container.py -v -m "not docker"

# Integration tests (require running services)
pytest tests/integration/gateway/test_mcp_gateway.py -v -m integration

# Container sandbox tests (require Docker)
pytest tests/unit/sandbox/test_container.py -v

# All Phase 2 tests
pytest tests/unit/mcp_gateway/ tests/unit/nexus/test_dynamic_loader.py tests/unit/sandbox/test_container.py tests/integration/gateway/ -v
```

---

## 6. Rollback Plan

Phase 2 is designed to be fully backward-compatible with Phase 1. The gateway is opt-in via the `MCP_GATEWAY_ENABLED` environment variable.

### To rollback to Phase 1 behavior:

1. **Set `MCP_GATEWAY_ENABLED=false`** in the orchestrator deployment (or remove the env var entirely). This causes the `run_agent_turn` activity to use `create_tools()` (Phase 1 static tools) instead of `create_dynamic_tools()`.

2. **Scale down the MCP Gateway deployment** to 0 replicas:
   ```bash
   kubectl scale deployment mcp-gateway -n nexus --replicas=0
   ```

3. **Remove the MCP Gateway resources from kustomization** (optional, for full cleanup):
   Remove these lines from `infrastructure/gitops/apps/nexus/kustomization.yaml`:
   ```yaml
   - mcp-gateway-deployment.yaml
   - mcp-gateway-service.yaml
   ```

4. **Container sandbox fallback**: The `execute_skill_in_sandbox` function in `executor.py` is unchanged. If Docker is unavailable, the container sandbox's `is_docker_available()` check returns False, and the orchestrator can fall back to the subprocess sandbox.

### What does NOT need to be rolled back:

- The `MCPServerConfig` changes (adding `gateway_url` and `gateway_enabled`) are backward-compatible. Defaults are `http://localhost:8090` and `False`.
- The audit table (`mcp_audit_log`) can remain in the database. It does not interfere with anything.
- The `nexus.json` policy file can remain. The policy engine is only used by the gateway.
- The `create_dynamic_tools()` function in `strands_tools.py` is additive. The original `create_tools()` is untouched.

---

## 7. Implementation Order

Recommended order with verification steps at each stage.

| Step | Component | Verify |
|------|-----------|--------|
| 1 | `kubani/mcp/gateway/__init__.py` | File exists |
| 2 | `kubani/mcp/gateway/policy.py` | `pytest tests/unit/mcp_gateway/test_policy.py` passes |
| 3 | `kubani/mcp/gateway/audit.py` | Table created in test DB, insert/query works |
| 4 | `kubani/mcp/gateway/router.py` | Unit tests pass (mock MCPServerClient) |
| 5 | `kubani/mcp/gateway/server.py` | `uvicorn kubani.mcp.gateway.server:app --port 8090` starts, `GET /health` returns 200 |
| 6 | `kubani/mcp/gateway/Dockerfile` | `docker build` succeeds, `docker run` starts server |
| 7 | `kubani/framework/config.py` | `gateway_url` and `gateway_enabled` accessible via `get_config().mcp` |
| 8 | `kubani/nexus/tools/dynamic_loader.py` | `pytest tests/unit/nexus/test_dynamic_loader.py` passes |
| 9 | `kubani/nexus/tools/strands_tools.py` | `create_dynamic_tools()` returns core + gateway tools |
| 10 | `kubani/nexus/orchestrator/activities.py` | With `MCP_GATEWAY_ENABLED=false`, behavior unchanged. With `MCP_GATEWAY_ENABLED=true`, dynamic tools loaded |
| 11 | `kubani/nexus/sandbox/container.py` | `pytest tests/unit/sandbox/test_container.py` passes (with Docker) |
| 12 | `kubani/nexus/sandbox/Dockerfile` | `docker build` succeeds, image pushed |
| 13 | `kubani/mcp/registry/policies/nexus.json` | Policy engine loads and applies it |
| 14 | `kubani/nexus/gateway/app.py` (HITL changes) | Approval decision routes to MCP Gateway |
| 15 | K8s manifests | `kubectl apply -k infrastructure/gitops/apps/nexus/` succeeds |
| 16 | End-to-end test | Send message via UI, agent discovers gateway tools, calls a tool, audit log records it |
| 17 | HITL test | Trigger an approval-required tool, approve via UI, verify tool executes |

### Local Development Quick Start

For local testing before cluster deployment:

```bash
# 1. Start the MCP Gateway locally
uvicorn kubani.mcp.gateway.server:app --port 8090

# 2. In another terminal, verify it works
curl http://localhost:8090/health
curl "http://localhost:8090/tools?agent_id=nexus"

# 3. Run the orchestrator with gateway enabled
MCP_GATEWAY_ENABLED=true MCP_GATEWAY_URL=http://localhost:8090 \
  python -m kubani.nexus.orchestrator.worker

# 4. Build and test the container sandbox image
docker build -t kubani-sandbox:latest -f kubani/nexus/sandbox/Dockerfile .
pytest tests/unit/sandbox/test_container.py -v
```
