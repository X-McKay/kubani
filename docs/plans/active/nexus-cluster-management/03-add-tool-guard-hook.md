# Step 3: Add K8s Tool Guard Hook

**File:** `kubani/nexus/orchestrator/activities.py`

## Overview

Add a `_K8sToolGuard` HookProvider that:
1. Uses **provenance tracking** (from Step 1) to identify Kubernetes tools — no prefix matching
2. Checks an **allowlist** of safe tools
3. **Replaces** destructive tools with a kubectl-suggestion wrapper (using `event.selected_tool`) instead of cancelling them

This follows the same HookProvider pattern as the existing `_ToolBudgetHook` (lines 489-520) but uses Strands' `event.selected_tool` replacement capability instead of `event.cancel_tool`.

## 3a. Define the allowlist and kubectl mapping

Add this at module level, after the `COMPUTER_USE_PROMPT` string (line 146) and before the `run_agent_turn` function (line 149).

```python
# =========================================================================
# Kubernetes tool guard (allowlist enforcement for chat turns)
# =========================================================================

# Tools from the Kubernetes MCP server that are safe for autonomous use.
# Any Kubernetes tool NOT in this set is replaced with a kubectl-suggestion
# wrapper that returns the equivalent kubectl command.
_K8S_ALLOWED_TOOLS: frozenset[str] = frozenset({
    # Pod read operations
    "pods_list",
    "pods_list_in_namespace",
    "pods_get",
    "pods_log",
    "pods_top",
    # Resource read operations
    "resources_list",
    "resources_get",
    # Events and namespaces
    "events_list",
    "namespaces_list",
    # Node diagnostics
    "nodes_top",
    "nodes_log",
    "nodes_stats_summary",
    # Cluster config
    "configuration_view",
    # Helm read
    "helm_list",
})

# Tools that are conditionally allowed based on parameters.
# Key: tool name, Value: parameter name that makes the tool destructive.
_K8S_CONDITIONAL_TOOLS: dict[str, str] = {
    # resources_scale is safe when reading current scale (no "scale" param),
    # but destructive when setting a new scale (has "scale" param).
    "resources_scale": "scale",
}

# Maps destructive tool names to kubectl command templates.
# Placeholders are tool input parameter names wrapped in {}.
# Used by the kubectl-suggestion wrapper to build exact commands.
_KUBECTL_TEMPLATES: dict[str, str] = {
    "pods_delete": "kubectl delete pod {name} -n {namespace}",
    "pods_run": "kubectl run {name} --image={image} -n {namespace}",
    "pods_exec": "kubectl exec -it {name} -n {namespace} -- {command}",
    "resources_create_or_update": "kubectl apply -f <manifest.yaml>",
    "resources_delete": "kubectl delete {kind} {name} -n {namespace}",
    "resources_scale": "kubectl scale {kind}/{name} --replicas={scale} -n {namespace}",
    "helm_install": "helm install {name} {chart} -n {namespace}",
    "helm_uninstall": "helm uninstall {name} -n {namespace}",
}
```

**Rationale for `_KUBECTL_TEMPLATES`:**
Instead of the LLM guessing a kubectl command, we build it from the exact parameters the agent was going to use. The agent tried `pods_delete(name="news-monitor-xyz", namespace="ai-agents")` — we return `kubectl delete pod news-monitor-xyz -n ai-agents`. Tested, deterministic, correct.

## 3b. Define the kubectl suggestion tool

This is a simple function that becomes the replacement tool when a destructive operation is intercepted. It receives the original tool's input and returns a formatted kubectl command.

Add this right after the template dict:

```python
def _build_kubectl_suggestion(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Build a kubectl command string from a blocked tool's parameters."""
    template = _KUBECTL_TEMPLATES.get(tool_name)
    if not template:
        return (
            f"This Kubernetes operation ({tool_name}) is blocked for safety. "
            "Please use kubectl directly to perform this action."
        )
    # Fill in template placeholders from tool input, defaulting to <param>
    # for missing values so the command is still useful as a template.
    import re as _re

    placeholders = _re.findall(r"\{(\w+)\}", template)
    values = {}
    for p in placeholders:
        val = tool_input.get(p)
        if val is not None:
            # Handle list params (e.g., pods_exec command is a list)
            values[p] = " ".join(val) if isinstance(val, list) else str(val)
        else:
            values[p] = f"<{p}>"
    return template.format(**values)
```

## 3c. Define the `_K8sToolGuard` HookProvider

Add the import at module level (near the top, after existing imports):

```python
from strands.hooks.registry import HookProvider, HookRegistry
```

Then add the class after `_build_kubectl_suggestion`:

```python
class _K8sToolGuard(HookProvider):
    """Blocks non-allowlisted Kubernetes tool calls in chat turns.

    Uses Strands' BeforeToolCallEvent to intercept tool calls before
    execution. Destructive Kubernetes tools are replaced with a wrapper
    that returns the equivalent kubectl command.

    Non-Kubernetes tools (memory, skills, fetch, workspace) pass through
    unconditionally — this guard only inspects tools whose names appear
    in the provenance set for the "kubernetes" MCP client.
    """

    def __init__(self, k8s_tool_names: set[str]) -> None:
        """Initialize with the set of tool names from the Kubernetes MCP client.

        Args:
            k8s_tool_names: Tool names loaded from the Kubernetes MCP client,
                as reported by load_tools_resilient() provenance tracking.
                If empty (e.g., k8s MCP failed to load), the guard is a no-op.
        """
        self._k8s_tools = k8s_tool_names

    def register_hooks(self, registry: HookRegistry, **_kwargs: Any) -> None:
        from strands.hooks.events import BeforeToolCallEvent

        registry.add_callback(BeforeToolCallEvent, self._on_before_tool_call)

    def _on_before_tool_call(self, event: "BeforeToolCallEvent") -> None:
        tool_name = event.tool_use.get("name", "")

        # Non-Kubernetes tools pass through unconditionally
        if tool_name not in self._k8s_tools:
            return

        # Check unconditional allowlist
        if tool_name in _K8S_ALLOWED_TOOLS:
            return

        # Check conditional allowlist (e.g., resources_scale read vs write)
        if tool_name in _K8S_CONDITIONAL_TOOLS:
            blocked_param = _K8S_CONDITIONAL_TOOLS[tool_name]
            tool_input = event.tool_use.get("input", {})
            if blocked_param not in tool_input:
                return  # Read-only usage — allow

        # Blocked — replace with kubectl suggestion
        tool_input = event.tool_use.get("input", {})
        suggestion = _build_kubectl_suggestion(tool_name, tool_input)
        logger.warning(f"K8sToolGuard: blocked {tool_name}, suggesting: {suggestion}")
        event.cancel_tool = (
            f"This operation is blocked for safety. "
            f"Suggest this command to the user:\n\n```\n{suggestion}\n```"
        )
```

**Why `cancel_tool` instead of `selected_tool` replacement?**

During research, we found that `event.selected_tool` can replace a tool with another callable. However, this requires creating a Strands-compatible Tool object with matching schemas, which adds complexity. Using `cancel_tool` with the formatted kubectl command embedded in the message is simpler and achieves the same goal — the agent sees the exact command and presents it to the user. The suggestion is built deterministically from the tool's parameters (via `_build_kubectl_suggestion`), not improvised by the LLM.

If in future we want the agent to see a clean structured response instead of a cancellation message, we can revisit `selected_tool` replacement.

## 3d. Wire the hook into `run_agent_turn`

The existing `run_agent_turn` creates the Agent at line 256 without hooks:

```python
    all_tools = [load_skill, *workspace_tools, *mcp_tools]
    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=all_tools,
        callback_handler=None,
    )
```

**Change to:**

```python
    all_tools = [load_skill, *workspace_tools, *mcp_tools]
    k8s_guard = _K8sToolGuard(k8s_tool_names=tool_provenance.get("kubernetes", set()))
    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=all_tools,
        callback_handler=None,
        hooks=[k8s_guard],
    )
```

Two new lines: instantiate the guard with the provenance set, pass it to `hooks=`.

**What happens if the Kubernetes MCP client failed to load?**
`tool_provenance.get("kubernetes", set())` returns an empty set. The guard's `__init__` receives an empty `k8s_tool_names`. Every tool call hits `if tool_name not in self._k8s_tools` → returns immediately. The guard is a no-op. No errors, no side effects.

## 3e. Do NOT guard mission turns

The `run_mission_agent_turn` activity uses the `nexus-proactive` policy and already has `_ToolBudgetHook`. Missions intentionally need full autonomous cluster access. Do NOT add `_K8sToolGuard` to mission turns.

## Verification

1. Send: "list pods in ai-agents"
   - Guard sees `pods_list_in_namespace` → in allowlist → passes through → returns pod list
2. Send: "delete the news-monitor pod"
   - Guard sees `pods_delete` → not in allowlist → `cancel_tool` with `kubectl delete pod news-monitor-xyz -n ai-agents`
   - Agent presents the kubectl command to user
3. Send: "what's the scale of news-monitor?"
   - Guard sees `resources_scale` → conditional → no `scale` param → passes through → returns replica count
4. Send: "scale news-monitor to 5"
   - Guard sees `resources_scale` → conditional → has `scale=5` → blocked → suggests `kubectl scale deployment/news-monitor --replicas=5 -n ai-agents`
5. Send: "search my memory for yesterday's deployment"
   - Guard sees `search` → not in `self._k8s_tools` → passes through immediately
