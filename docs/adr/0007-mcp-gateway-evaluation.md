# ADR 0007: MCP Gateway Evaluation and Adoption Decision

## Status

PROPOSED - Pending evaluation results

## Context

The Kubani platform currently uses a direct-connection model where each agent connects directly to individual MCP servers (discord-mcp, memory-mcp, skills-mcp, temporal-mcp, qdrant-mcp). This approach has several characteristics:

**Current Architecture (Direct Connection)**:
- Each agent maintains separate connections to 5+ MCP servers
- Each agent needs configuration for each server endpoint
- Network policies must be configured per agent per server
- Observability is distributed across multiple servers
- Authentication/authorization is handled per server

**Proposed Alternative (Gateway)**:
- Single gateway acts as unified access point for all MCP servers
- Agents connect to one endpoint instead of many
- Centralized observability, authentication, and authorization
- Simplified network policies (agents → gateway → servers)

Microsoft's mcp-gateway project provides a reference implementation for this pattern. This ADR documents our evaluation of whether to adopt it.

## Decision Drivers

1. **Configuration Complexity**: How much does it simplify agent configuration?
2. **Performance**: What is the latency overhead and throughput impact?
3. **Observability**: Does it improve monitoring and debugging?
4. **Security**: Does it enhance or complicate security posture?
5. **Operational Overhead**: What is the maintenance cost?
6. **Compatibility**: Does it work with our existing SSE-based servers?
7. **Failure Modes**: How does it affect reliability and failure isolation?

## Evaluation Methodology

We deployed mcp-gateway in a test environment (`ai-agents-test` namespace) and conducted the following tests:

1. **Performance Testing** (`gateway_performance.py`)
   - Sequential request latency comparison
   - Concurrent request handling
   - Throughput measurement
   - Resource usage

2. **Observability Testing** (`gateway_observability.py`)
   - Metrics collection and exposure
   - Health check aggregation
   - Request tracing capabilities
   - Logging quality

3. **Security Testing** (`gateway_security.py`)
   - Authentication mechanisms
   - Authorization capabilities
   - Egress control
   - Input validation

4. **Functional Testing** (`test_gateway.py`)
   - Tool discovery
   - Request routing
   - Error handling
   - Concurrent access

## Evaluation Results

### Performance

| Metric | Direct | Gateway | Overhead |
|--------|--------|---------|----------|
| Mean Latency | [TBD] ms | [TBD] ms | [TBD] ms ([TBD]%) |
| P95 Latency | [TBD] ms | [TBD] ms | [TBD] ms ([TBD]%) |
| Throughput (Sequential) | [TBD] req/s | [TBD] req/s | [TBD]% |
| Throughput (Concurrent) | [TBD] req/s | [TBD] req/s | [TBD]% |

**Analysis**: [To be filled after testing]

### Configuration Simplification

**Before (5 servers × N agents = 5N configurations)**:
```yaml
mcp:
  discord_url: http://discord-mcp-server.ai-agents.svc:8080
  memory_url: http://memory-mcp-server.ai-agents.svc:8080
  skills_url: http://skills-mcp-server.ai-agents.svc:8080
  temporal_url: http://temporal-mcp-server.ai-agents.svc:8080
  qdrant_url: http://qdrant-mcp-server.ai-agents.svc:8080
```

**After (1 gateway × N agents = N configurations)**:
```yaml
mcp:
  gateway_url: http://mcp-gateway.ai-agents-test.svc:8080
```

**Benefit**: ~80% reduction in configuration lines per agent

### Observability

| Feature | Direct | Gateway | Winner |
|---------|--------|---------|--------|
| Metrics Collection | Per-server | Centralized | Gateway |
| Request Tracing | Manual correlation | Automatic | Gateway |
| Health Aggregation | Manual | Automatic | Gateway |
| Debugging | Direct logs | [TBD] | [TBD] |

**Analysis**: [To be filled after testing]

### Security

| Feature | Direct | Gateway | Winner |
|---------|--------|---------|--------|
| Authentication | Per-server | Centralized | [TBD] |
| Authorization | Per-server | Centralized | [TBD] |
| Egress Control | Complex | Simplified | Gateway |
| Audit Trail | Distributed | Centralized | Gateway |
| Attack Surface | Distributed | Single point | [TBD] |

**Analysis**: [To be filled after testing]

### Operational Overhead

| Aspect | Direct | Gateway | Winner |
|--------|--------|---------|--------|
| Components to Deploy | 5 servers | 6 (5 + gateway) | Direct |
| Network Policies | N × 5 | N + 5 | Gateway |
| Configuration Management | Complex | Simple | Gateway |
| Failure Modes | Isolated | Cascading | Direct |
| Debugging Complexity | Low | [TBD] | [TBD] |

## Pros and Cons

### Option 1: Keep Direct Connections (Status Quo)

**Pros**:
- ✅ Simpler architecture (fewer components)
- ✅ Better failure isolation (server failures don't affect others)
- ✅ Lower latency (no proxy overhead)
- ✅ Direct debugging (no intermediary)
- ✅ No single point of failure
- ✅ Already working and stable

**Cons**:
- ❌ Complex agent configuration (5+ endpoints per agent)
- ❌ Distributed observability (harder to correlate)
- ❌ Complex network policies (N agents × M servers)
- ❌ Distributed authentication/authorization
- ❌ Harder to audit access patterns

### Option 2: Adopt MCP Gateway

**Pros**:
- ✅ Simplified agent configuration (1 endpoint)
- ✅ Centralized observability (single metrics/logs source)
- ✅ Simplified network policies (agents → gateway → servers)
- ✅ Centralized authentication/authorization
- ✅ Easier to audit and monitor
- ✅ Can add security layers (WAF, rate limiting)
- ✅ Better for dynamic server discovery

**Cons**:
- ❌ Additional component to deploy and maintain
- ❌ Single point of failure (requires HA setup)
- ❌ Added latency ([TBD]ms overhead)
- ❌ More complex debugging (additional hop)
- ❌ Potential bottleneck under high load
- ❌ Gateway bugs affect all agents

### Option 3: Hybrid Approach

**Pros**:
- ✅ Use gateway for most agents (simplified config)
- ✅ Allow direct connections for critical/high-performance agents
- ✅ Gradual migration path
- ✅ Flexibility based on use case

**Cons**:
- ❌ Most complex to maintain (two patterns)
- ❌ Inconsistent architecture
- ❌ Harder to reason about

## Decision

**[TO BE DETERMINED AFTER EVALUATION]**

### Recommended Option: [1/2/3]

**Rationale**: [To be filled based on evaluation results]

### Migration Plan (if adopting gateway)

**Phase 1: Pilot (Week 1-2)**
- Deploy gateway in production
- Migrate 1-2 non-critical agents
- Monitor performance and stability
- Gather feedback

**Phase 2: Gradual Rollout (Week 3-6)**
- Migrate remaining agents in batches
- Keep direct connections as fallback
- Monitor metrics and adjust

**Phase 3: Optimization (Week 7-8)**
- Tune gateway configuration
- Implement HA if needed
- Remove direct connection fallbacks

**Phase 4: Cleanup (Week 9-10)**
- Remove old configuration
- Update documentation
- Decommission test environment

### Rollback Plan

If gateway adoption fails:
1. Revert agent configurations to direct connections
2. Scale down gateway deployment
3. Document lessons learned
4. Consider alternative solutions

## Consequences

### If We Adopt the Gateway

**Positive**:
- Simplified agent development (less configuration)
- Better observability and monitoring
- Easier to add new MCP servers
- Centralized security controls
- Better audit trail

**Negative**:
- Additional operational complexity
- Need to ensure gateway HA
- Potential performance impact
- More complex debugging
- Dependency on gateway stability

**Neutral**:
- Need to train team on gateway operations
- Documentation updates required
- Monitoring dashboards need updates

### If We Keep Direct Connections

**Positive**:
- No additional complexity
- Proven stable architecture
- Better failure isolation
- Lower latency

**Negative**:
- Configuration complexity remains
- Distributed observability
- Harder to add new servers
- Complex network policies

**Neutral**:
- Status quo maintained
- No migration effort needed

## Implementation Notes

### Gateway Configuration

The gateway is configured via ConfigMap at `infrastructure/gitops/apps/ai-agents/mcp-gateway-test/gateway-config.yaml`.

Key configuration sections:
- **servers**: List of upstream MCP servers
- **gateway**: Port, timeout, health check settings
- **observability**: Metrics, tracing, logging

### Monitoring

Key metrics to monitor:
- `gateway_request_duration_seconds` - Request latency
- `gateway_requests_total` - Request count by server/status
- `gateway_upstream_health` - Upstream server health
- `gateway_active_connections` - Current connections

### High Availability

For production use, gateway should be deployed with:
- Multiple replicas (3+)
- Pod anti-affinity rules
- Horizontal Pod Autoscaler
- PodDisruptionBudget

## Related Decisions

- [ADR 0001: MCP Server Architecture](./0001-mcp-server-architecture.md) (if exists)
- [ADR 0002: Service Mesh Evaluation](./0002-service-mesh-evaluation.md) (if exists)

## References

- [MCP Gateway GitHub](https://github.com/microsoft/mcp-gateway)
- [MCP Specification](https://modelcontextprotocol.io/)
- [Evaluation Findings](../mcp-servers/gateway-evaluation-findings.md)
- [Performance Results](../../gateway_performance_results.json)
- [Security Results](../../gateway_security_results.json)
- [Observability Results](../../gateway_observability_results.json)

## Appendix A: Test Environment

- **Kubernetes**: k3s v1.28
- **Gateway Version**: [TBD]
- **Test Namespace**: `ai-agents-test`
- **Upstream Servers**: discord-mcp, memory-mcp, skills-mcp, temporal-mcp, qdrant-mcp
- **Test Duration**: [TBD]
- **Test Date**: [TBD]

## Appendix B: Alternative Solutions Considered

1. **Service Mesh (Istio/Linkerd)**
   - Pros: Comprehensive traffic management, security, observability
   - Cons: Much heavier weight, operational complexity
   - Decision: Too complex for our current needs

2. **API Gateway (Kong/Traefik)**
   - Pros: Mature, feature-rich, well-documented
   - Cons: Not MCP-specific, would need custom configuration
   - Decision: Possible alternative if mcp-gateway doesn't work

3. **Custom Gateway**
   - Pros: Tailored to our exact needs
   - Cons: Development and maintenance burden
   - Decision: Only if no existing solution works

## Appendix C: Success Criteria

Gateway adoption is successful if:
- [ ] Latency overhead < 20ms or < 30% of direct
- [ ] Throughput > 100 req/s per gateway instance
- [ ] 99.9% uptime over 30 days
- [ ] Configuration complexity reduced by > 50%
- [ ] Observability improved (subjective assessment)
- [ ] No security regressions
- [ ] Team comfortable operating gateway

## Appendix D: Review and Update

This ADR should be reviewed:
- After initial evaluation (before adoption decision)
- 30 days after adoption (if adopted)
- 90 days after adoption (if adopted)
- Annually thereafter

Last Updated: [Date]
Next Review: [Date + 30 days]
