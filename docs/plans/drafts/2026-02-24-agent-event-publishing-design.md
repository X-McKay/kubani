# Agent Event Publishing Design

**Date:** 2026-02-24
**Status:** Draft

## Problem

The Kubani UI has a fully-built Activity Feed page (`/activity`) with WebSocket real-time updates, filtering, unread counts, and markdown rendering. The backend consumes `kubani:activity` and `kubani:approvals` Redis Streams, stores events in DuckDB, and broadcasts via WebSocket. Python helpers `publish_activity()` and `publish_approval()` exist in `kubani/framework/ui_events.py`.

None of this is currently wired up. No agent, syndicate, or nexus component publishes events to the UI.

## Approach

**Hybrid: Direct publish calls + Strands hooks**

- **Syndicates:** Add explicit `publish_activity()` calls at key output points
- **Nexus missions:** Add `publish_activity()` in `run_mission_agent_turn` activity at start and completion

No new abstractions, no auto-bridging from the EventBus. Each publish point is intentional and controls what the user sees.

## Nexus Mission Events

Publish from `run_mission_agent_turn` in `kubani/nexus/orchestrator/activities.py`:

| Event | Type | Severity | When |
|-------|------|----------|------|
| Mission started | `agent_activity` | `info` | At start of activity, after DB record |
| Mission completed (noteworthy) | `agent_activity` | `success` | `should_notify=True`, `status=completed` |
| Mission completed (routine) | `agent_activity` | `info` | `should_notify=False`, `status=completed` |
| Mission failed | `alert` | `error` | `status=failed` |
| Mission timed out | `alert` | `warning` | Budget exceeded |

**Source:** `"nexus"`
**Content:** For noteworthy completions, `notification_text` as markdown. For routine, brief summary. For errors, the error message.

**Metadata:** `mission_id`, `run_id`, `tool_calls_made`, `duration_ms`, `status`

## Syndicate Events

### k8s-monitor

Publish after event classification, before remediation:
- **Type:** `alert` (critical/high severity), `agent_activity` (medium/low)
- **Content:** Issue description, affected resource, recommended action
- **Source:** `"k8s-monitor"`

### news-digest

Publish after digest generation:
- **Type:** `syndicate_output`
- **Content:** Full digest markdown
- **Source:** `"news-digest"`

### learning-system

Two publish points:
1. After critic evaluation: `publish_activity()` with type `learning`, evaluation summary
2. After skill synthesis: `publish_approval()` with skill spec for human review
- **Source:** `"learning-system"`

## UI Changes

Add `"nexus"` to `SOURCE_CONFIG` in `platform/ui/client/src/features/activity-feed/types.ts`:

```typescript
"nexus": { label: "Nexus Agent", shortLabel: "nex" }
```

No other UI changes needed — existing WebSocket broadcast, filtering, markdown rendering all work.

## Files to Modify

| File | Change |
|------|--------|
| `kubani/nexus/orchestrator/activities.py` | Add `publish_activity()` in `run_mission_agent_turn` (start + finally) |
| `kubani/syndicates/learning_system/syndicate.py` | Add `publish_activity()` after evaluations, `publish_approval()` for skill proposals |
| `kubani/syndicates/k8s_monitor/src/k8s_monitor_syndicate/worker.py` | Add `publish_activity()` after event classification |
| `kubani/syndicates/news_digest/` (TBD — locate digest generation point) | Add `publish_activity()` after digest generation |
| `platform/ui/client/src/features/activity-feed/types.ts` | Add `"nexus"` to `SOURCE_CONFIG` |

## Non-Goals

- No EventBus-to-UI auto-bridge
- No new event types or schemas
- No changes to the Rust backend
- No new files — uses existing `publish_activity()` / `publish_approval()` helpers
