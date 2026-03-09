use crate::models::*;
use axum::{http::StatusCode, Json};
use std::env;

/// Get available MCP tools (Kubernetes tools from kubernetes-mcp-server)
pub async fn get_tools() -> Json<Vec<Tool>> {
    let tools = vec![
        Tool {
            name: "pods_list".to_string(),
            description: "List all pods in the cluster, optionally filtered by namespace or label selector".to_string(),
        },
        Tool {
            name: "pods_get".to_string(),
            description: "Get detailed information about a specific pod".to_string(),
        },
        Tool {
            name: "pods_log".to_string(),
            description: "Get logs from a pod".to_string(),
        },
        Tool {
            name: "namespaces_list".to_string(),
            description: "List all namespaces in the cluster".to_string(),
        },
        Tool {
            name: "events_list".to_string(),
            description: "List Kubernetes events, optionally filtered by namespace".to_string(),
        },
        Tool {
            name: "nodes_top".to_string(),
            description: "Get resource consumption (CPU/memory) for nodes".to_string(),
        },
        Tool {
            name: "pods_top".to_string(),
            description: "Get resource consumption (CPU/memory) for pods".to_string(),
        },
        Tool {
            name: "resources_list".to_string(),
            description: "List Kubernetes resources by type (e.g., Deployments, Services)".to_string(),
        },
    ];

    Json(tools)
}

pub async fn get_agents() -> Result<Json<Vec<Agent>>, StatusCode> {
    let registry_url = env::var("REGISTRY_URL")
        .unwrap_or_else(|_| "http://metadata-registry.ai-agents.svc.cluster.local:8000".to_string());

    let client = reqwest::Client::new();
    let response = client
        .get(format!("{}/api/v1/agents", registry_url))
        .send()
        .await
        .map_err(|e| {
            tracing::error!("Failed to fetch agents: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    let mut agents: Vec<Agent> = if response.status().is_success() {
        response.json().await.map_err(|e| {
            tracing::error!("Failed to parse agents response: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?
    } else {
        tracing::warn!("Registry returned status {}: returning empty agents list", response.status());
        vec![]
    };

    // Append Nexus agent if gateway is configured and not already in list
    if env::var("NEXUS_GATEWAY_URL").is_ok() && !agents.iter().any(|a| a.id == "nexus") {
        agents.insert(
            0,
            Agent {
                id: "nexus".to_string(),
                name: "Nexus Agent".to_string(),
                description: "Conversational AI agent with tools, memory, and planning"
                    .to_string(),
                status: "ready".to_string(),
                version: None,
                capabilities: vec![],
            },
        );
    }

    Ok(Json(agents))
}

pub async fn get_mcp_servers() -> Result<Json<Vec<McpServer>>, StatusCode> {
    let registry_url = env::var("REGISTRY_URL")
        .unwrap_or_else(|_| "http://metadata-registry.ai-agents.svc.cluster.local:8000".to_string());

    let client = reqwest::Client::new();
    let response = client
        .get(format!("{}/api/v1/mcp/servers", registry_url))
        .send()
        .await
        .map_err(|e| {
            tracing::error!("Failed to fetch MCP servers: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    if response.status().is_success() {
        let servers: Vec<McpServer> = response.json().await.map_err(|e| {
            tracing::error!("Failed to parse MCP servers response: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;
        Ok(Json(servers))
    } else {
        tracing::warn!("Registry returned status {}: returning empty MCP servers list", response.status());
        Ok(Json(vec![]))
    }
}

pub async fn get_models() -> Result<Json<Vec<Model>>, StatusCode> {
    let vllm_url = env::var("VLLM_URL")
        .unwrap_or_else(|_| "http://llm-api.vllm.svc.cluster.local:8000/v1".to_string());
    let model_name = env::var("MODEL_NAME").unwrap_or_else(|_| "Qwen3.5-9B-NVFP4".to_string());

    let client = reqwest::Client::new();
    let response = client
        .get(format!("{}/models", vllm_url))
        .send()
        .await;

    if let Ok(resp) = response {
        if resp.status().is_success() {
            if let Ok(data) = resp.json::<serde_json::Value>().await {
                if let Some(models_array) = data.get("data").and_then(|d| d.as_array()) {
                    let models: Vec<Model> = models_array
                        .iter()
                        .map(|model| {
                            let id = model.get("id").and_then(|i| i.as_str()).unwrap_or(&model_name);
                            let name = id.split('/').last().unwrap_or(id);
                            let model_type = if id.to_lowercase().contains("embed") {
                                "embeddings"
                            } else {
                                "general"
                            };

                            Model {
                                id: id.to_string(),
                                name: name.to_string(),
                                model_type: model_type.to_string(),
                                provider: "local".to_string(),
                                status: "loaded".to_string(),
                                context_length: model
                                    .get("max_model_len")
                                    .and_then(|l| l.as_u64())
                                    .unwrap_or(131072) as u32,
                            }
                        })
                        .collect();

                    return Ok(Json(models));
                }
            }
        }
    }

    // Fallback to default model
    let default_model = Model {
        id: model_name.clone(),
        name: model_name.split('/').last().unwrap_or(&model_name).to_string(),
        model_type: "general".to_string(),
        provider: "local".to_string(),
        status: "loaded".to_string(),
        context_length: 131072,
    };

    Ok(Json(vec![default_model]))
}

pub async fn get_skills() -> Result<Json<Vec<Skill>>, StatusCode> {
    let registry_url = env::var("REGISTRY_URL")
        .unwrap_or_else(|_| "http://metadata-registry.ai-agents.svc.cluster.local:8000".to_string());

    let client = reqwest::Client::new();
    let response = client
        .get(format!("{}/api/v1/skills", registry_url))
        .send()
        .await
        .map_err(|e| {
            tracing::error!("Failed to fetch skills: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    if response.status().is_success() {
        let skills: Vec<Skill> = response.json().await.map_err(|e| {
            tracing::error!("Failed to parse skills response: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;
        Ok(Json(skills))
    } else {
        tracing::warn!("Registry returned status {}: returning empty skills list", response.status());
        Ok(Json(vec![]))
    }
}
