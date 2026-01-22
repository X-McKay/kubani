# Cluster Monitor - Orchestrator-Worker Architecture

> **⚠️ DEPRECATED**: This agent has been consolidated into [k8s-monitor](../k8s-monitor/README.md) (v0.4.0+).
> The patterns and capabilities have been preserved in the unified Kubernetes monitoring agent.

## Migration Notes

The cluster-monitor patterns have been preserved in k8s-monitor:
- **8-stage investigation pipeline** → `RemediationOrchestrationWorkflow` (Temporal workflow)
- **Event correlation (30s window)** → `EventCorrelator` in Sentinel
- **Orchestrator state machine** → Temporal workflow state with signals/queries
- **Worker delegation** → Temporal activities with MCP tools

For new deployments, use k8s-monitor instead.

---

**Status:** ~~Experimental (v0.1.0)~~ DEPRECATED - See k8s-monitor v0.4.0+

Intelligent Kubernetes cluster monitoring using an Orchestrator-Worker architecture for structured, predictable investigations.

## Architecture Overview

The Cluster Monitor uses a **structured delegation model** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                     Event Bus (Redis)                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │   Correlator     │  Groups related events
                    │    Service       │  (30s time window)
                    └──────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  Orchestrator    │  Manages investigation
                    │     Agent        │  workflow & state
                    └──────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
    │ Investigator│  │   Memory    │  │ Remediator  │
    │   Worker    │  │   Worker    │  │   Worker    │
    └─────────────┘  └─────────────┘  └─────────────┘
              │               │               │
              └───────────────┼───────────────┘
                              ▼
                    ┌──────────────────┐
                    │   Narrator       │  Crafts conversational
                    │    Worker        │  Discord updates
                    └──────────────────┘
```

## Key Components

### Correlator Service
- Subscribes to `K8S_ISSUE_DETECTED` events from Sentinel
- Groups related events within a 30-second window
- Identifies patterns (timeout, connection_error, oom, etc.)
- Publishes `INVESTIGATION_REQUESTED` events

### Orchestrator Agent
- Manages investigation lifecycle through defined stages:
  1. **Analyzing** - Initial assessment
  2. **Querying Memory** - Check for similar past incidents
  3. **Investigating** - Run diagnostic skills
  4. **Planning Remediation** - Decide on fix strategy
  5. **Executing Action** - Apply remediation
  6. **Verifying** - Confirm issue is resolved
  7. **Summarizing** - Store learnings and post summary
- Maintains investigation state in Redis
- Delegates tasks to specialized workers
- Ensures consistent narrative via Narrator

### Worker Agents

**Investigator Worker**
- Runs diagnostic skills using Kubernetes MCP tools
- Checks logs, events, resource states
- Identifies root causes

**Memory Worker**
- Queries memory-mcp-server for similar past incidents
- Stores investigation outcomes for future learning
- Provides historical context

**Remediator Worker**
- Plans safe remediation actions
- Executes fixes using Kubernetes MCP tools
- Verifies remediation success

**Narrator Worker**
- Crafts conversational Discord updates
- Maintains coherent narrative throughout investigation
- Translates technical findings into readable language

## Benefits

✅ **Predictable** - Clear execution path, easy to debug  
✅ **Consistent** - Every investigation follows the same workflow  
✅ **Maintainable** - Clear separation of concerns, easy to extend  
✅ **Cost-efficient** - 6-11 LLM calls per investigation  
✅ **Transparent** - Detailed logging and state tracking  

## Configuration

Environment variables:

```bash
# Redis (for event bus and state storage)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# Correlation settings
CORRELATION_WINDOW_SECONDS=30

# LLM settings (via strands)
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=https://api.openai.com/v1
```

## Usage

### Local Development

```bash
# Install dependencies
cd agents/cluster-monitor
uv sync

# Run the worker
cluster-monitor-worker
```

### Docker Deployment

```bash
# Build image
docker build -t cluster-monitor:latest .

# Run container
docker run -d \
  --name cluster-monitor \
  -e REDIS_HOST=redis \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  cluster-monitor:latest
```

## Testing

```bash
# Run tests
pytest tests/

# Run with coverage
pytest --cov=cluster_monitor tests/
```

## Comparison with cluster-swarm

| Aspect | cluster-monitor (Orchestrator-Worker) | cluster-swarm (Swarm Intelligence) |
|--------|---------------------------------------|-------------------------------------|
| **Architecture** | Structured workflow | Dynamic collaboration |
| **Predictability** | High | Medium |
| **LLM Calls** | 6-11 per investigation | 12-26 per investigation |
| **Development Time** | 6-9 weeks | 10-16 weeks |
| **Debugging** | Easy (linear traces) | Hard (multi-agent traces) |
| **Flexibility** | Medium | High |

## Future Enhancements

- [ ] Connect actual MCP servers (kubernetes, memory, discord)
- [ ] Implement actual agent execution (currently mock results)
- [ ] Add approval workflow for high-risk remediations
- [ ] Implement investigation resumption after crashes
- [ ] Add metrics and observability dashboards
- [ ] Support for custom remediation skills
- [ ] Multi-cluster support

## License

MIT
