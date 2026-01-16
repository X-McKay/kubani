use crate::{cache, mcp, models::*, parsers};
use axum::{http::StatusCode, Json};
use serde_json::json;
use std::collections::HashMap;

pub async fn get_nodes() -> Result<Json<Vec<ClusterNode>>, StatusCode> {
    // Check cache first
    if let Some(cached) = cache::get("monitoring:nodes").await {
        if let Ok(nodes) = serde_json::from_str(&cached) {
            return Ok(Json(nodes));
        }
    }

    // Fetch data in parallel
    let calls = vec![
        ("resources_list", json!({"apiVersion": "v1", "kind": "Node"})),
        ("nodes_top", json!({})),
        ("pods_list", json!({})),
    ];

    let results = mcp::call_tools_parallel(calls)
        .await
        .map_err(|e| {
            tracing::error!("Failed to fetch nodes data: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    // Parse results
    let nodes_result = results[0].as_ref().map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    let metrics_result = results[1].as_ref().map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    let pods_result = results[2].as_ref().map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    let mut nodes = parsers::parse_nodes_table(nodes_result);
    let metrics = parsers::parse_node_metrics_table(metrics_result);
    let pods = parsers::parse_pods_table(pods_result);

    // Count pods per node
    let mut pod_counts: HashMap<String, u32> = HashMap::new();
    for pod in pods {
        if let Some(node_name) = pod.get("node") {
            *pod_counts.entry(node_name.clone()).or_insert(0) += 1;
        }
    }

    // Merge metrics and pod counts into nodes
    for node in &mut nodes {
        if let Some((cpu, memory)) = metrics.get(&node.name) {
            node.cpu = *cpu;
            node.memory = *memory;
        }
        node.pods = *pod_counts.get(&node.name).unwrap_or(&0);
    }

    // Cache the result
    if let Ok(json_str) = serde_json::to_string(&nodes) {
        cache::set("monitoring:nodes".to_string(), json_str).await;
    }

    Ok(Json(nodes))
}

pub async fn get_namespaces() -> Result<Json<Vec<Namespace>>, StatusCode> {
    // Check cache
    if let Some(cached) = cache::get("monitoring:namespaces").await {
        if let Ok(namespaces) = serde_json::from_str(&cached) {
            return Ok(Json(namespaces));
        }
    }

    // Fetch data in parallel
    let calls = vec![
        ("namespaces_list", json!({})),
        ("pods_list", json!({})),
    ];

    let results = mcp::call_tools_parallel(calls)
        .await
        .map_err(|e| {
            tracing::error!("Failed to fetch namespaces data: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    let ns_result = results[0].as_ref().map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    let pods_result = results[1].as_ref().map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    let namespace_names = parsers::parse_namespaces_table(ns_result);
    let pods = parsers::parse_pods_table(pods_result);

    // Count pods per namespace
    let mut pod_counts: HashMap<String, (u32, u32)> = HashMap::new();
    for pod in pods {
        let ns = pod.get("namespace").cloned().unwrap_or_else(|| "default".to_string());
        let entry = pod_counts.entry(ns).or_insert((0, 0));
        entry.1 += 1; // total
        if pod.get("status").map(|s| s.as_str()) == Some("Running") {
            entry.0 += 1; // running
        }
    }

    // Build namespace list
    let mut namespaces: Vec<Namespace> = namespace_names
        .into_iter()
        .map(|name| {
            let (running, total) = pod_counts.get(&name).copied().unwrap_or((0, 0));
            let status = if total > 0 && running < total {
                "degraded".to_string()
            } else {
                "healthy".to_string()
            };

            Namespace {
                name,
                running,
                total,
                status,
            }
        })
        .collect();

    // Filter and sort
    namespaces.retain(|ns| {
        ns.total > 0 || ["default", "ai-agents", "monitoring", "databases"].contains(&ns.name.as_str())
    });
    namespaces.sort_by(|a, b| b.total.cmp(&a.total));
    namespaces.truncate(10);

    // Cache the result
    if let Ok(json_str) = serde_json::to_string(&namespaces) {
        cache::set("monitoring:namespaces".to_string(), json_str).await;
    }

    Ok(Json(namespaces))
}

pub async fn get_events() -> Result<Json<Vec<ClusterEvent>>, StatusCode> {
    // Check cache
    if let Some(cached) = cache::get("monitoring:events").await {
        if let Ok(events) = serde_json::from_str(&cached) {
            return Ok(Json(events));
        }
    }

    let events_result = mcp::call_tool("events_list", json!({}))
        .await
        .map_err(|e| {
            tracing::error!("Failed to fetch events: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    let mut events = parsers::parse_events_yaml(&events_result);
    events.truncate(50);

    // Cache the result
    if let Ok(json_str) = serde_json::to_string(&events) {
        cache::set("monitoring:events".to_string(), json_str).await;
    }

    Ok(Json(events))
}

pub async fn get_services() -> Result<Json<Vec<Service>>, StatusCode> {
    // Check cache
    if let Some(cached) = cache::get("monitoring:services").await {
        if let Ok(services) = serde_json::from_str(&cached) {
            return Ok(Json(services));
        }
    }

    // Fetch data in parallel
    let calls = vec![
        ("services_list", json!({})),
        ("deployments_list", json!({})),
    ];

    let results = mcp::call_tools_parallel(calls)
        .await
        .map_err(|e| {
            tracing::error!("Failed to fetch services data: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    let services_result = results[0].as_ref().map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    let deployments_result = results[1].as_ref().map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    let services_data = parsers::parse_services_table(services_result);
    let deployments_data = parsers::parse_deployments_table(deployments_result);

    // Build deployment status lookup
    let mut deployment_status: HashMap<String, String> = HashMap::new();
    for dep in deployments_data {
        if let (Some(ns), Some(name), Some(ready)) = (
            dep.get("namespace"),
            dep.get("name"),
            dep.get("ready"),
        ) {
            let key = format!("{}/{}", ns, name);
            deployment_status.insert(key, ready.clone());
        }
    }

    // Build services list
    let services: Vec<Service> = services_data
        .into_iter()
        .filter(|svc| svc.get("name").map(|n| n.as_str()) != Some("kubernetes"))
        .map(|svc| {
            let name = svc.get("name").cloned().unwrap_or_default();
            let namespace = svc.get("namespace").cloned().unwrap_or_else(|| "default".to_string());
            let service_type = svc.get("type").cloned().unwrap_or_else(|| "ClusterIP".to_string());

            let dep_key = format!("{}/{}", namespace, name);
            let ready = deployment_status.get(&dep_key).cloned().unwrap_or_else(|| "1/1".to_string());

            let status = if let Some((ready_count, desired_count)) = ready.split_once('/') {
                let ready_num: u32 = ready_count.parse().unwrap_or(1);
                let desired_num: u32 = desired_count.parse().unwrap_or(1);

                if ready_num < desired_num {
                    if ready_num == 0 {
                        "unhealthy".to_string()
                    } else {
                        "degraded".to_string()
                    }
                } else {
                    "healthy".to_string()
                }
            } else {
                "healthy".to_string()
            };

            Service {
                name,
                namespace,
                ready,
                status,
                service_type,
            }
        })
        .take(20)
        .collect();

    // Cache the result
    if let Ok(json_str) = serde_json::to_string(&services) {
        cache::set("monitoring:services".to_string(), json_str).await;
    }

    Ok(Json(services))
}
