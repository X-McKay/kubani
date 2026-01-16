use crate::models::McpRequest;
use anyhow::{anyhow, Context, Result};
use reqwest::Client;
use serde_json::json;

/// MCP Transport type
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum McpTransport {
    /// HTTP transport using /mcp endpoint (kubernetes-mcp-server style)
    Http,
    /// SSE transport using /sse and /messages endpoints (FastMCP style)
    Sse,
}

pub struct McpSessionManager {
    mcp_url: String,
    transport: McpTransport,
    session_id: Option<String>,
    initialized: bool,
    request_id: u64,
    client: Client,
}

impl McpSessionManager {
    pub fn new(mcp_url: String) -> Self {
        Self::with_transport(mcp_url, McpTransport::Http)
    }

    pub fn with_transport(mcp_url: String, transport: McpTransport) -> Self {
        Self {
            mcp_url,
            transport,
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

    /// Get the endpoint URL for sending messages based on transport type
    fn get_message_endpoint(&self) -> String {
        match self.transport {
            McpTransport::Http => format!("{}/mcp", self.mcp_url),
            McpTransport::Sse => {
                if let Some(session_id) = &self.session_id {
                    format!("{}/messages?sessionId={}", self.mcp_url, session_id)
                } else {
                    format!("{}/messages", self.mcp_url)
                }
            }
        }
    }

    pub async fn initialize(&mut self) -> Result<bool> {
        if self.initialized && self.session_id.is_some() {
            return Ok(true);
        }

        tracing::info!("Initializing MCP session (transport: {:?})...", self.transport);

        // For SSE transport, first establish SSE connection to get session ID
        if self.transport == McpTransport::Sse {
            self.initialize_sse().await?;
        }

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

        let endpoint = self.get_message_endpoint();
        let response = self
            .client
            .post(&endpoint)
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

        // Get session ID from header (for HTTP transport)
        if self.transport == McpTransport::Http {
            if let Some(session_id) = response.headers().get("Mcp-Session-Id") {
                self.session_id = Some(session_id.to_str()?.to_string());
                tracing::info!("MCP session established: {:?}", self.session_id);
            }
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

    /// Initialize SSE connection to get session ID (for SSE transport)
    async fn initialize_sse(&mut self) -> Result<()> {
        tracing::info!("Establishing SSE connection to get session ID...");

        let response = self
            .client
            .get(format!("{}/sse", self.mcp_url))
            .header("Accept", "text/event-stream")
            .send()
            .await
            .context("Failed to establish SSE connection")?;

        if !response.status().is_success() {
            return Err(anyhow!("SSE connection failed: {}", response.status()));
        }

        // Read initial SSE events to get the endpoint/session info
        let text = response.text().await?;

        // Parse SSE events to find session ID or endpoint
        for line in text.lines() {
            if let Some(data) = line.strip_prefix("data: ") {
                if let Ok(json) = serde_json::from_str::<serde_json::Value>(data) {
                    // Look for endpoint event which contains session info
                    if let Some(endpoint) = json.get("endpoint").and_then(|e| e.as_str()) {
                        // Extract session ID from endpoint URL
                        if let Some(session_start) = endpoint.find("sessionId=") {
                            let session_id = &endpoint[session_start + 10..];
                            let session_id = session_id.split('&').next().unwrap_or(session_id);
                            self.session_id = Some(session_id.to_string());
                            tracing::info!("SSE session ID extracted: {:?}", self.session_id);
                            return Ok(());
                        }
                    }
                }
            }
        }

        // If we didn't get a session ID, generate one (some servers accept any ID)
        let session_id = uuid::Uuid::new_v4().to_string();
        self.session_id = Some(session_id.clone());
        tracing::info!("Generated session ID: {}", session_id);
        Ok(())
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

        let endpoint = self.get_message_endpoint();
        let mut req_builder = self
            .client
            .post(&endpoint)
            .header("Content-Type", "application/json")
            .header("Accept", "application/json, text/event-stream");

        // For HTTP transport, include session ID in header
        if self.transport == McpTransport::Http {
            if let Some(session_id) = &self.session_id {
                req_builder = req_builder.header("Mcp-Session-Id", session_id);
            }
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
