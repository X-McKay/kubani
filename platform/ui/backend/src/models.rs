use serde::{Deserialize, Serialize};

// Monitoring models
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClusterNode {
    pub name: String,
    pub status: String,
    pub role: String,
    pub cpu: u32,
    pub memory: u32,
    pub pods: u32,
    pub ip: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Namespace {
    pub name: String,
    pub running: u32,
    pub total: u32,
    pub status: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClusterEvent {
    pub namespace: String,
    #[serde(rename = "lastSeen")]
    pub last_seen: String,
    #[serde(rename = "type")]
    pub event_type: String,
    pub reason: String,
    pub object: String,
    pub message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Service {
    pub name: String,
    pub namespace: String,
    pub ready: String,
    pub status: String,
    #[serde(rename = "type")]
    pub service_type: String,
}

// Registry models - match the metadata-registry API response format
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Agent {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub description: String,
    pub status: String,
    #[serde(default)]
    pub version: Option<String>,
    #[serde(default)]
    pub capabilities: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct McpServer {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub description: String,
    pub transport: String,
    pub status: String,
    #[serde(default)]
    pub capabilities: Vec<String>,
    #[serde(skip_deserializing, default)]
    pub tools: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Model {
    pub id: String,
    pub name: String,
    #[serde(rename = "type")]
    pub model_type: String,
    pub provider: String,
    pub status: String,
    #[serde(rename = "contextLength")]
    pub context_length: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Skill {
    pub id: String,
    pub name: String,
    pub domain: String,
    pub category: String,
    #[serde(default)]
    pub confidence: f32,
    #[serde(default, rename = "success_count")]
    pub success_count: u32,
    #[serde(default, rename = "failure_count")]
    pub failure_count: u32,
    pub status: String,
}

// Chat models
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatMessage {
    pub role: String,
    pub content: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_calls: Option<Vec<ToolCall>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_call_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCall {
    pub id: String,
    #[serde(rename = "type")]
    pub call_type: String,
    pub function: ToolFunction,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolFunction {
    pub name: String,
    pub arguments: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ChatRequest {
    pub messages: Vec<ChatMessage>,
    #[serde(rename = "agentId")]
    pub agent_id: Option<String>,
    #[serde(default)]
    pub stream: bool,
}

// MCP models
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct McpRequest {
    pub jsonrpc: String,
    pub id: u64,
    pub method: String,
    pub params: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct McpResponse {
    pub jsonrpc: String,
    pub id: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<McpError>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct McpError {
    pub code: i32,
    pub message: String,
}

// Workflow models
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Workflow {
    pub id: String,
    pub name: String,
    pub agent: String,
    pub status: String,
    #[serde(rename = "startTime")]
    pub start_time: String,
    pub duration: Option<String>,
    pub user: String,
    pub description: String,
    pub logs: Option<Vec<String>>,
}

// Workflow detail models
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkflowDetail {
    pub id: String,
    pub run_id: Option<String>,
    pub workflow_type: String,
    pub status: String,
    #[serde(rename = "startTime")]
    pub start_time: Option<String>,
    #[serde(rename = "closeTime")]
    pub close_time: Option<String>,
    #[serde(rename = "taskQueue")]
    pub task_queue: String,
    pub duration: Option<String>,
    pub events: Vec<WorkflowEvent>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkflowEvent {
    #[serde(rename = "eventId")]
    pub event_id: i64,
    #[serde(rename = "eventType")]
    pub event_type: String,
    pub timestamp: Option<String>,
}

// Tool models
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Tool {
    pub name: String,
    pub description: String,
}
