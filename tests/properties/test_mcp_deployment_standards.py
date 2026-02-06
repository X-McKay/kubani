"""Property-based tests for MCP server deployment standards.

Feature: mcp-infrastructure-improvements
Properties: 6, 7, 8, 10
"""

import os
from pathlib import Path

import yaml
from hypothesis import given
from hypothesis import strategies as st


def get_mcp_deployment_files():
    """Get all MCP server deployment files."""
    gitops_path = Path("infrastructure/gitops/apps/ai-agents")
    deployment_files = []

    if not gitops_path.exists():
        return []

    # List of known MCP server directories
    mcp_servers = [
        "discord-mcp-server",
        "memory-mcp-server",
        "skills-mcp-server",
        "temporal-mcp-server",
        "qdrant-mcp-server",
    ]

    for server_name in mcp_servers:
        server_dir = gitops_path / server_name
        if server_dir.exists() and server_dir.is_dir():
            deployment_file = server_dir / "deployment.yaml"
            if deployment_file.exists():
                deployment_files.append(deployment_file)

    return deployment_files


def parse_deployment_manifest(file_path: Path) -> dict:
    """Parse a Kubernetes deployment manifest."""
    with open(file_path) as f:
        content = f.read()
        # Handle multiple YAML documents
        docs = list(yaml.safe_load_all(content))
        # Find the Deployment resource
        for doc in docs:
            if doc and doc.get("kind") == "Deployment":
                return doc
    return {}


def test_property_6_deployment_resource_consistency():
    """
    Feature: mcp-infrastructure-improvements, Property 6: Deployment Resource Consistency

    For any MCP server deployment, the deployment manifest should include resource
    requests and limits following the standard template.

    Validates: Requirements 5.1
    """
    deployment_files = get_mcp_deployment_files()

    assert len(deployment_files) > 0, "Should have at least one MCP server deployment"

    for deployment_file in deployment_files:
        deployment = parse_deployment_manifest(deployment_file)

        assert deployment, f"Should parse deployment from {deployment_file}"

        # Get container spec
        containers = deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        assert len(containers) > 0, f"Deployment {deployment_file} should have at least one container"

        container = containers[0]  # Check the main container

        # Test 1: Container should have resources defined
        resources = container.get("resources", {})
        assert resources, f"Container in {deployment_file} should have resources defined"

        # Test 2: Should have requests
        requests = resources.get("requests", {})
        assert requests, f"Container in {deployment_file} should have resource requests"
        assert "cpu" in requests, f"Container in {deployment_file} should have CPU request"
        assert "memory" in requests, f"Container in {deployment_file} should have memory request"

        # Test 3: Should have limits
        limits = resources.get("limits", {})
        assert limits, f"Container in {deployment_file} should have resource limits"
        assert "cpu" in limits, f"Container in {deployment_file} should have CPU limit"
        assert "memory" in limits, f"Container in {deployment_file} should have memory limit"

        # Test 4: Requests should be less than or equal to limits
        # Parse CPU values (handle 'm' suffix)
        cpu_request = requests["cpu"]
        cpu_limit = limits["cpu"]

        def parse_cpu(value: str) -> int:
            """Parse CPU value to millicores."""
            if value.endswith("m"):
                return int(value[:-1])
            return int(float(value) * 1000)

        cpu_request_m = parse_cpu(cpu_request)
        cpu_limit_m = parse_cpu(cpu_limit)

        assert (
            cpu_request_m <= cpu_limit_m
        ), f"CPU request should be <= limit in {deployment_file}: {cpu_request} > {cpu_limit}"

        # Parse memory values (handle Mi/Gi suffix)
        memory_request = requests["memory"]
        memory_limit = limits["memory"]

        def parse_memory(value: str) -> int:
            """Parse memory value to MiB."""
            if value.endswith("Gi"):
                return int(value[:-2]) * 1024
            if value.endswith("Mi"):
                return int(value[:-2])
            if value.endswith("G"):
                return int(value[:-1]) * 1024
            if value.endswith("M"):
                return int(value[:-1])
            return int(value) // (1024 * 1024)

        memory_request_mi = parse_memory(memory_request)
        memory_limit_mi = parse_memory(memory_limit)

        assert (
            memory_request_mi <= memory_limit_mi
        ), f"Memory request should be <= limit in {deployment_file}: {memory_request} > {memory_limit}"


def test_property_7_deployment_health_checks():
    """
    Feature: mcp-infrastructure-improvements, Property 7: Deployment Health Checks

    For any MCP server deployment, the deployment should include both liveness and
    readiness probes configured to check the health endpoint.

    Validates: Requirements 5.2
    """
    deployment_files = get_mcp_deployment_files()

    assert len(deployment_files) > 0, "Should have at least one MCP server deployment"

    for deployment_file in deployment_files:
        deployment = parse_deployment_manifest(deployment_file)

        assert deployment, f"Should parse deployment from {deployment_file}"

        # Get container spec
        containers = deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        assert len(containers) > 0, f"Deployment {deployment_file} should have at least one container"

        container = containers[0]  # Check the main container

        # Test 1: Should have liveness probe
        liveness_probe = container.get("livenessProbe")
        assert liveness_probe, f"Container in {deployment_file} should have livenessProbe"

        # Test 2: Should have readiness probe
        readiness_probe = container.get("readinessProbe")
        assert readiness_probe, f"Container in {deployment_file} should have readinessProbe"

        # Test 3: Liveness probe should use HTTP GET to /health
        assert (
            "httpGet" in liveness_probe
        ), f"Liveness probe in {deployment_file} should use httpGet"
        assert (
            liveness_probe["httpGet"]["path"] == "/health"
        ), f"Liveness probe in {deployment_file} should check /health endpoint"
        assert (
            liveness_probe["httpGet"]["port"] == "http"
        ), f"Liveness probe in {deployment_file} should use http port"

        # Test 4: Readiness probe should use HTTP GET to /health
        assert (
            "httpGet" in readiness_probe
        ), f"Readiness probe in {deployment_file} should use httpGet"
        assert (
            readiness_probe["httpGet"]["path"] == "/health"
        ), f"Readiness probe in {deployment_file} should check /health endpoint"
        assert (
            readiness_probe["httpGet"]["port"] == "http"
        ), f"Readiness probe in {deployment_file} should use http port"

        # Test 5: Probes should have reasonable timing
        assert (
            "initialDelaySeconds" in liveness_probe
        ), f"Liveness probe in {deployment_file} should have initialDelaySeconds"
        assert (
            "periodSeconds" in liveness_probe
        ), f"Liveness probe in {deployment_file} should have periodSeconds"
        assert (
            "initialDelaySeconds" in readiness_probe
        ), f"Readiness probe in {deployment_file} should have initialDelaySeconds"
        assert (
            "periodSeconds" in readiness_probe
        ), f"Readiness probe in {deployment_file} should have periodSeconds"

        # Test 6: Readiness probe should start before liveness probe
        assert (
            readiness_probe["initialDelaySeconds"] <= liveness_probe["initialDelaySeconds"]
        ), f"Readiness probe should start before or with liveness probe in {deployment_file}"


def test_property_8_deployment_security_context():
    """
    Feature: mcp-infrastructure-improvements, Property 8: Deployment Security Context

    For any MCP server deployment, the security context should include runAsNonRoot,
    drop all capabilities, and disable privilege escalation.

    Validates: Requirements 5.3
    """
    deployment_files = get_mcp_deployment_files()

    assert len(deployment_files) > 0, "Should have at least one MCP server deployment"

    for deployment_file in deployment_files:
        deployment = parse_deployment_manifest(deployment_file)

        assert deployment, f"Should parse deployment from {deployment_file}"

        # Get container spec
        containers = deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        assert len(containers) > 0, f"Deployment {deployment_file} should have at least one container"

        container = containers[0]  # Check the main container

        # Test 1: Should have security context
        security_context = container.get("securityContext")
        assert security_context, f"Container in {deployment_file} should have securityContext"

        # Test 2: Should run as non-root
        assert (
            "runAsNonRoot" in security_context
        ), f"Security context in {deployment_file} should specify runAsNonRoot"
        assert (
            security_context["runAsNonRoot"] is True
        ), f"Container in {deployment_file} should run as non-root"

        # Test 3: Should specify a non-root user ID
        assert (
            "runAsUser" in security_context
        ), f"Security context in {deployment_file} should specify runAsUser"
        assert (
            security_context["runAsUser"] > 0
        ), f"Container in {deployment_file} should run as user ID > 0"

        # Test 4: Should disable privilege escalation
        assert (
            "allowPrivilegeEscalation" in security_context
        ), f"Security context in {deployment_file} should specify allowPrivilegeEscalation"
        assert (
            security_context["allowPrivilegeEscalation"] is False
        ), f"Container in {deployment_file} should disable privilege escalation"

        # Test 5: Should drop all capabilities
        assert (
            "capabilities" in security_context
        ), f"Security context in {deployment_file} should specify capabilities"
        capabilities = security_context["capabilities"]
        assert "drop" in capabilities, f"Security context in {deployment_file} should drop capabilities"
        assert (
            "ALL" in capabilities["drop"]
        ), f"Container in {deployment_file} should drop ALL capabilities"


def test_property_10_service_discovery_labels():
    """
    Feature: mcp-infrastructure-improvements, Property 10: Service Discovery Labels

    For any MCP server deployment, the deployment should include standard labels for
    service discovery (app.kubernetes.io/name, app.kubernetes.io/component, mcp.kubani.io/server).

    Validates: Requirements 5.5
    """
    deployment_files = get_mcp_deployment_files()

    assert len(deployment_files) > 0, "Should have at least one MCP server deployment"

    for deployment_file in deployment_files:
        deployment = parse_deployment_manifest(deployment_file)

        assert deployment, f"Should parse deployment from {deployment_file}"

        # Test 1: Deployment metadata should have labels
        metadata_labels = deployment.get("metadata", {}).get("labels", {})
        assert metadata_labels, f"Deployment {deployment_file} should have metadata labels"

        # Test 2: Should have app.kubernetes.io/name label
        assert (
            "app.kubernetes.io/name" in metadata_labels
        ), f"Deployment {deployment_file} should have app.kubernetes.io/name label"
        app_name = metadata_labels["app.kubernetes.io/name"]
        assert app_name, f"app.kubernetes.io/name should not be empty in {deployment_file}"

        # Test 3: Should have app.kubernetes.io/component label
        assert (
            "app.kubernetes.io/component" in metadata_labels
        ), f"Deployment {deployment_file} should have app.kubernetes.io/component label"
        assert (
            metadata_labels["app.kubernetes.io/component"] == "mcp-server"
        ), f"app.kubernetes.io/component should be 'mcp-server' in {deployment_file}"

        # Test 4: Should have app.kubernetes.io/part-of label
        assert (
            "app.kubernetes.io/part-of" in metadata_labels
        ), f"Deployment {deployment_file} should have app.kubernetes.io/part-of label"
        assert (
            metadata_labels["app.kubernetes.io/part-of"] == "kubani"
        ), f"app.kubernetes.io/part-of should be 'kubani' in {deployment_file}"

        # Test 5: Should have mcp.kubani.io/server label for registry reconciliation
        assert (
            "mcp.kubani.io/server" in metadata_labels
        ), f"Deployment {deployment_file} should have mcp.kubani.io/server label"
        assert (
            metadata_labels["mcp.kubani.io/server"] == "true"
        ), f"mcp.kubani.io/server should be 'true' in {deployment_file}"

        # Test 6: Pod template should have matching labels
        pod_labels = (
            deployment.get("spec", {}).get("template", {}).get("metadata", {}).get("labels", {})
        )
        assert pod_labels, f"Pod template in {deployment_file} should have labels"

        # Pod should have at least the selector labels
        assert (
            "app.kubernetes.io/name" in pod_labels
        ), f"Pod template in {deployment_file} should have app.kubernetes.io/name label"
        assert (
            pod_labels["app.kubernetes.io/name"] == app_name
        ), f"Pod app.kubernetes.io/name should match deployment in {deployment_file}"

        assert (
            "app.kubernetes.io/component" in pod_labels
        ), f"Pod template in {deployment_file} should have app.kubernetes.io/component label"
        assert (
            pod_labels["app.kubernetes.io/component"] == "mcp-server"
        ), f"Pod app.kubernetes.io/component should be 'mcp-server' in {deployment_file}"

        # Pod should have mcp.kubani.io/server label for registry reconciliation
        assert (
            "mcp.kubani.io/server" in pod_labels
        ), f"Pod template in {deployment_file} should have mcp.kubani.io/server label"
        assert (
            pod_labels["mcp.kubani.io/server"] == "true"
        ), f"Pod mcp.kubani.io/server should be 'true' in {deployment_file}"

        # Test 7: Selector should match pod labels
        selector_labels = deployment.get("spec", {}).get("selector", {}).get("matchLabels", {})
        assert selector_labels, f"Deployment {deployment_file} should have selector matchLabels"
        assert (
            "app.kubernetes.io/name" in selector_labels
        ), f"Selector in {deployment_file} should have app.kubernetes.io/name"
        assert (
            selector_labels["app.kubernetes.io/name"] == app_name
        ), f"Selector app.kubernetes.io/name should match in {deployment_file}"


def test_property_9_metrics_endpoint_configuration():
    """
    Feature: mcp-infrastructure-improvements, Property 9: Metrics Endpoint Configuration

    For any MCP server deployment, the deployment should expose a metrics port (9090)
    for Prometheus scraping.

    Validates: Requirements 5.4
    """
    deployment_files = get_mcp_deployment_files()

    assert len(deployment_files) > 0, "Should have at least one MCP server deployment"

    for deployment_file in deployment_files:
        deployment = parse_deployment_manifest(deployment_file)

        assert deployment, f"Should parse deployment from {deployment_file}"

        # Get container spec
        containers = deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        assert len(containers) > 0, f"Deployment {deployment_file} should have at least one container"

        container = containers[0]  # Check the main container

        # Test 1: Should have ports defined
        ports = container.get("ports", [])
        assert ports, f"Container in {deployment_file} should have ports defined"

        # Test 2: Should have metrics port
        port_names = [p.get("name") for p in ports]
        assert "metrics" in port_names, f"Container in {deployment_file} should have metrics port"

        # Test 3: Metrics port should be 9090
        metrics_port = next((p for p in ports if p.get("name") == "metrics"), None)
        assert metrics_port, f"Should find metrics port in {deployment_file}"
        assert (
            metrics_port.get("containerPort") == 9090
        ), f"Metrics port should be 9090 in {deployment_file}"
        assert (
            metrics_port.get("protocol") == "TCP"
        ), f"Metrics port should use TCP in {deployment_file}"

        # Test 4: Should also have http port
        assert "http" in port_names, f"Container in {deployment_file} should have http port"


def test_property_registry_integration_env_vars():
    """
    Feature: mcp-infrastructure-improvements: Registry Integration Environment Variables

    For any MCP server deployment, the deployment should include environment variables
    for registry integration (MCP_SERVER_ID, REGISTRY_URL).

    Validates: Requirements 3.1, 3.2
    """
    deployment_files = get_mcp_deployment_files()

    assert len(deployment_files) > 0, "Should have at least one MCP server deployment"

    for deployment_file in deployment_files:
        deployment = parse_deployment_manifest(deployment_file)

        assert deployment, f"Should parse deployment from {deployment_file}"

        # Get container spec
        containers = deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        assert len(containers) > 0, f"Deployment {deployment_file} should have at least one container"

        container = containers[0]  # Check the main container

        # Test 1: Should have environment variables
        env_vars = container.get("env", [])
        assert env_vars, f"Container in {deployment_file} should have environment variables"

        env_names = [e.get("name") for e in env_vars]

        # Test 2: Should have MCP_SERVER_ID
        assert (
            "MCP_SERVER_ID" in env_names
        ), f"Container in {deployment_file} should have MCP_SERVER_ID env var"

        # Test 3: Should have REGISTRY_URL
        assert (
            "REGISTRY_URL" in env_names
        ), f"Container in {deployment_file} should have REGISTRY_URL env var"

        # Test 4: MCP_SERVER_ID should not be empty
        server_id_var = next((e for e in env_vars if e.get("name") == "MCP_SERVER_ID"), None)
        assert server_id_var, f"Should find MCP_SERVER_ID in {deployment_file}"
        assert (
            server_id_var.get("value")
        ), f"MCP_SERVER_ID should have a value in {deployment_file}"

        # Test 5: REGISTRY_URL should point to registry service
        registry_url_var = next((e for e in env_vars if e.get("name") == "REGISTRY_URL"), None)
        assert registry_url_var, f"Should find REGISTRY_URL in {deployment_file}"
        registry_url = registry_url_var.get("value")
        assert registry_url, f"REGISTRY_URL should have a value in {deployment_file}"
        assert (
            "registry" in registry_url.lower()
        ), f"REGISTRY_URL should reference registry service in {deployment_file}"
