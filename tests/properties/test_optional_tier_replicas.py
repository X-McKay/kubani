"""Property-based tests for optional-tier deployment replica counts.

Feature: cluster-stability, Property 3: Optional-tier deployments have zero replicas
Validates: Requirements 4.2, 4.5
"""

from pathlib import Path

import yaml

# Nexus deployments that remain optional (not yet scaled up)
NEXUS_OPTIONAL_DEPLOYMENTS = [
    Path("infrastructure/gitops/apps/nexus/computer-mcp-deployment.yaml"),
]

# AI agent deployments that remain optional (not yet scaled up)
# Wave 1-4 services have been intentionally enabled and are excluded here.
# learning-agent and kubernetes-mcp-executor remain at 0 by default.
AI_AGENT_OPTIONAL_DIRS = [
    "learning-agent",
    "kubernetes-mcp-executor",
]

AI_AGENT_OPTIONAL_DEPLOYMENTS = [
    Path(f"infrastructure/gitops/apps/ai-agents/{d}/deployment.yaml")
    for d in AI_AGENT_OPTIONAL_DIRS
]


def load_yaml(path: Path) -> dict:
    assert path.exists(), f"Required manifest not found: {path}"
    with open(path) as f:
        return yaml.safe_load(f)


def get_replicas(data: dict) -> int | None:
    """Extract spec.replicas from a Deployment manifest."""
    return data.get("spec", {}).get("replicas")


# --- Tests ---


def test_property_3_nexus_optional_deployments_have_zero_replicas():
    """
    Feature: cluster-stability, Property 3: Optional-tier deployments have zero replicas

    Nexus components not yet enabled must remain at replicas: 0.
    Validates: Requirements 4.2, 4.5
    """
    failures = []
    for path in NEXUS_OPTIONAL_DEPLOYMENTS:
        if not path.exists():
            failures.append(f"{path}: file not found")
            continue
        data = load_yaml(path)
        replicas = get_replicas(data)
        if replicas != 0:
            failures.append(f"{path.name}: spec.replicas={replicas!r} (expected 0)")

    assert not failures, (
        "The following Nexus optional deployments are not scaled to zero:\n"
        + "\n".join(f"  - {f}" for f in failures)
    )


def test_property_3_ai_agent_optional_deployments_have_zero_replicas():
    """
    Feature: cluster-stability, Property 3: Optional-tier deployments have zero replicas

    AI agent deployments not yet enabled must remain at replicas: 0.
    Validates: Requirements 4.2, 4.5
    """
    failures = []
    for path in AI_AGENT_OPTIONAL_DEPLOYMENTS:
        if not path.exists():
            failures.append(f"{path}: file not found")
            continue
        data = load_yaml(path)
        replicas = get_replicas(data)
        if replicas != 0:
            failures.append(f"{path}: spec.replicas={replicas!r} (expected 0)")

    assert not failures, (
        "The following AI agent optional deployments are not scaled to zero:\n"
        + "\n".join(f"  - {f}" for f in failures)
    )
