# ADR-002: MCP-First Tool Integration

## Status
Accepted

## Context

AI agents need to interact with external services such as Kubernetes, Discord, vector databases, and workflow engines. The traditional approach involves direct SDK integration within each agent, which creates tight coupling between agents and services, makes testing difficult, and requires each agent to handle authentication, error handling, and retries independently.

The Model Context Protocol (MCP) provides a standardized way for AI systems to interact with external tools and services. By adopting MCP as the primary integration pattern, we can create a consistent interface for all tool access while maintaining flexibility in implementation.

## Decision

All external tool access goes through MCP servers. Each service has a dedicated MCP server that exposes its functionality through the MCP protocol. Agents use a unified MCP client to access these servers.

The architecture follows this pattern:

```
Agent → MCPClient → MCP Server → External Service
```

We created the following MCP servers:

| Server | Purpose |
|--------|---------|
| Temporal MCP | Workflow management (list, start, signal, cancel) |
| Qdrant MCP | Vector operations (search, upsert, delete) |
| Memory MCP | Unified memory interface (learnings, knowledge graph, cache) |
| Discord MCP | Messaging and reactions |
| Kubernetes MCP | Cluster operations |

MCP servers use FastMCP from the official MCP library, providing consistent patterns for tool registration and request handling.

## Consequences

### Positive

The MCP-first approach provides a standardized interface that all agents use consistently, eliminating the need to learn different SDK patterns for each service. Testing becomes significantly easier because MCP servers can be mocked at the client level, allowing isolated unit tests without real service dependencies.

Adding new capabilities requires only creating a new MCP server, which can be done independently of agent code. The protocol's language-agnostic nature means we can leverage the growing ecosystem of MCP servers created by the community.

Centralized metrics and logging at the MCP layer provide visibility into all tool usage across agents, making debugging and optimization more straightforward.

### Negative

The additional network hop through MCP servers adds latency compared to direct SDK calls. For high-frequency operations, this overhead may become significant.

Each MCP server is an additional service to deploy and maintain, increasing operational complexity. Teams must learn MCP patterns in addition to the underlying service patterns.

### Neutral

The MCP protocol is still evolving, so we may need to update our implementations as the specification matures. However, the abstraction layer means changes are isolated to the MCP servers rather than spreading across all agents.

## Alternatives Considered

### Direct SDK Integration

Using SDKs directly in agents would eliminate the MCP overhead but would result in inconsistent patterns across agents, difficult testing, and tight coupling to specific service implementations. Each agent would need to handle its own authentication, error handling, and retries.

### gRPC Service Layer

A custom gRPC service layer would provide similar benefits to MCP but would require defining and maintaining our own protocol. MCP provides a standard that is gaining adoption in the AI community, reducing the need for custom protocol design.

### REST API Wrappers

Simple REST wrappers around services would be easier to implement initially but would not provide the structured tool definitions that LLMs can use for function calling. MCP's tool schema format is designed specifically for AI agent interaction.
