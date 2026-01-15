use crate::models::McpRequest;
use anyhow::{anyhow, Context, Result};
use reqwest::Client;
use serde_json::json;

pub struct McpSessionManager {
    mcp_url: String,
    session_id: Option<String>,
    initialized: bool,
    request_id: u64,
    client: Client,
}

impl McpSessionManager {
    pub fn new(mcp_url: String) -> Self {
        Self {
            mcp_url,
            session_id: None,
            initialized: false,
            request_id: 0,
            client: Client::new(),
        }
    }

    fn get_next_id(&mut self) -> u64 {
        self.request_id += 1;
        self.request_id
    }

    fn parse_sse_response(&self, text: &str) -> Result<serde_json::Value> {
        // Try to parse SSE format first
        for line in text.lines() {
            if let Some(data) = line.strip_prefix("data: ") {
                if let Ok(json) = serde_json::from_str(data) {
                    return Ok(json);
                }
            }
        }

        // Fallback to plain JSON
        serde_json::from_str(text).context("Failed to parse MCP response")
    }

    pub async fn initialize(&mut self) -> Result<bool> {
        if self.initialized && self.session_id.is_some() {
            return Ok(true);
        }

        tracing::info!("Initializing MCP session...");

        let request = McpRequest {
            jsonrpc: "2.0".to_string(),
            id: self.get_next_id(),
            method: "initialize".to_string(),
            params: json!({
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {
                    "name": "kubani-ui-rust",
                    "version": "1.0.0"
                }
            }),
        };

        let response = self
            .client
            .post(format!("{}/mcp", self.mcp_url))
            .header("Content-Type", "application/json")
            .header("Accept", "application/json, text/event-stream")
            .json(&request)
            .send()
            .await
            .context("Failed to send MCP initialize request")?;

        if !response.status().is_success() {
            return Err(anyhow!(
                "MCP initialize failed: {}",
                response.status()
            ));
        }

        // Get session ID from header
        if let Some(session_id) = response.headers().get("Mcp-Session-Id") {
            self.session_id = Some(session_id.to_str()?.to_string());
            tracing::info!("MCP session established: {:?}", self.session_id);
        }

        // Parse response
        let text = response.text().await?;
        let data = self.parse_sse_response(&text)?;

        if data.get("result").and_then(|r| r.get("protocolVersion")).is_some() {
            self.initialized = true;
            tracing::info!("MCP initialized successfully");
            return Ok(true);
        }

        Err(anyhow!("MCP initialize response missing result"))
    }

    pub async fn call_tool(&mut self, name: &str, args: serde_json::Value) -> Result<String> {
        // Ensure session is initialized
        if !self.initialized {
            self.initialize().await?;
        }

        let request = McpRequest {
            jsonrpc: "2.0".to_string(),
            id: self.get_next_id(),
            method: "tools/call".to_string(),
            params: json!({
                "name": name,
                "arguments": args
            }),
        };

        let mut req_builder = self
            .client
            .post(format!("{}/mcp", self.mcp_url))
            .header("Content-Type", "application/json")
            .header("Accept", "application/json, text/event-stream");

        if let Some(session_id) = &self.session_id {
            req_builder = req_builder.header("Mcp-Session-Id", session_id);
        }

        let response = req_builder
            .json(&request)
            .send()
            .await
            .context("Failed to send MCP tool call")?;

        // Handle session expiry - reinitialize and retry
        if response.status() == 404 {
            tracing::info!("MCP session expired, reinitializing...");
            self.initialized = false;
            self.session_id = None;
            self.initialize().await?;
            // Retry by creating a new request instead of recursing
            return Box::pin(self.call_tool(name, args)).await;
        }

        if !response.status().is_success() {
            return Err(anyhow!("Tool call failed: {}", response.status()));
        }

        // Parse response
        let text = response.text().await?;
        let data = self.parse_sse_response(&text)?;

        if let Some(error) = data.get("error") {
            return Err(anyhow!("Tool call error: {}", error));
        }

        // Extract content from MCP response
        if let Some(result) = data.get("result") {
            if let Some(content) = result.get("content").and_then(|c| c.as_array()) {
                let text_parts: Vec<String> = content
                    .iter()
                    .filter_map(|item| item.get("text").and_then(|t| t.as_str()))
                    .map(|s| s.to_string())
                    .collect();
                return Ok(text_parts.join("\n"));
            }
            return Ok(serde_json::to_string(result)?);
        }

        Err(anyhow!("Tool call response missing result"))
    }
}
