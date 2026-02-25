# Phase 3: Syndicate Event Publishing

**Parent:** `2026-02-24-agent-event-publishing-design.md`
**Depends on:** Phase 1 (for consistency, though syndicates can use `get_config()` directly)

## Overview

Wire up three syndicates to publish events to the UI activity feed:
1. **Learning System** — evaluations, reflections, skill proposals
2. **K8s Monitor** — classified Kubernetes issues
3. **News Digest** — published digests and breaking news

Each syndicate already publishes events to the **framework EventBus** (`kubani:events` Redis Stream) for inter-agent communication. This phase adds **separate** `publish_activity()` calls to the **UI stream** (`kubani:activity`). These are different streams consumed by different systems — the EventBus is for agents, the UI stream is for humans.

## Important: Syndicates Use `get_config()`

Unlike Nexus, syndicates use the full kubani config system. Their containers have `REDIS_HOST` and `REDIS_PORT` set. So syndicates can call `publish_activity()` **without** the `redis_url` parameter — the default `get_config()` path works.

---

## Step 3.1: Learning System Syndicate

**File:** `kubani/syndicates/learning_system/syndicate.py`

### 3.1a: Add Import

At the top of the file, after the existing imports (around line 25), add:

```python
from kubani.framework.ui_events import publish_activity, publish_approval
```

This can be a top-level import (not lazy) because the learning system syndicate already imports from `kubani.framework`.

### 3.1b: Publish After Critic Evaluation

**Location:** Inside `_run_critic_loop`, after the existing EventBus publish (after line 122), still inside the `if evaluations:` block.

**Current code (lines 108-122):**
```python
                if evaluations:
                    logger.info(f"Critic evaluated {len(evaluations)} executions")

                    # Publish evaluation event (using local event type)
                    from kubani.syndicates.learning_system.events import EVALUATION_COMPLETE

                    await self._event_bus.publish(
                        EVALUATION_COMPLETE,
                        {
                            "syndicate": self.name,
                            "evaluations": len(evaluations),
                            "avg_score": sum(e.overall_score for e in evaluations)
                            / len(evaluations),
                        },
                        source=self.name,
                    )
```

**Add after the EventBus publish (after line 122), still inside `if evaluations:`:**

```python
                    # Publish to UI activity feed
                    avg = sum(e.overall_score for e in evaluations) / len(evaluations)
                    successes = sum(1 for e in evaluations if e.success)
                    failures = len(evaluations) - successes
                    try:
                        await publish_activity(
                            source="learning-system",
                            event_type="learning",
                            title=f"Critic evaluation: {len(evaluations)} executions reviewed",
                            content=(
                                f"**Average score:** {avg:.2f}\n\n"
                                f"**Results:** {successes} successful, {failures} failed\n\n"
                                f"Evaluated agent executions from the past hour."
                            ),
                            severity="info",
                            metadata={
                                "evaluations": len(evaluations),
                                "avg_score": round(avg, 3),
                                "successes": successes,
                                "failures": failures,
                            },
                        )
                    except Exception as e:
                        logger.debug(f"Could not publish critic evaluation to UI: {e}")
```

### 3.1c: Publish After Reflection

**Location:** Inside `_run_reflection_loop`, after the existing EventBus publish (around line 156), still inside `if result.total_insights > 0:`.

**Current code (lines 140-156):**
```python
                if result.total_insights > 0:
                    logger.info(...)
                    from kubani.syndicates.learning_system.events import REFLECTION_COMPLETE
                    await self._event_bus.publish(
                        REFLECTION_COMPLETE,
                        {
                            "syndicate": self.name,
                            "insights": result.total_insights,
                            "patterns": len(result.patterns),
                            "skill_opportunities": len(result.skill_opportunities),
                        },
                        source=self.name,
                    )
```

**Add after the EventBus publish:**

```python
                    # Publish to UI activity feed
                    try:
                        await publish_activity(
                            source="learning-system",
                            event_type="learning",
                            title=f"Reflection: {result.total_insights} insights synthesized",
                            content=(
                                f"**Insights:** {result.total_insights}\n\n"
                                f"**Patterns identified:** {len(result.patterns)}\n\n"
                                f"**Skill opportunities:** {len(result.skill_opportunities)}\n\n"
                                f"Analyzed {result.evaluations_analyzed} evaluations "
                                f"from the past {getattr(self, '_reflection_window', 'unknown')} period."
                            ),
                            severity="info",
                            metadata={
                                "insights": result.total_insights,
                                "patterns": len(result.patterns),
                                "skill_opportunities": len(result.skill_opportunities),
                                "evaluations_analyzed": result.evaluations_analyzed,
                            },
                        )
                    except Exception as e:
                        logger.debug(f"Could not publish reflection to UI: {e}")
```

### 3.1d: Publish Skill Proposals as Approvals

**Location:** Inside `_run_synthesis_loop`, after the existing EventBus publish (around line 197), still inside `if result.proposals_created > 0:`.

**Current code (lines 181-197):**
```python
                if result.proposals_created > 0:
                    logger.info(...)
                    from kubani.syndicates.learning_system.events import SKILL_PROPOSED
                    await self._event_bus.publish(
                        SKILL_PROPOSED,
                        {
                            "syndicate": self.name,
                            "proposals_created": result.proposals_created,
                            "proposals_posted": result.proposals_posted,
                        },
                        source=self.name,
                    )
```

**Add after the EventBus publish:**

```python
                    # Publish skill proposals to UI for human approval
                    for proposal in result.proposals:
                        try:
                            await publish_approval(
                                approval_type="skill_proposal",
                                source="learning-system",
                                title=f"New Skill: {proposal.name}",
                                summary=proposal.description[:200] if hasattr(proposal, 'description') else str(proposal)[:200],
                                spec=proposal.to_yaml() if hasattr(proposal, 'to_yaml') else str(proposal),
                                metadata={
                                    "confidence": getattr(proposal, 'confidence', None),
                                    "domain": getattr(proposal, 'domain', None),
                                    "proposals_in_batch": result.proposals_created,
                                },
                            )
                        except Exception as e:
                            logger.debug(f"Could not publish skill proposal to UI: {e}")

                    # Also publish a summary activity event
                    try:
                        await publish_activity(
                            source="learning-system",
                            event_type="learning",
                            title=f"Skill synthesis: {result.proposals_created} proposals",
                            content=(
                                f"**Proposals created:** {result.proposals_created}\n\n"
                                f"**Posted for approval:** {result.proposals_posted}\n\n"
                                "Check the Approvals tab to review proposed skills."
                            ),
                            severity="info",
                            metadata={
                                "proposals_created": result.proposals_created,
                                "proposals_posted": result.proposals_posted,
                            },
                        )
                    except Exception as e:
                        logger.debug(f"Could not publish synthesis summary to UI: {e}")
```

### Important Notes for 3.1d:

- **`publish_approval`** goes to the `kubani:approvals` stream, which the Rust backend consumes and shows in the approvals UI. This is separate from the activity feed.
- **`proposal.to_yaml()`** and **`proposal.description`** — these access methods on the proposal objects. The actual attribute names depend on the `SkillSynthesizerAgent` result type. You MUST verify the actual proposal object structure before implementing. Check `kubani/agents/skill_synthesizer/agent.py` for the return type.
- If `proposal` is a dict (not an object), use `proposal.get("name")`, `proposal.get("description")`, etc. instead.
- The `for proposal in result.proposals` loop publishes each proposal as a separate approval. This is intentional — each skill proposal should be individually reviewable.

---

## Step 3.2: K8s Monitor Syndicate

The K8s monitor publishes events at two points:
1. **Event bridge** (`worker.py:run_event_bridge`) — when a K8s event is detected and bridged to a Temporal workflow
2. **Remediation workflow** (`workflows/remediation.py`) — after classification and after remediation

### 3.2a: Publish in Event Bridge

**File:** `kubani/syndicates/k8s_monitor/src/k8s_monitor_syndicate/worker.py`

**Location:** Inside `run_event_bridge()`, after the workflow is started (either investigation or remediation), around lines 352-365.

**Add import at the top of the function:**
```python
from kubani.framework.ui_events import publish_activity
```

**After starting the investigation swarm (after line 352, `await client.start_workflow(K8sInvestigationSwarm.run, ...)`), add:**

```python
                # Publish to UI activity feed
                try:
                    await publish_activity(
                        source="k8s-monitor",
                        event_type="alert",
                        title=f"K8s investigation: {k8s_event.get('name', 'unknown')}",
                        content=(
                            f"**Resource:** {k8s_event.get('kind', 'Unknown')}/{k8s_event.get('name', 'unknown')} "
                            f"in `{k8s_event.get('namespace', 'default')}`\n\n"
                            f"**Reason:** {k8s_event.get('reason', 'Unknown')}\n\n"
                            f"**Message:** {k8s_event.get('message', 'No message')}\n\n"
                            f"*Severity: {severity} — Started investigation swarm*"
                        ),
                        severity="warning" if severity != "critical" else "error",
                        metadata={
                            "event_id": event.id,
                            "resource_kind": k8s_event.get("kind"),
                            "resource_name": k8s_event.get("name"),
                            "namespace": k8s_event.get("namespace"),
                            "reason": k8s_event.get("reason"),
                            "severity": severity,
                            "workflow_type": "investigation",
                        },
                    )
                except Exception:
                    pass
```

**After starting the remediation workflow (after line 365, `await client.start_workflow(K8sRemediationWorkflow.run, ...)`), add:**

```python
                # Publish to UI activity feed
                try:
                    await publish_activity(
                        source="k8s-monitor",
                        event_type="alert" if severity in ("critical", "high") else "agent_activity",
                        title=f"K8s issue: {k8s_event.get('reason', 'Unknown')} — {k8s_event.get('name', 'unknown')}",
                        content=(
                            f"**Resource:** {k8s_event.get('kind', 'Unknown')}/{k8s_event.get('name', 'unknown')} "
                            f"in `{k8s_event.get('namespace', 'default')}`\n\n"
                            f"**Reason:** {k8s_event.get('reason', 'Unknown')}\n\n"
                            f"**Message:** {k8s_event.get('message', 'No message')}\n\n"
                            f"*Severity: {severity} — Started remediation workflow*"
                        ),
                        severity="warning" if severity in ("critical", "high") else "info",
                        metadata={
                            "event_id": event.id,
                            "resource_kind": k8s_event.get("kind"),
                            "resource_name": k8s_event.get("name"),
                            "namespace": k8s_event.get("namespace"),
                            "reason": k8s_event.get("reason"),
                            "severity": severity,
                            "workflow_type": "remediation",
                        },
                    )
                except Exception:
                    pass
```

### 3.2b: Publish After Remediation Completes

**File:** `kubani/syndicates/k8s_monitor/workflows/remediation.py`

**Important constraint:** This is a **Temporal Workflow**, not an activity. Workflows are deterministic and cannot make network calls directly. `publish_activity()` makes a Redis call, which is a side effect.

**Solution:** You CANNOT call `publish_activity()` from inside a workflow. Instead, publish from within an activity that the workflow calls. The cleanest option is:

**Option A (Recommended):** Add the publish call to the existing `remediate_issue_activity` in `kubani/framework/temporal/activities.py`. After remediation completes, publish the result.

**Option B:** Create a new lightweight activity `publish_ui_event_activity` that wraps `publish_activity()`. The workflow calls this activity after remediation.

**Go with Option A** to avoid creating new files. Inside `remediate_issue_activity` (line 407 of `kubani/framework/temporal/activities.py`), after the agent runs and returns a result, add a publish call.

**Location:** At the end of `remediate_issue_activity`, before the return statement.

First, read the full function to find the exact return point. The function runs a remediation agent and returns the result. Add the publish call just before the return.

```python
    # Publish remediation result to UI activity feed
    try:
        from kubani.framework.ui_events import publish_activity

        success = result.get("success", False)
        await publish_activity(
            source="k8s-monitor",
            event_type="agent_activity",
            title=f"Remediation {'completed' if success else 'failed'}: {resource_info.get('name', 'unknown')}",
            content=(
                f"**Resource:** {resource_info.get('kind', 'Unknown')}/{resource_info.get('name', 'unknown')} "
                f"in `{resource_info.get('namespace', 'default')}`\n\n"
                f"**Issue:** {issue_summary}\n\n"
                f"**Result:** {result.get('result', 'No details')[:500]}"
            ),
            severity="success" if success else "error",
            metadata={
                "resource_kind": resource_info.get("kind"),
                "resource_name": resource_info.get("name"),
                "namespace": resource_info.get("namespace"),
                "success": success,
            },
        )
    except Exception:
        pass
```

### Important Notes for 3.2:

- **Do NOT publish from Temporal workflows** — only from activities. Workflows must be deterministic.
- The k8s-monitor syndicate may not be running in production currently. These changes prepare the code for when it's deployed.
- The `severity` variable is available in `run_event_bridge` because it's computed earlier in the function.

---

## Step 3.3: News Digest Syndicate

The news digest has two key publish points:
1. **Digest published** — after `_compose_and_publish` completes
2. **Breaking news detected** — after `_notify_breaking_news`

Both are inside **Temporal Workflows** (`NewsDigestWorkflow` and `NewsCollectionWorkflow`). Same constraint as k8s-monitor: cannot call `publish_activity()` from workflows.

### 3.3a: Publish After Digest is Composed

**File:** `kubani/syndicates/news_digest/workflows/digest.py`

**Location:** Inside `_compose_and_publish`, after the success check (line 417-424):

```python
        if result.get("success"):
            publish_result = self._parse_json_from_result(result.get("result", ""))
            self._result.message_id = publish_result.get("message_id")
            self._log_event(
                "digest_published",
                f"Published digest to {channel}",
                message_id=self._result.message_id,
            )
```

**Problem:** This is a workflow method. We can't call `publish_activity()` directly.

**Solution:** Execute `publish_activity()` inside a Temporal activity. Create a small wrapper activity.

**Add a new activity function in `kubani/framework/temporal/activities.py`:**

```python
@activity.defn
async def publish_ui_activity(
    source: str,
    event_type: str,
    title: str,
    content: str = "",
    severity: str = "info",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish an event to the UI activity feed.

    This is a thin wrapper around publish_activity() that can be called
    from Temporal workflows. It's fire-and-forget — failures are logged
    but don't propagate.
    """
    try:
        from kubani.framework.ui_events import publish_activity

        entry_id = await publish_activity(
            source=source,
            event_type=event_type,
            title=title,
            content=content,
            severity=severity,
            metadata=metadata,
        )
        return {"success": True, "entry_id": entry_id}
    except Exception as e:
        logger.warning(f"publish_ui_activity failed: {e}")
        return {"success": False, "error": str(e)}
```

**Register the activity** in the syndicate workers that need it:
- `kubani/syndicates/news_digest/src/news_digest_syndicate/worker.py` — add to `get_activities()` list
- `kubani/syndicates/k8s_monitor/src/k8s_monitor_syndicate/worker.py` — add to `get_activities()` list
- Also register in `kubani/framework/temporal/__init__.py` exports

**WAIT — This changes the approach.** Let me reconsider.

Actually, for k8s-monitor's `run_event_bridge()` function (Step 3.2a), publishing happens **outside** the workflow, in the bridge function that runs as a plain async function. So `publish_activity()` works there directly.

For k8s-monitor's remediation result (Step 3.2b), publishing happens inside `remediate_issue_activity` which is already a Temporal activity. So `publish_activity()` works there too.

**Only the news-digest workflows need the wrapper activity.** Let me revise:

### Revised 3.3a: Create `publish_ui_activity` Temporal Activity

**File:** `kubani/framework/temporal/activities.py`

Add at the end of the file (before any `__all__` or exports):

```python
@activity.defn
async def publish_ui_activity(
    source: str,
    event_type: str,
    title: str,
    content: str = "",
    severity: str = "info",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish an event to the UI activity feed.

    Thin Temporal activity wrapper around publish_activity() for use by
    workflows that cannot make direct network calls.
    """
    try:
        from kubani.framework.ui_events import publish_activity

        entry_id = await publish_activity(
            source=source,
            event_type=event_type,
            title=title,
            content=content,
            severity=severity,
            metadata=metadata,
        )
        return {"success": True, "entry_id": entry_id}
    except Exception as e:
        logger.warning(f"publish_ui_activity failed: {e}")
        return {"success": False, "error": str(e)}
```

**Register in `kubani/framework/temporal/__init__.py`:**
- Add `publish_ui_activity` to the imports and `__all__`

**Register in news-digest worker** (`kubani/syndicates/news_digest/src/news_digest_syndicate/worker.py`):
- Add to the `get_activities()` return list:
  ```python
  from kubani.framework.temporal import publish_ui_activity
  # ... in get_activities():
  return [
      ...,
      publish_ui_activity,
  ]
  ```

### 3.3b: Publish Digest to UI from Workflow

**File:** `kubani/syndicates/news_digest/workflows/digest.py`

**Location:** Inside `_compose_and_publish`, after the success check (after line 424):

```python
        if result.get("success"):
            publish_result = self._parse_json_from_result(result.get("result", ""))
            self._result.message_id = publish_result.get("message_id")
            self._log_event(
                "digest_published",
                f"Published digest to {channel}",
                message_id=self._result.message_id,
            )

            # Publish digest to UI activity feed
            await workflow.execute_activity(
                publish_ui_activity,
                args=[
                    "news-digest",                    # source
                    "syndicate_output",                # event_type
                    f"AI News Digest — {digest_type.title()}",  # title
                    result.get("result", "")[:2000],   # content (truncated)
                    "info",                            # severity
                    {                                  # metadata
                        "digest_type": digest_type,
                        "articles_analyzed": len(self._articles),
                        "trends": len(self._trends),
                        "message_id": self._result.message_id,
                    },
                ],
                start_to_close_timeout=timedelta(seconds=10),
            )
```

**Add import** at the top of the workflow file:
```python
from kubani.framework.temporal import publish_ui_activity
```

### 3.3c: Publish Breaking News to UI from Workflow

**File:** `kubani/syndicates/news_digest/workflows/collection.py`

**Location:** Inside `_notify_breaking_news`, after the success check (after line 522):

```python
        if result.get("success"):
            self._log_event(
                "breaking_notification_sent",
                f"Notified {result.get('articles_notified', 0)} breaking articles to #{channel}",
                message_id=result.get("message_id"),
            )

            # Publish breaking news to UI activity feed
            for article in breaking[:3]:  # Limit to top 3
                await workflow.execute_activity(
                    publish_ui_activity,
                    args=[
                        "news-digest",                      # source
                        "alert",                            # event_type
                        f"Breaking: {article.get('title', 'Unknown')[:80]}",  # title
                        (                                   # content
                            f"**{article.get('title', 'Unknown')}**\n\n"
                            f"{article.get('reason', 'Breaking news detected')}\n\n"
                            f"*Urgency: {article.get('urgency', '?')}/10*"
                        ),
                        "warning",                          # severity
                        {                                   # metadata
                            "url": article.get("url"),
                            "urgency": article.get("urgency"),
                            "breaking_count": len(breaking),
                        },
                    ],
                    start_to_close_timeout=timedelta(seconds=10),
                )
```

**Add import** at the top of the workflow file:
```python
from kubani.framework.temporal import publish_ui_activity
```

### Important Notes for 3.3:

- **`result.get("result", "")[:2000]`** — Truncate digest content to 2000 chars. Full digests can be very long. The UI detail panel renders markdown, but we don't want to flood Redis with huge messages.
- **Breaking news publishes per article** (up to 3) — each breaking article gets its own alert card in the feed, making them individually visible and filterable.
- The `start_to_close_timeout=timedelta(seconds=10)` is short because `publish_activity()` just does an `XADD` to Redis — it should be near-instant.
- If the `publish_ui_activity` fails, the workflow continues — the `execute_activity` will raise but we can optionally wrap it in try/except inside the workflow. However, since it's a non-critical enhancement, the retry policy will handle transient Redis failures, and permanent failures will just be logged in the workflow history without blocking the main workflow.

**Actually — wrap the publish calls in try/except** to prevent a Redis failure from failing the workflow:

```python
            # Publish digest to UI activity feed
            try:
                await workflow.execute_activity(
                    publish_ui_activity,
                    args=[...],
                    start_to_close_timeout=timedelta(seconds=10),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
            except Exception:
                pass  # UI publishing is non-critical
```

Use `RetryPolicy(maximum_attempts=1)` to avoid retrying — if Redis is down, don't waste time retrying a non-critical publish.

---

## Summary of All Files Modified in Phase 3

| File | Lines Added | Nature |
|------|------------|--------|
| `kubani/syndicates/learning_system/syndicate.py` | ~50 lines | 3 publish blocks (critic, reflection, synthesis) |
| `kubani/syndicates/k8s_monitor/src/k8s_monitor_syndicate/worker.py` | ~40 lines | 2 publish blocks in event bridge |
| `kubani/framework/temporal/activities.py` | ~25 lines | `publish_ui_activity` wrapper |
| `kubani/framework/temporal/__init__.py` | ~3 lines | Export `publish_ui_activity` |
| `kubani/syndicates/news_digest/workflows/digest.py` | ~20 lines | 1 publish block + import |
| `kubani/syndicates/news_digest/workflows/collection.py` | ~20 lines | 1 publish block + import |
| `kubani/syndicates/news_digest/src/news_digest_syndicate/worker.py` | ~2 lines | Register activity |

## Verification Checklist

- [ ] Learning system: critic evaluation → event in UI
- [ ] Learning system: skill proposal → approval in UI
- [ ] K8s monitor: event bridge → alert in UI
- [ ] K8s monitor: remediation result → event in UI
- [ ] News digest: published digest → output in UI
- [ ] News digest: breaking news → alert in UI
- [ ] All publish calls wrapped in try/except
- [ ] No `publish_activity()` calls from inside Temporal workflows (only from activities)
- [ ] `publish_ui_activity` registered in all syndicate workers that use it
