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
                // FastMCP uses /messages/ with session_id (underscore)
                if let Some(session_id) = &self.session_id {
                    format!("{}/messages/?session_id={}", self.mcp_url, session_id)
                } else {
                    format!("{}/messages/", self.mcp_url)
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
        let mut req_builder = self
            .client
            .post(&endpoint)
            .header("Content-Type", "application/json")
            .header("Accept", "application/json, text/event-stream");

        // For SSE transport, use Host: localhost to bypass DNS rebinding protection
        if self.transport == McpTransport::Sse {
            req_builder = req_builder.header("Host", "localhost");
        }

        let response = req_builder
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
        use futures::StreamExt;

        tracing::info!("Establishing SSE connection to get session ID...");

        // Use Host: localhost to bypass FastMCP's DNS rebinding protection
        // FastMCP validates the Host header against allowed hosts, and using
        // "localhost" is always allowed by default
        let response = self
            .client
            .get(format!("{}/sse", self.mcp_url))
            .header("Accept", "text/event-stream")
            .header("Host", "localhost")
            .send()
            .await
            .context("Failed to establish SSE connection")?;

        if !response.status().is_success() {
            return Err(anyhow!("SSE connection failed: {}", response.status()));
        }

        // Read initial SSE events using streaming with timeout
        // SSE is a streaming protocol, so we read chunks until we get the session ID
        let mut stream = response.bytes_stream();
        let mut buffer = String::new();

        // Read chunks with a timeout - we only need the first few events
        let timeout = tokio::time::timeout(std::time::Duration::from_secs(3), async {
            while let Some(chunk) = stream.next().await {
                if let Ok(bytes) = chunk {
                    buffer.push_str(&String::from_utf8_lossy(&bytes));

                    // Check if we have the session ID in the buffer
                    for line in buffer.lines() {
                        if let Some(data) = line.strip_prefix("data: ") {
                            // Try to parse as JSON, but also handle plain endpoint paths
                            if data.contains("session_id=") {
                                // Extract session ID from endpoint URL
                                if let Some(session_start) = data.find("session_id=") {
                                    let session_id = &data[session_start + 11..];
                                    let session_id =
                                        session_id.split('&').next().unwrap_or(session_id);
                                    return Some(session_id.to_string());
                                }
                            }
                        }
                    }
                }
            }
            None
        })
        .await;

        match timeout {
            Ok(Some(session_id)) => {
                self.session_id = Some(session_id.clone());
                tracing::info!("SSE session ID extracted: {}", session_id);
                Ok(())
            }
            _ => {
                // If we didn't get a session ID, generate one (some servers accept any ID)
                let session_id = uuid::Uuid::new_v4().to_string();
                self.session_id = Some(session_id.clone());
                tracing::info!("Generated session ID (timeout or not found): {}", session_id);
                Ok(())
            }
        }
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

        // For SSE transport, use Host: localhost to bypass DNS rebinding protection
        if self.transport == McpTransport::Sse {
            req_builder = req_builder.header("Host", "localhost");
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

    /// List available tools from the MCP server
    pub async fn list_tools(&mut self) -> Result<Vec<serde_json::Value>> {
        self.initialize().await?;

        let request_id = self.get_next_id();
        let request = serde_json::json!({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/list",
            "params": {}
        });

        let endpoint = match self.transport {
            McpTransport::Http => format!("{}/mcp", self.mcp_url),
            McpTransport::Sse => {
                let session_id = self.session_id.as_ref().ok_or_else(|| anyhow!("No session ID"))?;
                format!("{}/messages/?session_id={}", self.mcp_url, session_id)
            }
        };

        let client = reqwest::Client::new();
        let mut req_builder = client.post(&endpoint);

        if self.transport == McpTransport::Http {
            if let Some(session_id) = &self.session_id {
                req_builder = req_builder.header("Mcp-Session-Id", session_id);
            }
        }

        if self.transport == McpTransport::Sse {
            req_builder = req_builder.header("Host", "localhost");
        }

        let response = req_builder
            .json(&request)
            .send()
            .await
            .context("Failed to send MCP tools/list request")?;

        if !response.status().is_success() {
            return Err(anyhow!("tools/list failed: {}", response.status()));
        }

        let text = response.text().await?;
        let data = self.parse_sse_response(&text)?;

        if let Some(error) = data.get("error") {
            return Err(anyhow!("tools/list error: {}", error));
        }

        if let Some(result) = data.get("result") {
            if let Some(tools) = result.get("tools").and_then(|t| t.as_array()) {
                return Ok(tools.clone());
            }
        }

        Ok(vec![])
    }
}
