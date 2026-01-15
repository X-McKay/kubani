use crate::models::*;
use axum::{http::StatusCode, Json};
use std::env;

pub async fn get_agents() -> Result<Json<Vec<Agent>>, StatusCode> {
    let registry_url = env::var("REGISTRY_URL")
        .unwrap_or_else(|_| "http://metadata-registry.ai-agents.svc.cluster.local:8000".to_string());

    let client = reqwest::Client::new();
    let response = client
        .get(format!("{}/agents", registry_url))
        .send()
        .await
        .map_err(|e| {
            tracing::error!("Failed to fetch agents: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    if response.status().is_success() {
        let agents: Vec<Agent> = response.json().await.map_err(|e| {
            tracing::error!("Failed to parse agents response: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;
        Ok(Json(agents))
    } else {
        // Return empty list if registry is unavailable
        Ok(Json(vec![]))
    }
}

pub async fn get_mcp_servers() -> Result<Json<Vec<McpServer>>, StatusCode> {
    // For now, return the kubernetes MCP server info
    let servers = vec![McpServer {
        id: "kubernetes-mcp".to_string(),
        name: "Kubernetes MCP Server".to_string(),
        description: "Provides Kubernetes cluster management tools".to_string(),
        transport: "streamable-http".to_string(),
        status: "active".to_string(),
        capabilities: vec!["tools".to_string(), "resources".to_string()],
        tools: 15, // Approximate number of k8s tools
    }];

    Ok(Json(servers))
}

pub async fn get_models() -> Result<Json<Vec<Model>>, StatusCode> {
    let vllm_url = env::var("VLLM_URL")
        .unwrap_or_else(|_| "http://llm-api.vllm.svc.cluster.local:8000/v1".to_string());
    let model_name = env::var("MODEL_NAME").unwrap_or_else(|_| "Qwen/Qwen3-14B".to_string());

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
    // Placeholder skills based on available tools
    let skills = vec![
        Skill {
            id: "analyze-pod-logs".to_string(),
            name: "Analyze Pod Logs".to_string(),
            domain: "kubernetes".to_string(),
            category: "diagnostics".to_string(),
            confidence: 0.92,
            success_rate: 94,
            status: "validated".to_string(),
        },
        Skill {
            id: "list-resources".to_string(),
            name: "List Kubernetes Resources".to_string(),
            domain: "kubernetes".to_string(),
            category: "monitoring".to_string(),
            confidence: 0.95,
            success_rate: 98,
            status: "validated".to_string(),
        },
        Skill {
            id: "check-cluster-health".to_string(),
            name: "Check Cluster Health".to_string(),
            domain: "kubernetes".to_string(),
            category: "diagnostics".to_string(),
            confidence: 0.90,
            success_rate: 92,
            status: "validated".to_string(),
        },
    ];

    Ok(Json(skills))
}
