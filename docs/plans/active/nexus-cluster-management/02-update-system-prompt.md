# Step 2: Update System Prompt

**File:** `kubani/nexus/orchestrator/activities.py`

## What to change

Replace lines 132-135 of `AGENT_SYSTEM_PROMPT`. These are the last lines before the closing `"""`.

**Before (lines 132-136):**
```python
Notes:
- For cluster operations (pod status, deployments, etc.), let the user
  know that dedicated cluster tools are coming soon. You can still help
  with Kubernetes YAML files, Helm charts, and documentation.
- Be concise in your responses."""
```

**After:**
```python
KUBERNETES (via MCP): Cluster monitoring and troubleshooting tools are available.
  Use your Kubernetes skills (load_skill) for structured investigation and
  remediation workflows. For ad-hoc queries, use the cluster tools directly
  (pods_list, pods_log, events_list, resources_get, nodes_top, etc.).
  Some destructive operations are blocked — when this happens, suggest the
  equivalent kubectl command the user can run.

Notes:
- Be concise in your responses."""
```

## Rationale

**Why minimal?** The original plan had ~30 lines of investigation workflows, tool groupings, and kubectl suggestion patterns in the system prompt. This duplicated knowledge already encoded in the existing k8s skills:

| Skill | What it encodes |
|-------|----------------|
| `investigate-pod-failure` | 4-step investigation workflow (events → logs → describe → correlate) |
| `get-cluster-health` | Events → pods → nodes diagnostic sequence |
| `restart-crashloop` | Remediation with approval gate and exact commands |
| `scale-deployment` | Scaling with approval gate and exact commands |

The system prompt should announce tool availability and point to skills. The skills carry the detailed workflows — that's what they're for. Two places encoding the same knowledge means two places to maintain and potential conflicts when skills evolve.

**What the prompt does:**
1. Tells the agent Kubernetes tools exist
2. Points to skills for structured workflows
3. Permits direct tool use for simple queries
4. Sets expectation that some ops are blocked (so the agent isn't surprised)

**What the prompt does NOT do:**
- List every tool (the agent sees the MCP tool schemas already)
- Describe investigation workflows (skills handle this)
- Explain the allowlist (the hook handles enforcement)

## Important: Keep the rest of the prompt unchanged

Only the `Notes:` section at the end changes. Everything above (CRITICAL RULES FOR TOOL USE, WORKSPACE, MEMORY, SKILLS, FETCH, WEB SEARCH, WHEN TOOLS FAIL sections) stays exactly as-is.

The `MISSION_SYSTEM_PROMPT` is also unchanged — missions use `nexus-proactive` with no tool guard.

## Verification

Start orchestrator locally, send "what tools do you have?" — response should mention Kubernetes cluster tools. Agent should NOT say "cluster tools are coming soon."
