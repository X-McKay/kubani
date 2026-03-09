//! Agentic loop executor for chat with tool execution
//!
//! This module handles the orchestration of LLM calls and tool execution:
//! 1. Call vLLM with tools
//! 2. Stream content to frontend
//! 3. Buffer and execute tool calls
//! 4. Feed results back to LLM
//! 5. Repeat until no more tool calls

use crate::mcp;
use crate::models::{ChatMessage, ToolCall, ToolFunction};
use futures::stream::{self, Stream};
use serde::Serialize;
use serde_json::{json, Value};
use std::convert::Infallible;
use std::env;
use tokio::sync::mpsc;

/// Maximum number of agentic loop iterations to prevent infinite loops
const MAX_ITERATIONS: usize = 10;

/// Events sent to frontend via SSE
#[derive(Debug, Clone, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum StreamEvent {
    /// Text content from the LLM
    Content { content: String },

    /// LLM requested a tool call (sent as tool call is being streamed)
    ToolCall {
        id: String,
        name: String,
        arguments: Value,
    },

    /// Tool execution is starting
    ToolStart { id: String, name: String },

    /// Tool execution completed successfully
    ToolComplete { id: String, result: String },

    /// Tool execution failed
    ToolError { id: String, error: String },

    /// Response complete
    Done,

    /// Fatal error occurred
    Error { message: String },
}

/// Accumulated tool call from streaming LLM response
#[derive(Debug, Clone)]
struct AccumulatedToolCall {
    id: String,
    name: String,
    arguments: String,
}

/// Agent configuration for chat
#[derive(Debug, Clone)]
pub struct AgentConfig {
    pub system_prompt: Option<String>,
    pub tools: Vec<Value>,
}

/// System prompts for different agents
pub const DYNAMIC_AGENT_PROMPT: &str = r#"You are Kubani, an intelligent AI assistant for Kubernetes cluster management.

You have access to tools for querying and managing the cluster. When users ask about the cluster state, use the available tools to gather accurate, real-time information.

Guidelines:
- Use tools to get current cluster state rather than making assumptions
- Be concise and actionable in your responses
- Format data clearly using tables or lists when appropriate
- If a tool call fails, explain what happened and suggest alternatives
- For complex queries, break them down into multiple tool calls if needed

Available capabilities:
- List and inspect pods across namespaces
- Get pod logs for debugging
- Check node resource usage and status
- List any Kubernetes resource type"#;

pub const K8S_MONITOR_PROMPT: &str = r#"You are the Kubernetes Monitor agent, specialized in cluster health monitoring and diagnostics.

Your focus areas:
- Detecting and diagnosing pod failures and crashes
- Monitoring resource utilization across nodes
- Identifying potential issues before they become critical
- Providing remediation suggestions for common problems

When investigating issues:
1. First gather current state using available tools
2. Analyze the data for anomalies or problems
3. Provide clear diagnosis and actionable recommendations

Be proactive in identifying related issues that might not be immediately obvious."#;

/// Get agent configuration based on agent ID
pub fn get_agent_config(agent_id: &Option<String>) -> AgentConfig {
    let system_prompt = match agent_id.as_deref() {
        Some("k8s-monitor") => Some(K8S_MONITOR_PROMPT.to_string()),
        Some("dynamic") | None => Some(DYNAMIC_AGENT_PROMPT.to_string()),
        _ => Some(DYNAMIC_AGENT_PROMPT.to_string()), // Default for unknown agents
    };

    AgentConfig {
        system_prompt,
        tools: get_kubernetes_tools(),
    }
}

/// Fetch tools dynamically from MCP server and convert to OpenAI format
pub async fn get_dynamic_tools() -> Vec<Value> {
    match mcp::list_tools().await {
        Ok(mcp_tools) => {
            mcp_tools
                .into_iter()
                .filter_map(|tool| {
                    let name = tool.get("name")?.as_str()?;
                    let description = tool
                        .get("description")
                        .and_then(|d| d.as_str())
                        .unwrap_or("");
                    let input_schema = tool
                        .get("inputSchema")
                        .cloned()
                        .unwrap_or_else(|| json!({"type": "object", "properties": {}}));

                    Some(json!({
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": description,
                            "parameters": input_schema
                        }
                    }))
                })
                .collect()
        }
        Err(e) => {
            tracing::warn!("Failed to fetch dynamic tools: {}, using defaults", e);
            get_kubernetes_tools()
        }
    }
}

/// Get agent configuration with dynamic tool discovery
pub async fn get_agent_config_dynamic(agent_id: &Option<String>) -> AgentConfig {
    let system_prompt = match agent_id.as_deref() {
        Some("k8s-monitor") => Some(K8S_MONITOR_PROMPT.to_string()),
        Some("dynamic") | None => Some(DYNAMIC_AGENT_PROMPT.to_string()),
        _ => Some(DYNAMIC_AGENT_PROMPT.to_string()),
    };

    // Try to get tools dynamically, fall back to static list
    let tools = get_dynamic_tools().await;

    AgentConfig {
        system_prompt,
        tools,
    }
}

/// Create the agentic loop stream that handles tool execution
pub fn create_agentic_stream(
    messages: Vec<ChatMessage>,
    config: AgentConfig,
) -> impl Stream<Item = Result<axum::response::sse::Event, Infallible>> {
    let (tx, rx) = mpsc::channel::<StreamEvent>(100);

    // Spawn the agentic loop in a background task
    tokio::spawn(async move {
        if let Err(e) = run_agentic_loop(messages, config, tx.clone()).await {
            let _ = tx
                .send(StreamEvent::Error {
                    message: e.to_string(),
                })
                .await;
        }
        let _ = tx.send(StreamEvent::Done).await;
    });

    // Convert receiver to stream
    let stream = tokio_stream::wrappers::ReceiverStream::new(rx);

    stream::unfold(stream, |mut stream| async move {
        use tokio_stream::StreamExt;
        match stream.next().await {
            Some(event) => {
                let json = serde_json::to_string(&event).unwrap_or_default();
                let sse_event = axum::response::sse::Event::default().data(json);
                Some((Ok(sse_event), stream))
            }
            None => None,
        }
    })
}

/// Run the agentic loop until completion or max iterations
async fn run_agentic_loop(
    mut messages: Vec<ChatMessage>,
    config: AgentConfig,
    tx: mpsc::Sender<StreamEvent>,
) -> anyhow::Result<()> {
    let vllm_url = env::var("VLLM_URL")
        .unwrap_or_else(|_| "http://llm-api.vllm.svc.cluster.local:8000/v1".to_string());
    let model_name = env::var("MODEL_NAME").unwrap_or_else(|_| "Qwen3.5-9B-NVFP4".to_string());

    // Add system prompt if configured
    if let Some(system_prompt) = &config.system_prompt {
        // Insert system message at the beginning if not already present
        if messages.first().map(|m| m.role.as_str()) != Some("system") {
            messages.insert(
                0,
                ChatMessage {
                    role: "system".to_string(),
                    content: system_prompt.clone(),
                    tool_calls: None,
                    tool_call_id: None,
                },
            );
        }
    }

    for iteration in 0..MAX_ITERATIONS {
        tracing::debug!("Agentic loop iteration {}", iteration);

        // Call vLLM and stream response
        let (content, tool_calls) =
            stream_llm_response(&vllm_url, &model_name, &messages, &config.tools, &tx).await?;

        // If no tool calls, we're done
        if tool_calls.is_empty() {
            tracing::debug!("No tool calls, loop complete");
            break;
        }

        // Execute tool calls
        let tool_results = execute_tool_calls(&tool_calls, &tx).await;

        // Build assistant message with tool calls
        let assistant_tool_calls: Vec<ToolCall> = tool_calls
            .iter()
            .map(|tc| ToolCall {
                id: tc.id.clone(),
                call_type: "function".to_string(),
                function: ToolFunction {
                    name: tc.name.clone(),
                    arguments: tc.arguments.clone(),
                },
            })
            .collect();

        messages.push(ChatMessage {
            role: "assistant".to_string(),
            content: content.unwrap_or_default(),
            tool_calls: Some(assistant_tool_calls),
            tool_call_id: None,
        });

        // Add tool result messages
        for (tc, result) in tool_calls.iter().zip(tool_results.iter()) {
            let result_content = match result {
                Ok(r) => r.clone(),
                Err(e) => format!("Error: {}", e),
            };

            messages.push(ChatMessage {
                role: "tool".to_string(),
                content: result_content,
                tool_calls: None,
                tool_call_id: Some(tc.id.clone()),
            });
        }
    }

    Ok(())
}

/// Stream LLM response and collect tool calls
async fn stream_llm_response(
    vllm_url: &str,
    model_name: &str,
    messages: &[ChatMessage],
    tools: &[Value],
    tx: &mpsc::Sender<StreamEvent>,
) -> anyhow::Result<(Option<String>, Vec<AccumulatedToolCall>)> {
    let client = reqwest::Client::new();

    let llm_request = json!({
        "model": model_name,
        "messages": messages,
        "tools": tools,
        "stream": true,
        "temperature": 0.7,
        "max_tokens": 4096,
    });

    let response = client
        .post(format!("{}/chat/completions", vllm_url))
        .json(&llm_request)
        .send()
        .await?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        anyhow::bail!("LLM request failed: {} - {}", status, body);
    }

    let mut content = String::new();
    let mut tool_calls: Vec<AccumulatedToolCall> = Vec::new();
    let mut buffer = String::new();

    let mut stream = response.bytes_stream();
    use futures::StreamExt;

    while let Some(chunk) = stream.next().await {
        let bytes = chunk?;
        let text = String::from_utf8_lossy(&bytes);
        buffer.push_str(&text);

        // Process complete SSE events from buffer
        while let Some(data) = extract_sse_data(&mut buffer) {
            if data == "[DONE]" {
                continue;
            }

            // Parse the SSE data as JSON
            if let Ok(parsed) = serde_json::from_str::<Value>(&data) {
                if let Some(choices) = parsed.get("choices").and_then(|c| c.as_array()) {
                    if let Some(choice) = choices.first() {
                        if let Some(delta) = choice.get("delta") {
                            // Handle content
                            if let Some(c) = delta.get("content").and_then(|c| c.as_str()) {
                                if !c.is_empty() {
                                    content.push_str(c);
                                    let _ = tx
                                        .send(StreamEvent::Content {
                                            content: c.to_string(),
                                        })
                                        .await;
                                }
                            }

                            // Handle tool calls
                            if let Some(tcs) = delta.get("tool_calls").and_then(|t| t.as_array()) {
                                for tc in tcs {
                                    let index =
                                        tc.get("index").and_then(|i| i.as_u64()).unwrap_or(0)
                                            as usize;

                                    // Ensure we have enough entries
                                    while tool_calls.len() <= index {
                                        tool_calls.push(AccumulatedToolCall {
                                            id: String::new(),
                                            name: String::new(),
                                            arguments: String::new(),
                                        });
                                    }

                                    // Update tool call fields
                                    if let Some(id) = tc.get("id").and_then(|i| i.as_str()) {
                                        tool_calls[index].id = id.to_string();
                                    }

                                    if let Some(function) = tc.get("function") {
                                        if let Some(name) =
                                            function.get("name").and_then(|n| n.as_str())
                                        {
                                            tool_calls[index].name = name.to_string();
                                        }

                                        if let Some(args) =
                                            function.get("arguments").and_then(|a| a.as_str())
                                        {
                                            tool_calls[index].arguments.push_str(args);
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // Send tool_call events for each accumulated tool call
    for tc in &tool_calls {
        if !tc.id.is_empty() && !tc.name.is_empty() {
            let args: Value = serde_json::from_str(&tc.arguments).unwrap_or(json!({}));
            let _ = tx
                .send(StreamEvent::ToolCall {
                    id: tc.id.clone(),
                    name: tc.name.clone(),
                    arguments: args,
                })
                .await;
        }
    }

    let content_result = if content.is_empty() {
        None
    } else {
        Some(content)
    };

    // Filter out incomplete tool calls
    let complete_tool_calls: Vec<AccumulatedToolCall> = tool_calls
        .into_iter()
        .filter(|tc| !tc.id.is_empty() && !tc.name.is_empty())
        .collect();

    Ok((content_result, complete_tool_calls))
}

/// Maximum number of retries for transient tool failures
const MAX_TOOL_RETRIES: usize = 3;

/// Tool execution timeout in seconds
const TOOL_TIMEOUT_SECS: u64 = 30;

/// Execute tool calls via MCP and send progress events
async fn execute_tool_calls(
    tool_calls: &[AccumulatedToolCall],
    tx: &mpsc::Sender<StreamEvent>,
) -> Vec<anyhow::Result<String>> {
    let mut results = Vec::with_capacity(tool_calls.len());

    for tc in tool_calls {
        // Send start event
        let _ = tx
            .send(StreamEvent::ToolStart {
                id: tc.id.clone(),
                name: tc.name.clone(),
            })
            .await;

        // Parse arguments
        let args: Value = serde_json::from_str(&tc.arguments).unwrap_or(json!({}));

        // Execute tool with retry logic
        let result = execute_tool_with_retry(&tc.name, args, MAX_TOOL_RETRIES).await;

        match &result {
            Ok(r) => {
                let _ = tx
                    .send(StreamEvent::ToolComplete {
                        id: tc.id.clone(),
                        result: r.clone(),
                    })
                    .await;
            }
            Err(e) => {
                let _ = tx
                    .send(StreamEvent::ToolError {
                        id: tc.id.clone(),
                        error: e.to_string(),
                    })
                    .await;
            }
        }

        results.push(result);
    }

    results
}

/// Execute a single tool with retry logic and timeout
async fn execute_tool_with_retry(
    name: &str,
    args: Value,
    max_retries: usize,
) -> anyhow::Result<String> {
    let mut last_error = None;

    for attempt in 0..max_retries {
        if attempt > 0 {
            tracing::debug!("Retrying tool {} (attempt {}/{})", name, attempt + 1, max_retries);
            // Exponential backoff: 100ms, 200ms, 400ms...
            tokio::time::sleep(tokio::time::Duration::from_millis(100 * (1 << attempt))).await;
        }

        // Execute with timeout
        let result = tokio::time::timeout(
            tokio::time::Duration::from_secs(TOOL_TIMEOUT_SECS),
            mcp::call_tool(name, args.clone()),
        )
        .await;

        match result {
            Ok(Ok(response)) => return Ok(response),
            Ok(Err(e)) => {
                // Check if this is a retryable error
                let error_str = e.to_string();
                if is_retryable_error(&error_str) {
                    tracing::warn!("Tool {} failed with retryable error: {}", name, error_str);
                    last_error = Some(e);
                    continue;
                }
                // Non-retryable error, return immediately
                return Err(e);
            }
            Err(_) => {
                // Timeout
                tracing::warn!("Tool {} timed out after {}s", name, TOOL_TIMEOUT_SECS);
                last_error = Some(anyhow::anyhow!("Tool execution timed out after {}s", TOOL_TIMEOUT_SECS));
                continue;
            }
        }
    }

    Err(last_error.unwrap_or_else(|| anyhow::anyhow!("Tool execution failed after {} retries", max_retries)))
}

/// Determine if an error is retryable (transient network issues, etc.)
fn is_retryable_error(error: &str) -> bool {
    let retryable_patterns = [
        "connection refused",
        "connection reset",
        "timeout",
        "temporarily unavailable",
        "service unavailable",
        "500",
        "502",
        "503",
        "504",
    ];

    let error_lower = error.to_lowercase();
    retryable_patterns.iter().any(|p| error_lower.contains(p))
}

/// Extract data from SSE format
fn extract_sse_data(buffer: &mut String) -> Option<String> {
    let data_prefix = "data: ";
    if let Some(start) = buffer.find(data_prefix) {
        let content_start = start + data_prefix.len();

        if let Some(rel_newline) = buffer[content_start..].find('\n') {
            let content_end = content_start + rel_newline;
            let data = buffer[content_start..content_end]
                .trim_end_matches('\r')
                .to_string();

            let remove_end = content_end + 1;
            let final_end = buffer[remove_end..]
                .find(|c: char| c != '\n' && c != '\r')
                .map_or(buffer.len(), |p| remove_end + p);

            buffer.drain(start..final_end);
            return Some(data);
        }
    }
    None
}

/// Get Kubernetes tools definitions for LLM
fn get_kubernetes_tools() -> Vec<Value> {
    vec![
        json!({
            "type": "function",
            "function": {
                "name": "pods_list",
                "description": "List all pods in the cluster, optionally filtered by namespace or label selector",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "namespace": {
                            "type": "string",
                            "description": "Namespace to list pods from (optional, lists all if not provided)"
                        },
                        "labelSelector": {
                            "type": "string",
                            "description": "Label selector to filter pods (e.g., 'app=nginx')"
                        }
                    }
                }
            }
        }),
        json!({
            "type": "function",
            "function": {
                "name": "pods_get",
                "description": "Get detailed information about a specific pod",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the pod"
                        },
                        "namespace": {
                            "type": "string",
                            "description": "Namespace of the pod (defaults to 'default')"
                        }
                    },
                    "required": ["name"]
                }
            }
        }),
        json!({
            "type": "function",
            "function": {
                "name": "pods_log",
                "description": "Get logs from a pod",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the pod"
                        },
                        "namespace": {
                            "type": "string",
                            "description": "Namespace of the pod"
                        },
                        "container": {
                            "type": "string",
                            "description": "Container name (optional)"
                        },
                        "tail": {
                            "type": "integer",
                            "description": "Number of lines to tail (optional)"
                        }
                    },
                    "required": ["name"]
                }
            }
        }),
        json!({
            "type": "function",
            "function": {
                "name": "nodes_top",
                "description": "Get resource usage metrics for cluster nodes",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        }),
        json!({
            "type": "function",
            "function": {
                "name": "resources_list",
                "description": "List Kubernetes resources of any kind",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "apiVersion": {
                            "type": "string",
                            "description": "API version (e.g., 'v1', 'apps/v1')"
                        },
                        "kind": {
                            "type": "string",
                            "description": "Resource kind (e.g., 'Pod', 'Deployment', 'Service')"
                        },
                        "namespace": {
                            "type": "string",
                            "description": "Namespace to list from (optional)"
                        }
                    },
                    "required": ["apiVersion", "kind"]
                }
            }
        }),
        json!({
            "type": "function",
            "function": {
                "name": "namespaces_list",
                "description": "List all namespaces in the cluster",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        }),
        json!({
            "type": "function",
            "function": {
                "name": "events_list",
                "description": "List Kubernetes events, optionally filtered by namespace",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "namespace": {
                            "type": "string",
                            "description": "Namespace to list events from (optional)"
                        }
                    }
                }
            }
        }),
    ]
}
