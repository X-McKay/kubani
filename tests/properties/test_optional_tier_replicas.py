"""Property-based tests for optional-tier deployment replica counts.

Feature: cluster-stability, Property 3: Optional-tier deployments have zero replicas
Validates: Requirements 4.2, 4.5
"""

from pathlib import Path

import yaml

# All deployment manifests in the optional service tier (nexus + ai-agents)
# These must have spec.replicas == 0 per the design document.
NEXUS_DEPLOYMENTS = list(Path("infrastructure/gitops/apps/nexus").glob("*-deployment.yaml"))

# AI agents: only include deployments that are referenced in the active kustomization
# (excludes .cluster-swarm-disabled/ and other disabled directories)
AI_AGENT_ACTIVE_DIRS = [
    "k8s-monitor",
    "news-monitor",
    "learning-agent",
    "kubernetes-mcp-server",
    "kubernetes-mcp-executor",
    "temporal-mcp-server",
    "qdrant-mcp-server",
    "memory-mcp-server",
    "skills-mcp-server",
]

AI_AGENT_DEPLOYMENTS = [
    Path(f"infrastructure/gitops/apps/ai-agents/{d}/deployment.yaml")
    for d in AI_AGENT_ACTIVE_DIRS
]


def load_yaml(path: Path) -> dict:
    assert path.exists(), f"Required manifest not found: {path}"
    with open(path) as f:
        return yaml.safe_load(f)


def get_replicas(data: dict) -> int | None:
    """Extract spec.replicas from a Deployment manifest."""
    return data.get("spec", {}).get("replicas")


# --- Tests ---


def test_property_3_nexus_deployments_have_zero_replicas():
    """
    Feature: cluster-stability, Property 3: Optional-tier deployments have zero replicas

    For any deployment in the Nexus optional tier, spec.replicas must be 0.
    Validates: Requirements 4.2, 4.5
    """
    assert NEXUS_DEPLOYMENTS, "No Nexus deployment manifests found — check path"

    failures = []
    for path in NEXUS_DEPLOYMENTS:
        data = load_yaml(path)
        replicas = get_replicas(data)
        if replicas != 0:
            failures.append(f"{path.name}: spec.replicas={replicas!r} (expected 0)")

    assert not failures, (
        "The following Nexus deployments are not scaled to zero:\n"
        + "\n".join(f"  - {f}" for f in failures)
        + "\nAdd 'replicas: 0  # OPTIONAL: set replicas > 0 to enable' to each."
    )


def test_property_3_ai_agent_deployments_have_zero_replicas():
    """
    Feature: cluster-stability, Property 3: Optional-tier deployments have zero replicas

    For any deployment in the AI agents optional tier, spec.replicas must be 0.
    Validates: Requirements 4.2, 4.5
    """
    failures = []
    for path in AI_AGENT_DEPLOYMENTS:
        if not path.exists():
            failures.append(f"{path}: file not found")
            continue
        data = load_yaml(path)
        replicas = get_replicas(data)
        if replicas != 0:
            failures.append(f"{path}: spec.replicas={replicas!r} (expected 0)")

    assert not failures, (
        "The following AI agent deployments are not scaled to zero:\n"
        + "\n".join(f"  - {f}" for f in failures)
        + "\nAdd 'replicas: 0  # OPTIONAL: set replicas > 0 to enable' to each."
    )
