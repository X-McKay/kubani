# MCP Gateway Evaluation Guide

This guide explains how to run the MCP Gateway evaluation tests.

## Prerequisites

1. Kubernetes cluster with kubectl access
2. MCP servers deployed in `ai-agents` namespace
3. Python 3.11+ with uv
4. Access to cluster via Tailscale (for external testing)

## Deployment

### 1. Deploy the Gateway

```bash
# Deploy gateway and test namespace
kubectl apply -k infrastructure/gitops/apps/ai-agents/mcp-gateway-test/

# Check deployment status
kubectl get pods -n ai-agents-test
kubectl get svc -n ai-agents-test
kubectl get ingress -n ai-agents-test

# View gateway logs
kubectl logs -n ai-agents-test -l app.kubernetes.io/name=mcp-gateway -f
```

### 2. Deploy Test Agent (Optional)

```bash
# Deploy test agent that uses gateway
kubectl apply -k infrastructure/gitops/apps/ai-agents/gateway-test-agent/

# Check agent status
kubectl get pods -n ai-agents-test -l app.kubernetes.io/name=gateway-test-agent

# View agent logs
kubectl logs -n ai-agents-test -l app.kubernetes.io/name=gateway-test-agent -f
```

## Running Tests

### From Within Cluster

If running tests from a pod within the cluster:

```bash
# Port forward to gateway (if needed)
kubectl port-forward -n ai-agents-test svc/mcp-gateway 8080:8080 9090:9090

# Run all tests
uv run python kubani/mcp/servers/tests/test_gateway.py
uv run python kubani/mcp/servers/tests/gateway_performance.py
uv run python kubani/mcp/servers/tests/gateway_observability.py
uv run python kubani/mcp/servers/tests/gateway_security.py
```

### From Outside Cluster

If running tests from your local machine via Tailscale:

```bash
# Update URLs in test scripts to use external domain
# gateway_url = "https://mcp-gateway.almckay.io"

# Run tests
uv run python kubani/mcp/servers/tests/test_gateway.py
uv run python kubani/mcp/servers/tests/gateway_performance.py
uv run python kubani/mcp/servers/tests/gateway_observability.py
uv run python kubani/mcp/servers/tests/gateway_security.py
```

### Using pytest

```bash
# Run functional tests
uv run pytest kubani/mcp/servers/tests/test_gateway.py -v

# Run specific test
uv run pytest kubani/mcp/servers/tests/test_gateway.py::test_gateway_health -v
```

## Test Descriptions

### 1. Functional Tests (`test_gateway.py`)

Tests basic gateway functionality:
- Health check
- Tool discovery
- Read operations
- Concurrent requests
- Error handling
- Latency comparison with direct connections

**Run**: `uv run pytest kubani/mcp/servers/tests/test_gateway.py -v`

### 2. Performance Tests (`gateway_performance.py`)

Measures gateway performance:
- Sequential request latency
- Concurrent request handling
- Throughput (requests per second)
- Latency percentiles (P95, P99)
- Comparison with direct connections

**Run**: `uv run python kubani/mcp/servers/tests/gateway_performance.py`

**Output**: `gateway_performance_results.json`

### 3. Observability Tests (`gateway_observability.py`)

Evaluates observability features:
- Metrics endpoint availability
- Health check aggregation
- Request tracing support
- Logging capabilities
- Routing visibility

**Run**: `uv run python kubani/mcp/servers/tests/gateway_observability.py`

**Output**: `gateway_observability_results.json`

### 4. Security Tests (`gateway_security.py`)

Evaluates security features:
- Authentication mechanisms
- Authorization capabilities
- Egress control
- Rate limiting
- Input validation
- Comparison with direct connections

**Run**: `uv run python kubani/mcp/servers/tests/gateway_security.py`

**Output**: `gateway_security_results.json`

## Interpreting Results

### Performance

**Good**:
- Latency overhead < 20ms or < 30%
- Throughput > 100 req/s
- P99 latency < 200ms
- Success rate > 99%

**Concerning**:
- Latency overhead > 50ms or > 50%
- Throughput < 50 req/s
- P99 latency > 500ms
- Success rate < 95%

### Observability

**Good**:
- Metrics endpoint available
- Health aggregates upstream status
- Request tracing supported
- Structured logging

**Concerning**:
- No metrics endpoint
- Health doesn't check upstream
- No tracing support
- Poor logging

### Security

**Good**:
- Multiple auth mechanisms supported
- Authorization configurable
- Input validation robust
- Rate limiting available

**Concerning**:
- No authentication
- No authorization
- Poor input validation
- No rate limiting

## Troubleshooting

### Gateway Not Starting

```bash
# Check pod status
kubectl describe pod -n ai-agents-test -l app.kubernetes.io/name=mcp-gateway

# Check logs
kubectl logs -n ai-agents-test -l app.kubernetes.io/name=mcp-gateway

# Common issues:
# - ConfigMap not mounted
# - Upstream servers not accessible
# - Port conflicts
```

### Tests Failing

```bash
# Check gateway health
curl http://mcp-gateway.ai-agents-test.svc:8080/health

# Check upstream servers
kubectl get pods -n ai-agents -l mcp.kubani.io/server=true

# Check network connectivity
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  curl http://mcp-gateway.ai-agents-test.svc:8080/health
```

### Timeout Errors

```bash
# Increase timeout in test scripts
# client = httpx.AsyncClient(timeout=60.0)  # Increase from 30.0

# Check if upstream servers are slow
kubectl logs -n ai-agents -l app.kubernetes.io/name=skills-mcp-server
```

## Cleanup

```bash
# Delete test resources
kubectl delete namespace ai-agents-test

# Or delete specific resources
kubectl delete -k infrastructure/gitops/apps/ai-agents/mcp-gateway-test/
kubectl delete -k infrastructure/gitops/apps/ai-agents/gateway-test-agent/
```

## Next Steps

After running all tests:

1. Review results in JSON files
2. Update `docs/mcp-servers/gateway-evaluation-findings.md` with actual results
3. Update `docs/adr/0007-mcp-gateway-evaluation.md` with decision
4. Present findings to team
5. Make adoption decision

## Notes

### Gateway Image

The deployment uses `ghcr.io/microsoft/mcp-gateway:latest`. If this image is not available:

1. Check Microsoft's mcp-gateway repository for actual image location
2. Build from source if needed
3. Update deployment.yaml with correct image

### Configuration

Gateway configuration is in `infrastructure/gitops/apps/ai-agents/mcp-gateway-test/gateway-config.yaml`.

Adjust as needed for your environment:
- Server URLs
- Timeouts
- Health check intervals
- Observability settings

### Production Considerations

If adopting gateway for production:

1. Deploy with multiple replicas (3+)
2. Configure HPA for auto-scaling
3. Set up PodDisruptionBudget
4. Configure pod anti-affinity
5. Set up monitoring alerts
6. Document runbooks
7. Train team on operations

## References

- [ADR 0007: MCP Gateway Evaluation](../../../docs/adr/0007-mcp-gateway-evaluation.md)
- [Evaluation Findings](../../../docs/mcp-servers/gateway-evaluation-findings.md)
- [MCP Gateway GitHub](https://github.com/microsoft/mcp-gateway)
