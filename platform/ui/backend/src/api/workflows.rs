use crate::mcp;
use crate::models::*;
use axum::extract::Path;
use axum::Json;
use serde_json::json;

/// Get workflows from Temporal via MCP server
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
    tracing::info!("Fetching workflows from Temporal MCP server...");

    // Call list_workflows tool from Temporal MCP server
    let result = mcp::call_temporal_tool("list_workflows", json!({ "limit": 50 })).await?;

    tracing::debug!("Temporal MCP response: {}", result);

    // Parse the response
    let data: serde_json::Value = serde_json::from_str(&result)?;

    let mut workflows = Vec::new();

    if let Some(workflow_list) = data.get("workflows").and_then(|w| w.as_array()) {
        for wf in workflow_list {
            let workflow_id = wf
                .get("workflow_id")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown")
                .to_string();

            let workflow_type = wf
                .get("workflow_type")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown")
                .to_string();

            let status = wf
                .get("status")
                .and_then(|v| v.as_str())
                .map(|s| s.to_lowercase())
                .unwrap_or_else(|| "unknown".to_string());

            let start_time = wf
                .get("start_time")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();

            let close_time = wf.get("close_time").and_then(|v| v.as_str());

            let task_queue = wf
                .get("task_queue")
                .and_then(|v| v.as_str())
                .unwrap_or("default");

            // Extract agent name from workflow type (e.g., "k8s_monitor_workflow" -> "k8s-monitor")
            let agent = workflow_type
                .replace("_workflow", "")
                .replace("Workflow", "")
                .replace('_', "-")
                .to_string();

            // Calculate duration if we have both start and close times
            let duration = if let Some(close) = close_time {
                calculate_duration(&start_time, close)
            } else {
                None
            };

            workflows.push(Workflow {
                id: workflow_id.clone(),
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

    tracing::info!("Found {} workflows from Temporal MCP", workflows.len());
    Ok(workflows)
}

/// Get workflow detail from Temporal via MCP server
pub async fn get_workflow_detail(Path(workflow_id): Path<String>) -> Json<serde_json::Value> {
    match fetch_workflow_detail(&workflow_id).await {
        Ok(detail) => match serde_json::to_value(detail) {
            Ok(val) => Json(val),
            Err(e) => Json(json!({ "error": format!("Serialization error: {}", e) })),
        },
        Err(e) => {
            tracing::warn!("Failed to fetch workflow detail for {}: {}", workflow_id, e);
            Json(json!({ "error": format!("Failed to fetch workflow detail: {}", e) }))
        }
    }
}

async fn fetch_workflow_detail(workflow_id: &str) -> anyhow::Result<WorkflowDetail> {
    tracing::info!("Fetching workflow detail for {} from Temporal MCP server...", workflow_id);

    // Fetch workflow metadata and event history concurrently
    let (workflow_result, history_result) = tokio::join!(
        mcp::call_temporal_tool("get_workflow", json!({ "workflow_id": workflow_id })),
        mcp::call_temporal_tool("get_workflow_history", json!({ "workflow_id": workflow_id, "limit": 100 })),
    );

    let workflow_data: serde_json::Value = serde_json::from_str(&workflow_result?)?;
    let history_data: serde_json::Value = serde_json::from_str(&history_result?)?;

    let start_time = workflow_data
        .get("start_time")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());

    let close_time = workflow_data
        .get("close_time")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());

    let duration = match (&start_time, &close_time) {
        (Some(start), Some(close)) => calculate_duration(start, close),
        _ => None,
    };

    let events = history_data
        .get("events")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .map(|e| WorkflowEvent {
                    event_id: e.get("event_id").and_then(|v| v.as_i64()).unwrap_or(0),
                    event_type: e
                        .get("event_type")
                        .and_then(|v| v.as_str())
                        .unwrap_or("unknown")
                        .to_string(),
                    timestamp: e.get("timestamp").and_then(|v| v.as_str()).map(|s| s.to_string()),
                })
                .collect()
        })
        .unwrap_or_default();

    Ok(WorkflowDetail {
        id: workflow_data
            .get("workflow_id")
            .and_then(|v| v.as_str())
            .unwrap_or(workflow_id)
            .to_string(),
        run_id: workflow_data
            .get("run_id")
            .and_then(|v| v.as_str())
            .map(|s| s.to_string()),
        workflow_type: workflow_data
            .get("workflow_type")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown")
            .to_string(),
        status: workflow_data
            .get("status")
            .and_then(|v| v.as_str())
            .map(|s| s.to_lowercase())
            .unwrap_or_else(|| "unknown".to_string()),
        start_time,
        close_time,
        task_queue: workflow_data
            .get("task_queue")
            .and_then(|v| v.as_str())
            .unwrap_or("default")
            .to_string(),
        duration,
        events,
    })
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
