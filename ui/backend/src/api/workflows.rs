use crate::models::*;
use axum::Json;

/// Get workflows/tasks - placeholder endpoint
/// In the future this will connect to Temporal MCP
pub async fn get_workflows() -> Json<Vec<Workflow>> {
    // For now return an empty list - workflows will appear when Temporal is integrated
    Json(vec![])
}
