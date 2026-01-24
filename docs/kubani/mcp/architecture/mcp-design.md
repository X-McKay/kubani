# MCP Server Integration Guide

This guide covers how to integrate MCP (Model Context Protocol) servers with the Kubani federated agent architecture.

## Overview

The federated architecture follows an **MCP-First** principle: agents use MCP servers for all actions, and skills contain knowledge about *when* and *how* to use them, not executable code.

```
┌─────────────────────────────────────────────────────────────────┐
│                     MCP INTEGRATION FLOW                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Skill (Knowledge)        Agent           MCP Server            │
│  ┌─────────────────┐     ┌───────┐       ┌─────────────────┐   │
│  │ preconditions   │────►│       │       │ kubernetes-mcp  │   │
│  │ actions:        │     │       │──────►│                 │   │
│  │   - mcp_tool:   │     │       │       │ • pods_list     │   │
│  │     server: k8s │     │       │◄──────│ • pods_delete   │   │
│  │     tool: pods_ │     │       │       │ • events_list   │   │
│  │     params: ... │     │       │       └─────────────────┘   │
│  │ success_criteria│     │       │                              │
│  └─────────────────┘     └───────┘                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Currently Deployed MCP Servers

| Server | Namespace | Purpose | Endpoint |
|--------|-----------|---------|----------|
| `kubernetes-mcp-server` | ai-agents | Kubernetes operations | `kubernetes-mcp-server.ai-agents.svc.cluster.local:3000` |

## Kubernetes MCP Server Tools

The kubernetes-mcp-server provides these tools for skill actions:

### Pod Operations
| Tool | Description | Parameters |
|------|-------------|------------|
| `pods_list` | List pods in cluster | `namespace?`, `labelSelector?` |
| `pods_list_in_namespace` | List pods in specific namespace | `namespace`, `labelSelector?` |
| `pods_get` | Get pod details | `name`, `namespace?` |
| `pods_delete` | Delete a pod | `name`, `namespace?` |
| `pods_log` | Get pod logs | `name`, `namespace?`, `container?`, `tail?`, `previous?` |
| `pods_exec` | Execute command in pod | `name`, `command[]`, `namespace?`, `container?` |
| `pods_run` | Run a new pod | `image`, `name?`, `namespace?`, `port?` |
| `pods_top` | Get pod resource usage | `name?`, `namespace?`, `all_namespaces?`, `label_selector?` |

### Resource Operations
| Tool | Description | Parameters |
|------|-------------|------------|
| `resources_list` | List resources by kind | `apiVersion`, `kind`, `namespace?`, `labelSelector?` |
| `resources_get` | Get specific resource | `apiVersion`, `kind`, `name`, `namespace?` |
| `resources_create_or_update` | Create/update resource | `resource` (YAML/JSON) |
| `resources_delete` | Delete resource | `apiVersion`, `kind`, `name`, `namespace?` |
| `resources_scale` | Scale deployment/statefulset | `apiVersion`, `kind`, `name`, `namespace?`, `scale?` |

### Cluster Operations
| Tool | Description | Parameters |
|------|-------------|------------|
| `events_list` | List cluster events | `namespace?` |
| `namespaces_list` | List all namespaces | - |
| `nodes_top` | Get node resource usage | `name?`, `label_selector?` |
| `nodes_log` | Get node logs | `name`, `query`, `tailLines?` |
| `nodes_stats_summary` | Get node stats | `name` |

### Helm Operations
| Tool | Description | Parameters |
|------|-------------|------------|
| `helm_list` | List Helm releases | `namespace?`, `all_namespaces?` |
| `helm_install` | Install Helm chart | `chart`, `name?`, `namespace?`, `values?` |
| `helm_uninstall` | Uninstall Helm release | `name`, `namespace?` |

## Referencing MCP Tools in Skills

Skills reference MCP tools using the `MCPToolReference` schema:

```python
from core_agents.skills import MCPToolReference, SkillAction

action = SkillAction(
    description="Delete the pod to trigger recreation",
    mcp_tool=MCPToolReference(
        server="kubernetes-mcp-server",
        tool="pods_delete",
        params={
            "name": "$pod_name",      # Variable from context
            "namespace": "$namespace"  # Variable from context
        },
    ),
    timeout_seconds=30,
)
```

### Parameter Variables

Use `$variable_name` syntax for parameters that come from the issue context:

| Variable | Source | Description |
|----------|--------|-------------|
| `$pod_name` | Issue event | Name of the affected pod |
| `$namespace` | Issue event | Namespace of the resource |
| `$deployment_name` | Issue event | Name of the deployment |
| `$node_name` | Issue event | Name of the node |
| `$container_name` | Issue event | Container within the pod |

## Adding a New MCP Server

### Step 1: Deploy the MCP Server

Create a deployment in `gitops/apps/ai-agents/`:

```yaml
# gitops/apps/ai-agents/prometheus-mcp/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prometheus-mcp-server
  namespace: ai-agents
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: prometheus-mcp-server
  template:
    metadata:
      labels:
        app.kubernetes.io/name: prometheus-mcp-server
        app.kubernetes.io/component: mcp-server
    spec:
      containers:
        - name: prometheus-mcp
          image: your-registry/prometheus-mcp-server:latest
          ports:
            - containerPort: 3000
              name: mcp
          env:
            - name: PROMETHEUS_URL
              value: "http://prometheus.monitoring.svc.cluster.local:9090"
---
apiVersion: v1
kind: Service
metadata:
  name: prometheus-mcp-server
  namespace: ai-agents
spec:
  selector:
    app.kubernetes.io/name: prometheus-mcp-server
  ports:
    - port: 3000
      targetPort: mcp
```

### Step 2: Register in Agent Configuration

Update the agent's MCP client configuration:

```python
# In worker.py or agent initialization
MCP_SERVERS = {
    "kubernetes-mcp-server": "http://kubernetes-mcp-server.ai-agents.svc.cluster.local:3000",
    "prometheus-mcp-server": "http://prometheus-mcp-server.ai-agents.svc.cluster.local:3000",
}
```

### Step 3: Create Skills Using the New Server

```python
from core_agents.skills import Skill, SkillAction, MCPToolReference

capacity_skill = Skill(
    id="k8s-capacity-forecast",
    name="Forecast Resource Exhaustion",
    domain=SkillDomain.K8S,
    category=SkillCategory.DIAGNOSTIC,
    description="Query historical metrics to predict resource exhaustion",
    preconditions=[
        "Node or namespace specified",
        "High resource usage detected (>80%)",
    ],
    actions=[
        SkillAction(
            description="Query CPU usage trend",
            mcp_tool=MCPToolReference(
                server="prometheus-mcp-server",
                tool="query_range",
                params={
                    "query": "avg(node_cpu_seconds_total{node='$node_name'})",
                    "start": "$now - 7d",
                    "end": "$now",
                    "step": "1h",
                },
            ),
        ),
    ],
    success_criteria=["Trend data retrieved", "Forecast generated"],
    failure_handling="Fall back to current metrics only",
)
```

## Requesting New MCP Servers

When an agent identifies a capability gap, it can request a new MCP server:

```python
from core_agents.events import EventBus, EventType

async def request_mcp_server(bus: EventBus, server: str, reason: str):
    """Request deployment of a new MCP server."""
    await bus.publish(
        event_type=EventType.SYSTEM_MCP_SERVER_REQUESTED,
        payload={
            "server": server,
            "reason": reason,
            "requested_by": "k8s-explorer",
            "priority": "medium",
            "capabilities_needed": ["query", "query_range", "alerts"],
        },
        source="explorer-agent",
    )
```

This event is logged and can trigger alerts in Grafana for human review.

## MCP Server Health Checks

The agents check MCP server availability before executing skills:

```python
async def check_mcp_available(server: str) -> bool:
    """Check if an MCP server is available."""
    endpoint = MCP_SERVERS.get(server)
    if not endpoint:
        return False

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{endpoint}/health", timeout=5.0)
            return response.status_code == 200
    except Exception:
        return False
```

## Troubleshooting

### MCP Server Not Responding

1. Check pod status:
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl get pods -n ai-agents -l app.kubernetes.io/component=mcp-server
   ```

2. Check logs:
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl logs -n ai-agents deployment/kubernetes-mcp-server --tail=50
   ```

3. Test connectivity from agent pod:
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl exec -n ai-agents deployment/k8s-monitor -- \
     curl -s http://kubernetes-mcp-server:3000/health
   ```

### Skill Execution Fails

1. Check skill references correct server name
2. Verify MCP tool name matches server's tool list
3. Check parameter variables are populated in context
4. Review agent logs for MCP call details

### Adding New Tools to Existing Server

If you need a tool that doesn't exist, options are:

1. **Contribute upstream**: Submit PR to the MCP server project
2. **Fork and extend**: Create a custom build with additional tools
3. **Request new server**: If the capability is orthogonal, request a new specialized server

## Best Practices

1. **Never duplicate MCP functionality in skills** - Skills are knowledge, not code
2. **Use semantic tool names** - `pods_delete` not `delete_k8s_pod`
3. **Document parameter variables** - Make it clear what context is needed
4. **Set appropriate timeouts** - Network calls need realistic timeouts
5. **Handle server unavailability** - Skills should fail gracefully
6. **Monitor MCP call metrics** - Track `agent_mcp_calls_total` in Grafana
