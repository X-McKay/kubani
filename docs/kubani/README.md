# Kubani Package Documentation

Documentation for the core `kubani` package containing framework, agents, syndicates, MCP servers, skills, and evaluations.

## Quick Links

- [**Creating Agents**](agents/development/creating-agents.md) - Build new agents
- [**MCP Design**](mcp/architecture/mcp-design.md) - MCP server architecture
- [**Operations Runbook**](syndicates/reference/operations-runbook.md) - Syndicate operations

## Package Structure

```
kubani/
├── framework/         # Core framework
├── agents/            # Reusable agent implementations
├── syndicates/        # Multi-agent orchestration systems
├── mcp/               # MCP server implementations
├── skills/            # Skill definitions
└── evaluations/       # Evaluation framework
```

## Framework

Core framework providing:
- Configuration management
- Event bus (Redis Streams)
- Memory systems (Qdrant, Neo4j, Redis)
- MCP client
- Learning system
- Observability

**Documentation:**
- [Framework Architecture](framework/architecture/) (coming soon)
- [Configuration Reference](framework/reference/config-schema.md) (coming soon)

## Agents

Reusable agent implementations:
- Event Classifier
- Remediator
- Skill Learner
- Sentinel (monitoring)

**Documentation:**
- [Creating Agents](agents/development/creating-agents.md)
- [Agent Patterns](agents/patterns/) (coming soon)

## Syndicates

Multi-agent orchestration systems:
- **k8s-monitor**: Kubernetes monitoring and remediation
- **news-digest**: News aggregation and analysis

**Documentation:**
- [Operations Runbook](syndicates/reference/operations-runbook.md)
- [Syndicate Architecture](syndicates/architecture/) (coming soon)

## MCP Servers

Model Context Protocol server implementations:
- Temporal MCP (workflow management)
- Qdrant MCP (vector database)
- Memory MCP (unified memory interface)
- Discord MCP (messaging)

**Documentation:**
- [MCP Design](mcp/architecture/mcp-design.md)
- [MCP Server APIs](mcp/reference/) (coming soon)

## Skills

Skill definitions for agents:
- Kubernetes diagnostics
- News analysis
- Publishing workflows

**Documentation:**
- [Skill Development](skills/development/) (coming soon)

## Evaluations

Evaluation framework and test suites:
- Automated evaluations
- LLM-as-judge
- Human review workflows

**Documentation:**
- [Evaluation Guide](evaluations/guide/) (coming soon)

## Related Documentation

- [Platform CLI](../platform/cli/) - Development tools
- [Infrastructure](../infrastructure/) - Deployment
- [Architecture](../architecture/) - System design
