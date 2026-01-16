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
        tracing::error!("Chat request failed: {}", response.status());
        return Err(StatusCode::INTERNAL_SERVER_ERROR);
    }

    // Stream the response
    let stream = response.bytes_stream();
    let event_stream = stream::unfold(stream, |mut stream_state| async move {
        use futures::StreamExt;

        match stream_state.next().await {
            Some(Ok(bytes)) => {
                let text = String::from_utf8_lossy(&bytes);
                Some((Ok(Event::default().data(text.to_string())), stream_state))
            }
            Some(Err(e)) => {
                tracing::error!("Stream error: {}", e);
                None
            }
            None => None,
        }
    });

    Ok(Sse::new(event_stream).keep_alive(KeepAlive::default()))
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
