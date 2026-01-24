# Local Development Guide

This guide documents how to develop, test, and iterate on AI agents locally while connecting to external cluster services.

## Architecture Overview

The local development workflow allows you to run agent code on your local machine while connecting to external cluster services via Tailscale VPN:

```
┌─────────────────────────────────────────────────────────────────┐
│                     Local Development Machine                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Agent Code (news-monitor, k8s-monitor, etc.)            │   │
│  │  - Worker processes                                       │   │
│  │  - Federated agents                                       │   │
│  │  - Activities & workflows                                 │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                    Tailscale VPN (100.x.x.x)                    │
└──────────────────────────────│──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Kubernetes Cluster                         │
│                                                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐    │
│  │  Temporal      │  │  Qdrant        │  │  Neo4j         │    │
│  │  :7233 (gRPC)  │  │  :443 (HTTPS)  │  │  :7687 (Bolt)  │    │
│  └────────────────┘  └────────────────┘  └────────────────┘    │
│                                                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐    │
│  │  Redis         │  │  vLLM (LLM)    │  │  Embeddings    │    │
│  │  :6379 (TCP)   │  │  :443 (HTTPS)  │  │  :443 (HTTPS)  │    │
│  └────────────────┘  └────────────────┘  └────────────────┘    │
│                                                                  │
│  All services exposed via Traefik at *.almckay.io               │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Setup Development Environment

```bash
# One-time setup: populate .env with secrets from cluster
just dev-setup

# This creates .env from .env.development and fetches:
# - Qdrant API key
# - Neo4j password
```

### 2. Run Agent Commands Locally

```bash
# Run any agent command with full logging
just run-local <agent> <command> [args...]

# Examples:
just run-local news-monitor worker           # Start worker
just run-local news-monitor digest           # Run single digest
just run-local news-monitor ingest           # Run article ingestion
just run-local news-monitor federated-only   # Run only federated agents

just run-local k8s-monitor worker            # Start k8s-monitor worker
just run-local k8s-monitor check             # Run single health check
```

### 3. Use Temporal CLI

```bash
# The Temporal CLI connects to the cluster automatically
temporal workflow list
temporal workflow describe --workflow-id <id>
temporal workflow show --workflow-id <id>
```

## External Services

| Service | Endpoint | Protocol | Port |
|---------|----------|----------|------|
| Temporal | temporal.almckay.io:7233 | gRPC | 7233 |
| Qdrant | qdrant.almckay.io | HTTPS | 443 |
| Neo4j | neo4j.almckay.io:7687 | Bolt | 7687 |
| Redis | redis.almckay.io:6379 | TCP | 6379 |
| vLLM | llm.almckay.io | HTTPS | 443 |
| Embeddings | embeddings.almckay.io | HTTPS | 443 |

All services are exposed via Traefik with TCP routing for non-HTTP protocols.

## Environment Variables

The `.env.development` template contains all required environment variables:

```bash
# LLM Configuration
KUBANI_VLLM_API_URL=https://llm.almckay.io/v1
KUBANI_DEFAULT_MODEL_ID=Qwen/Qwen3-14B-FP8

# Embeddings
KUBANI_EMBEDDINGS_API_URL=https://embeddings.almckay.io/v1
KUBANI_EMBEDDINGS_MODEL=Qwen/Qwen3-Embedding-0.6B

# Vector Database (Qdrant)
KUBANI_QDRANT_URL=https://qdrant.almckay.io
KUBANI_QDRANT_API_KEY=<populated by just dev-setup>

# Graph Database (Neo4j)
KUBANI_NEO4J_URL=bolt://neo4j.almckay.io:7687
KUBANI_NEO4J_PASSWORD=<populated by just dev-setup>

# Temporal
TEMPORAL_HOST=temporal.almckay.io:7233
TEMPORAL_ADDRESS=temporal.almckay.io:7233
```

## Testing and Iteration Workflow

### Rapid Testing Cycle

1. **Make code changes** in your IDE
2. **Test immediately** with `just run-local`:
   ```bash
   just run-local news-monitor federated-only
   ```
3. **Check logs** - full output is visible in terminal
4. **Iterate** - no build/deploy cycle needed

### Testing Specific Components

```bash
# Test federated agents (source discovery, trends)
just run-local news-monitor federated-only

# Test Temporal workflows
just run-local news-monitor digest
just run-local news-monitor ingest

# Test worker with all components
timeout 30 just run-local news-monitor worker
```

### Debugging Tips

1. **Verbose logging** is enabled by default (`KUBANI_LOG_LEVEL=DEBUG`)

2. **Check service connectivity**:
   ```bash
   # Test Qdrant
   curl -H "Authorization: Bearer $KUBANI_QDRANT_API_KEY" https://qdrant.almckay.io

   # Test Neo4j port
   nc -zv neo4j.almckay.io 7687

   # Test Temporal
   temporal workflow list
   ```

3. **Check cluster logs** for comparison:
   ```bash
   KUBECONFIG=~/.kube/config kubectl logs -n ai-agents deployment/news-monitor --tail=100
   ```

4. **Inspect Temporal workflows**:
   ```bash
   temporal workflow list --query 'WorkflowType="ArticleIngestionWorkflow"'
   ```

### Common Issues

| Issue | Solution |
|-------|----------|
| `Redis unavailable` | Check Tailscale connection, Redis may not be exposed |
| `Cannot connect to Temporal` | Verify `TEMPORAL_HOST` in .env |
| `Qdrant 401 Unauthorized` | Run `just dev-setup` to refresh API key |
| `Neo4j connection refused` | Ensure Neo4j TCP routing is deployed |
| `Memory not available: object Memory can't be used in await` | Check if function is sync vs async |

## Key Design Patterns

### Atomic Operations for Deduplication

Breaking news alerts use atomic Redis SADD to prevent race conditions:

```python
def try_claim_breaking_alert(url: str) -> bool | None:
    """
    Atomically try to claim the right to send a breaking alert.
    Uses Redis SADD which returns 1 if new, 0 if exists.
    """
    result = redis_client.sadd(REDIS_BREAKING_ALERTS_KEY, url)
    return result == 1  # Only first caller wins
```

### Memory System Configuration

The memory system auto-detects HTTPS for Qdrant:

```python
# Auto-detect HTTPS: use if port is 443 or QDRANT_USE_HTTPS=true
_qdrant_use_https = (
    os.environ.get("QDRANT_USE_HTTPS", "").lower() in ("true", "1", "yes")
    or _qdrant_port == 443
)
```

### Fail-Closed Behavior

When Redis is unavailable, operations fail-closed to prevent duplicates:

```python
claim_status = try_claim_breaking_alert(article.url)
if claim_status is None:
    # Cannot verify - skip to avoid duplicates
    logger.warning("Redis unavailable, skipping alert")
    return False
```

## Adding New Services

To expose a new TCP service externally:

1. **Add entrypoint to Traefik config** (`gitops/infrastructure/traefik/traefik-config.yaml`):
   ```yaml
   ports:
     myservice:
       port: 1234
       expose: true
       exposedPort: 1234
       protocol: TCP
   additionalArguments:
     - "--entrypoints.myservice.address=:1234/tcp"
   ```

2. **Create IngressRouteTCP** in the service's namespace:
   ```yaml
   apiVersion: traefik.containo.us/v1alpha1
   kind: IngressRouteTCP
   metadata:
     name: myservice-tcp
     namespace: myns
   spec:
     entryPoints:
       - myservice
     routes:
       - match: HostSNI(`*`)
         services:
           - name: myservice
             port: 1234
   ```

3. **Add to kustomization.yaml** and commit

4. **Update .env.development** with the new endpoint

## Files Reference

| File | Purpose |
|------|---------|
| `.env.development` | Template with all service endpoints |
| `.env` | Active config (gitignored, created by `dev-setup`) |
| `justfile` | Development commands (`run-local`, `dev-setup`) |
| `gitops/infrastructure/traefik/traefik-config.yaml` | TCP entrypoints |
| `gitops/infrastructure/neo4j/ingressroutetcp.yaml` | Neo4j TCP routing |
| `gitops/apps/temporal/ingressroutetcp.yaml` | Temporal gRPC routing |
