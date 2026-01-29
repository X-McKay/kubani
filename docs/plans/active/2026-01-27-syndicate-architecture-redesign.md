# Syndicate Architecture Redesign: Dual-Pattern Temporal Architecture

**Status:** Active
**Created:** 2026-01-27
**Author:** Claude + Al

## TL;DR

Two standard patterns for syndicates, both built on Temporal:

| Pattern | Use Case | Example |
|---------|----------|---------|
| **Workflow** | Known sequence, deterministic | News Digest, Skill Auto |
| **Swarm** | Unknown path, emergent behavior | Incident Response, Research |

Both share: Temporal durability, Memory MCP, Event Bus triggers, same agent implementations.

## Problem Statement

The current syndicate implementation has significant issues:

1. **Not agentic**: 475 lines of imperative orchestration code in `news_digest/syndicate.py` with hardcoded pipeline steps
2. **Not durable**: Uses `asyncio.sleep()` for scheduling, no crash recovery
3. **No batching**: K8s monitor processes events in isolation, missing "forest for trees" (5 health check failures = 1 connectivity issue)
4. **Inconsistent**: `skill-auto` uses Temporal beautifully, syndicates don't
5. **No transparency**: Execution history not visible, debugging is guesswork

## Design Goals

1. **Durable execution**: Survive crashes, restarts, network partitions
2. **Agentic autonomy**: Agents decide handoffs, not hardcoded pipelines
3. **Event batching**: Correlate related events before acting
4. **Self-improving**: Judge agents can refine behavior over time
5. **Observable**: Full execution history in Temporal UI
6. **Simple code**: Less imperative orchestration, more declarative agent definitions

## Two Patterns: Swarm and Workflow

Not every task benefits from emergent behavior. We propose **two standard patterns** that share infrastructure but differ in orchestration style:

### Pattern Selection Guide

| Pattern | Use When | Examples |
|---------|----------|----------|
| **Swarm** | Path is unknown, agents should explore and decide | Incident response, debugging, research |
| **Workflow** | Sequence is known, steps are deterministic | Scheduled digests, skill evaluation, deployments |

### Comparison

| Aspect | Swarm | Workflow |
|--------|-------|----------|
| **Task routing** | Pull-based (agents choose) | Push-based (workflow assigns) |
| **Execution order** | Emergent | Deterministic |
| **Agent handoffs** | Agent decides capability + target | Workflow decides next step |
| **Best for** | Unknown paths, exploration | Known pipelines, repeatability |
| **Complexity** | Higher (needs safety mechanisms) | Lower (explicit control flow) |
| **Testability** | Harder (emergent paths) | Easier (deterministic) |

### When to Use Each

**Use Swarm when:**
- Root cause is unknown (incident investigation)
- Multiple valid approaches exist (research tasks)
- Agents need to collaborate and build on each other's work
- The "right" sequence can't be known ahead of time

**Use Workflow when:**
- Steps are well-defined (collect → analyze → publish)
- Order matters (can't publish before collecting)
- You want predictable, repeatable execution
- Testing and debugging need determinism

### Existing Syndicate Mapping

| Syndicate/Task | Recommended Pattern | Reasoning |
|---------------|---------------------|-----------|
| K8s Incident Response | **Swarm** | Unknown root cause, agents explore |
| K8s Scheduled Health Check | **Workflow** | Defined check sequence |
| News Collection (continuous) | **Workflow** | Collect → Analyze → Store is deterministic |
| News Digest (scheduled) | **Workflow** | Query → Compose → Publish is deterministic |
| Breaking News Detection | **Swarm** | Dynamic urgency assessment |
| Skill Auto | **Workflow** | Create → Eval → Improve loop |
| Agent Auto | **Workflow** | Similar defined iteration |

---

## Swarm Pattern: Pull-Based Multi-Agent

### Core Concept

Combine the durability and observability of Temporal with the emergent, self-organizing behavior of A2A swarms:

```
┌────────────────────────────────────────────────────────────────────┐
│                    Event Bus (Redis Streams)                        │
│                    (External triggers + inter-workflow signals)     │
└─────────┬────────────────────────────────────────┬─────────────────┘
          │                                        │
          │ K8S_ISSUE_DETECTED                     │ NEWS_COLLECTION_REQUESTED
          ▼                                        ▼
┌───────────────────────────────────────────────────────────────────┐
│                      Shared Task Pool (Postgres/Redis)             │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ SwarmTask { task_id, swarm_id, capability, message, status } │  │
│  └─────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
          │                                        │
          │ lease_next_task()                      │ lease_next_task()
          ▼                                        ▼
┌───────────────────────┐              ┌───────────────────────┐
│ K8s Agent Workflows   │              │ News Agent Workflows  │
│ (Temporal, pull-based)│              │ (Temporal, pull-based)│
│                       │              │                       │
│  - Classifier         │              │  - FeedCollector      │
│  - Remediator         │              │  - ContentAnalyst     │
│  - SkillLearner       │              │  - Publisher          │
└───────────┬───────────┘              └───────────┬───────────┘
            │                                      │
            │  record_event() / set_lease()        │
            ▼                                      ▼
┌───────────────────────────────────────────────────────────────────┐
│              Request Tracker Workflow (per swarm/mission)          │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ SwarmStatus { total, done, open, leases, events, phase }    │  │
│  │ @query get_status() → UI/CLI can poll for progress          │  │
│  └─────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
            │                                      │
            │ append_shared_knowledge()            │
            ▼                                      ▼
┌───────────────────────────────────────────────────────────────────┐
│              Shared Memory (Memory MCP Server)                     │
│  - Swarm context (goal, history, knowledge)                       │
│  - Agent learnings (Qdrant)                                       │
│  - Relationships (Neo4j)                                          │
└───────────────────────────────────────────────────────────────────┘
```

### Key Components

#### 1. Shared Task Pool

A durable task queue where agents pull work (instead of being assigned):

```python
@dataclass
class SwarmTask:
    task_id: str
    swarm_id: str                        # Groups related tasks
    requested_capability: str            # "classify", "remediate", "collect", "analyze"
    target_agent: str | None             # Direct handoff target (optional)
    message: str                         # Handoff instruction
    context: dict[str, Any]              # Task-specific payload
    status: str                          # "open" | "leased" | "done" | "failed"
    parent_task_id: str | None           # For tracking handoff chains
    leased_by: str | None
    lease_expires_at: datetime | None
```

**Why pull-based instead of push?**
- Agents self-organize based on capabilities
- No central dispatcher bottleneck
- Natural load balancing
- Agents can be added/removed without changing orchestration

#### 2. Agent Workflows (Temporal)

Each agent runs as a long-lived Temporal workflow that pulls tasks:

```python
@workflow.defn
class ClassifierAgentWorkflow:
    def __init__(self):
        self._pending_events: list[K8sEvent] = []
        self._batch_timeout = timedelta(seconds=30)

    @workflow.signal
    def new_event(self, event: K8sEvent):
        """Receive events from event bus listener."""
        self._pending_events.append(event)

    @workflow.run
    async def run(self, swarm_id: str, agent_id: str):
        while True:
            # Pull next task from pool
            task = await workflow.execute_activity(
                lease_next_task,
                args=[swarm_id, agent_id, ["classify", "batch_classify"]],
                start_to_close_timeout=timedelta(seconds=30),
            )

            if task is None:
                # No task available - check for batched events
                if self._pending_events:
                    await self._process_batch()
                else:
                    await workflow.sleep(1.0)
                continue

            # Execute the task
            output = await workflow.execute_activity(
                run_agent_step,
                args=[task],
                start_to_close_timeout=timedelta(minutes=5),
            )

            # Share knowledge with swarm
            if output.get("shared_knowledge"):
                await workflow.execute_activity(
                    append_shared_knowledge,
                    args=[swarm_id, agent_id, output["shared_knowledge"]],
                    start_to_close_timeout=timedelta(seconds=30),
                )

            # Agent decides on handoff (agentic!)
            if handoff := output.get("handoff"):
                await workflow.execute_activity(
                    create_handoff_task,
                    args=[
                        swarm_id,
                        handoff["capability"],
                        handoff["message"],
                        handoff.get("context", {}),
                        handoff.get("target_agent"),
                        task.task_id,  # parent for chain tracking
                    ],
                    start_to_close_timeout=timedelta(seconds=30),
                )

            # Complete task
            await workflow.execute_activity(
                complete_task,
                args=[task.task_id, output.get("artifact_ref", {})],
                start_to_close_timeout=timedelta(seconds=30),
            )

    async def _process_batch(self):
        """Batch-process accumulated events (forest, not trees)."""
        events = self._pending_events.copy()
        self._pending_events.clear()

        # Classify as a batch - find root causes, not symptoms
        batch_result = await workflow.execute_activity(
            classify_event_batch,
            args=[events],
            start_to_close_timeout=timedelta(minutes=2),
        )

        # Create tasks for identified issues (deduplicated)
        for issue in batch_result.root_causes:
            await workflow.execute_activity(
                create_handoff_task,
                args=[
                    self._swarm_id,
                    "remediate",
                    f"Root cause identified: {issue.description}",
                    {"events": [e.to_dict() for e in issue.related_events]},
                    None,  # Let any remediator pick it up
                    None,
                ],
                start_to_close_timeout=timedelta(seconds=30),
            )
```

**Key features:**
- **Batching via signals**: Events accumulate via Temporal signals, processed together
- **Pull-based work**: Agent pulls from task pool when ready
- **Agentic handoffs**: Agent decides `handoff["capability"]` and `handoff["message"]`
- **Shared knowledge**: Learnings flow to Memory MCP server

#### 3. Swarm Context (Memory MCP Integration)

Use existing Memory MCP server for shared swarm context:

```python
# Activities that interact with Memory MCP

async def get_swarm_context(swarm_id: str) -> SwarmContext:
    """Get the full swarm context from memory."""
    memory = get_mcp_client().memory

    # Get cached swarm state
    cached = await memory.cache_get(f"swarm:{swarm_id}:context")
    if cached["found"]:
        return SwarmContext.from_dict(cached["value"])

    # Build from learnings and knowledge
    learnings = await memory.query_learnings(
        query=f"swarm:{swarm_id}",
        limit=50,
    )

    return SwarmContext(
        swarm_id=swarm_id,
        goal="",
        shared_knowledge=[l.content for l in learnings.learnings],
        history=[],
    )

async def append_shared_knowledge(
    swarm_id: str,
    agent_name: str,
    knowledge: dict,
) -> None:
    """Add knowledge to swarm context."""
    memory = get_mcp_client().memory

    await memory.store_learning(
        agent_id=agent_name,
        learning_type="swarm_contribution",
        content=json.dumps(knowledge),
        context={"swarm_id": swarm_id},
        tags=[f"swarm:{swarm_id}"],
    )
```

#### 4. Request Tracker Workflow (Observability)

A dedicated workflow per request/mission that tracks status without assigning work. This is the key to observability in a pull-based swarm:

```python
from temporalio import workflow
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class AgentLease:
    agent_id: str
    task_id: str
    capability: str
    started_at: datetime

@dataclass
class SwarmStatus:
    swarm_id: str
    goal: str
    started_at: datetime
    total_tasks: int = 0
    completed_tasks: int = 0
    open_tasks: int = 0
    leased_tasks: int = 0
    failed_tasks: int = 0
    current_leases: dict[str, AgentLease] = field(default_factory=dict)
    recent_events: list[str] = field(default_factory=list)  # Last N events
    current_phase: str = "initializing"

@workflow.defn
class RequestTrackerWorkflow:
    """
    Tracks swarm status without dispatching work.

    Agents emit progress events here; UI/CLI queries for status.
    One tracker per user request or mission.
    """

    def __init__(self):
        self._status: SwarmStatus | None = None

    @workflow.run
    async def run(self, swarm_id: str, goal: str) -> SwarmStatus:
        """Run until swarm completes or times out."""
        self._status = SwarmStatus(
            swarm_id=swarm_id,
            goal=goal,
            started_at=datetime.utcnow(),
        )

        # Wait until all tasks complete (or timeout)
        await workflow.wait_condition(
            lambda: self._is_complete(),
            timeout=timedelta(hours=24),
        )

        return self._status

    def _is_complete(self) -> bool:
        """Check if swarm has finished all work."""
        return (
            self._status.total_tasks > 0
            and self._status.open_tasks == 0
            and self._status.leased_tasks == 0
        )

    @workflow.query
    def get_status(self) -> SwarmStatus:
        """Query current swarm status (for UI/CLI)."""
        return self._status

    @workflow.update
    def record_event(
        self,
        kind: str,
        message: str,
        totals: dict[str, int] | None = None,
        phase: str | None = None,
    ) -> None:
        """Record a progress event from an agent."""
        timestamp = datetime.utcnow().isoformat()
        self._status.recent_events.append(f"[{timestamp}] {kind}: {message}")
        self._status.recent_events = self._status.recent_events[-50:]  # Keep last 50

        if totals:
            self._status.total_tasks = totals.get("total", self._status.total_tasks)
            self._status.completed_tasks = totals.get("done", self._status.completed_tasks)
            self._status.open_tasks = totals.get("open", self._status.open_tasks)
            self._status.leased_tasks = totals.get("leased", self._status.leased_tasks)
            self._status.failed_tasks = totals.get("failed", self._status.failed_tasks)

        if phase:
            self._status.current_phase = phase

    @workflow.update
    def set_lease(self, task_id: str, agent_id: str, capability: str) -> None:
        """Record that an agent has leased a task."""
        self._status.current_leases[task_id] = AgentLease(
            agent_id=agent_id,
            task_id=task_id,
            capability=capability,
            started_at=datetime.utcnow(),
        )

    @workflow.update
    def clear_lease(self, task_id: str, success: bool = True) -> None:
        """Record that a task lease has ended."""
        self._status.current_leases.pop(task_id, None)
        if success:
            self._status.completed_tasks += 1
        else:
            self._status.failed_tasks += 1
```

**How agents use the tracker:**

```python
# In agent workflow, after leasing a task:
tracker = workflow.get_external_workflow_handle(f"tracker-{swarm_id}")

# Report lease
await tracker.execute_update(
    RequestTrackerWorkflow.set_lease,
    args=[task.task_id, agent_id, task.capability],
)

# ... do work ...

# Report completion
await tracker.execute_update(
    RequestTrackerWorkflow.clear_lease,
    args=[task.task_id, True],
)

# Report progress event
await tracker.execute_update(
    RequestTrackerWorkflow.record_event,
    args=["task_complete", f"Classified 5 events into 2 root causes"],
)
```

**Benefits:**
- Single request ID to query "where are we at?"
- Real-time status without polling the task pool
- Visible in Temporal UI
- No central dispatcher—tracker only observes, doesn't assign

#### 5. Event Bus Bridge

A lightweight Temporal workflow that bridges Redis events to swarm tasks:

```python
@workflow.defn
class EventBusBridgeWorkflow:
    """Converts event bus events to swarm tasks."""

    @workflow.run
    async def run(self, config: BridgeConfig):
        while True:
            # Listen for events (via activity)
            events = await workflow.execute_activity(
                poll_event_bus,
                args=[config.event_types, config.batch_size],
                start_to_close_timeout=timedelta(seconds=30),
            )

            for event in events:
                # Map event type to swarm + capability
                mapping = config.event_mappings.get(event.type.value)
                if not mapping:
                    continue

                # Create or get swarm for this event group
                swarm_id = await workflow.execute_activity(
                    get_or_create_swarm,
                    args=[mapping.swarm_name, event.correlation_id],
                    start_to_close_timeout=timedelta(seconds=30),
                )

                # Start tracker workflow for this swarm (if not already running)
                await workflow.execute_activity(
                    ensure_tracker_running,
                    args=[swarm_id, mapping.goal_template.format(event=event)],
                    start_to_close_timeout=timedelta(seconds=30),
                )

                # Create initial task
                await workflow.execute_activity(
                    create_task,
                    args=[
                        swarm_id,
                        mapping.initial_capability,
                        f"Handle {event.type.value}",
                        event.payload,
                    ],
                    start_to_close_timeout=timedelta(seconds=30),
                )
```

#### 6. Judge Agent (Self-Improvement)

Following the ambient agents pattern, a judge agent reviews executions:

```python
@workflow.defn
class JudgeAgentWorkflow:
    """Reviews swarm executions and improves agent behavior."""

    @workflow.run
    async def run(self, swarm_id: str):
        while True:
            # Run periodically
            await workflow.sleep(timedelta(hours=1))

            # Get recent executions
            executions = await workflow.execute_activity(
                get_recent_swarm_executions,
                args=[swarm_id, 50],
                start_to_close_timeout=timedelta(minutes=1),
            )

            # Evaluate quality
            evaluation = await workflow.execute_activity(
                evaluate_execution_quality,
                args=[executions],
                start_to_close_timeout=timedelta(minutes=5),
            )

            # If improvements identified, signal agents with updated prompts
            for agent_id, improvement in evaluation.improvements.items():
                agent_handle = workflow.get_external_workflow_handle(
                    f"{swarm_id}-{agent_id}"
                )
                await agent_handle.signal("update_system_prompt", improvement.new_prompt)

            # Store evaluation as learning
            await workflow.execute_activity(
                store_evaluation_learning,
                args=[swarm_id, evaluation],
                start_to_close_timeout=timedelta(seconds=30),
            )
```

### Safety Mechanisms

Following the Strands recommendations:

```python
@dataclass
class SwarmConfig:
    max_handoffs_per_task: int = 10       # Prevent infinite handoff loops
    max_task_depth: int = 5               # Limit chain depth
    repetitive_handoff_window: int = 3    # Detect A->B->A->B patterns
    lease_ttl_seconds: int = 300          # Task lease timeout
    max_concurrent_tasks: int = 50        # Per swarm limit
```

```python
async def create_handoff_task(..., parent_task_id: str | None) -> str:
    """Create a handoff task with safety checks."""

    # Check chain depth
    if parent_task_id:
        depth = await get_task_chain_depth(parent_task_id)
        if depth >= config.max_task_depth:
            raise HandoffDepthExceeded(f"Max depth {config.max_task_depth} reached")

    # Check for repetitive handoffs
    if parent_task_id:
        recent = await get_recent_handoffs(parent_task_id, config.repetitive_handoff_window)
        if detect_ping_pong(recent, requested_capability):
            raise RepetitiveHandoffDetected("Ping-pong handoff pattern detected")

    # Create the task
    return await _create_task(...)
```

---

## Workflow Pattern: Deterministic Multi-Agent

For tasks with known sequences, we use a simpler pattern that still benefits from Temporal's durability.

### Core Concept

A single Temporal workflow orchestrates agents in a defined sequence, with each agent call as an activity:

```
┌───────────────────────────────────────────────────────────────────┐
│                    Workflow Orchestrator                           │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  @workflow.run                                               │  │
│  │  async def run(self, input):                                │  │
│  │      articles = await activity(collect_feeds, ...)          │  │
│  │      analysis = await activity(analyze_content, articles)   │  │
│  │      await activity(publish_digest, analysis)               │  │
│  └─────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
          │                    │                    │
          ▼                    ▼                    ▼
    ┌───────────┐        ┌───────────┐        ┌───────────┐
    │ Collector │        │ Analyst   │        │ Publisher │
    │ Activity  │        │ Activity  │        │ Activity  │
    └───────────┘        └───────────┘        └───────────┘
```

### Key Differences from Swarm

| Aspect | Swarm | Workflow |
|--------|-------|----------|
| Orchestration | Agents pull tasks | Workflow pushes to agents |
| Handoffs | Agent decides | Workflow decides |
| Task pool | Shared, pull-based | None (direct activity calls) |
| Tracker | Separate workflow | Built into orchestrator |

### Example: News Syndicate (Split into Collection + Digest)

The news syndicate is split into two separate workflows:

1. **NewsCollectionWorkflow** - Continuous ambient collection (every 15-30 min)
2. **NewsDigestWorkflow** - Scheduled digest composition (2x/day)

This separation enables:
- Breaking news detection (requires continuous collection)
- Cross-day deduplication
- Richer trend analysis from accumulated data
- Memory MCP as the integration point

```
┌─────────────────────────────────────────────────────────────────────┐
│                    NewsCollectionWorkflow                            │
│                    (Temporal Schedule: every 15 min)                 │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Collect feeds → Analyze → Store to Memory MCP                │  │
│  │  Collect arXiv → Analyze → Store to Memory MCP                │  │
│  │  Collect GitHub → Analyze → Store to Memory MCP               │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ store_article(), store_learning()
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Memory MCP (Shared State)                         │
│  - Articles (Qdrant): deduped, analyzed, scored                     │
│  - Trends (Redis): entity counts, velocity tracking                 │
│  - Knowledge (Neo4j): topic relationships                           │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ query_articles(), get_entity_counts()
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    NewsDigestWorkflow                                │
│                    (Temporal Schedule: 7am, 3pm)                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Query recent articles → Compose digest → Publish to Discord  │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

**NewsCollectionWorkflow** (ambient, continuous):

```python
@workflow.defn
class NewsCollectionWorkflow:
    """
    Continuous news collection and analysis.

    Runs every 15 minutes, stores to Memory MCP.
    """

    @workflow.run
    async def run(self, config: CollectionConfig) -> CollectionResult:
        # Parallel collection from all sources
        articles, papers, repos = await asyncio.gather(
            workflow.execute_activity(collect_feeds, ...),
            workflow.execute_activity(collect_arxiv_papers, ...),
            workflow.execute_activity(collect_github_trending, ...),
        )

        # Dedupe against Memory MCP (already stored)
        new_articles = await workflow.execute_activity(
            dedupe_against_memory,
            args=[articles],
            ...
        )

        if not new_articles and not papers:
            return CollectionResult(new_items=0)

        # Analyze new content
        analyzed = await workflow.execute_activity(
            analyze_and_score,
            args=[new_articles, papers, repos],
            ...
        )

        # Store to Memory MCP
        stored = await workflow.execute_activity(
            store_to_memory,
            args=[analyzed],
            ...
        )

        # Check for breaking news (high importance + recency)
        breaking = [a for a in analyzed.articles if a.importance >= 9]
        if breaking:
            # Emit event for breaking news swarm
            await workflow.execute_activity(
                emit_breaking_news_event,
                args=[breaking],
                ...
            )

        return CollectionResult(new_items=stored.count)
```

**NewsDigestWorkflow** (scheduled, 2x/day):

```python
@workflow.defn
class NewsDigestWorkflow:
    """
    Scheduled digest composition from stored articles.

    Runs at 7am and 3pm, queries Memory MCP for content.
    """

    @workflow.run
    async def run(self, config: DigestConfig) -> DigestResult:
        # Query articles from last digest window
        articles = await workflow.execute_activity(
            query_articles_from_memory,
            args=[config.lookback_hours, config.min_importance],
            ...
        )

        if not articles:
            return DigestResult(success=False, reason="No articles in window")

        # Get trend data
        trends = await workflow.execute_activity(
            get_trends_from_memory,
            args=[config.lookback_hours],
            ...
        )

        # Compose digest (LLM-powered)
        digest = await workflow.execute_activity(
            compose_executive_digest,
            args=[articles, trends],
            ...
        )

        # Publish to Discord
        result = await workflow.execute_activity(
            publish_digest,
            args=[digest, config.channel_id],
            ...
        )

        return result
```

### Benefits of Workflow Pattern

1. **Predictable**: Same input → same execution path
2. **Testable**: Easy to unit test with mocked activities
3. **Debuggable**: Clear stack trace, no emergent paths
4. **Simpler**: No task pool, no lease management, no safety mechanisms
5. **Efficient**: Direct activity calls, no polling overhead

### When Workflow Can Use Swarm Elements

The patterns aren't mutually exclusive. A workflow can:

1. **Spawn a swarm for exploration**: When the workflow hits an uncertain phase
   ```python
   if analysis.needs_deep_research:
       # Spawn a swarm for exploratory research
       swarm_id = await spawn_research_swarm(analysis.topics)
       await wait_for_swarm_completion(swarm_id)
   ```

2. **Use agents-as-tools**: Call agents as activities but let them reason
   ```python
   # Agent activity with reasoning
   result = await workflow.execute_activity(
       run_agent_with_reasoning,
       args=[analyst_agent, "Analyze these articles for trends", articles],
       ...
   )
   ```

3. **Fan out with parallel activities**: When order doesn't matter
   ```python
   # Parallel agent execution (still deterministic)
   results = await asyncio.gather(*[
       workflow.execute_activity(analyze_article, article)
       for article in articles
   ])
   ```

### Shared Infrastructure

Both patterns share:

- **Temporal** for durability and observability
- **Memory MCP** for shared context and learnings
- **Event Bus** for external triggers
- **Agent implementations** (same agents, different orchestration)

The difference is *how* agents are coordinated, not *what* they do.

---

### Comparison: Before vs After

#### K8s Monitor

**Before (current):**
```python
# syndicate.py - 223 lines of imperative orchestration
async def _watch_and_classify(self, classifier, remediator):
    async for event in self._event_bus.subscribe(...):
        # Process each event in isolation
        classification = await classifier.classify_event(k8s_event)
        if classification.is_actionable:
            await remediator.handle_issue(issue_context)
```

**After (swarm):**
```python
# Classifier workflow - pulls tasks, batches events, decides handoffs
@workflow.defn
class ClassifierAgentWorkflow:
    @workflow.signal
    def new_event(self, event):
        self._pending_events.append(event)

    async def _process_batch(self):
        # See the forest: 5 health failures = 1 network issue
        root_causes = classify_batch(self._pending_events)
        for cause in root_causes:
            # Agent decides to hand off
            create_handoff_task(capability="remediate", ...)
```

**Benefits:**
- Events batched before classification
- Root cause identification, not symptom-by-symptom
- Durable execution (survives crashes)
- Observable in Temporal UI

#### News Digest

**Before (current):**
```python
# syndicate.py - 475 lines of hardcoded pipeline
async def _run_executive_digest_pipeline(self, ...):
    articles = await feed_collector.collect_as_dicts()
    papers = await research_collector.fetch_arxiv_papers()
    news_result = await content_analyst.full_analysis(articles)
    # ... 200 more lines of hardcoded orchestration
    await publisher.compose_and_publish_executive(...)
```

**After (workflow pattern - recommended for scheduled digests):**
```python
# Clean, deterministic workflow
@workflow.defn
class NewsDigestWorkflow:
    @workflow.run
    async def run(self, config: DigestConfig) -> DigestResult:
        # Parallel collection
        articles, papers, repos = await asyncio.gather(
            workflow.execute_activity(collect_feeds, ...),
            workflow.execute_activity(collect_arxiv_papers, ...),
            workflow.execute_activity(collect_github_trending, ...),
        )

        # Sequential analysis and publish
        analysis = await workflow.execute_activity(analyze_content, articles, papers, repos)
        return await workflow.execute_activity(publish_digest, analysis)
```

**Benefits:**
- ~30 lines instead of 475
- Clear, testable sequence
- Parallel collection, sequential analysis
- Scheduling via Temporal schedules, not `asyncio.sleep()`
- Full execution history in Temporal UI

### Implementation Phases

#### Phase 1: Shared Foundation ✅ COMPLETE
- [x] Create base agent activity wrapper (agents callable as Temporal activities)
  - `kubani/framework/temporal/activities.py` - run_agent_activity, classify_event_activity, remediate_issue_activity
- [x] Implement common observability (status queries, event logging)
  - `kubani/framework/temporal/workflows.py` - ObservableWorkflowMixin with _set_status, _log_event, _wait_if_paused
- [x] Set up Temporal schedules infrastructure
  - `kubani/framework/temporal/schedules.py` - ScheduleConfig, create_schedule, EVERY_15_MINUTES, etc.
- [x] Create shared Memory MCP integration utilities
  - `kubani/framework/temporal/memory.py` - store_learning_activity, query_articles_activity, etc.

#### Phase 2: Workflow Pattern - News Syndicate ✅ COMPLETE
- [x] Create `BaseWorkflow` class with status tracking and signals
  - ObservableWorkflowMixin provides WorkflowStatus, queries, and pause/resume/cancel signals
- [x] Implement `NewsCollectionWorkflow` (continuous, every 15 min)
  - `kubani/syndicates/news_digest/workflows/collection.py`
- [x] Implement `NewsDigestWorkflow` (scheduled, 2x/day)
  - `kubani/syndicates/news_digest/workflows/digest.py`
- [x] Add Temporal schedules for both workflows
  - Worker supports setup_schedules(), teardown_schedules(), list_schedules()
- [x] Implement breaking news event emission (triggers notification)
  - Collection workflow checks for breaking news and notifies
- [x] Unit tests added
  - `tests/workflows/syndicates/test_news_workflows.py`

#### Phase 3: K8s Monitor - Dual Pattern ✅ COMPLETE
- [x] Implement `K8sRemediationWorkflow` (Workflow pattern for simple issues)
  - `kubani/syndicates/k8s_monitor/workflows/remediation.py`
  - Deterministic: Classify → Match Skills → Remediate → Verify → Learn
- [x] Implement `K8sInvestigationSwarm` (Swarm pattern for complex issues)
  - `kubani/syndicates/k8s_monitor/workflows/investigation.py`
  - Multi-agent: Diagnostics, RootCause, Impact, Recommendation
  - Shared context via Memory MCP (SwarmContext)
- [x] Create event bridge for routing
  - Worker includes _is_complex_issue() for workflow selection
- [x] Add complexity detection logic
  - Critical severity, NodeNotReady, cascading failures → Swarm
  - Simple issues (OOMKilled, CrashLoop) → Workflow
- [x] Unit tests added
  - `tests/workflows/syndicates/test_k8s_workflows.py`

#### Phase 4: Event Bus Bridge ✅ COMPLETE
- [x] Create `EventBridge` class for connecting event bus to Temporal
  - `kubani/framework/temporal/bridge.py`
- [x] Implement `WorkflowTrigger` configuration
  - Maps event types to workflows with conditions and input mappers
- [x] Create pre-built trigger factories
  - `create_k8s_triggers()`, `create_news_triggers()`
- [x] Implement `WorkflowResultPublisher` for bidirectional integration
- [x] Unit tests added
  - `tests/workflows/syndicates/test_event_bridge.py`

#### Phase 5: Testing & Validation ✅ COMPLETE
- [x] All 48 unit tests pass
- [x] Workflow definitions compile correctly
- [x] Input/output dataclass structures validated
- [x] Query and signal handlers verified
- [x] Activity registration confirmed

#### Phase 6: Documentation & Migration (Remaining)
- [ ] Document "Workflow vs Swarm" decision guide
- [ ] Create syndicate template for each pattern
- [ ] Add examples to CLAUDE.md
- [ ] Update kubani CLI for new patterns
- [ ] Integration tests with running Temporal

### Open Questions

1. **Task pool backend**: Redis (simpler, already have) vs Postgres (richer queries)?
2. **Swarm lifetime**: One swarm per syndicate, or one per "mission" (e.g., per digest cycle)?
3. **Agent discovery**: Static config or A2A-style AgentCards for capability discovery?
4. **Confidence thresholds**: What confidence scores trigger human-in-the-loop?

### References

- [Temporal Multi-Agent Architectures](https://temporal.io/blog/using-multi-agent-architectures-with-temporal)
- [Orchestrating Ambient Agents](https://temporal.io/blog/orchestrating-ambient-agents-with-temporal)
- [Strands Agents Swarm Pattern](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/multi-agent-patterns/)
- [Strands Agents as Tools](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/agents-as-tools/)
- [A2A Protocol](https://a2a-protocol.org/latest/)
- [Temporal AI Cookbook](https://docs.temporal.io/ai-cookbook)
- Existing Kubani `skill-auto` workflow as reference implementation

---

## Related Documents

- **Architecture Decision Record**: [ADR-006: Dual-Pattern Syndicate Architecture](../adr/006-dual-pattern-syndicate-architecture.md) - Documents the thought process and rationale behind key architectural decisions
