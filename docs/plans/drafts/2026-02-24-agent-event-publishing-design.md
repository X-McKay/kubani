# Agent Event Publishing Design

**Date:** 2026-02-24
**Status:** Draft

## Problem

The Kubani UI has a fully-built Activity Feed page (`/activity`) with WebSocket real-time updates, filtering, unread counts, and markdown rendering. The backend consumes `kubani:activity` and `kubani:approvals` Redis Streams, stores events in DuckDB, and broadcasts via WebSocket. Python helpers `publish_activity()` and `publish_approval()` exist in `kubani/framework/ui_events.py`.

**None of this is currently wired up.** `publish_activity` and `publish_approval` are defined but never called anywhere in the codebase. The pipes are laid, the UI is built, but nobody has turned on the faucet.

## Approach

**Hybrid: Direct publish calls for syndicates, direct calls for Nexus missions**

- **Syndicates:** Add explicit `publish_activity()` calls at key output points in each syndicate
- **Nexus missions:** Add `publish_activity()` calls directly in `run_mission_agent_turn` at start and completion
- **No new abstractions** — no auto-bridging from the EventBus, no decorators

Each publish point is intentional and controls exactly what the user sees in the feed.

## Critical Implementation Detail: Redis URL in Nexus Container

`publish_activity()` uses `get_config().memory.redis.url` which builds the URL from `REDIS_HOST`+`REDIS_PORT` env vars. The nexus orchestrator container only has `REDIS_URL` (a full connection string), NOT `REDIS_HOST`/`REDIS_PORT`.

**Solution:** Add an optional `redis_url` parameter to `publish_activity()` and `publish_approval()`. When provided, use it directly instead of `get_config()`. This avoids changing the deployment config and keeps the existing syndicate code path unchanged.

## Implementation Phases

The implementation is split into phases, each in its own detailed plan file:

1. **Phase 1: Foundation** — Update `publish_activity()`/`publish_approval()` to support direct Redis URL, add `"nexus"` source to UI
2. **Phase 2: Nexus Missions** — Wire up event publishing in `run_mission_agent_turn`
3. **Phase 3: Syndicates** — Wire up k8s-monitor, news-digest, and learning-system

See:
- `docs/plans/drafts/2026-02-24-event-publishing-phase1-foundation.md`
- `docs/plans/drafts/2026-02-24-event-publishing-phase2-nexus.md`
- `docs/plans/drafts/2026-02-24-event-publishing-phase3-syndicates.md`

## Non-Goals

- No EventBus-to-UI auto-bridge
- No new event types or schemas beyond what the UI already supports
- No changes to the Rust backend (`platform/ui/backend/src/events.rs`)
- No new Python files — uses existing `publish_activity()`/`publish_approval()` helpers
- No changes to Temporal workflow definitions (only activities and syndicate code)
