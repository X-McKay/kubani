/**
 * API client for Kubani backend services
 */

export interface Agent {
  id: string;
  name: string;
  description: string;
  status: "ready" | "busy" | "offline" | "healthy";
  capabilities: Array<{
    name: string;
    description: string;
  }>;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatRequest {
  messages: ChatMessage[];
  agentId?: string;
  stream?: boolean;
}

export interface ChatResponse {
  content: string;
  role: "assistant";
}

export interface StreamToolCall {
  index: number;
  id?: string;
  function?: {
    name?: string;
    arguments?: string;
  };
}

export interface StreamChunk {
  type: "content" | "tool_call" | "done";
  content?: string;
  toolCall?: StreamToolCall;
}

const API_BASE = "";

/**
 * Fetch available agents from the registry
 */
export async function fetchAgents(): Promise<Agent[]> {
  const response = await fetch(`${API_BASE}/api/agents`);
  if (!response.ok) {
    throw new Error(`Failed to fetch agents: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Send a chat message and get a response (may take time due to tool calls)
 */
export async function sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ...request, stream: false }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || `Chat request failed: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Fetch available MCP tools
 */
export async function fetchTools(): Promise<Array<{ name: string; description: string }>> {
  const response = await fetch(`${API_BASE}/api/tools`);
  if (!response.ok) {
    return [];
  }
  return response.json();
}

/**
 * Send a chat message and stream the response
 * Returns an async generator that yields content chunks (simple string version)
 */
export async function* streamChatMessage(
  request: ChatRequest
): AsyncGenerator<string, void, unknown> {
  for await (const chunk of streamChatMessageWithToolCalls(request)) {
    if (chunk.type === "content" && chunk.content) {
      yield chunk.content;
    }
  }
}

/**
 * Send a chat message and stream the response with tool call information
 * Returns an async generator that yields StreamChunk objects
 */
export async function* streamChatMessageWithToolCalls(
  request: ChatRequest
): AsyncGenerator<StreamChunk, void, unknown> {
  const response = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ...request, stream: true }),
  });

  if (!response.ok) {
    throw new Error(`Chat request failed: ${response.statusText}`);
  }

  if (!response.body) {
    throw new Error("No response body");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Process SSE events
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6);
          if (data === "[DONE]") {
            yield { type: "done" };
            return;
          }
          try {
            const json = JSON.parse(data);
            const delta = json.choices?.[0]?.delta;

            // Check for content
            if (delta?.content) {
              yield { type: "content", content: delta.content };
            }

            // Check for tool calls
            if (delta?.tool_calls) {
              for (const toolCall of delta.tool_calls) {
                yield {
                  type: "tool_call",
                  toolCall: {
                    index: toolCall.index,
                    id: toolCall.id,
                    function: toolCall.function
                  }
                };
              }
            }
          } catch {
            // Skip invalid JSON lines
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * Health check for the API
 */
export async function checkHealth(): Promise<{ status: string; timestamp: string }> {
  const response = await fetch(`${API_BASE}/api/health`);
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.statusText}`);
  }
  return response.json();
}
