# Step 4: Test and Verify

## Unit Tests

**File:** `kubani/nexus/orchestrator/test_k8s_tool_guard.py` (new file)

Test the `_K8sToolGuard` hook and `_build_kubectl_suggestion` in isolation. No MCP servers or Temporal needed.

```python
"""Tests for _K8sToolGuard hook and kubectl suggestion builder."""

import pytest

from kubani.nexus.orchestrator.activities import (
    _K8S_ALLOWED_TOOLS,
    _K8S_CONDITIONAL_TOOLS,
    _KUBECTL_TEMPLATES,
    _K8sToolGuard,
    _build_kubectl_suggestion,
)

# -- All known Kubernetes MCP tool names (as of @modelcontextprotocol/server-kubernetes) --
# This simulates what load_tools_resilient() provenance tracking would return.
_ALL_K8S_TOOLS: set[str] = {
    # Read/safe
    "pods_list", "pods_list_in_namespace", "pods_get", "pods_log", "pods_top",
    "resources_list", "resources_get",
    "events_list", "namespaces_list",
    "nodes_top", "nodes_log", "nodes_stats_summary",
    "configuration_view",
    "helm_list",
    # Conditional
    "resources_scale",
    # Destructive
    "pods_delete", "pods_run", "pods_exec",
    "resources_create_or_update", "resources_delete",
    "helm_install", "helm_uninstall",
}


class FakeBeforeToolCallEvent:
    """Minimal mock of strands.hooks.events.BeforeToolCallEvent."""

    def __init__(self, tool_name: str, tool_input: dict | None = None):
        self.tool_use = {"name": tool_name, "input": tool_input or {}}
        self.cancel_tool: str | None = None


@pytest.fixture
def guard():
    return _K8sToolGuard(k8s_tool_names=_ALL_K8S_TOOLS)


@pytest.fixture
def empty_guard():
    """Guard with no k8s tools (simulates k8s MCP load failure)."""
    return _K8sToolGuard(k8s_tool_names=set())


# =========================================================================
# Allowed tools
# =========================================================================


class TestAllowedTools:
    """Verify every tool in the allowlist passes through."""

    @pytest.mark.parametrize("tool_name", sorted(_K8S_ALLOWED_TOOLS))
    def test_allowed_tool_passes(self, guard, tool_name):
        event = FakeBeforeToolCallEvent(tool_name)
        guard._on_before_tool_call(event)
        assert event.cancel_tool is None

    def test_resources_scale_read_only_passes(self, guard):
        """resources_scale without 'scale' param is read-only."""
        event = FakeBeforeToolCallEvent(
            "resources_scale",
            {"apiVersion": "apps/v1", "kind": "Deployment", "name": "x"},
        )
        guard._on_before_tool_call(event)
        assert event.cancel_tool is None


# =========================================================================
# Blocked tools
# =========================================================================


class TestBlockedTools:
    """Verify destructive tools are blocked with kubectl suggestions."""

    @pytest.mark.parametrize("tool_name", [
        "pods_delete",
        "pods_run",
        "pods_exec",
        "resources_create_or_update",
        "resources_delete",
        "helm_install",
        "helm_uninstall",
    ])
    def test_destructive_tool_blocked(self, guard, tool_name):
        event = FakeBeforeToolCallEvent(tool_name)
        guard._on_before_tool_call(event)
        assert event.cancel_tool is not None
        assert "blocked for safety" in event.cancel_tool

    def test_resources_scale_write_blocked(self, guard):
        """resources_scale WITH 'scale' param is destructive."""
        event = FakeBeforeToolCallEvent(
            "resources_scale",
            {"apiVersion": "apps/v1", "kind": "Deployment", "name": "x", "scale": 3},
        )
        guard._on_before_tool_call(event)
        assert event.cancel_tool is not None

    def test_unknown_k8s_tool_blocked(self, guard):
        """Future/unknown Kubernetes tools are blocked by default.

        This is the most important test — it verifies deny-by-default.
        If the MCP server adds a new tool, it must be explicitly
        allowlisted before it can execute autonomously.
        """
        # Simulate a future tool added to the k8s MCP server
        guard_with_new_tool = _K8sToolGuard(
            k8s_tool_names=_ALL_K8S_TOOLS | {"namespaces_delete"}
        )
        event = FakeBeforeToolCallEvent("namespaces_delete")
        guard_with_new_tool._on_before_tool_call(event)
        assert event.cancel_tool is not None


# =========================================================================
# Non-Kubernetes tools (pass-through)
# =========================================================================


class TestNonK8sToolsPassThrough:
    """Non-Kubernetes tools are never affected by the guard."""

    @pytest.mark.parametrize("tool_name", [
        "save_memory",
        "search",
        "load_skill",
        "read_file",
        "write_file",
        "bash",
        "fetch",
        "web_search",
    ])
    def test_non_k8s_tool_passes(self, guard, tool_name):
        event = FakeBeforeToolCallEvent(tool_name)
        guard._on_before_tool_call(event)
        assert event.cancel_tool is None


# =========================================================================
# Empty guard (k8s MCP failed to load)
# =========================================================================


class TestEmptyGuard:
    """When k8s MCP fails to load, guard is a complete no-op."""

    def test_any_tool_passes(self, empty_guard):
        """With no k8s tools tracked, nothing is blocked."""
        for tool_name in ["pods_delete", "resources_delete", "helm_uninstall"]:
            event = FakeBeforeToolCallEvent(tool_name)
            empty_guard._on_before_tool_call(event)
            assert event.cancel_tool is None


# =========================================================================
# Kubectl suggestion builder
# =========================================================================


class TestKubectlSuggestion:
    """Verify kubectl command generation from tool parameters."""

    def test_pods_delete(self):
        result = _build_kubectl_suggestion(
            "pods_delete", {"name": "news-monitor-xyz", "namespace": "ai-agents"}
        )
        assert result == "kubectl delete pod news-monitor-xyz -n ai-agents"

    def test_resources_scale(self):
        result = _build_kubectl_suggestion(
            "resources_scale",
            {"apiVersion": "apps/v1", "kind": "Deployment", "name": "news-monitor",
             "namespace": "ai-agents", "scale": 5},
        )
        assert result == "kubectl scale Deployment/news-monitor --replicas=5 -n ai-agents"

    def test_pods_exec_with_list_command(self):
        result = _build_kubectl_suggestion(
            "pods_exec",
            {"name": "web-pod", "namespace": "default", "command": ["ls", "-la", "/tmp"]},
        )
        assert result == "kubectl exec -it web-pod -n default -- ls -la /tmp"

    def test_missing_params_show_placeholders(self):
        """Missing parameters become <param> placeholders."""
        result = _build_kubectl_suggestion("pods_delete", {"name": "my-pod"})
        assert result == "kubectl delete pod my-pod -n <namespace>"

    def test_unknown_tool_gives_generic_message(self):
        result = _build_kubectl_suggestion("some_future_tool", {})
        assert "blocked for safety" in result
        assert "kubectl" in result
```

## Run the tests

```bash
cd /home/al/git/kubani
python -m pytest kubani/nexus/orchestrator/test_k8s_tool_guard.py -v
```

Expected: all tests pass. If Strands imports fail in the test environment, the issue is with the module-level import of `HookProvider` — see Step 3c for the import location.

## Local Integration Verification

After tests pass, verify end-to-end locally:

```bash
cd kubani/nexus/orchestrator
source .env
python -m kubani.nexus.orchestrator.worker
```

Then send messages via the gateway (or Discord):

| Message | Expected tool call | Expected behavior |
|---------|-------------------|-------------------|
| "list pods in ai-agents" | `pods_list_in_namespace` | Passes allowlist, returns pod list |
| "show recent cluster events" | `events_list` | Passes allowlist, returns events |
| "get logs from news-monitor pod" | `pods_log` | Passes allowlist, returns logs |
| "what nodes do we have?" | `nodes_top` | Passes allowlist, returns metrics |
| "delete the stuck pod" | `pods_delete` | Blocked, agent shows `kubectl delete pod ...` |
| "deploy a new nginx pod" | `pods_run` | Blocked, agent shows `kubectl run ...` |
| "scale news-monitor to 5" | `resources_scale` (with scale=5) | Blocked, agent shows `kubectl scale ...` |
| "what's the current scale of news-monitor?" | `resources_scale` (no scale param) | Passes conditional check, returns count |
| "install prometheus helm chart" | `helm_install` | Blocked, agent shows `helm install ...` |
| "search memory for deployment history" | `search` | Non-k8s tool, passes through immediately |

## Ship

Once local verification passes:

```bash
kubani ship nexus-orchestrator
```

This builds, pushes, patches the gitops manifest, and verifies the pod comes up healthy.
