# K8s Monitor Update Plan

**Date:** 2026-03-15
**Status:** Active
**Scope:** Unblock the k8s-monitor agent so it can detect and resolve cluster issues autonomously

## Background

The k8s-monitor agent failed to detect and remediate a PostgreSQL CrashLoopBackOff that persisted for 8 days. The agent isn't lacking intelligence — it's an LLM that already knows how StatefulSets, PVCs, and debug pods work. It failed because its plumbing is broken: wrong tool names, missing permissions, silent failures, and no log inspection before acting.

The fix is not to add specialized remediation skills, pattern registries, or hardcoded decision trees. The fix is to **unblock the agent** and let it reason.

## What's Wrong (5 bugs)

| # | Bug | Impact | File |
|---|-----|--------|------|
| 1 | Coordinator prompt references MCP tool names (`pods_list`, `nodes_top`) but agent only has skill-wrapped tools (`k8s_collection_*`) | Agent hallucinates non-existent tools, diagnostics fail | `prompt.md` |
| 2 | `discord_update` missing `@tool` decorator | Strands can't register it, Discord updates silently fail | `remediator/tools.py` |
| 3 | Empty results from specialist agents logged without warning | Issues investigated but findings silently lost | `k8s_coordinator/tools.py` |
| 4 | Activity timeout 10min, but multi-agent dispatch takes 10-15min | Workflow reports failure even when work succeeds | `workflows/monitor.py` |
| 5 | `SCHEDULE_INTERVAL_MINUTES = 5` but Temporal schedule manually set to 60min | Redeployment reverts to 5min, causing noise | `worker.py` |

## What's Missing (2 gaps)

| # | Gap | Impact | File |
|---|-----|--------|------|
| 6 | RBAC: no pod `delete`/`create`/`exec` permissions | Agent can't restart pods or use debug pods for PVC issues | `rbac.yaml` |
| 7 | Coordinator doesn't check pod logs before choosing remediation | Blindly restarts pods with storage issues (restart won't fix stale PID files) | `prompt.md` |

## What's Stale (2 config issues)

| # | Issue | File |
|---|-------|------|
| 8 | Node list `[rig0, asio, workstation]` is wrong — actual: `[sparky, asio, strix, rig0, osprey]` | `config.yaml` |
| 9 | "All clear" cadence says "every 30 min" but should match 60min interval | `prompt.md` |

## Implementation Order

These should be done sequentially — each fix builds on the previous:

### 1. Fix tool names in coordinator prompt (~15 min)
**File:** `kubani/agents/k8s_coordinator/prompt.md` (lines 17-22)

Replace MCP tool names with actual skill names:
```markdown
Use your skills to gather cluster state:
- `k8s_collection_get_cluster_health` — overall cluster health snapshot
- `k8s_collection_list_pods_in_namespace` — list pods in a specific namespace
- `k8s_collection_list_recent_events` — recent cluster events
- `k8s_collection_get_resource_usage` — CPU/memory usage
- `k8s_collection_get_deployment_status` — deployment rollout status
```

### 2. Fix `discord_update` tool registration (~10 min)
**File:** `kubani/agents/remediator/tools.py`

The function (line 28) is missing the `@tool` decorator and is sync but called from an async agent. Add `@tool` decorator from strands. Also fix the sync/async issue — it tries to call `asyncio.run()` from within an already-running event loop (line 120), which always fails and logs a warning.

### 3. Fix empty result logging (~10 min)
**File:** `kubani/agents/k8s_coordinator/tools.py`

`dispatch_diagnostics` and `dispatch_remediation` log `result[:200]` but don't handle empty results. Add a warning when the result is empty and return a fallback message. This is likely a symptom of bug #1 (agent can't use tools → returns nothing), but the defensive logging will help diagnose any remaining issues.

### 4. Fix activity timeout and heartbeat (~15 min)
**File:** `kubani/syndicates/k8s_monitor/workflows/monitor.py`

Increase `start_to_close_timeout` from 10min to 15min and `heartbeat_timeout` from 2min to 3min.

**File:** `kubani/syndicates/k8s_monitor/activities.py`

Add a background heartbeat loop (every 30s) around the coordinator agent run so Temporal doesn't think the activity is stuck.

### 5. Fix schedule interval (~5 min)
**File:** `kubani/syndicates/k8s_monitor/src/k8s_monitor_syndicate/worker.py` (line 38)

Change `SCHEDULE_INTERVAL_MINUTES = 5` to `60`.

### 6. Expand RBAC for remediation (~10 min)
**File:** `infrastructure/gitops/apps/ai-agents/k8s-monitor/rbac.yaml`

Add pod lifecycle verbs and exec access:
```yaml
- apiGroups: [""]
  resources: [pods]
  verbs: ["get", "list", "watch", "delete", "create"]
- apiGroups: [""]
  resources: [pods/exec]
  verbs: ["create"]
```

The agent already has safety guards (`skip_resource_patterns: ^k8s-monitor-`) and namespace restrictions.

### 7. Update coordinator prompt to check logs before acting (~15 min)
**File:** `kubani/agents/k8s_coordinator/prompt.md`

Add to Step 2 (Filter and Triage):
```markdown
### Step 2b: Check Logs Before Remediation

For any CrashLoopBackOff or Error pod, check the pod logs (last 50 lines) before dispatching.
If the logs indicate a storage issue (I/O errors, stale PID files, read-only filesystem,
full disk, mount failures), dispatch to diagnostics instead of remediation — a pod restart
won't fix storage problems.

Include the relevant log lines in your dispatch so the specialist has context.
```

This is a prompt change, not code. The LLM knows what storage errors look like — we don't need to enumerate patterns in config. We just need to tell it to look.

### 8. Fix stale config (~5 min)
**File:** `kubani/agents/k8s_coordinator/config.yaml`

Update node list to `[sparky, asio, strix, rig0, osprey]`. Update the same in `kubani/agents/remediator/config.yaml`.

**File:** `kubani/agents/k8s_coordinator/prompt.md`

Update "all clear" cadence to match 60min interval: "publish a brief all clear only every 6th run (every 6 hours)".

## What We're NOT Doing

- **No `cleanup-statefulset-pvc` skill** — the LLM already knows the debug-pod pattern (scale down → mount PVC in debug pod → remove stale files → scale back up). It just needs RBAC permission to do it.
- **No storage pattern registry** — hardcoding `postmaster.pid` patterns for PostgreSQL, Redis, MySQL is brittle. The LLM can read logs and reason about what files are stale.
- **No Redis-based deduplication** — with 60-minute intervals, duplicate alerts are tolerable. If this becomes a problem, add prompt-level dedup ("don't re-report issues you reported last run").
- **No UI feed auth** — that's a platform-wide concern, not a k8s-monitor fix.

## Verification

After all changes:
1. `kubani local-run --agent k8s-monitor` — no `tool not found` errors in logs
2. Coordinator successfully calls `k8s_collection_get_cluster_health` and other skills
3. Specialist agents return non-empty results
4. Discord updates post successfully (no `unrecognized tool specification` warnings)
5. Activity completes within timeout (check Temporal UI)
6. `kubectl auth can-i delete pods --as=system:serviceaccount:ai-agents:k8s-monitor` returns `yes`

## Key Files

| File | Role |
|------|------|
| `kubani/agents/k8s_coordinator/prompt.md` | Coordinator system prompt (bugs #1, #7, #9) |
| `kubani/agents/k8s_coordinator/tools.py` | Dispatch tools (bug #3) |
| `kubani/agents/k8s_coordinator/config.yaml` | Node list, namespaces (bug #8) |
| `kubani/agents/remediator/tools.py` | discord_update (bug #2) |
| `kubani/syndicates/k8s_monitor/workflows/monitor.py` | Activity timeout (bug #4) |
| `kubani/syndicates/k8s_monitor/activities.py` | Heartbeat loop (bug #4) |
| `kubani/syndicates/k8s_monitor/src/k8s_monitor_syndicate/worker.py` | Schedule interval (bug #5) |
| `infrastructure/gitops/apps/ai-agents/k8s-monitor/rbac.yaml` | RBAC permissions (gap #6) |
