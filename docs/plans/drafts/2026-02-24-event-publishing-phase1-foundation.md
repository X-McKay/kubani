# Phase 1: Foundation — Redis URL Support + UI Source Config

**Parent:** `2026-02-24-agent-event-publishing-design.md`

## Overview

Before any agent can publish events, we need two foundational changes:
1. Make `publish_activity()`/`publish_approval()` work in containers that only have `REDIS_URL` (not `REDIS_HOST`/`REDIS_PORT`)
2. Add `"nexus"` to the UI's source config so events display correctly

## Step 1.1: Add `redis_url` Parameter to `publish_activity()` and `publish_approval()`

**File:** `kubani/framework/ui_events.py`

### Problem

Currently both functions get Redis from the config system:
```python
config = get_config()
r = redis.from_url(config.memory.redis.url)
```

`get_config().memory.redis.url` builds the URL from `REDIS_HOST` + `REDIS_PORT` env vars (via `RedisConfig` with `env_prefix="REDIS_"`). But the nexus orchestrator container only sets `REDIS_URL` as a full connection string (e.g., `redis://redis-master.cache.svc.cluster.local:6379`). The `RedisConfig` class doesn't parse a full URL — it expects `REDIS_HOST` and `REDIS_PORT` separately.

### Solution

Add an optional `redis_url` parameter to both functions. When provided, skip `get_config()` entirely and use the URL directly. This keeps backward compatibility for syndicates that use the config system.

### Exact Code Change

In `kubani/framework/ui_events.py`, change the `publish_activity` function signature and body:

**BEFORE (lines 45-89):**
```python
async def publish_activity(
    source: str,
    event_type: str,
    title: str,
    content: str = "",
    severity: Literal["info", "warning", "error", "success"] = "info",
    metadata: dict | None = None,
) -> str:
    """Publish an activity event to the UI feed.

    Args:
        source: Syndicate/agent name (e.g., 'news-digest', 'k8s-monitor')
        event_type: Event category. Common types:
            - 'syndicate_output': Output from a syndicate workflow
            - 'agent_activity': Agent action or decision
            - 'alert': Warning or critical notification
            - 'workflow': Temporal workflow status
            - 'learning': Learning system insight
            - 'system': System-level event
        title: Short title for the feed card
        content: Rich markdown content for detail view
        severity: Event severity level
        metadata: Additional structured data (will be JSON serialized)

    Returns:
        Redis stream entry ID
    """
    config = get_config()
    r = redis.from_url(config.memory.redis.url)

    try:
        entry = {
            "source": source,
            "type": event_type,
            "title": title,
            "content": content,
            "severity": severity,
            "metadata": json.dumps(metadata or {}),
        }

        entry_id = await r.xadd(ACTIVITY_STREAM, entry)
        logger.debug(f"Published activity event {entry_id}: {title}")
        return entry_id.decode() if isinstance(entry_id, bytes) else entry_id
    finally:
        await r.aclose()
```

**AFTER:**
```python
async def publish_activity(
    source: str,
    event_type: str,
    title: str,
    content: str = "",
    severity: Literal["info", "warning", "error", "success"] = "info",
    metadata: dict | None = None,
    redis_url: str | None = None,
) -> str:
    """Publish an activity event to the UI feed.

    Args:
        source: Syndicate/agent name (e.g., 'news-digest', 'k8s-monitor')
        event_type: Event category. Common types:
            - 'syndicate_output': Output from a syndicate workflow
            - 'agent_activity': Agent action or decision
            - 'alert': Warning or critical notification
            - 'workflow': Temporal workflow status
            - 'learning': Learning system insight
            - 'system': System-level event
        title: Short title for the feed card
        content: Rich markdown content for detail view
        severity: Event severity level
        metadata: Additional structured data (will be JSON serialized)
        redis_url: Optional Redis URL override. When provided, uses this
            URL directly instead of get_config().memory.redis.url.
            Useful in containers that set REDIS_URL but not REDIS_HOST/PORT.

    Returns:
        Redis stream entry ID
    """
    if redis_url is None:
        config = get_config()
        redis_url = config.memory.redis.url

    r = redis.from_url(redis_url)

    try:
        entry = {
            "source": source,
            "type": event_type,
            "title": title,
            "content": content,
            "severity": severity,
            "metadata": json.dumps(metadata or {}),
        }

        entry_id = await r.xadd(ACTIVITY_STREAM, entry)
        logger.debug(f"Published activity event {entry_id}: {title}")
        return entry_id.decode() if isinstance(entry_id, bytes) else entry_id
    finally:
        await r.aclose()
```

Apply the **same pattern** to `publish_approval` (lines 92-133):

**BEFORE signature:**
```python
async def publish_approval(
    approval_type: str,
    source: str,
    title: str,
    summary: str,
    spec: str = "",
    metadata: dict | None = None,
) -> str:
```

**AFTER signature:**
```python
async def publish_approval(
    approval_type: str,
    source: str,
    title: str,
    summary: str,
    spec: str = "",
    metadata: dict | None = None,
    redis_url: str | None = None,
) -> str:
```

And change the body from:
```python
    config = get_config()
    r = redis.from_url(config.memory.redis.url)
```
to:
```python
    if redis_url is None:
        config = get_config()
        redis_url = config.memory.redis.url

    r = redis.from_url(redis_url)
```

Add `redis_url` to the docstring Args section:
```
        redis_url: Optional Redis URL override. When provided, uses this
            URL directly instead of get_config().memory.redis.url.
```

### Important Notes

- The `get_config` import at the top of the file stays — it's still used when `redis_url` is None
- No other changes to the file
- This is fully backward compatible — existing callers without `redis_url` work exactly as before

## Step 1.2: Add "nexus" to UI Source Config

**File:** `platform/ui/client/src/features/activity-feed/types.ts`

### Exact Code Change

The current `SOURCE_CONFIG` (lines 33-39):
```typescript
export const SOURCE_CONFIG: Record<
  string,
  { label: string; shortLabel: string }
> = {
  "k8s-monitor": { label: "Kubernetes Monitor", shortLabel: "k8s" },
  "news-digest": { label: "News Digest", shortLabel: "news" },
  "learning-system": { label: "Learning System", shortLabel: "learn" },
  system: { label: "System", shortLabel: "sys" },
};
```

**Add `nexus` entry after `system`:**
```typescript
export const SOURCE_CONFIG: Record<
  string,
  { label: string; shortLabel: string }
> = {
  "k8s-monitor": { label: "Kubernetes Monitor", shortLabel: "k8s" },
  "news-digest": { label: "News Digest", shortLabel: "news" },
  "learning-system": { label: "Learning System", shortLabel: "learn" },
  system: { label: "System", shortLabel: "sys" },
  nexus: { label: "Nexus Agent", shortLabel: "nex" },
};
```

### What This Enables

- The filter bar will show "Nexus Agent" as a filterable source
- Events from source `"nexus"` will display with the "nex" short label badge
- Events from unknown sources still display — they just show the raw source string. So this step is nice-to-have for polish, not blocking.

## Step 1.3: Verification

After these changes:

1. **Unit test `publish_activity` with `redis_url` param:**
   ```python
   # In a test, verify that passing redis_url skips get_config()
   # Mock redis.from_url and verify it receives the passed URL
   ```

2. **Check UI compiles:**
   ```bash
   cd platform/ui && npm run build
   ```
   (Or just verify TypeScript is valid — the change is additive to a dict literal.)

## Files Modified

| File | Lines Changed | Nature |
|------|--------------|--------|
| `kubani/framework/ui_events.py` | ~10 lines across 2 functions | Add `redis_url` param |
| `platform/ui/client/src/features/activity-feed/types.ts` | 1 line | Add `nexus` to `SOURCE_CONFIG` |
