# Step 1: Update MCP Policy and Add Provenance Tracking

**File:** `kubani/nexus/tools/mcp_clients.py`

## 1a. Flip the `kubernetes` flag in the `nexus` policy (line 53)

**Before:**
```python
_POLICIES: dict[str, dict[str, bool]] = {
    "nexus": {
        "memory": True,
        "skills": True,
        "fetch": True,
        "kubernetes": False,
        "temporal": False,
        "computer": False,
    },
```

**After:**
```python
_POLICIES: dict[str, dict[str, bool]] = {
    "nexus": {
        "memory": True,
        "skills": True,
        "fetch": True,
        "kubernetes": True,
        "temporal": False,
        "computer": False,
    },
```

**Rationale:** This single flag controls whether `create_mcp_clients()` includes the Kubernetes MCP server when called with the default `"nexus"` policy. The `run_agent_turn` activity calls `create_mcp_clients()` with no arguments, which defaults to `"nexus"`. Flipping this flag is all that's needed to make Kubernetes tools available in user-facing chat.

## 1b. Update the module docstring (lines 9-16)

**Before:**
```python
``nexus`` (default, conservative):
    Memory + Skills + Fetch
    Safe for all conversational turns. No cluster access.

``nexus-proactive`` (expanded, for mission turns):
    Memory + Skills + Fetch + Kubernetes + Temporal
    Grants read-heavy cluster access for background monitoring missions.
    Destructive operations (delete, scale, terminate) require HITL approval.
```

**After:**
```python
``nexus`` (default):
    Memory + Skills + Fetch + Kubernetes
    Full conversational access including cluster read operations.
    Destructive Kubernetes operations are blocked by _K8sToolGuard hook
    in activities.py.

``nexus-proactive`` (expanded, for mission turns):
    Memory + Skills + Fetch + Kubernetes + Temporal
    Full cluster access for background monitoring missions.
    No tool guard — missions have autonomous access.
```

**Rationale:** The HITL approval mentioned in the old docstring was never implemented. Update to reflect reality: missions have full autonomous access, chat has guarded access via the hook.

## 1c. Update the `create_mcp_clients` docstring (line 103)

**Before:**
```python
            ``nexus`` (default) — memory, skills, fetch.
```

**After:**
```python
            ``nexus`` (default) — memory, skills, fetch, kubernetes.
```

## 1d. Add provenance tracking to `load_tools_resilient()`

The current `load_tools_resilient()` returns `tuple[list, list[MCPClient]]` — a flat list of tools with no record of which client produced which tool. The `_K8sToolGuard` hook needs to know whether a tool came from the Kubernetes MCP client (vs memory, skills, fetch) to decide whether to apply the allowlist.

**Current signature and return (lines 196-229):**
```python
async def load_tools_resilient(
    clients: list[MCPClient],
) -> tuple[list, list[MCPClient]]:
    """Load tools from each MCP client individually, skipping failures.
    ...
    Returns:
        Tuple of (loaded_tools, started_clients).
        ``loaded_tools`` are Tool objects to pass to ``Agent(tools=...)``.
        ``started_clients`` must be stopped in the caller's finally block.
    """
    all_tools: list = []
    started: list[MCPClient] = []

    for client in clients:
        try:
            tools = await client.load_tools()
            all_tools.extend(tools)
            started.append(client)
            logger.info(f"Loaded {len(tools)} tool(s) from MCP client")
        except Exception as exc:
            logger.warning(f"MCP client failed to load tools, skipping: {exc}")
            try:
                client.stop(None, None, None)
            except Exception:
                pass

    logger.info(
        f"Resilient tool loading: {len(all_tools)} tools from {len(started)}/{len(clients)} clients"
    )
    return all_tools, started
```

**New signature and return:**
```python
async def load_tools_resilient(
    clients: list[MCPClient],
    client_names: list[str] | None = None,
) -> tuple[list, list[MCPClient], dict[str, set[str]]]:
    """Load tools from each MCP client individually, skipping failures.

    Args:
        clients: MCP client instances to load tools from.
        client_names: Optional parallel list of names identifying each client
            (e.g., ``["memory", "skills", "fetch", "kubernetes"]``). Used to
            build the provenance map. If not provided, provenance is empty.

    Returns:
        Tuple of (loaded_tools, started_clients, tool_provenance).
        ``loaded_tools`` are Tool objects to pass to ``Agent(tools=...)``.
        ``started_clients`` must be stopped in the caller's finally block.
        ``tool_provenance`` maps client name → set of tool names loaded from it.
    """
    all_tools: list = []
    started: list[MCPClient] = []
    provenance: dict[str, set[str]] = {}
    names = client_names or []

    for i, client in enumerate(clients):
        name = names[i] if i < len(names) else f"client_{i}"
        try:
            tools = await client.load_tools()
            all_tools.extend(tools)
            started.append(client)
            tool_names = set()
            for t in tools:
                # Strands Tool objects expose .tool_name or .name
                tool_name = getattr(t, "tool_name", None) or getattr(t, "name", "unknown")
                tool_names.add(tool_name)
            provenance[name] = tool_names
            logger.info(f"Loaded {len(tools)} tool(s) from MCP client '{name}'")
        except Exception as exc:
            logger.warning(f"MCP client '{name}' failed to load tools, skipping: {exc}")
            try:
                client.stop(None, None, None)
            except Exception:
                pass

    logger.info(
        f"Resilient tool loading: {len(all_tools)} tools from {len(started)}/{len(clients)} clients"
    )
    return all_tools, started, provenance
```

**Key details:**
- `client_names` is optional with a default of `None` — backward compatible. Existing callers that don't pass it get an empty provenance dict.
- The provenance map is `dict[str, set[str]]` — client name → set of tool name strings. This is passed to `_K8sToolGuard` so it can check `tool_name in provenance.get("kubernetes", set())`.
- Tool name extraction uses `getattr` with fallback because the Strands Tool type may expose the name as `.tool_name` or `.name` depending on the version.

## 1e. Update `create_mcp_clients()` to return client names

Currently `create_mcp_clients()` returns `list[MCPClient]`. We need to also return the names so the caller can pass them to `load_tools_resilient()`.

**New signature:**
```python
def create_mcp_clients(policy_name: str = "nexus") -> tuple[list[MCPClient], list[str]]:
    """Create MCPClient instances filtered by the given MCP policy.

    Returns:
        Tuple of (clients, client_names). Names are parallel to clients and
        identify each client's source server (e.g., "memory", "kubernetes").
    """
```

**Implementation change — track names alongside clients:**

At the top of the function, change:
```python
    clients: list[MCPClient] = []
```
to:
```python
    clients: list[MCPClient] = []
    client_names: list[str] = []
```

Then everywhere a client is appended, also append the name. Three locations:

**SSE clients (line 143):**
```python
            clients.append(client)
            client_names.append(name)     # <-- add this line
```

**Kubernetes client (line 164):**
```python
            clients.append(k8s_client)
            client_names.append("kubernetes")  # <-- add this line
```

**Fetch client (line 185):**
```python
            clients.append(fetch_client)
            client_names.append("fetch")       # <-- add this line
```

**Return statement (line 193):**
```python
    return clients, client_names
```

## Callers that need updating

Two callers of `create_mcp_clients()` and `load_tools_resilient()`:

### `run_agent_turn` (activities.py, line 198)

**Before:**
```python
    mcp_clients = create_mcp_clients()
    ...
    mcp_tools, started_clients = await load_tools_resilient(mcp_clients)
    mcp_clients = started_clients
```

**After:**
```python
    mcp_clients, client_names = create_mcp_clients()
    ...
    mcp_tools, started_clients, tool_provenance = await load_tools_resilient(mcp_clients, client_names)
    mcp_clients = started_clients
```

`tool_provenance` is then passed to `_K8sToolGuard` (see Step 3).

### `run_mission_agent_turn` (activities.py, ~line 467)

**Before:**
```python
    mcp_clients = create_mcp_clients(policy_name=mcp_policy)
    ...
    mcp_tools, started_clients = await load_tools_resilient(mcp_clients)
```

**After:**
```python
    mcp_clients, _client_names = create_mcp_clients(policy_name=mcp_policy)
    ...
    mcp_tools, started_clients, _provenance = await load_tools_resilient(mcp_clients, _client_names)
```

Mission turns don't use `_K8sToolGuard`, so the provenance is discarded with `_`. The signature change is needed for compatibility.

## Verification

After this step:
```
INFO  MCP policy 'nexus': allowed servers = ['fetch', 'kubernetes', 'memory', 'skills']
INFO  Loaded 20 tool(s) from MCP client 'kubernetes'
INFO  Resilient tool loading: 35 tools from 4/4 clients
```

The provenance dict should look like:
```python
{
    "memory": {"save_memory", "search", "get_observations", ...},
    "skills": {"load_skill", "execute_skill", ...},
    "fetch": {"fetch"},
    "kubernetes": {"pods_list", "pods_get", "pods_log", "pods_delete", ...},
}
```
