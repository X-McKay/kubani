use crate::models::*;
use anyhow::Context;
use axum::Json;
use once_cell::sync::Lazy;
use reqwest::Client;

static HTTP_CLIENT: Lazy<Client> = Lazy::new(Client::new);

/// Get Temporal Web API URL from environment
fn get_temporal_web_url() -> String {
    std::env::var("TEMPORAL_WEB_URL")
        .unwrap_or_else(|_| "http://temporal-web.temporal.svc.cluster.local:8080".to_string())
}

/// Get Temporal namespace from environment
fn get_temporal_namespace() -> String {
    std::env::var("TEMPORAL_NAMESPACE").unwrap_or_else(|_| "default".to_string())
}

/// Get workflows directly from Temporal Web API
pub async fn get_workflows() -> Json<Vec<Workflow>> {
    match fetch_temporal_workflows().await {
        Ok(workflows) => Json(workflows),
        Err(e) => {
            tracing::warn!("Failed to fetch workflows from Temporal: {}", e);
            Json(vec![])
        }
    }
}

async fn fetch_temporal_workflows() -> anyhow::Result<Vec<Workflow>> {
    let base_url = get_temporal_web_url();
    let namespace = get_temporal_namespace();

    // Temporal UI API endpoint for listing workflows
    let url = format!(
        "{}/api/v1/namespaces/{}/workflows?status=",
        base_url, namespace
    );

    tracing::info!("Fetching workflows from Temporal Web API: {}", url);

    let response = HTTP_CLIENT
        .get(&url)
        .header("Accept", "application/json")
        .send()
        .await
        .context("Failed to connect to Temporal Web API")?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        tracing::error!("Temporal API error: {} - {}", status, body);
        anyhow::bail!("Temporal API returned {}: {}", status, body);
    }

    let data: serde_json::Value = response
        .json()
        .await
        .context("Failed to parse Temporal API response")?;

    tracing::debug!("Temporal API response: {:?}", data);

    let mut workflows = Vec::new();

    // Temporal UI API returns { "executions": [...] }
    if let Some(executions) = data.get("executions").and_then(|e| e.as_array()) {
        for exec in executions {
            // Extract execution info
            let execution = exec.get("execution");
            let workflow_id = execution
                .and_then(|e| e.get("workflowId"))
                .and_then(|v| v.as_str())
                .unwrap_or("unknown")
                .to_string();

            let run_id = execution
                .and_then(|e| e.get("runId"))
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();

            // Extract workflow type
            let workflow_type = exec
                .get("type")
                .and_then(|t| t.get("name"))
                .and_then(|v| v.as_str())
                .unwrap_or("unknown")
                .to_string();

            // Extract status (e.g., WORKFLOW_EXECUTION_STATUS_RUNNING)
            let raw_status = exec
                .get("status")
                .and_then(|v| v.as_str())
                .unwrap_or("UNKNOWN");

            let status = raw_status
                .replace("WORKFLOW_EXECUTION_STATUS_", "")
                .to_lowercase();

            // Extract timestamps
            let start_time = exec
                .get("startTime")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();

            let close_time = exec.get("closeTime").and_then(|v| v.as_str());

            // Extract task queue
            let task_queue = exec
                .get("taskQueue")
                .and_then(|v| v.as_str())
                .unwrap_or("default");

            // Extract agent name from workflow type (e.g., "k8s_monitor_workflow" -> "k8s-monitor")
            let agent = workflow_type
                .replace("_workflow", "")
                .replace("Workflow", "")
                .replace("_", "-")
                .to_string();

            // Calculate duration if we have both start and close times
            let duration = if let Some(close) = close_time {
                calculate_duration(&start_time, close)
            } else {
                None
            };

            workflows.push(Workflow {
                id: format!("{}:{}", workflow_id, run_id),
                name: workflow_type.clone(),
                agent,
                status,
                start_time,
                duration,
                user: "system".to_string(),
                description: format!("Workflow {} in task queue {}", workflow_id, task_queue),
                logs: None,
            });
        }
    }

    tracing::info!("Found {} workflows", workflows.len());
    Ok(workflows)
}

fn calculate_duration(start: &str, end: &str) -> Option<String> {
    use chrono::{DateTime, Utc};

    let start_time: DateTime<Utc> = start.parse().ok()?;
    let end_time: DateTime<Utc> = end.parse().ok()?;
    let duration = end_time.signed_duration_since(start_time);

    let secs = duration.num_seconds();
    if secs < 60 {
        Some(format!("{}s", secs))
    } else if secs < 3600 {
        Some(format!("{}m {}s", secs / 60, secs % 60))
    } else {
        Some(format!("{}h {}m", secs / 3600, (secs % 3600) / 60))
    }
}
