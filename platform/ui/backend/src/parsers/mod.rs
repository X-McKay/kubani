use crate::models::*;
use regex::Regex;
use std::collections::HashMap;

/// Parse generic table output into a vector of HashMaps
/// Handles multi-word column names by splitting on 2+ consecutive spaces
pub fn parse_table_output(text: &str) -> Vec<HashMap<String, String>> {
    let lines: Vec<&str> = text.lines().collect();
    if lines.is_empty() {
        return vec![];
    }

    // First line is the header
    let header_line = lines[0];

    // Split on 2+ whitespace to handle multi-word column names like "NOMINATED NODE"
    let multi_space_re = Regex::new(r"\s{2,}").unwrap();
    let header_parts: Vec<&str> = multi_space_re.split(header_line).collect();

    // Find each header's position in the original line
    let mut headers: Vec<(String, usize)> = Vec::new();
    for part in &header_parts {
        let part = part.trim();
        if part.is_empty() {
            continue;
        }
        // Find where this header starts in the original line
        if let Some(pos) = header_line.find(part) {
            // Normalize header name: lowercase, replace spaces and hyphens with underscores
            let normalized = part.to_lowercase().replace(" ", "_").replace("-", "_");
            headers.push((normalized, pos));
        }
    }

    if headers.is_empty() {
        return vec![];
    }

    // Sort headers by position to ensure correct order
    headers.sort_by_key(|h| h.1);

    // Build column positions (start positions)
    let col_positions: Vec<usize> = headers.iter().map(|h| h.1).collect();

    // Parse data rows
    let mut results = Vec::new();
    for line in lines.iter().skip(1) {
        if line.trim().is_empty() {
            continue;
        }

        let mut row = HashMap::new();
        for (i, (header_name, _)) in headers.iter().enumerate() {
            let start = col_positions[i];
            let end = if i + 1 < col_positions.len() {
                col_positions[i + 1]
            } else {
                line.len()
            };

            // Ensure valid slice bounds: start < line.len() and end >= start
            let value = if start < line.len() {
                let safe_end = end.min(line.len()).max(start);
                line[start..safe_end].trim()
            } else {
                ""
            };

            row.insert(header_name.clone(), value.to_string());
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
/// Handles output from nodes_top which has columns like:
/// NAME, CPU(cores), CPU(%), MEMORY(bytes), MEMORY(%)
pub fn parse_node_metrics_table(text: &str) -> HashMap<String, (u32, u32)> {
    let rows = parse_table_output(text);
    let mut metrics = HashMap::new();

    for row in rows {
        if let Some(name) = row.get("name") {
            // Try to get CPU percentage - check multiple possible column names
            // MCP server returns columns like "CPU(%)" which becomes "cpu(%)" after lowercase
            let cpu = row.get("cpu(%)")
                .or_else(|| row.get("cpu%"))
                .or_else(|| row.get("cpu_"))
                .map(|s| parse_percentage(s))
                .or_else(|| {
                    // If no percentage, try to parse millicores from cpu(cores)
                    row.get("cpu(cores)")
                        .or_else(|| row.get("cpu_cores_"))
                        .or_else(|| row.get("cpu"))
                        .map(|s| parse_millicores(s))
                })
                .unwrap_or(0);

            // Try to get Memory percentage - check multiple possible column names
            let memory = row.get("memory(%)")
                .or_else(|| row.get("memory%"))
                .or_else(|| row.get("memory_"))
                .map(|s| parse_percentage(s))
                .or_else(|| {
                    // If no percentage, try to parse memory bytes
                    row.get("memory(bytes)")
                        .or_else(|| row.get("memory_bytes_"))
                        .or_else(|| row.get("memory"))
                        .map(|s| parse_memory_bytes(s))
                })
                .unwrap_or(0);

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

/// Parse millicores string (e.g., "250m" -> ~6% assuming 4 cores)
fn parse_millicores(s: &str) -> u32 {
    let s = s.trim();
    if s.ends_with('m') {
        // Convert millicores to percentage (assuming 4 cores = 4000m = 100%)
        let millicores: u32 = s.trim_end_matches('m').parse().unwrap_or(0);
        (millicores / 40).min(100)
    } else {
        // Full cores - convert to percentage
        let cores: f32 = s.parse().unwrap_or(0.0);
        ((cores / 4.0) * 100.0).min(100.0) as u32
    }
}

/// Parse memory bytes string (e.g., "4096Mi" -> ~25% assuming 16GB total)
fn parse_memory_bytes(s: &str) -> u32 {
    let s = s.trim();
    let mem_mi: u32 = if s.ends_with("Gi") {
        s.trim_end_matches("Gi").parse::<u32>().unwrap_or(0) * 1024
    } else if s.ends_with("Mi") {
        s.trim_end_matches("Mi").parse().unwrap_or(0)
    } else if s.ends_with("Ki") {
        s.trim_end_matches("Ki").parse::<u32>().unwrap_or(0) / 1024
    } else {
        // Assume bytes
        s.parse::<u64>().unwrap_or(0) as u32 / 1024 / 1024
    };

    // Calculate percentage assuming 16GB (16384Mi) total
    ((mem_mi as f32 / 16384.0) * 100.0).min(100.0) as u32
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_table_output_basic() {
        let text = "NAME    STATUS    ROLE\nnode1   Ready     worker\nnode2   Ready     control-plane";
        let result = parse_table_output(text);

        assert_eq!(result.len(), 2);
        assert_eq!(result[0].get("name").unwrap(), "node1");
        assert_eq!(result[0].get("status").unwrap(), "Ready");
        assert_eq!(result[1].get("name").unwrap(), "node2");
    }

    #[test]
    fn test_parse_table_output_short_lines() {
        // This tests the fix for slice bounds panic
        // Header has wide columns but data lines are shorter
        let text = "NAME                      STATUS    INTERNAL-IP    EXTERNAL-IP\nshort                     Ready     10.0.0.1";
        let result = parse_table_output(text);

        assert_eq!(result.len(), 1);
        assert_eq!(result[0].get("name").unwrap(), "short");
        assert_eq!(result[0].get("status").unwrap(), "Ready");
        // external_ip should be empty since line is too short
        assert_eq!(result[0].get("external_ip").unwrap_or(&String::new()), "");
    }

    #[test]
    fn test_parse_table_output_misaligned_columns() {
        // Test case that caused the original panic: columns misaligned with header
        let text = "NAME              CPU%   MEMORY%\nnodeabc           45%    70%";
        let result = parse_table_output(text);

        assert_eq!(result.len(), 1);
        assert!(result[0].contains_key("name"));
    }

    #[test]
    fn test_parse_table_output_empty_input() {
        let text = "";
        let result = parse_table_output(text);
        assert!(result.is_empty());
    }

    #[test]
    fn test_parse_table_output_only_header() {
        let text = "NAME    STATUS    ROLE";
        let result = parse_table_output(text);
        assert!(result.is_empty());
    }

    #[test]
    fn test_parse_nodes_table() {
        let text = "NAME    STATUS    ROLES           AGE   VERSION\nnode1   Ready     control-plane   10d   v1.28.0\nnode2   Ready     <none>          5d    v1.28.0";
        let result = parse_nodes_table(text);

        assert_eq!(result.len(), 2);
        assert_eq!(result[0].name, "node1");
        assert_eq!(result[0].role, "control-plane");
        assert_eq!(result[1].role, "worker"); // <none> becomes worker
    }

    #[test]
    fn test_parse_node_metrics_table_with_parentheses() {
        // Test parsing the actual format returned by kubernetes-mcp-server nodes_top
        let text = "NAME     CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)\nasio     144m         2%       6290Mi          61%\nrig0     1041m        3%       25396Mi         46%";
        let result = parse_node_metrics_table(text);

        assert_eq!(result.len(), 2);

        // Check asio metrics
        let (cpu, memory) = result.get("asio").unwrap();
        assert_eq!(*cpu, 2);  // 2%
        assert_eq!(*memory, 61);  // 61%

        // Check rig0 metrics
        let (cpu, memory) = result.get("rig0").unwrap();
        assert_eq!(*cpu, 3);  // 3%
        assert_eq!(*memory, 46);  // 46%
    }

    #[test]
    fn test_parse_percentage() {
        assert_eq!(parse_percentage("45%"), 45);
        assert_eq!(parse_percentage("100%"), 100);
        assert_eq!(parse_percentage("0%"), 0);
        assert_eq!(parse_percentage("  3%  "), 3);
    }

    #[test]
    fn test_parse_millicores() {
        // 250m on a 4-core system = 250/4000 * 100 = 6.25%
        assert_eq!(parse_millicores("250m"), 6);  // 250/40 = 6
        assert_eq!(parse_millicores("4000m"), 100);  // capped at 100
        assert_eq!(parse_millicores("2"), 50);  // 2 cores / 4 cores * 100 = 50%
    }

    #[test]
    fn test_parse_table_output_multiword_columns() {
        // Test handling of multi-word column names like "NOMINATED NODE"
        let text = "NAMESPACE   NAME       NODE     NOMINATED NODE   STATUS\ndefault     pod1       node1    <none>           Running\nkube-sys    pod2       node2    <none>           Running";
        let result = parse_table_output(text);

        assert_eq!(result.len(), 2);
        // Verify "node" column is correctly parsed (not overwritten by "nominated_node")
        assert_eq!(result[0].get("node").unwrap(), "node1");
        assert_eq!(result[0].get("nominated_node").unwrap(), "<none>");
        assert_eq!(result[1].get("node").unwrap(), "node2");
    }
}
