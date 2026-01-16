use crate::models::*;
use axum::{
    http::StatusCode,
    response::{
        sse::{Event, KeepAlive},
        Sse,
    },
    Json,
};
use futures::stream::{self, Stream};
use serde_json::json;
use std::{convert::Infallible, env};

/// State for accumulating partial SSE data across chunks
struct StreamState<S> {
    stream: S,
    buffer: String,
}

pub async fn chat_handler(
    Json(request): Json<ChatRequest>,
) -> Result<Sse<impl Stream<Item = Result<Event, Infallible>>>, StatusCode> {
    let vllm_url = env::var("VLLM_URL")
        .unwrap_or_else(|_| "http://llm-api.vllm.svc.cluster.local:8000/v1".to_string());
    let model_name = env::var("MODEL_NAME").unwrap_or_else(|_| "Qwen/Qwen3-14B".to_string());

    // Get Kubernetes tools
    let tools = get_kubernetes_tools();

    // Build the LLM request
    let llm_request = json!({
        "model": model_name,
        "messages": request.messages,
        "tools": tools,
        "stream": true,
        "temperature": 0.7,
        "max_tokens": 4096,
    });

    // Create HTTP client
    let client = reqwest::Client::new();

    // Make streaming request to vLLM
    let response = client
        .post(format!("{}/chat/completions", vllm_url))
        .json(&llm_request)
        .send()
        .await
        .map_err(|e| {
            tracing::error!("Failed to send chat request: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        tracing::error!("Chat request failed: {} - {}", status, body);
        return Err(StatusCode::INTERNAL_SERVER_ERROR);
    }

    // Stream the response, parsing vLLM's SSE format and forwarding properly
    let stream = response.bytes_stream();
    let state = StreamState {
        stream,
        buffer: String::new(),
    };

    let event_stream = stream::unfold(state, |mut state| async move {
        use futures::StreamExt;

        loop {
            // First, try to extract a complete SSE event from buffer
            if let Some(event_data) = extract_sse_data(&mut state.buffer) {
                // Forward the extracted JSON data as a proper SSE event
                return Some((Ok(Event::default().data(event_data)), state));
            }

            // Need more data from the stream
            match state.stream.next().await {
                Some(Ok(bytes)) => {
                    let text = String::from_utf8_lossy(&bytes);
                    state.buffer.push_str(&text);
                    // Continue loop to try extracting from updated buffer
                }
                Some(Err(e)) => {
                    tracing::error!("Stream error: {}", e);
                    return None;
                }
                None => {
                    // Stream ended - check if there's any remaining data
                    if let Some(event_data) = extract_sse_data(&mut state.buffer) {
                        return Some((Ok(Event::default().data(event_data)), state));
                    }
                    return None;
                }
            }
        }
    });

    Ok(Sse::new(event_stream).keep_alive(KeepAlive::default()))
}

/// Extract data from SSE format. vLLM sends lines like:
/// "data: {...json...}\n\n" or "data: [DONE]\n\n"
/// Returns the JSON/data portion without the "data: " prefix
fn extract_sse_data(buffer: &mut String) -> Option<String> {
    // Find the first "data: " prefix
    let data_prefix = "data: ";
    if let Some(start) = buffer.find(data_prefix) {
        let content_start = start + data_prefix.len();

        // Find the end of this line (newline character)
        if let Some(rel_newline) = buffer[content_start..].find('\n') {
            let content_end = content_start + rel_newline;

            // Extract the data (trim any trailing \r)
            let data = buffer[content_start..content_end].trim_end_matches('\r').to_string();

            // Remove this event from buffer (including the newline)
            let remove_end = content_end + 1;
            // Skip any additional newlines (SSE events are separated by blank lines)
            let final_end = buffer[remove_end..]
                .find(|c: char| c != '\n' && c != '\r')
                .map_or(buffer.len(), |p| remove_end + p);

            buffer.drain(start..final_end);
            return Some(data);
        }
    }

    None
}

fn get_kubernetes_tools() -> Vec<serde_json::Value> {
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
    ]
}
