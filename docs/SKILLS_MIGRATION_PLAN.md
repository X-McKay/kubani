# Skills-First Architecture Migration Plan

This document outlines the complete migration of all agent functionality to the Skills-First architecture.

## Current State

### K8s-Monitor (Partially Migrated)

**Skills-Based (New):**
```
skills/k8s/
├── collection/
│   ├── list-pods-in-namespace/
│   └── list-recent-events/
├── diagnostic/
│   ├── check-node-resources/
│   ├── check-pod-resources/
│   └── investigate-pod-failure/
└── remediation/
    ├── restart-crashloop/
    ├── restart-imagepullbackoff/
    └── scale-deployment/

agents/k8s-monitor/src/k8s_monitor/federated/
├── sentinel.py      # Watches K8s events, triggers skills
├── healer.py        # Executes remediation skills
├── explorer.py      # Learns new skills from observations
└── skills.py        # K8S_SKILLS bootstrap
```

**Legacy (To Deprecate):**
```
agents/k8s-monitor/src/k8s_monitor/
├── swarm.py                    # Old swarm orchestration
├── remediation_workflows.py    # Old Temporal workflows
├── remediation_activities.py   # Old Temporal activities
└── agents/
    ├── cluster_triage.py       # Swarm agent
    ├── cluster_scout.py        # Swarm agent
    ├── cluster_remediator.py   # Swarm agent
    ├── pod_diagnostician.py    # Swarm agent
    ├── discord_notifier.py     # Swarm agent
    └── remediation_memory.py   # Swarm agent
```

### News-Monitor (Not Migrated)

**Current Architecture:**
```
agents/news-monitor/src/news_monitor/
├── worker.py           # Temporal worker
├── workflows.py        # NewsDigestWorkflow, BreakingNewsWorkflow
├── activities.py       # Temporal activities
├── feeds.py            # RSS feed configuration
├── memory.py           # Article deduplication
└── agents/
    ├── collector.py    # RSSCollectorAgent
    ├── analyst.py      # ContentAnalystAgent
    ├── trends.py       # TrendAnalyzerAgent
    ├── composer.py     # DigestComposerAgent
    └── publisher.py    # DiscordPublisherAgent
```

### Core Library

```
agents/core/src/core_agents/
├── skills/
│   ├── unified.py      # UnifiedSkillLibrary
│   ├── local_runner.py # LocalRunner for testing
│   ├── validator.py    # Skill format validation
│   └── schema.py       # Skill schema definitions
├── sop_executor.py     # SOP execution
├── factory.py          # AgentFactory
├── worker.py           # AgentWorker base
└── config.py           # Centralized config
```

---

## Target Architecture

### Principles

1. **Skills are the source of truth** - All operations defined as markdown SKILL.md files
2. **Federated agents execute skills** - Sentinel watches, Healer executes, Explorer learns
3. **Temporal for scheduling only** - Workflows schedule skill execution, not implement logic
4. **Domain separation** - `skills/k8s/` for Kubernetes, `skills/news/` for news monitoring

### Target Structure

```
skills/
├── k8s/                        # Kubernetes operations
│   ├── collection/             # Data gathering
│   ├── diagnostic/             # Investigation
│   └── remediation/            # Fixes
│
└── news/                       # News monitoring operations
    ├── collection/             # RSS/API data collection
    │   ├── fetch-rss-feeds/
    │   └── filter-duplicates/
    ├── diagnostic/             # Analysis
    │   ├── analyze-article/
    │   ├── detect-breaking-news/
    │   └── analyze-trends/
    └── action/                 # Output actions
        ├── compose-digest/
        └── publish-to-discord/

agents/
├── core/                       # Shared library (unchanged)
│
├── k8s-monitor/
│   └── src/k8s_monitor/
│       ├── worker.py           # Temporal worker (simplified)
│       ├── workflows.py        # Scheduling only
│       └── federated/          # Skills-based agents
│           ├── sentinel.py
│           ├── healer.py
│           └── explorer.py
│
└── news-monitor/
    └── src/news_monitor/
        ├── worker.py           # Temporal worker (simplified)
        ├── workflows.py        # Scheduling only
        └── federated/          # NEW: Skills-based agents
            ├── collector.py    # Periodically fetches feeds
            ├── analyst.py      # Processes with skills
            └── publisher.py    # Publishes digests
```

---

## Migration Phases

### Phase 1: Create News-Monitor Skills

**Goal:** Define all news-monitor operations as skills

**New Files:**
```
skills/news/
├── collection/
│   ├── fetch-rss-feeds/
│   │   ├── SKILL.md
│   │   └── test.yaml
│   └── filter-duplicates/
│       ├── SKILL.md
│       └── test.yaml
├── diagnostic/
│   ├── analyze-article/
│   │   ├── SKILL.md
│   │   └── test.yaml
│   ├── detect-breaking-news/
│   │   ├── SKILL.md
│   │   └── test.yaml
│   └── analyze-trends/
│       ├── SKILL.md
│       └── test.yaml
└── action/
    ├── compose-digest/
    │   ├── SKILL.md
    │   └── test.yaml
    └── publish-to-discord/
        ├── SKILL.md
        └── test.yaml
```

**Skill Format Example:**
```yaml
---
name: fetch-rss-feeds
description: Collect articles from configured RSS feeds. Filters by age and AI relevance.
metadata:
  domain: news
  category: collection
  mcp-servers: []  # Uses internal RSS parsing
  requires-approval: false
  confidence: 0.9
input:
  - name: max_age_hours
    type: int
    default: 24
    description: Maximum age of articles to collect
output:
  - name: articles
    type: list[RawArticle]
    description: List of collected articles
---

## Preconditions
- RSS feed URLs are configured in feeds.py
- Network access to feed sources

## Actions

### Step 1: Load Feed Configuration
Load RSS feed URLs from configuration.

### Step 2: Fetch Each Feed
For each configured feed:
1. Make HTTP request to feed URL
2. Parse RSS/Atom XML response
3. Extract article entries

### Step 3: Filter by Age
Remove articles older than `max_age_hours`.

### Step 4: Filter AI Relevance
Keep only articles related to AI/ML topics based on keywords.

## Success Criteria
- At least one feed successfully fetched
- Articles have required fields (title, url, published_date)
```

### Phase 2: Create News-Monitor Federated Agents

**Goal:** Create federated agents that execute news skills

**New Files:**
```
agents/news-monitor/src/news_monitor/federated/
├── __init__.py
├── collector.py     # Scheduled collection using skills
├── analyst.py       # Article analysis using skills
├── publisher.py     # Digest publishing using skills
└── skills.py        # NEWS_SKILLS bootstrap
```

**Architecture:**
```
┌─────────────────────────────────────────────────────────────┐
│                    Temporal Scheduler                        │
│  (ScheduledDigestWorkflow runs every 12 hours)              │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   CollectorAgent                             │
│  Executes: fetch-rss-feeds, filter-duplicates               │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    AnalystAgent                              │
│  Executes: analyze-article, detect-breaking-news,           │
│            analyze-trends                                    │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   PublisherAgent                             │
│  Executes: compose-digest, publish-to-discord               │
└─────────────────────────────────────────────────────────────┘
```

### Phase 3: Simplify News-Monitor Workflows

**Goal:** Workflows only schedule, don't implement logic

**Modify:**
- `agents/news-monitor/src/news_monitor/workflows.py` - Simplified to call federated agents
- `agents/news-monitor/src/news_monitor/worker.py` - Start federated agents

**Delete:**
- `agents/news-monitor/src/news_monitor/activities.py` - Logic moves to skills
- `agents/news-monitor/src/news_monitor/agents/` - Replaced by federated/

### Phase 4: Complete K8s-Monitor Migration

**Goal:** Remove all swarm agents, use skills exclusively

**Keep:**
```
agents/k8s-monitor/src/k8s_monitor/
├── worker.py           # Temporal worker
├── workflows.py        # Health check scheduling
├── memory.py           # Learning system
├── watch.py            # K8s event streaming
├── hooks.py            # Safety hooks
└── federated/          # Skills-based agents
    ├── sentinel.py
    ├── healer.py
    ├── explorer.py
    └── skills.py
```

**Delete:**
```
agents/k8s-monitor/src/k8s_monitor/
├── swarm.py                    # DELETE
├── remediation_workflows.py    # DELETE
├── remediation_activities.py   # DELETE
├── tools.py                    # DELETE (replaced by MCP)
├── mcp_tools.py                # KEEP (MCP client)
├── prompts.py                  # DELETE (in SKILL.md now)
└── agents/                     # DELETE entire directory
    ├── base.py
    ├── cluster_triage.py
    ├── cluster_scout.py
    ├── cluster_remediator.py
    ├── pod_diagnostician.py
    ├── discord_notifier.py
    ├── remediation_memory.py
    ├── context.py              # MOVE to models.py
    └── diagnosis.py
```

### Phase 5: Add More K8s Skills

**Goal:** Cover all operations currently in swarm agents

**New Skills:**
```
skills/k8s/
├── collection/
│   ├── get-cluster-health/         # Overall cluster status
│   ├── get-deployment-status/      # Deployment health
│   └── get-resource-usage/         # Resource metrics
├── diagnostic/
│   ├── diagnose-network-issue/     # Network problems
│   ├── diagnose-storage-issue/     # PVC/storage problems
│   └── check-workflow-health/      # Temporal workflow status
└── remediation/
    ├── cordon-node/                # Mark node unschedulable
    ├── drain-node/                 # Evict pods from node
    └── rollback-deployment/        # Rollback to previous version
```

---

## Testing Strategy

### Unit Tests
- Skill format validation (existing)
- LocalRunner execution with mocks (existing)
- Federated agent logic

### Integration Tests
- Skills execute against real cluster (MCP tools)
- Federated agents process events end-to-end
- Workflows schedule correctly

### Acceptance Tests
- News digest generated and published
- K8s issues detected and remediated
- Breaking news alerts sent

---

## File Changes Summary

### New Files (25+)
- 7 news skills with SKILL.md and test.yaml
- 4 news federated agent files
- 9+ additional k8s skills

### Modified Files (5)
- `agents/news-monitor/src/news_monitor/worker.py`
- `agents/news-monitor/src/news_monitor/workflows.py`
- `agents/k8s-monitor/src/k8s_monitor/worker.py`
- `agents/k8s-monitor/src/k8s_monitor/workflows.py`
- `agents/k8s-monitor/src/k8s_monitor/models.py` (add context types)

### Deleted Files (15+)
- `agents/news-monitor/src/news_monitor/activities.py`
- `agents/news-monitor/src/news_monitor/agents/` (5 files)
- `agents/k8s-monitor/src/k8s_monitor/swarm.py`
- `agents/k8s-monitor/src/k8s_monitor/remediation_workflows.py`
- `agents/k8s-monitor/src/k8s_monitor/remediation_activities.py`
- `agents/k8s-monitor/src/k8s_monitor/tools.py`
- `agents/k8s-monitor/src/k8s_monitor/prompts.py`
- `agents/k8s-monitor/src/k8s_monitor/agents/` (9 files)

---

## Rollout Plan

1. **Week 1:** Phase 1 - Create news skills
2. **Week 2:** Phase 2 - News federated agents
3. **Week 3:** Phase 3 - Simplify news workflows, deprecate old code
4. **Week 4:** Phase 4 - K8s swarm deprecation
5. **Week 5:** Phase 5 - Additional k8s skills

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking news-monitor during migration | High | Feature flag to run old/new in parallel |
| Missing edge cases in skill definitions | Medium | Comprehensive test.yaml scenarios |
| Performance regression | Medium | Benchmark before/after |
| Memory/learning system incompatibility | High | Keep memory.py, adapt interface |

---

## Success Criteria

1. All agents use skills exclusively (no swarm/activity code)
2. 100% test coverage for all skills
3. No regression in functionality
4. Skills are human-readable runbooks
5. New skills can be added without code changes
