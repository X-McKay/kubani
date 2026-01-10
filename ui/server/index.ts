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

// Types for chat
interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
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

// System prompts for different agents
const AGENT_SYSTEM_PROMPTS: Record<string, string> = {
  "k8s-monitor": `You are a Kubernetes cluster monitoring and remediation assistant. You help users understand their cluster health, diagnose issues with pods and services, and can suggest or perform automated remediation actions.

Your capabilities include:
- Checking overall cluster health (nodes, pods, services)
- Diagnosing specific pod issues
- Suggesting and performing remediation actions
- Explaining Kubernetes concepts and best practices

When discussing cluster issues, be specific about namespaces, pod names, and resource types. Provide actionable guidance.`,

  "news-monitor": `You are an AI news monitoring assistant. You help users stay informed about the latest developments in artificial intelligence, machine learning, and related technologies.

Your capabilities include:
- Summarizing recent AI news and developments
- Creating personalized news digests
- Analyzing trends in AI research and industry
- Explaining complex AI concepts in accessible terms`,

  "backup-agent": `You are a backup and disaster recovery assistant. You help users manage their data backup strategies and ensure business continuity.

Your capabilities include:
- Monitoring backup job status
- Verifying backup integrity
- Suggesting backup schedule optimizations
- Assisting with disaster recovery planning`,

  "general": `You are Kubani, an AI assistant for managing and monitoring Kubernetes clusters. You can help with:
- Understanding cluster health and status
- Diagnosing and resolving issues
- Explaining Kubernetes concepts
- Providing best practices and recommendations

Be helpful, concise, and technically accurate.`,
};

async function startServer() {
  const app = express();
  const server = createServer(app);

  // Parse JSON bodies
  app.use(express.json());

  // API Routes - must come before static file serving

  // Health check
  app.get("/api/health", (_req: Request, res: Response) => {
    res.json({ status: "ok", timestamp: new Date().toISOString() });
  });

  // Get available agents
  app.get("/api/agents", async (_req: Request, res: Response) => {
    try {
      // Try to fetch from registry
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
        // Fallback to default agents
        res.json(getDefaultAgents());
      }
    } catch {
      // Return default agents if registry is unavailable
      res.json(getDefaultAgents());
    }
  });

  // Chat endpoint - streams responses from vLLM
  app.post("/api/chat", async (req: Request, res: Response) => {
    try {
      const { messages, agentId, stream = true }: ChatRequest = req.body;

      if (!messages || !Array.isArray(messages)) {
        res.status(400).json({ error: "messages array is required" });
        return;
      }

      // Get system prompt for the agent
      const systemPrompt = AGENT_SYSTEM_PROMPTS[agentId || "general"] || AGENT_SYSTEM_PROMPTS["general"];

      // Prepare messages with system prompt
      const fullMessages: ChatMessage[] = [
        { role: "system", content: systemPrompt },
        ...messages,
      ];

      // Make request to vLLM
      const vllmResponse = await fetch(`${VLLM_URL}/chat/completions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: MODEL_NAME,
          messages: fullMessages,
          stream,
          temperature: 0.7,
          max_tokens: 2048,
        }),
      });

      if (!vllmResponse.ok) {
        const error = await vllmResponse.text();
        console.error("vLLM error:", error);
        res.status(500).json({ error: "Failed to get response from LLM" });
        return;
      }

      if (stream && vllmResponse.body) {
        // Set up SSE headers for streaming
        res.setHeader("Content-Type", "text/event-stream");
        res.setHeader("Cache-Control", "no-cache");
        res.setHeader("Connection", "keep-alive");

        // Stream the response
        const reader = vllmResponse.body.getReader();
        const decoder = new TextDecoder();

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            // Forward SSE data directly
            res.write(chunk);
          }
        } finally {
          res.end();
        }
      } else {
        // Non-streaming response
        const data = await vllmResponse.json();
        res.json({
          content: data.choices?.[0]?.message?.content || "",
          role: "assistant",
        });
      }
    } catch (error) {
      console.error("Chat error:", error);
      res.status(500).json({ error: "Internal server error" });
    }
  });

  // Serve static files from dist/public in production
  const staticPath =
    process.env.NODE_ENV === "production"
      ? path.resolve(__dirname, "public")
      : path.resolve(__dirname, "..", "dist", "public");

  app.use(express.static(staticPath));

  // Handle client-side routing - serve index.html for all non-API routes
  app.get("*", (_req: Request, res: Response) => {
    res.sendFile(path.join(staticPath, "index.html"));
  });

  const port = process.env.PORT || 3000;

  server.listen(port, () => {
    console.log(`Server running on http://localhost:${port}/`);
    console.log(`Registry URL: ${REGISTRY_URL}`);
    console.log(`vLLM URL: ${VLLM_URL}`);
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
