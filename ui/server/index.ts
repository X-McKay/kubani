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

  // Serve static files
  const staticPath =
    process.env.NODE_ENV === "production"
      ? path.resolve(__dirname, "public")
      : path.resolve(__dirname, "..", "dist", "public");

  app.use(express.static(staticPath));

  app.get("*", (_req: Request, res: Response) => {
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
