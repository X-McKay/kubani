mod session;

pub use session::{McpSessionManager, McpTransport};

use anyhow::Result;
use once_cell::sync::Lazy;
use std::sync::Arc;
use tokio::sync::Mutex;

// Global MCP session manager for Kubernetes (uses HTTP transport with /mcp endpoint)
static K8S_MCP_SESSION: Lazy<Arc<Mutex<McpSessionManager>>> = Lazy::new(|| {
    let url = std::env::var("K8S_MCP_URL")
        .unwrap_or_else(|_| "http://kubernetes-mcp-server.ai-agents.svc.cluster.local:8080".to_string());
    Arc::new(Mutex::new(McpSessionManager::new(url)))
});

// Global MCP session manager for Temporal (uses SSE transport with /sse endpoint)
static TEMPORAL_MCP_SESSION: Lazy<Arc<Mutex<McpSessionManager>>> = Lazy::new(|| {
    let url = std::env::var("TEMPORAL_MCP_URL")
        .unwrap_or_else(|_| "http://temporal-mcp.ai-agents.svc.cluster.local:8081".to_string());
    Arc::new(Mutex::new(McpSessionManager::with_transport(
        url,
        McpTransport::Sse,
    )))
});

pub async fn get_session() -> Arc<Mutex<McpSessionManager>> {
    Arc::clone(&K8S_MCP_SESSION)
}

pub async fn get_temporal_session() -> Arc<Mutex<McpSessionManager>> {
    Arc::clone(&TEMPORAL_MCP_SESSION)
}

pub async fn call_tool(name: &str, args: serde_json::Value) -> Result<String> {
    let session = get_session().await;
    let mut mgr = session.lock().await;
    mgr.call_tool(name, args).await
}

pub async fn call_temporal_tool(name: &str, args: serde_json::Value) -> Result<String> {
    let session = get_temporal_session().await;
    let mut mgr = session.lock().await;
    mgr.call_tool(name, args).await
}

pub async fn call_tools_parallel(
    calls: Vec<(&str, serde_json::Value)>,
) -> Result<Vec<Result<String>>> {
    let session = get_session().await;

    let futures: Vec<_> = calls
        .into_iter()
        .map(|(name, args)| {
            let session = Arc::clone(&session);
            async move {
                let mut mgr = session.lock().await;
                mgr.call_tool(name, args).await
            }
        })
        .collect();

    let results = futures::future::join_all(futures).await;
    Ok(results)
}

pub async fn list_tools() -> Result<Vec<serde_json::Value>> {
    let session = get_session().await;
    let mut mgr = session.lock().await;
    mgr.list_tools().await
}
