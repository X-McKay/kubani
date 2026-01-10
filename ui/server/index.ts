import express, { Request, Response } from "express";
import { createServer } from "http";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Environment configuration
const REGISTRY_URL = process.env.REGISTRY_URL || "http://metadata-registry.ai-agents.svc.cluster.local:8000";
const VLLM_URL = process.env.VLLM_URL || "http://llm-api.vllm.svc.cluster.local:8000/v1";
const MODEL_NAME = process.env.MODEL_NAME || "Qwen/Qwen3-14B";
const K8S_MCP_URL = process.env.K8S_MCP_URL || "http://kubernetes-mcp-server.ai-agents.svc.cluster.local:8080";

// Types for chat
interface ChatMessage {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
}

interface ChatRequest {
  messages: ChatMessage[];
  agentId?: string;
  stream?: boolean;
}

interface Agent {
  id: string;
  name: string;
  description: string;
  status: "ready" | "busy" | "offline";
  capabilities: Array<{
    name: string;
    description: string;
  }>;
}

interface ToolCall {
  id: string;
  type: "function";
  function: {
    name: string;
    arguments: string;
  };
}

interface OpenAITool {
  type: "function";
  function: {
    name: string;
    description: string;
    parameters: Record<string, unknown>;
  };
}

interface MCPTool {
  name: string;
  description?: string;
  inputSchema?: Record<string, unknown>;
}

// MCP Session Manager - handles Streamable HTTP transport session lifecycle
class MCPSessionManager {
  private sessionId: string | null = null;
  private initialized = false;
  private mcpUrl: string;
  private requestId = 0;

  constructor(mcpUrl: string) {
    this.mcpUrl = mcpUrl;
  }

  private getNextId(): number {
    return ++this.requestId;
  }

  // Parse SSE response to extract JSON-RPC data
  private parseSSEResponse(sseText: string): unknown {
    const lines = sseText.split("\n");
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const jsonStr = line.slice(6);
        try {
          return JSON.parse(jsonStr);
        } catch {
          // Continue looking for valid JSON
        }
      }
    }
    // Try parsing as plain JSON (non-SSE response)
    try {
      return JSON.parse(sseText);
    } catch {
      return null;
    }
  }

  // Initialize MCP session
  async initialize(): Promise<boolean> {
    if (this.initialized && this.sessionId) {
      return true;
    }

    try {
      console.log("Initializing MCP session...");
      const response = await fetch(`${this.mcpUrl}/mcp`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json, text/event-stream",
        },
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: this.getNextId(),
          method: "initialize",
          params: {
            protocolVersion: "2025-03-26",
            capabilities: {},
            clientInfo: {
              name: "kubani-ui",
              version: "1.0.0",
            },
          },
        }),
      });

      if (!response.ok) {
        console.error(`MCP initialize failed: ${response.status} ${response.statusText}`);
        return false;
      }

      // Get session ID from header
      const sessionId = response.headers.get("Mcp-Session-Id");
      if (sessionId) {
        this.sessionId = sessionId;
        console.log(`MCP session established: ${sessionId.slice(0, 20)}...`);
      }

      // Parse response
      const text = await response.text();
      const data = this.parseSSEResponse(text) as { result?: { protocolVersion?: string } };

      if (data?.result?.protocolVersion) {
        console.log(`MCP protocol version: ${data.result.protocolVersion}`);
        this.initialized = true;
        return true;
      }

      console.error("MCP initialize response missing result:", text.slice(0, 200));
      return false;
    } catch (error) {
      console.error("MCP initialize error:", error);
      return false;
    }
  }

  // Call an MCP tool
  async callTool(name: string, args: Record<string, unknown>): Promise<string> {
    // Ensure session is initialized
    if (!this.initialized) {
      const ok = await this.initialize();
      if (!ok) {
        return JSON.stringify({ error: "Failed to initialize MCP session" });
      }
    }

    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
      };

      if (this.sessionId) {
        headers["Mcp-Session-Id"] = this.sessionId;
      }

      const response = await fetch(`${this.mcpUrl}/mcp`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: this.getNextId(),
          method: "tools/call",
          params: {
            name,
            arguments: args,
          },
        }),
      });

      // Handle session expiry - reinitialize and retry
      if (response.status === 404) {
        console.log("MCP session expired, reinitializing...");
        this.initialized = false;
        this.sessionId = null;
        const ok = await this.initialize();
        if (!ok) {
          return JSON.stringify({ error: "Failed to reinitialize MCP session" });
        }
        // Retry the call
        return this.callTool(name, args);
      }

      if (!response.ok) {
        return JSON.stringify({ error: `Tool call failed: ${response.status} ${response.statusText}` });
      }

      // Parse response
      const text = await response.text();
      const data = this.parseSSEResponse(text) as {
        error?: { message?: string };
        result?: { content?: Array<{ text?: string }> };
      } | null;

      if (!data) {
        console.error(`Failed to parse MCP response for ${name}:`, text.slice(0, 200));
        return JSON.stringify({ error: "Failed to parse MCP response" });
      }

      if (data.error) {
        return JSON.stringify({ error: data.error.message || "Tool call failed" });
      }

      // Extract content from MCP response
      const content = data.result?.content;
      if (Array.isArray(content)) {
        return content.map((c) => c.text || "").join("\n");
      }
      return JSON.stringify(data.result || {});
    } catch (error) {
      console.error(`Error calling MCP tool ${name}:`, error);
      return JSON.stringify({ error: `Failed to call tool: ${error}` });
    }
  }

  // Close session
  async close(): Promise<void> {
    if (this.sessionId) {
      try {
        await fetch(`${this.mcpUrl}/mcp`, {
          method: "DELETE",
          headers: {
            "Mcp-Session-Id": this.sessionId,
          },
        });
      } catch {
        // Ignore close errors
      }
      this.sessionId = null;
      this.initialized = false;
    }
  }
}

// Global MCP session manager
let mcpSession: MCPSessionManager | null = null;

function getMCPSession(): MCPSessionManager {
  if (!mcpSession) {
    mcpSession = new MCPSessionManager(K8S_MCP_URL);
  }
  return mcpSession;
}

// Helper to strip <think>...</think> blocks from content
function stripThinkingBlocks(content: string): string {
  return content.replace(/<think>[\s\S]*?<\/think>\s*/gi, "").trim();
}

// Kubernetes tools - these match the kubernetes-mcp-server tools
function getKubernetesTools(): OpenAITool[] {
  return [
    {
      type: "function",
      function: {
        name: "pods_list",
        description: "List all pods in the cluster, optionally filtered by namespace or label selector",
        parameters: {
          type: "object",
          properties: {
            namespace: { type: "string", description: "Namespace to list pods from (optional, lists all if not provided)" },
            labelSelector: { type: "string", description: "Label selector to filter pods (e.g., 'app=nginx')" },
          },
        },
      },
    },
    {
      type: "function",
      function: {
        name: "pods_get",
        description: "Get detailed information about a specific pod",
        parameters: {
          type: "object",
          properties: {
            name: { type: "string", description: "Name of the pod" },
            namespace: { type: "string", description: "Namespace of the pod" },
          },
          required: ["name"],
        },
      },
    },
    {
      type: "function",
      function: {
        name: "pods_log",
        description: "Get logs from a pod",
        parameters: {
          type: "object",
          properties: {
            name: { type: "string", description: "Name of the pod" },
            namespace: { type: "string", description: "Namespace of the pod" },
            container: { type: "string", description: "Container name (optional)" },
            tail: { type: "integer", description: "Number of lines to return from the end (default 100)" },
          },
          required: ["name"],
        },
      },
    },
    {
      type: "function",
      function: {
        name: "namespaces_list",
        description: "List all namespaces in the cluster",
        parameters: { type: "object", properties: {} },
      },
    },
    {
      type: "function",
      function: {
        name: "events_list",
        description: "List Kubernetes events, optionally filtered by namespace",
        parameters: {
          type: "object",
          properties: {
            namespace: { type: "string", description: "Namespace to list events from (optional)" },
          },
        },
      },
    },
    {
      type: "function",
      function: {
        name: "nodes_top",
        description: "Get resource consumption (CPU/memory) for nodes",
        parameters: {
          type: "object",
          properties: {
            name: { type: "string", description: "Name of a specific node (optional)" },
          },
        },
      },
    },
    {
      type: "function",
      function: {
        name: "pods_top",
        description: "Get resource consumption (CPU/memory) for pods",
        parameters: {
          type: "object",
          properties: {
            namespace: { type: "string", description: "Namespace to list pod metrics from" },
            all_namespaces: { type: "boolean", description: "List from all namespaces (default true)" },
          },
        },
      },
    },
    {
      type: "function",
      function: {
        name: "resources_list",
        description: "List Kubernetes resources by type (e.g., Deployments, Services)",
        parameters: {
          type: "object",
          properties: {
            apiVersion: { type: "string", description: "API version (e.g., 'apps/v1', 'v1')" },
            kind: { type: "string", description: "Resource kind (e.g., 'Deployment', 'Service')" },
            namespace: { type: "string", description: "Namespace (optional)" },
          },
          required: ["apiVersion", "kind"],
        },
      },
    },
  ];
}

// System prompts for different agents
const AGENT_SYSTEM_PROMPTS: Record<string, string> = {
  "k8s-monitor": `/no_think
You are a Kubernetes cluster monitoring and remediation assistant with access to real cluster data. You can query the actual cluster state using the available tools.

When users ask about cluster health, pods, services, or other Kubernetes resources, USE THE TOOLS to get real data. Don't make up information.

Your capabilities include:
- Checking real cluster health (nodes, pods, services) using tools
- Getting actual pod logs and events
- Diagnosing specific issues with real data
- Explaining Kubernetes concepts and best practices

Always use tools to answer questions about the cluster state. Keep responses concise and well-structured.`,

  "news-monitor": `/no_think
You are an AI news monitoring assistant. You help users stay informed about the latest developments in artificial intelligence, machine learning, and related technologies.

Your capabilities include:
- Summarizing recent AI news and developments
- Creating personalized news digests
- Analyzing trends in AI research and industry
- Explaining complex AI concepts in accessible terms

Keep responses concise and well-organized.`,

  "backup-agent": `/no_think
You are a backup and disaster recovery assistant. You help users manage their data backup strategies and ensure business continuity.

Your capabilities include:
- Monitoring backup job status
- Verifying backup integrity
- Suggesting backup schedule optimizations
- Assisting with disaster recovery planning

Be concise and provide actionable recommendations.`,

  "general": `/no_think
You are Kubani, an AI assistant for managing and monitoring Kubernetes clusters. You have access to tools that can query the actual cluster state.

Use the available tools to answer questions about:
- Cluster health and status
- Pod and service information
- Logs and events
- Resource utilization

Be helpful, concise, and technically accurate. Always use tools to get real data when asked about the cluster.`,
};

async function startServer() {
  const app = express();
  const server = createServer(app);

  // Parse JSON bodies
  app.use(express.json());

  // Health check
  app.get("/api/health", (_req: Request, res: Response) => {
    res.json({ status: "ok", timestamp: new Date().toISOString() });
  });

  // Get available agents
  app.get("/api/agents", async (_req: Request, res: Response) => {
    try {
      const response = await fetch(`${REGISTRY_URL}/api/v1/agents`);
      if (response.ok) {
        const data = await response.json();
        const agents: Agent[] = data.map((agent: Record<string, unknown>) => ({
          id: agent.id,
          name: agent.name || agent.id,
          description: agent.description || "",
          status: "ready",
          capabilities: agent.capabilities || [],
        }));
        res.json(agents);
      } else {
        res.json(getDefaultAgents());
      }
    } catch {
      res.json(getDefaultAgents());
    }
  });

  // Get available tools
  app.get("/api/tools", (_req: Request, res: Response) => {
    const tools = getKubernetesTools();
    res.json(tools.map(t => ({
      name: t.function.name,
      description: t.function.description,
    })));
  });

  // ============================================
  // MONITORING ENDPOINTS - Real cluster data
  // ============================================

  // Get cluster nodes with metrics
  app.get("/api/monitoring/nodes", async (_req: Request, res: Response) => {
    try {
      const mcp = getMCPSession();

      // Get nodes list
      const nodesResult = await mcp.callTool("resources_list", {
        apiVersion: "v1",
        kind: "Node"
      });

      // Get node metrics
      const metricsResult = await mcp.callTool("nodes_top", {});

      let nodes: Array<{
        name: string;
        status: string;
        role: string;
        cpu: number;
        memory: number;
        pods: number;
        ip: string;
      }> = [];

      try {
        const nodesData = JSON.parse(nodesResult);
        const metricsData = JSON.parse(metricsResult);

        // Build metrics lookup
        const metricsLookup: Record<string, { cpuPercent: number; memoryPercent: number }> = {};
        if (metricsData?.nodes) {
          for (const metric of metricsData.nodes) {
            metricsLookup[metric.name] = {
              cpuPercent: metric.cpuPercent || 0,
              memoryPercent: metric.memoryPercent || 0,
            };
          }
        }

        if (nodesData?.items) {
          nodes = nodesData.items.map((node: Record<string, unknown>) => {
            const metadata = node.metadata as Record<string, unknown> || {};
            const status = node.status as Record<string, unknown> || {};
            const conditions = (status.conditions as Array<{ type: string; status: string }>) || [];
            const addresses = (status.addresses as Array<{ type: string; address: string }>) || [];
            const labels = (metadata.labels as Record<string, string>) || {};

            const name = (metadata.name as string) || "unknown";
            const readyCondition = conditions.find(c => c.type === "Ready");
            const nodeStatus = readyCondition?.status === "True" ? "Ready" : "NotReady";
            const internalIP = addresses.find(a => a.type === "InternalIP")?.address || "";

            // Determine role from labels
            let role = "worker";
            if (labels["node-role.kubernetes.io/control-plane"] !== undefined) {
              role = "control-plane";
            } else if (labels["node-role.kubernetes.io/master"] !== undefined) {
              role = "control-plane";
            } else if (labels["nvidia.com/gpu"] || labels["gpu"] === "true") {
              role = "gpu-worker";
            }

            const metrics = metricsLookup[name] || { cpuPercent: 0, memoryPercent: 0 };

            return {
              name,
              status: nodeStatus,
              role,
              cpu: Math.round(metrics.cpuPercent),
              memory: Math.round(metrics.memoryPercent),
              pods: 0, // Will be filled in below
              ip: internalIP,
            };
          });
        }

        // Get pod counts per node
        const podsResult = await mcp.callTool("pods_list", {});
        try {
          const podsData = JSON.parse(podsResult);
          if (podsData?.items) {
            const podCountByNode: Record<string, number> = {};
            for (const pod of podsData.items) {
              const spec = pod.spec as Record<string, unknown> || {};
              const nodeName = spec.nodeName as string;
              if (nodeName) {
                podCountByNode[nodeName] = (podCountByNode[nodeName] || 0) + 1;
              }
            }
            // Update node pod counts
            for (const node of nodes) {
              node.pods = podCountByNode[node.name] || 0;
            }
          }
        } catch {
          // Continue with zeros for pod counts
        }

      } catch (e) {
        console.error("Failed to parse nodes data:", e);
      }

      res.json(nodes);
    } catch (error) {
      console.error("Error fetching nodes:", error);
      res.status(500).json({ error: "Failed to fetch nodes" });
    }
  });

  // Get namespaces with pod counts
  app.get("/api/monitoring/namespaces", async (_req: Request, res: Response) => {
    try {
      const mcp = getMCPSession();

      // Get namespaces
      const nsResult = await mcp.callTool("namespaces_list", {});

      let namespaces: Array<{
        name: string;
        running: number;
        total: number;
        status: string;
      }> = [];

      try {
        const nsData = JSON.parse(nsResult);

        if (nsData?.items) {
          // Get all pods to count by namespace
          const podsResult = await mcp.callTool("pods_list", {});
          const podsData = JSON.parse(podsResult);

          // Count pods per namespace
          const podsByNs: Record<string, { running: number; total: number }> = {};
          if (podsData?.items) {
            for (const pod of podsData.items) {
              const metadata = pod.metadata as Record<string, unknown> || {};
              const status = pod.status as Record<string, unknown> || {};
              const ns = (metadata.namespace as string) || "default";
              const phase = (status.phase as string) || "";

              if (!podsByNs[ns]) {
                podsByNs[ns] = { running: 0, total: 0 };
              }
              podsByNs[ns].total++;
              if (phase === "Running") {
                podsByNs[ns].running++;
              }
            }
          }

          namespaces = nsData.items.map((ns: Record<string, unknown>) => {
            const metadata = ns.metadata as Record<string, unknown> || {};
            const name = (metadata.name as string) || "";
            const counts = podsByNs[name] || { running: 0, total: 0 };

            let status = "healthy";
            if (counts.total > 0 && counts.running < counts.total) {
              status = "degraded";
            }

            return {
              name,
              running: counts.running,
              total: counts.total,
              status,
            };
          });

          // Filter out system namespaces with no pods and sort
          namespaces = namespaces
            .filter(ns => ns.total > 0 || ["default", "ai-agents", "monitoring", "databases"].includes(ns.name))
            .sort((a, b) => b.total - a.total)
            .slice(0, 10); // Limit to top 10
        }
      } catch (e) {
        console.error("Failed to parse namespaces data:", e);
      }

      res.json(namespaces);
    } catch (error) {
      console.error("Error fetching namespaces:", error);
      res.status(500).json({ error: "Failed to fetch namespaces" });
    }
  });

  // Get recent cluster events
  app.get("/api/monitoring/events", async (_req: Request, res: Response) => {
    try {
      const mcp = getMCPSession();

      const eventsResult = await mcp.callTool("events_list", {});

      let events: Array<{
        time: string;
        type: string;
        reason: string;
        message: string;
        namespace: string;
      }> = [];

      try {
        const eventsData = JSON.parse(eventsResult);

        if (eventsData?.items) {
          // Sort by lastTimestamp descending and take most recent
          const sortedEvents = eventsData.items
            .filter((e: Record<string, unknown>) => e.lastTimestamp || e.eventTime)
            .sort((a: Record<string, unknown>, b: Record<string, unknown>) => {
              const timeA = new Date((a.lastTimestamp as string) || (a.eventTime as string) || 0).getTime();
              const timeB = new Date((b.lastTimestamp as string) || (b.eventTime as string) || 0).getTime();
              return timeB - timeA;
            })
            .slice(0, 20);

          events = sortedEvents.map((event: Record<string, unknown>) => {
            const metadata = event.metadata as Record<string, unknown> || {};
            const timestamp = (event.lastTimestamp as string) || (event.eventTime as string) || "";

            // Calculate relative time
            let timeAgo = "unknown";
            if (timestamp) {
              const eventTime = new Date(timestamp).getTime();
              const now = Date.now();
              const diffMs = now - eventTime;
              const diffMins = Math.floor(diffMs / 60000);

              if (diffMins < 1) {
                timeAgo = "just now";
              } else if (diffMins < 60) {
                timeAgo = `${diffMins} min ago`;
              } else if (diffMins < 1440) {
                timeAgo = `${Math.floor(diffMins / 60)} hr ago`;
              } else {
                timeAgo = `${Math.floor(diffMins / 1440)} days ago`;
              }
            }

            return {
              time: timeAgo,
              type: (event.type as string) || "Normal",
              reason: (event.reason as string) || "",
              message: (event.message as string) || "",
              namespace: (metadata.namespace as string) || "",
            };
          });
        }
      } catch (e) {
        console.error("Failed to parse events data:", e);
      }

      res.json(events);
    } catch (error) {
      console.error("Error fetching events:", error);
      res.status(500).json({ error: "Failed to fetch events" });
    }
  });

  // Get services with status
  app.get("/api/monitoring/services", async (_req: Request, res: Response) => {
    try {
      const mcp = getMCPSession();

      // Get all deployments to check ready replicas
      const deploymentsResult = await mcp.callTool("resources_list", {
        apiVersion: "apps/v1",
        kind: "Deployment",
      });

      // Get all services
      const servicesResult = await mcp.callTool("resources_list", {
        apiVersion: "v1",
        kind: "Service",
      });

      let services: Array<{
        name: string;
        namespace: string;
        ready: string;
        status: string;
        type: string;
      }> = [];

      try {
        const deploymentsData = JSON.parse(deploymentsResult);
        const servicesData = JSON.parse(servicesResult);

        // Build deployment status lookup
        const deploymentStatus: Record<string, { ready: number; desired: number }> = {};
        if (deploymentsData?.items) {
          for (const dep of deploymentsData.items) {
            const metadata = dep.metadata as Record<string, unknown> || {};
            const status = dep.status as Record<string, unknown> || {};
            const spec = dep.spec as Record<string, unknown> || {};
            const name = metadata.name as string;
            const ns = metadata.namespace as string;
            const key = `${ns}/${name}`;

            deploymentStatus[key] = {
              ready: (status.readyReplicas as number) || 0,
              desired: (spec.replicas as number) || 1,
            };
          }
        }

        if (servicesData?.items) {
          services = servicesData.items
            .filter((svc: Record<string, unknown>) => {
              const metadata = svc.metadata as Record<string, unknown> || {};
              const name = metadata.name as string;
              // Filter out kubernetes internal services
              return name !== "kubernetes";
            })
            .map((svc: Record<string, unknown>) => {
              const metadata = svc.metadata as Record<string, unknown> || {};
              const spec = svc.spec as Record<string, unknown> || {};
              const name = (metadata.name as string) || "";
              const namespace = (metadata.namespace as string) || "";
              const svcType = (spec.type as string) || "ClusterIP";

              // Try to find matching deployment
              const depKey = `${namespace}/${name}`;
              const depStatus = deploymentStatus[depKey];

              let ready = "1/1";
              let status = "healthy";

              if (depStatus) {
                ready = `${depStatus.ready}/${depStatus.desired}`;
                if (depStatus.ready < depStatus.desired) {
                  status = depStatus.ready === 0 ? "unhealthy" : "degraded";
                }
              }

              return {
                name,
                namespace,
                ready,
                status,
                type: svcType,
              };
            })
            .slice(0, 20); // Limit to 20 services
        }
      } catch (e) {
        console.error("Failed to parse services data:", e);
      }

      res.json(services);
    } catch (error) {
      console.error("Error fetching services:", error);
      res.status(500).json({ error: "Failed to fetch services" });
    }
  });

  // ============================================
  // REGISTRY ENDPOINTS - Real cluster data
  // ============================================

  // Get MCP servers (from deployments in ai-agents namespace with mcp label)
  app.get("/api/registry/mcp-servers", async (_req: Request, res: Response) => {
    try {
      // For now, return the kubernetes MCP server info and any discovered ones
      const servers = [
        {
          id: "kubernetes-mcp",
          name: "Kubernetes MCP Server",
          description: "Provides Kubernetes cluster management tools",
          transport: "streamable-http",
          status: "active",
          capabilities: ["tools", "resources"],
          tools: getKubernetesTools().length,
        },
      ];

      // TODO: Discover additional MCP servers from cluster

      res.json(servers);
    } catch (error) {
      console.error("Error fetching MCP servers:", error);
      res.status(500).json({ error: "Failed to fetch MCP servers" });
    }
  });

  // Get available models from vLLM
  app.get("/api/registry/models", async (_req: Request, res: Response) => {
    try {
      const response = await fetch(`${VLLM_URL}/models`);

      if (response.ok) {
        const data = await response.json();
        const models = (data.data || []).map((model: Record<string, unknown>) => ({
          id: model.id,
          name: String(model.id).split("/").pop() || model.id,
          type: String(model.id).toLowerCase().includes("embed") ? "embeddings" : "general",
          provider: "local",
          status: "loaded",
          contextLength: model.max_model_len || 0,
        }));
        res.json(models);
      } else {
        // Return default model info
        res.json([{
          id: MODEL_NAME,
          name: MODEL_NAME.split("/").pop() || MODEL_NAME,
          type: "general",
          provider: "local",
          status: "loaded",
          contextLength: 131072,
        }]);
      }
    } catch (error) {
      console.error("Error fetching models:", error);
      // Return configured model as fallback
      res.json([{
        id: MODEL_NAME,
        name: MODEL_NAME.split("/").pop() || MODEL_NAME,
        type: "general",
        provider: "local",
        status: "unknown",
        contextLength: 131072,
      }]);
    }
  });

  // Get skills from skills directory (placeholder - would scan filesystem)
  app.get("/api/registry/skills", async (_req: Request, res: Response) => {
    // For now, return skills based on available tools
    const skills = [
      {
        id: "analyze-pod-logs",
        name: "Analyze Pod Logs",
        domain: "kubernetes",
        category: "diagnostics",
        confidence: 0.92,
        successRate: 94,
        status: "validated",
      },
      {
        id: "list-resources",
        name: "List Kubernetes Resources",
        domain: "kubernetes",
        category: "monitoring",
        confidence: 0.95,
        successRate: 98,
        status: "validated",
      },
      {
        id: "check-cluster-health",
        name: "Check Cluster Health",
        domain: "kubernetes",
        category: "diagnostics",
        confidence: 0.90,
        successRate: 92,
        status: "validated",
      },
    ];

    res.json(skills);
  });

  // Chat endpoint with tool calling support
  app.post("/api/chat", async (req: Request, res: Response) => {
    try {
      const { messages, agentId, stream = false }: ChatRequest = req.body;

      if (!messages || !Array.isArray(messages)) {
        res.status(400).json({ error: "messages array is required" });
        return;
      }

      // Get system prompt and tools
      const systemPrompt = AGENT_SYSTEM_PROMPTS[agentId || "general"] || AGENT_SYSTEM_PROMPTS["general"];
      const tools = agentId === "k8s-monitor" || agentId === "general" ? getKubernetesTools() : [];

      // Build conversation with system prompt
      const conversation: ChatMessage[] = [
        { role: "system", content: systemPrompt },
        ...messages,
      ];

      // Tool calling loop (max 5 iterations to prevent infinite loops)
      let iterations = 0;
      const maxIterations = 5;
      let finalContent = "";

      while (iterations < maxIterations) {
        iterations++;

        const requestBody: Record<string, unknown> = {
          model: MODEL_NAME,
          messages: conversation,
          temperature: 0.7,
          max_tokens: 2048,
          stream: false, // Don't stream during tool calls
        };

        if (tools.length > 0) {
          requestBody.tools = tools;
          requestBody.tool_choice = "auto";
        }

        const vllmResponse = await fetch(`${VLLM_URL}/chat/completions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(requestBody),
        });

        if (!vllmResponse.ok) {
          const error = await vllmResponse.text();
          console.error("vLLM error:", error);
          res.status(500).json({ error: "Failed to get response from LLM" });
          return;
        }

        const data = await vllmResponse.json();
        const choice = data.choices?.[0];
        const message = choice?.message;

        if (!message) {
          res.status(500).json({ error: "Invalid response from LLM" });
          return;
        }

        // Check if the model wants to call tools
        if (message.tool_calls && message.tool_calls.length > 0) {
          // Add assistant message with tool calls to conversation
          conversation.push({
            role: "assistant",
            content: message.content || "",
            tool_calls: message.tool_calls,
          });

          // Execute each tool call
          for (const toolCall of message.tool_calls) {
            console.log(`Executing tool: ${toolCall.function.name}`);
            let args = {};
            try {
              args = JSON.parse(toolCall.function.arguments || "{}");
            } catch {
              args = {};
            }

            const result = await getMCPSession().callTool(toolCall.function.name, args);

            // Add tool result to conversation
            conversation.push({
              role: "tool",
              content: result,
              tool_call_id: toolCall.id,
            });
          }

          // Continue the loop to get the final response
          continue;
        }

        // No tool calls, we have the final response
        finalContent = stripThinkingBlocks(message.content || "");
        break;
      }

      // Return the final response
      res.json({
        content: finalContent,
        role: "assistant",
      });

    } catch (error) {
      console.error("Chat error:", error);
      res.status(500).json({ error: "Internal server error" });
    }
  });

  // Serve static files with cache headers that prevent stale JS issues
  const staticPath =
    process.env.NODE_ENV === "production"
      ? path.resolve(__dirname, "public")
      : path.resolve(__dirname, "..", "dist", "public");

  // Static assets - use ETags for validation, short max-age for active development
  app.use(express.static(staticPath, {
    etag: true,
    lastModified: true,
    maxAge: "5m", // Short cache, but ETag prevents re-download if unchanged
    setHeaders: (res, filePath) => {
      // Never cache index.html - always fetch fresh to get new asset hashes
      if (filePath.endsWith("index.html")) {
        res.setHeader("Cache-Control", "no-cache, no-store, must-revalidate");
      }
    },
  }));

  // SPA fallback - always serve fresh index.html
  app.get("*", (_req: Request, res: Response) => {
    res.setHeader("Cache-Control", "no-cache, no-store, must-revalidate");
    res.sendFile(path.join(staticPath, "index.html"));
  });

  const port = process.env.PORT || 3000;

  // Log available Kubernetes tools
  const tools = getKubernetesTools();
  console.log(`Loaded ${tools.length} Kubernetes MCP tools`);

  // Pre-initialize MCP session
  getMCPSession().initialize().then((ok) => {
    if (ok) {
      console.log("MCP session pre-initialized successfully");
    } else {
      console.warn("Failed to pre-initialize MCP session (will retry on first tool call)");
    }
  }).catch((err) => {
    console.warn("MCP session pre-initialization error:", err);
  });

  server.listen(port, () => {
    console.log(`Server running on http://localhost:${port}/`);
    console.log(`Registry URL: ${REGISTRY_URL}`);
    console.log(`vLLM URL: ${VLLM_URL}`);
    console.log(`K8s MCP URL: ${K8S_MCP_URL}`);
  });
}

function getDefaultAgents(): Agent[] {
  return [
    {
      id: "k8s-monitor",
      name: "Kubernetes Monitor",
      description: "Monitors cluster health and performs automated remediation",
      status: "ready",
      capabilities: [
        { name: "cluster-health", description: "Check overall cluster health" },
        { name: "pod-diagnosis", description: "Diagnose issues with pods" },
        { name: "remediation", description: "Automated issue remediation" },
      ],
    },
    {
      id: "news-monitor",
      name: "AI News Monitor",
      description: "Tracks and summarizes AI news and developments",
      status: "ready",
      capabilities: [
        { name: "news-digest", description: "Generate personalized news digest" },
        { name: "trend-analysis", description: "Analyze AI trends" },
      ],
    },
    {
      id: "backup-agent",
      name: "Backup Agent",
      description: "Manages backup jobs and disaster recovery",
      status: "ready",
      capabilities: [
        { name: "backup-status", description: "Check backup job status" },
        { name: "verify-integrity", description: "Verify backup integrity" },
      ],
    },
  ];
}

startServer().catch(console.error);
