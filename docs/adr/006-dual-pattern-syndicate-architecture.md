# ADR-006: Dual-Pattern Syndicate Architecture

## Status
Accepted

## Context

Kubani syndicates orchestrate multiple AI agents to accomplish complex tasks. The existing implementation has several problems:

1. **Not durable**: Syndicates use `asyncio.sleep()` for scheduling with no crash recovery
2. **Not agentic**: 475 lines of imperative orchestration code with hardcoded pipeline steps
3. **No batching**: K8s monitor processes events in isolation, missing correlated issues (5 health check failures that indicate 1 network problem)
4. **Inconsistent**: `skill-auto` uses Temporal workflows beautifully, but syndicates don't
5. **No transparency**: Execution history not visible, debugging is guesswork

We needed to redesign syndicate architecture to be durable, observable, and appropriately agentic.

## Decision

We adopted a **dual-pattern architecture** where syndicates can use either a Workflow pattern or a Swarm pattern, both built on Temporal:

| Pattern | Use Case | Examples |
|---------|----------|----------|
| **Workflow** | Known sequence, deterministic execution | News Collection, News Digest, Skill Auto |
| **Swarm** | Unknown path, emergent behavior | Incident Response, Breaking News, Research |

### Workflow Pattern

A single Temporal workflow orchestrates agents in a defined sequence. Each agent call is a Temporal activity with automatic retries and timeouts. The workflow explicitly controls execution order.

Best for:
- Well-defined sequences (collect → analyze → publish)
- Repeatable, predictable execution
- Easy testing and debugging

### Swarm Pattern

Multiple agent workflows pull tasks from a shared task pool. Agents decide their own handoffs based on capabilities. A separate Request Tracker workflow observes progress without dispatching work.

Best for:
- Unknown root causes (incident investigation)
- Multiple valid approaches (research tasks)
- Agents that need to collaborate and build on each other's work

### Shared Infrastructure

Both patterns share:
- **Temporal** for durability, retries, and observability
- **Memory MCP** for shared context and learnings
- **Event Bus** for external triggers (K8s events, Discord commands)
- **Agent implementations** (same agents, different orchestration)

### Key Design Decisions

**Pull-based Swarm with Request Tracker**: Swarms use a pull-based task pool where agents lease tasks based on capabilities. A separate Request Tracker workflow provides observability without introducing a central dispatcher bottleneck.

**News Syndicate Split**: The news syndicate is split into two workflows:
- `NewsCollectionWorkflow` - Continuous ambient collection (every 15 min), stores to Memory MCP
- `NewsDigestWorkflow` - Scheduled composition (2x/day), queries from Memory MCP

This enables breaking news detection (requires continuous collection), cross-day deduplication, and richer trend analysis.

**Agents as Temporal Activities**: Agent execution is wrapped as Temporal activities. This provides automatic retries, timeouts, and clean separation between orchestration (workflows) and work (activities).

## Consequences

### Positive

**Durability**: All syndicate execution survives crashes, restarts, and network partitions. Temporal handles state persistence automatically.

**Observability**: Full execution history visible in Temporal UI. No custom tooling needed to understand what happened.

**Right tool for the job**: Deterministic tasks use the simpler Workflow pattern. Exploratory tasks use the more powerful Swarm pattern.

**Testability**: Workflow pattern is deterministic and easy to unit test. Swarm pattern can be tested with mocked task pools.

**Event batching**: K8s monitor can accumulate events via Temporal signals and classify them as a batch, identifying root causes instead of treating each failure in isolation.

**Consistency**: All syndicates now use Temporal, matching the existing `skill-auto` implementation.

### Negative

**Learning curve**: Developers need to understand Temporal concepts (workflows, activities, signals, queries).

**Infrastructure dependency**: Temporal server must be healthy for syndicates to function.

**Pattern selection**: Teams must decide which pattern to use for new syndicates. The decision guide helps, but there's judgment involved.

### Risks

**Over-engineering**: Risk of using Swarm pattern when Workflow would suffice. Mitigation: Default to Workflow; only use Swarm when paths are truly unknown.

**Swarm complexity**: Pull-based coordination requires safety mechanisms (depth limits, ping-pong detection). Mitigation: Built into the SwarmAgentWorkflow base class.

## Alternatives Considered

### Pure Event-Driven (Current Approach)
Rejected because: No durability, no observability, `asyncio.sleep()` scheduling is fragile.

### Single Pattern (Swarm Only)
Rejected because: Swarm overhead is unnecessary for deterministic tasks like news digests. Forcing emergence on known sequences adds complexity without benefit.

### Single Pattern (Workflow Only)
Rejected because: Some tasks genuinely benefit from emergent behavior. Incident response with unknown root cause shouldn't have a hardcoded sequence.

### External Task Queue (Celery, RabbitMQ)
Rejected because: Would introduce another infrastructure component. Temporal already provides task queueing, retries, and visibility.

## References

- [Temporal Multi-Agent Architectures](https://temporal.io/blog/using-multi-agent-architectures-with-temporal)
- [Orchestrating Ambient Agents with Temporal](https://temporal.io/blog/orchestrating-ambient-agents-with-temporal)
- [Strands Agents Multi-Agent Patterns](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/multi-agent-patterns/)
- [A2A Protocol](https://a2a-protocol.org/latest/)
- [Implementation Plan](../plans/active/2026-01-27-syndicate-architecture-redesign.md) - Detailed implementation phases and code examples
