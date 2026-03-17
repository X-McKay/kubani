# Nexus Cluster Management — Implementation Plan

**Date:** 2026-03-16
**Status:** Active
**Goal:** Enable Nexus to answer cluster questions and perform safe remediation from chat, with destructive operations hard-blocked.

## Summary

Four changes across two files:
1. Flip the `kubernetes` flag in the `nexus` MCP policy
2. Add tool provenance tracking to `load_tools_resilient()`
3. Update the system prompt — minimal change, defer to existing k8s skills
4. Add a `_K8sToolGuard` hook that allowlists safe tools and replaces destructive tools with kubectl-suggestion wrappers

## Architecture

```
User: "what pods are crashing?"
  │
  ▼
Gateway → Temporal signal → NexusOrchestratorWorkflow
  │
  ▼
run_agent_turn activity
  │
  ├── MCP policy: "nexus" (now includes kubernetes)
  ├── load_tools_resilient() tracks tool provenance (which MCP client → which tools)
  ├── _K8sToolGuard hook (allowlist + tool replacement)
  │
  ▼
Strands Agent
  ├── pods_list ✅ (in allowlist → executes normally)
  ├── pods_log ✅ (in allowlist → executes normally)
  ├── pods_delete ❌ (not in allowlist → replaced with kubectl suggestion tool)
  │                   → returns: "kubectl delete pod <name> -n <namespace>"
  ▼
Response streamed to user
```

## Design Decisions

- **Allowlist over blocklist**: Kubernetes MCP is a third-party package. Unknown new tools are blocked by default.
- **Tool replacement over cancel_tool**: `event.selected_tool` swap gives the agent a structured kubectl command built from the exact parameters it was going to use, instead of a generic "blocked" message.
- **Provenance tracking over prefix matching**: `load_tools_resilient()` already iterates per-client. Tracking which tools came from which client is reliable; parsing name prefixes is fragile.
- **Minimal system prompt**: Existing k8s skills (`investigate-pod-failure`, `get-cluster-health`, etc.) already encode investigation workflows. The prompt just announces tool availability and points to skills.

## Files Changed

| File | Change | Lines affected |
|------|--------|---------------|
| `kubani/nexus/tools/mcp_clients.py` | Flip policy flag, update docstrings, add provenance tracking to `load_tools_resilient()` | ~20 lines |
| `kubani/nexus/orchestrator/activities.py` | Minimal system prompt update, `_K8sToolGuard` hook class, kubectl suggestion tool, wiring | ~80 lines |

## Steps

1. [Update MCP policy and add provenance tracking](./01-update-mcp-policy.md)
2. [Update system prompt](./02-update-system-prompt.md)
3. [Add K8s tool guard hook](./03-add-tool-guard-hook.md)
4. [Test and verify](./04-test-and-verify.md)

## Open Items

These are out of scope for this implementation but should be addressed in follow-up work:

### 1. Annotation-based filtering (replaces hardcoded allowlist)
Strands `BeforeToolCallEvent` does not currently expose MCP tool annotations (`destructiveHint`, `readOnlyHint`). When Strands adds annotation support, the allowlist should be replaced with annotation-based filtering — zero-maintenance, automatically blocks new destructive tools if the MCP server annotates them properly. Track Strands SDK releases for this.

### 2. Kubernetes skills consolidation
The 18 k8s skills in `kubani/skills/k8s/` have significant overlap:
- 3 skills for resource usage (`check-node-resources`, `get-resource-usage`, `check-pod-resources`)
- `list-pods-in-namespace` and `get-cluster-health` both list pods
- `list-recent-events` and `get-cluster-health` both check events

Consolidate to ~10 skills: one broad `cluster-health` collection skill, focused diagnostic skills, and focused remediation skills.

### 3. Migrate to Strands native `AgentSkills` plugin
Strands has a native skills system (`AgentSkills` plugin) that uses the same `SKILL.md` format Kubani already uses. It handles discovery, catalog injection into system prompt, and activation automatically. Migrating from the custom `load_skill` tool + `_build_skill_catalog()` to the native plugin would reduce custom code and benefit from upstream improvements. This is a larger refactor — evaluate separately.

### 4. Skill-level `requires-approval` enforcement
Several k8s remediation skills have `requires-approval: true` metadata, but this is not enforced at runtime. The tool guard hook could be extended to read skill metadata and enforce approval gates, unifying the two safety models (skill-level and tool-level).

### 5. Custom tool executors
Strands has a `tool_executor` parameter on Agent (currently only `ConcurrentToolExecutor` and `SequentialToolExecutor`). Custom executors are planned (GitHub Issue #762). When available, this could be an alternative enforcement point — intercepting tool execution at the executor level rather than via hooks.
