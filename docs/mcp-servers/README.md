# MCP Server Documentation

Welcome to the Kubani MCP (Model Context Protocol) server documentation. This guide will help you develop, test, deploy, and maintain MCP servers for the Kubani platform.

## Overview

MCP servers expose tools and capabilities that AI agents can use to interact with external systems. The Kubani platform provides a comprehensive framework for building production-ready MCP servers with:

- **Standardized framework** - Shared utilities for health checks, metrics, and registry integration
- **Multi-transport support** - SSE, stdio, and HTTP transports
- **Comprehensive testing** - Unit, contract, integration, and property-based tests
- **Automatic service discovery** - Registry integration with lifecycle management
- **Production-ready deployments** - Kubernetes manifests with security and observability

## Documentation Structure

### 1. [Development Guide](development-guide.md)

**Start here if you're building a new MCP server.**

Covers:
- Quick start guide
- Framework components (HealthCheck, MetricsCollector, RegistryClient)
- Multi-transport support
- Secrets management best practices
- Code examples and templates

### 2. [Testing Guide](testing-guide.md)

**Essential reading for ensuring your MCP server is correct and reliable.**

Covers:
- Testing layers (unit, contract, integration, property-based)
- Writing and running tests
- Test organization and best practices
- CI/CD integration
- Using the unified test runner

### 3. [Deployment Guide](deployment-guide.md)

**Follow this guide to deploy your MCP server to Kubernetes.**

Covers:
- Standard deployment template
- Environment variables and configuration
- Secrets management with SOPS
- Health checks and metrics
- Service and ingress configuration
- Troubleshooting deployment issues

### 4. [Registry Integration Guide](registry-integration.md)

**Learn how MCP servers integrate with the Kubani Registry.**

Covers:
- Registration process
- Heartbeat mechanism
- Lifecycle management and reconciliation
- Service discovery
- Implementation examples
- Troubleshooting registry issues

### 5. [Multi-Transport Support](multi-transport.md)

**Learn how to configure and use different transport modes.**

Covers:
- SSE, stdio, and HTTP transport modes
- Configuration options and environment variables
- Server-specific configuration examples
- Testing and troubleshooting
- Security considerations

### 6. [Gateway Evaluation Findings](gateway-evaluation-findings.md)

**Background on the mcp-gateway evaluation.**

Covers:
- Gateway architecture and benefits
- Performance evaluation
- Security and observability analysis
- Recommendation and decision rationale

### 7. [Verification Reports](verification-reports.md)

**Implementation verification and audit results.**

Covers:
- Final checkpoint verification
- Test verification summary
- Secrets management verification
- Outstanding items and recommendations

### 8. [Agent-Specific Code Audit](agent-audit.md)

**Audit results confirming generic server design.**

Covers:
- Audit findings by server
- Best practices observed
- Generic design validation
- Testing approach

## Quick Links

### For New Developers

1. Read the [Development Guide](development-guide.md)
2. Review existing servers in `kubani/mcp/servers/`
3. Follow the quick start to create your server
4. Write tests following the [Testing Guide](testing-guide.md)
5. Deploy using the [Deployment Guide](deployment-guide.md)

### For Existing Server Maintenance

- **Adding features**: See [Development Guide](development-guide.md) for framework usage
- **Fixing bugs**: Use [Testing Guide](testing-guide.md) to add tests first
- **Deployment issues**: Check [Deployment Guide](deployment-guide.md) troubleshooting
- **Registry problems**: See [Registry Integration Guide](registry-integration.md)

### For Operations

- **Monitoring**: See [Deployment Guide](deployment-guide.md) - Health and Metrics section
- **Troubleshooting**: Each guide has a troubleshooting section
- **Secrets rotation**: See [Deployment Guide](deployment-guide.md) - Secrets Management
- **Scaling**: Adjust replicas in deployment manifests

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Kubani Platform                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐                                          │
│  │   Agents     │                                          │
│  │              │                                          │
│  │ - k8s-monitor│                                          │
│  │ - news-agent │                                          │
│  │ - learning   │                                          │
│  └──────┬───────┘                                          │
│         │                                                   │
│         │ Discover via Registry                            │
│         │                                                   │
│         ▼                                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Kubani Registry                                     │  │
│  │  - Service discovery                                 │  │
│  │  - Health tracking                                   │  │
│  │  - Lifecycle management                              │  │
│  └──────────────────────────────────────────────────────┘  │
│         │                                                   │
│         │ Connect to servers                               │
│         │                                                   │
│         ▼                                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  MCP Servers (SSE/stdio/HTTP)                        │  │
│  │                                                       │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐          │  │
│  │  │ Discord  │  │  Memory  │  │  Skills  │          │  │
│  │  │   MCP    │  │   MCP    │  │   MCP    │          │  │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘          │  │
│  │       │             │              │                 │  │
│  │       │ Health &    │ Metrics      │                 │  │
│  │       │ Metrics     │              │                 │  │
│  │       ▼             ▼              ▼                 │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Backend Services                                    │  │
│  │  - Discord API                                       │  │
│  │  - Qdrant, Neo4j, Redis                             │  │
│  │  - Temporal                                          │  │
│  │  - Skill Repository                                  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Key Concepts

### MCP Server

A service that exposes tools via the Model Context Protocol. Tools are functions that agents can call to interact with external systems.

### Transport

The communication mechanism between agents and MCP servers:
- **SSE** (Server-Sent Events) - For cluster deployments
- **stdio** - For local development
- **HTTP** - Alternative for cluster deployments

### Registry

Central service that tracks all MCP servers, their capabilities, and connection information. Enables dynamic service discovery.

### Framework

Shared utilities (`kubani.framework.mcp.server`) that provide:
- Health checks with backend verification
- Prometheus metrics collection
- Registry integration (registration, heartbeats)
- Multi-transport configuration

### Generic Design

MCP servers are designed to be reusable across all agents. They accept generic parameters (like `agent_id`) rather than being tied to specific agents.

## Best Practices

### Development

1. **Use the framework** - Don't reinvent health checks, metrics, or registry integration
2. **Design generically** - Make tools reusable across all agents
3. **Validate inputs** - Use Pydantic models for type safety
4. **Handle errors consistently** - Use standard error patterns
5. **Document thoroughly** - Clear docstrings for all tools

### Testing

1. **Write tests first** - TDD helps catch issues early
2. **Use all test layers** - Unit, contract, integration, and property tests
3. **Test error cases** - Don't just test the happy path
4. **Use property-based testing** - Catch edge cases automatically
5. **Run tests in CI/CD** - Automate testing

### Deployment

1. **Follow the template** - Use standard deployment manifests
2. **Never commit secrets** - Always use SOPS encryption
3. **Set resource limits** - Prevent resource exhaustion
4. **Use health probes** - Enable automatic recovery
5. **Monitor metrics** - Track performance and errors

### Operations

1. **Monitor health endpoints** - Alert on failures
2. **Track metrics** - Use Grafana dashboards
3. **Review logs** - Centralize with Loki
4. **Rotate secrets** - Update credentials regularly
5. **Test deployments** - Run post-deployment tests

## Existing MCP Servers

Reference implementations:

- **discord-mcp-server** - Bidirectional Discord integration
  - Location: `kubani/mcp/servers/discord/`
  - Features: Messages, reactions, channels, webhooks
  
- **memory-mcp-server** - Agent memory and knowledge graph
  - Location: `kubani/mcp/servers/memory/`
  - Features: Learnings, knowledge, caching
  
- **skills-mcp-server** - Skill discovery and execution
  - Location: `kubani/mcp/servers/skills/`
  - Features: OCI registry integration, skill management
  
- **temporal-mcp-server** - Workflow orchestration
  - Location: `kubani/mcp/servers/temporal/`
  - Features: Workflow execution, scheduling
  
- **qdrant-mcp-server** - Vector database operations
  - Location: `kubani/mcp/servers/qdrant/`
  - Features: Vector search, collections

## Getting Help

### Documentation Issues

If you find errors or gaps in the documentation:
1. Check the source code for the most up-to-date information
2. Review existing MCP servers for examples
3. Open an issue or submit a PR

### Development Questions

- Review the [Development Guide](development-guide.md)
- Check existing server implementations
- Look at framework source code in `kubani/framework/mcp/server/`

### Deployment Problems

- Check the [Deployment Guide](deployment-guide.md) troubleshooting section
- Review Kubernetes events and logs
- Verify secrets are properly encrypted

### Testing Help

- See the [Testing Guide](testing-guide.md)
- Review existing test files
- Use the unified test runner for consistent results

## Contributing

When contributing to MCP server documentation:

1. **Keep it practical** - Focus on actionable information
2. **Include examples** - Show, don't just tell
3. **Update all guides** - If you change one, check if others need updates
4. **Test your examples** - Ensure code snippets actually work
5. **Be concise** - Developers want quick answers

## Additional Resources

- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Flux CD Documentation](https://fluxcd.io/docs/)
- [Prometheus Documentation](https://prometheus.io/docs/)

## Version History

- **v1.0** (2026-02-06) - Initial comprehensive documentation
  - Development guide
  - Testing guide
  - Deployment guide
  - Registry integration guide
  - Gateway evaluation findings
