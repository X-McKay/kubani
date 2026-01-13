# Cluster Swarm - Swarm Intelligence Architecture

**Status:** Experimental (v0.1.0)

Intelligent Kubernetes cluster monitoring using Swarm Intelligence for dynamic, adaptive investigations.

## Architecture Overview

The Cluster Swarm uses a **collaborative agent model** where specialized agents work together through handoffs:

```
┌─────────────────────────────────────────────────────────────┐
│                     Event Bus (Redis)                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │   Correlator     │  (Shared with cluster-monitor)
                    │    Service       │  Groups related events
                    └──────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  Triage Agent    │  Entry point, analyzes
                    │  (Entry Point)   │  and routes to specialist
                    └──────────────────┘
                              │
              ┌───────────────┼───────────────┬───────────────┐
              ▼               ▼               ▼               ▼
    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
    │Investigator │  │   Memory    │  │ Remediation │  │Communications│
    │   Agent     │  │   Agent     │  │   Agent     │  │   Agent     │
    └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
              │               │               │               │
              └───────────────┴───────────────┴───────────────┘
                         Handoffs & Collaboration
```

## Key Components

### Swarm Agents

**Triage Agent** (Entry Point)
- Analyzes incoming correlated issues
- Assesses severity and urgency
- Routes to appropriate specialist agents
- Coordinates overall investigation flow

**Investigator Agent**
- Diagnostic specialist
- Runs Kubernetes diagnostic skills
- Checks logs, events, resource states
- Hands off findings to other agents

**Memory Agent**
- Queries past incidents for patterns
- Provides historical context
- Stores new learnings after investigations
- Identifies recurring issues

**Remediation Agent**
- Plans safe remediation actions
- Executes fixes using Kubernetes tools
- Verifies remediation success
- Coordinates with other agents on strategy

**Communications Agent**
- Manages all Discord communication
- Crafts conversational updates
- Maintains coherent narrative
- Translates technical findings for users

### Swarm Dynamics

Agents collaborate through **handoffs**:

```
Triage → Communications (initial message)
      → Investigator (diagnostics)
            → Memory (check past incidents)
                  → Remediation (plan fix)
                        → Communications (report action)
                              → Remediation (execute)
                                    → Communications (final summary)
                                          → Memory (store learning)
```

The path is **dynamic** - agents decide who to hand off to based on what they discover.

## Benefits

✅ **Adaptive** - Handles novel situations dynamically  
✅ **Flexible** - No fixed workflow, explores multiple hypotheses  
✅ **Intelligent** - Agents collaborate and learn from each other  
✅ **Emergent** - Complex behavior from simple agent rules  
✅ **Resilient** - Can recover from unexpected situations  

## Tradeoffs

⚠️ **Less Predictable** - Execution path varies by investigation  
⚠️ **Higher Cost** - 12-26 LLM calls per investigation (2x more)  
⚠️ **Complex Debugging** - Multi-agent traces harder to follow  
⚠️ **Longer Development** - 10-16 weeks to production-ready  
⚠️ **Maintenance Burden** - Requires holistic prompt tuning  

## Configuration

Environment variables:

```bash
# Redis (for event bus)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# Swarm settings
MAX_HANDOFFS=20
MAX_ITERATIONS=30

# LLM settings (via strands)
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=https://api.openai.com/v1
```

## Usage

### Local Development

```bash
# Install dependencies
cd agents/cluster-swarm
uv sync

# Run the worker
cluster-swarm-worker
```

### Docker Deployment

```bash
# Build image
docker build -t cluster-swarm:latest .

# Run container
docker run -d \
  --name cluster-swarm \
  -e REDIS_HOST=redis \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  cluster-swarm:latest
```

## Testing

```bash
# Run tests
pytest tests/

# Run with coverage
pytest --cov=cluster_swarm tests/
```

## Comparison with cluster-monitor

| Aspect | cluster-monitor (Orchestrator-Worker) | cluster-swarm (Swarm Intelligence) |
|--------|---------------------------------------|-------------------------------------|
| **Architecture** | Structured workflow | Dynamic collaboration |
| **Predictability** | High | Medium |
| **LLM Calls** | 6-11 per investigation | 12-26 per investigation |
| **Development Time** | 6-9 weeks | 10-16 weeks |
| **Debugging** | Easy (linear traces) | Hard (multi-agent traces) |
| **Flexibility** | Medium | High |
| **Novel Situations** | Requires workflow updates | Adapts dynamically |

## When to Use cluster-swarm

Choose cluster-swarm over cluster-monitor when:

- Your operational environment is **highly unpredictable**
- You need **maximum flexibility** to handle novel issues
- Your team has **strong multi-agent expertise**
- You're willing to invest in **sophisticated observability**
- You value **emergent intelligence** over predictability
- You have **resources for complex system management**

## Future Enhancements

- [ ] Connect actual MCP servers (kubernetes, memory, discord)
- [ ] Implement actual swarm execution with Strands
- [ ] Add loop detection and recovery mechanisms
- [ ] Implement swarm state persistence and resumption
- [ ] Add metrics for swarm behavior analysis
- [ ] Support for dynamic agent addition/removal
- [ ] Swarm optimization based on investigation outcomes

## License

MIT
