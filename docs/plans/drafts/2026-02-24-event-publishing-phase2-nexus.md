# Phase 2: Nexus Mission Event Publishing

**Parent:** `2026-02-24-agent-event-publishing-design.md`
**Depends on:** Phase 1 (redis_url parameter)

## Overview

Add `publish_activity()` calls to the `run_mission_agent_turn` activity so every mission run appears in the UI activity feed. Two publish points:

1. **Mission started** — immediately after the DB run record is created
2. **Mission completed/failed/timed_out** — in the `finally` block, after the DB run outcome is recorded

## File to Modify

`kubani/nexus/orchestrator/activities.py` — specifically the `run_mission_agent_turn` function (lines 288-567).

## Important Context

- This function is a **Temporal activity** (not a workflow). It runs in the nexus orchestrator container.
- The container has `REDIS_URL` env var but NOT `REDIS_HOST`/`REDIS_PORT`. So we MUST pass `redis_url` explicitly.
- The `REDIS_URL` value comes from the same env var already used by `publish_response_activity` at line 938: `os.environ.get("REDIS_URL", "redis://localhost:6379")`.
- The publish calls must be **fire-and-forget** with try/except — a Redis failure must NOT crash the mission. This matches the existing pattern where DB failures are caught and logged (line 364-366).
- `publish_activity` is an async function, which is fine since we're in an async activity.

## Step 2.1: Add Import

At the top of the function (around line 319, near the existing `import os`), add:

```python
from kubani.framework.ui_events import publish_activity
```

This goes alongside the existing lazy imports inside the function. The nexus activities use lazy imports to avoid import cycles.

## Step 2.2: Get Redis URL

Right after `started_at = time.monotonic()` (line 334), add:

```python
redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
```

Note: `os` is already imported at line 319. The `redis_url` variable will be used by both publish points.

## Step 2.3: Publish "Mission Started" Event

**Location:** After the DB record creation block (after line 366), before the "Build the agent" section.

**Insert this code between the DB record block and the "Build the agent" comment:**

```python
    # ------------------------------------------------------------------
    # Publish "mission started" to the UI activity feed
    # ------------------------------------------------------------------
    try:
        await publish_activity(
            source="nexus",
            event_type="agent_activity",
            title=f"Mission started: {mission_title}",
            content=f"**Goal:** {mission_goal}\n\n*Budget: {max_tool_calls} tool calls, Policy: {mcp_policy}*",
            severity="info",
            metadata={
                "mission_id": mission_id,
                "run_id": run_id,
                "user_id": user_id,
                "mcp_policy": mcp_policy,
                "max_tool_calls": max_tool_calls,
            },
            redis_url=redis_url,
        )
    except Exception:
        logger.debug(f"Mission {mission_id}: could not publish start event to UI")
```

### Notes on this code:

- **`source="nexus"`** — matches the UI's `SOURCE_CONFIG` entry added in Phase 1
- **`event_type="agent_activity"`** — maps to the "Agent" badge with Bot icon in the UI
- **`severity="info"`** — neutral severity for a start event
- **Title format:** `"Mission started: {mission_title}"` — concise, shown in feed card
- **Content:** Shows the goal and budget as markdown. The content appears in the detail panel when you click the event.
- **try/except with bare Exception:** This MUST never crash the mission. We log at `debug` level because this is a non-critical enhancement.
- **No `logger.warning`** on failure — this is intentional. A warning would be noisy in logs if Redis is temporarily unreachable. Debug is sufficient.

## Step 2.4: Publish Mission Completion Event

**Location:** Inside the `finally` block, after the `complete_mission_run` DB call (after line 564, before `activity.heartbeat` on line 566).

**Insert this code:**

```python
        # Publish mission result to the UI activity feed
        try:
            status = result_dict["status"]
            if status == "completed" and result_dict["should_notify"]:
                await publish_activity(
                    source="nexus",
                    event_type="agent_activity",
                    title=f"Mission finding: {mission_title}",
                    content=result_dict["notification_text"],
                    severity="success",
                    metadata={
                        "mission_id": mission_id,
                        "run_id": run_id,
                        "status": status,
                        "tool_calls_made": result_dict["tool_calls_made"],
                        "found_anomaly": result_dict["found_anomaly"],
                        "duration_ms": duration_ms,
                    },
                    redis_url=redis_url,
                )
            elif status == "completed":
                await publish_activity(
                    source="nexus",
                    event_type="agent_activity",
                    title=f"Mission completed: {mission_title}",
                    content=f"Completed normally. Used {result_dict['tool_calls_made']}/{max_tool_calls} tool calls in {duration_ms}ms.",
                    severity="info",
                    metadata={
                        "mission_id": mission_id,
                        "run_id": run_id,
                        "status": status,
                        "tool_calls_made": result_dict["tool_calls_made"],
                        "duration_ms": duration_ms,
                    },
                    redis_url=redis_url,
                )
            elif status == "failed":
                await publish_activity(
                    source="nexus",
                    event_type="alert",
                    title=f"Mission failed: {mission_title}",
                    content=result_dict["notification_text"],
                    severity="error",
                    metadata={
                        "mission_id": mission_id,
                        "run_id": run_id,
                        "status": status,
                        "tool_calls_made": result_dict["tool_calls_made"],
                        "duration_ms": duration_ms,
                    },
                    redis_url=redis_url,
                )
            elif status == "timed_out":
                await publish_activity(
                    source="nexus",
                    event_type="alert",
                    title=f"Mission timed out: {mission_title}",
                    content=result_dict["notification_text"],
                    severity="warning",
                    metadata={
                        "mission_id": mission_id,
                        "run_id": run_id,
                        "status": status,
                        "tool_calls_made": result_dict["tool_calls_made"],
                        "duration_ms": duration_ms,
                    },
                    redis_url=redis_url,
                )
        except Exception:
            logger.debug(f"Mission {mission_id}: could not publish result event to UI")
```

### Notes on this code:

- **Four branches** matching the four possible `status` values: `completed` (with notify), `completed` (routine), `failed`, `timed_out`
- **`event_type` varies:** `"agent_activity"` for completions, `"alert"` for failures/timeouts
- **`severity` varies:** `"success"` for noteworthy findings, `"info"` for routine, `"error"` for failures, `"warning"` for timeouts
- **`notification_text`** is used as-is for the content when available — this is the agent's actual finding, which may be a paragraph of markdown
- **`duration_ms`** is already computed on line 546 and available in the finally block
- **Title prefixes** (`"Mission finding:"`, `"Mission completed:"`, `"Mission failed:"`, `"Mission timed out:"`) make it instantly clear what happened when scanning the feed
- **Same fire-and-forget pattern** as the start event — bare except, debug log

## Step 2.5: Complete Picture — Where Code Goes in the Function

Here's the annotated function structure showing where new code is inserted:

```
async def run_mission_agent_turn(input_data):
    # Lines 319-331: Parse input_data
    # Line 333-334: Generate run_id, started_at

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")  # NEW

    # Lines 336-340: Heartbeat + log
    # Lines 342-366: DB record creation

    # NEW: Publish "mission started" event (Step 2.3)
    try:
        await publish_activity(...)
    except Exception:
        logger.debug(...)

    # Lines 368-395: Build agent (MCP clients, model)
    # Lines 397-431: Tool budget hook
    # Lines 433-455: Build prompt
    # Lines 457-467: Initialize result_dict

    try:
        # Lines 469-516: Run agent, parse JSON result
    except RuntimeError as budget_exc:
        # Lines 518-528: Budget exceeded
    except Exception as exc:
        # Lines 530-535: Agent error

    finally:
        # Lines 538-543: Clean up MCP connections
        # Lines 545-564: Record run outcome in DB

        # NEW: Publish mission result event (Step 2.4)
        try:
            status = result_dict["status"]
            if status == "completed" and result_dict["should_notify"]:
                await publish_activity(...)
            elif status == "completed":
                await publish_activity(...)
            elif status == "failed":
                await publish_activity(...)
            elif status == "timed_out":
                await publish_activity(...)
        except Exception:
            logger.debug(...)

    # Line 566: Heartbeat
    # Line 567: Return result_dict
```

## Step 2.6: Build and Deploy

After code changes:

1. **Run linting:**
   ```bash
   just lint
   ```

2. **Build the container:**
   ```bash
   just build nexus-orchestrator
   ```
   The `publish_activity` import is lazy (inside the function), so no import errors at module load time. The `redis.asyncio` package is already a dependency of the orchestrator (used by `NexusPubSub`).

3. **Deploy and verify:**
   ```bash
   # Update image tag in infrastructure/gitops/apps/nexus/orchestrator-deployment.yaml
   # Push, reconcile Flux
   # Create a test mission and check the UI activity feed
   ```

## Verification Checklist

- [ ] `publish_activity` import resolves in the orchestrator container
- [ ] `redis.asyncio` is available (it is — already used by pubsub.py)
- [ ] `REDIS_URL` env var is set in the container (it is — line 34-38 of orchestrator-deployment.yaml)
- [ ] Mission start event appears in UI activity feed
- [ ] Mission completion event appears with correct severity
- [ ] Mission failure shows as alert with error severity
- [ ] A Redis connection failure does NOT crash the mission (try/except works)
- [ ] `duration_ms` is correct (computed before the publish call)

## Files Modified

| File | Lines Added | Nature |
|------|------------|--------|
| `kubani/nexus/orchestrator/activities.py` | ~60 lines | Two publish blocks + redis_url var + import |
