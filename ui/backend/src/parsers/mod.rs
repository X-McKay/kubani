use crate::models::*;
use regex::Regex;
use std::collections::HashMap;

/// Parse generic table output into a vector of HashMaps
pub fn parse_table_output(text: &str) -> Vec<HashMap<String, String>> {
    let lines: Vec<&str> = text.lines().collect();
    if lines.is_empty() {
        return vec![];
    }

    // First line is the header
    let header_line = lines[0];
    let headers: Vec<&str> = header_line.split_whitespace().collect();

    if headers.is_empty() {
        return vec![];
    }

    // Find column positions
    let mut col_positions: Vec<usize> = Vec::new();
    for header in &headers {
        if let Some(pos) = header_line.find(header) {
            col_positions.push(pos);
        }
    }
    col_positions.push(header_line.len());

    // Parse data rows
    let mut results = Vec::new();
    for line in lines.iter().skip(1) {
        if line.trim().is_empty() {
            continue;
        }

        let mut row = HashMap::new();
        for (i, header) in headers.iter().enumerate() {
            let start = col_positions[i];
            let end = if i + 1 < col_positions.len() {
                col_positions[i + 1]
            } else {
                line.len()
            };

            let value = if start < line.len() {
                let end = end.min(line.len());
                line[start..end].trim()
            } else {
                ""
            };

            row.insert(header.to_lowercase().replace("-", "_"), value.to_string());
        }
        results.push(row);
    }

    results
}

/// Parse nodes table into ClusterNode structs
pub fn parse_nodes_table(text: &str) -> Vec<ClusterNode> {
    let rows = parse_table_output(text);
    rows.into_iter()
        .map(|row| {
            let role = if row.get("roles").map(|s| s.as_str()).unwrap_or("") == "<none>" {
                "worker".to_string()
            } else {
                row.get("roles").cloned().unwrap_or_else(|| "worker".to_string())
            };

            ClusterNode {
                name: row.get("name").cloned().unwrap_or_default(),
                status: row.get("status").cloned().unwrap_or_else(|| "Unknown".to_string()),
                role,
                cpu: 0,
                memory: 0,
                pods: 0,
                ip: row.get("internal_ip")
                    .or_else(|| row.get("external_ip"))
                    .cloned()
                    .unwrap_or_default(),
            }
        })
        .collect()
}

/// Parse node metrics table
pub fn parse_node_metrics_table(text: &str) -> HashMap<String, (u32, u32)> {
    let rows = parse_table_output(text);
    let mut metrics = HashMap::new();

    for row in rows {
        if let Some(name) = row.get("name") {
            let cpu = parse_percentage(row.get("cpu_").unwrap_or(&String::new()));
            let memory = parse_percentage(row.get("memory_").unwrap_or(&String::new()));
            metrics.insert(name.clone(), (cpu, memory));
        }
    }

    metrics
}

/// Parse pods table
pub fn parse_pods_table(text: &str) -> Vec<HashMap<String, String>> {
    parse_table_output(text)
}

/// Parse namespaces table
pub fn parse_namespaces_table(text: &str) -> Vec<String> {
    let rows = parse_table_output(text);
    rows.into_iter()
        .filter_map(|row| row.get("name").cloned())
        .collect()
}

/// Parse services table
pub fn parse_services_table(text: &str) -> Vec<HashMap<String, String>> {
    parse_table_output(text)
}

/// Parse deployments table
pub fn parse_deployments_table(text: &str) -> Vec<HashMap<String, String>> {
    parse_table_output(text)
}

/// Parse events YAML output
pub fn parse_events_yaml(text: &str) -> Vec<ClusterEvent> {
    let mut events = Vec::new();
    let event_blocks: Vec<&str> = text.split("- InvolvedObject:").collect();

    for block in event_blocks.iter().skip(1) {
        let mut event = ClusterEvent {
            namespace: String::new(),
            last_seen: String::new(),
            event_type: "Normal".to_string(),
            reason: String::new(),
            object: String::new(),
            message: String::new(),
        };

        // Extract fields using regex
        if let Some(caps) = Regex::new(r"Kind:\s*(\S+)").unwrap().captures(block) {
            event.object = caps[1].to_string();
        }
        if let Some(caps) = Regex::new(r"Namespace:\s*(\S+)").unwrap().captures(block) {
            event.namespace = caps[1].to_string();
        }
        if let Some(caps) = Regex::new(r"Reason:\s*(\S+)").unwrap().captures(block) {
            event.reason = caps[1].to_string();
        }
        if let Some(caps) = Regex::new(r"Type:\s*(\S+)").unwrap().captures(block) {
            event.event_type = caps[1].to_string();
        }
        if let Some(caps) = Regex::new(r#"Message:\s*['"]?(.+?)['"]?(?:\n|$)"#).unwrap().captures(block) {
            event.message = caps[1].trim().to_string();
        }
        if let Some(caps) = Regex::new(r"Timestamp:\s*(.+?)(?:\n|$)").unwrap().captures(block) {
            event.last_seen = format_relative_time(&caps[1]);
        }

        if !event.reason.is_empty() || !event.message.is_empty() {
            events.push(event);
        }
    }

    events
}

/// Parse percentage string (e.g., "45%" -> 45)
fn parse_percentage(s: &str) -> u32 {
    s.trim()
        .trim_end_matches('%')
        .parse()
        .unwrap_or(0)
}

/// Format timestamp as relative time
fn format_relative_time(timestamp: &str) -> String {
    use chrono::{DateTime, Utc};

    if let Ok(event_time) = timestamp.trim().parse::<DateTime<Utc>>() {
        let now = Utc::now();
        let diff = now.signed_duration_since(event_time);

        let mins = diff.num_minutes();
        if mins < 1 {
            return "just now".to_string();
        } else if mins < 60 {
            return format!("{}m ago", mins);
        } else if mins < 1440 {
            return format!("{}h ago", mins / 60);
        } else {
            return format!("{}d ago", mins / 1440);
        }
    }

    "unknown".to_string()
}
