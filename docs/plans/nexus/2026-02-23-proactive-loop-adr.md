# ADR: Nexus Proactive Agent Loop (feature/nexus-loop)

**Date:** 2026-02-23
**Status:** Implemented
**Branch:** `feature/nexus-loop`
**Author:** Nexus implementation

---

## Context

The Nexus Agent was reactive: it blocked on `workflow.wait_condition` and did nothing between user messages. This was correct for Phase 1 (PI agent), but the project's goal is a continuously-working autonomous agent similar to OpenClaw and NanoClaw. Those projects use a `while True` polling loop with a cron scheduler; we need an equivalent that is more secure and observable.

## Decision

Implement a **proactive agent loop** using three additive components:

1. **`NexusMission`** — a user-defined background goal with a cron schedule, MCP policy, tool call budget, and notification conditions. Stored in a new `nexus_missions` PostgreSQL table.

2. **`NexusHeartbeatWorkflow`** — a lightweight Temporal workflow registered as a Temporal Schedule (every 1 minute, SKIP overlap). It queries for due missions and signals the existing `NexusOrchestratorWorkflow` via a new `proactive_mission` signal. It is a pure dispatcher — no agentic logic.

3. **`run_mission_agent_turn`** — a new Temporal activity that runs a bounded Strands agent turn for a single mission. It enforces a hard `max_tool_calls` budget, uses a policy-scoped MCP client set, and returns a structured `{ should_notify, found_anomaly, notification_text }` result.

## Key Design Choices

### Why Temporal Schedules instead of `while True`?

Temporal Schedules are durable, observable, and restartable. A `while True` loop in a workflow would accumulate history unboundedly and is not observable in the Temporal UI. The SKIP overlap policy prevents pile-up under load.

### Why signal the existing workflow instead of starting a new one?

The `NexusOrchestratorWorkflow` already holds the user's conversation history, memory context, and approval state. Signalling it keeps all agentic work in one auditable workflow per user. Starting a new workflow per mission would fragment the audit trail.

### Why a hard `max_tool_calls` budget?

This is the primary safety control preventing runaway loops. A mission with `max_tool_calls=20` can never make more than 20 tool calls regardless of what the LLM decides. This is enforced in the activity callback handler, not in the prompt.

### Why a separate `nexus-proactive` MCP policy?

The default `nexus` policy (memory + skills) is conservative and appropriate for reactive user interactions. Proactive missions that need cluster access (kubernetes, discord, temporal) must explicitly opt in by setting `mcp_policy="nexus-proactive"`. Destructive operations in that policy still require HITL approval via the `requireApproval` list.

### Why not allow missions to trigger other missions?

The heartbeat workflow is the sole trigger. Missions cannot signal other missions. This prevents cascading loops.

## Files Changed

### New files

| File | Purpose |
|---|---|
| `kubani/nexus/models/missions.py` | `NexusMission`, `NexusMissionRun`, `MissionStatus`, `NotifyOn` Pydantic models |
| `kubani/nexus/missions/__init__.py` | Package init |
| `kubani/nexus/missions/db.py` | PostgreSQL CRUD for missions and runs |
| `kubani/nexus/missions/scheduler.py` | Cron computation, validation, human-readable labels |
| `kubani/nexus/missions/activities.py` | Temporal activities for mission CRUD and heartbeat dispatch |
| `kubani/nexus/schema_missions.sql` | PostgreSQL schema for `nexus_missions` and `nexus_mission_runs` |
| `kubani/nexus/orchestrator/heartbeat_workflow.py` | `NexusHeartbeatWorkflow` Temporal workflow |
| `kubani/nexus/mcp/registry/policies/nexus-proactive.json` | New MCP policy for proactive missions |
| `kubani/skills/general/missions/create-mission/SKILL.md` | Skill for creating missions |
| `kubani/skills/general/missions/list-missions/SKILL.md` | Skill for listing missions |
| `kubani/skills/general/missions/pause-mission/SKILL.md` | Skill for pausing missions |
| `kubani/skills/general/missions/resume-mission/SKILL.md` | Skill for resuming missions |
| `kubani/skills/general/missions/delete-mission/SKILL.md` | Skill for deleting missions |
| `kubani/skills/general/missions/get-mission-history/SKILL.md` | Skill for viewing run history |
| `infrastructure/gitops/apps/nexus/heartbeat-schedule-job.yaml` | K8s Job to register the Temporal Schedule |
| `infrastructure/gitops/apps/nexus/missions-migration-job.yaml` | K8s Job to apply the DB migration |
| `tests/test_nexus_loop_e2e.py` | 29 unit + integration tests (no external deps) |

### Modified files

| File | Change |
|---|---|
| `kubani/nexus/models/__init__.py` | Export mission models |
| `kubani/nexus/orchestrator/workflow.py` | Add `proactive_mission` signal handler and `_run_mission_turn` |
| `kubani/nexus/orchestrator/activities.py` | Add `MISSION_SYSTEM_PROMPT` and `run_mission_agent_turn` |
| `kubani/nexus/orchestrator/worker.py` | Register new workflows and activities; add `register_heartbeat_schedule` |
| `kubani/nexus/tools/mcp_clients.py` | Add `_get_allowed_servers`, policy-aware `create_mcp_clients` |
| `infrastructure/gitops/apps/nexus/orchestrator-deployment.yaml` | Add `MCP_DISCORD_URL`, `MCP_TEMPORAL_URL` env vars |
| `infrastructure/gitops/apps/nexus/kustomization.yaml` | Add new job manifests |

## Deployment Order

1. Apply `missions-migration-job.yaml` (creates DB tables)
2. Deploy updated `nexus-orchestrator` image (registers new workflows/activities)
3. Apply `heartbeat-schedule-job.yaml` (registers the Temporal Schedule)

## Security Controls Summary

| Control | Mechanism |
|---|---|
| Tool call budget | Hard cap in `run_mission_agent_turn` callback handler |
| MCP policy enforcement | `_get_allowed_servers` filters servers by policy name |
| Destructive operation approval | `requireApproval` list in `nexus-proactive.json` |
| No mission-triggers-mission | Heartbeat workflow is the sole trigger |
| Audit trail | All runs recorded in `nexus_mission_runs` with full outcome |
| Isolated execution | Each mission turn runs in a Temporal activity (ephemeral) |
| User ownership | All missions scoped to `user_id`; DB queries filter by user |

## Testing

29 tests in `tests/test_nexus_loop_e2e.py` covering:
- Model creation, validation, serialization
- Cron computation and validation
- Prompt formatting and JSON schema presence
- MCP policy filtering
- Full `run_mission_agent_turn` activity (mocked LLM, DB, MCP)
- `should_notify` decision matrix
- Heartbeat dispatch ordering

All tests pass without external services.
