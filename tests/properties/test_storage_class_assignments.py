"""Property-based tests for stateful workload storage class assignments.

Feature: cluster-stability, Property 2 (storage aspect): Longhorn replicas never scheduled on secondary-site nodes
Validates: Requirements 3.2, 3.3, 3.4, 3.5
"""

from pathlib import Path

import yaml

# Storage policy table from design document
# workload -> (pvc_path, expected_storage_class, description)
STORAGE_POLICY = {
    "postgresql": (
        Path("infrastructure/gitops/apps/postgresql/helmrelease.yaml"),
        "longhorn",
        "PostgreSQL must use Longhorn for durability (Req 3.2)",
    ),
    "redis": (
        Path("infrastructure/gitops/apps/redis/helmrelease.yaml"),
        "local-path",
        "Redis must use local-path for fast single-node cache (Req 3.3)",
    ),
    "qdrant": (
        Path("infrastructure/gitops/infrastructure/qdrant/pvc.yaml"),
        "longhorn",
        "Qdrant must use Longhorn — vector data is expensive to rebuild (Req 3.4)",
    ),
    "neo4j": (
        Path("infrastructure/gitops/infrastructure/neo4j/pvc.yaml"),
        "longhorn",
        "Neo4j must use Longhorn — graph data is expensive to rebuild (Req 3.4)",
    ),
}

# vLLM NAS model storage uses static binding (storageClassName: "") to a NAS-backed PV
VLLM_NAS_PVC_PATH = Path("infrastructure/gitops/apps/vllm/nas-model-storage-pvc.yaml")


def load_yaml(path: Path) -> dict:
    assert path.exists(), f"Required manifest not found: {path}"
    with open(path) as f:
        return yaml.safe_load(f)


def get_storage_class_from_helmrelease(data: dict, workload: str) -> str:
    """Extract storageClass from a Bitnami HelmRelease values section."""
    values = data.get("spec", {}).get("values", {})

    if workload == "postgresql":
        return (
            values.get("primary", {})
            .get("persistence", {})
            .get("storageClass", "")
        )
    elif workload == "redis":
        return (
            values.get("master", {})
            .get("persistence", {})
            .get("storageClass", "")
        )
    return ""


def get_storage_class_from_pvc(data: dict) -> str:
    return data.get("spec", {}).get("storageClassName", "")


# --- Tests ---


def test_property_2_postgresql_uses_longhorn():
    """
    Feature: cluster-stability, Property 2 (storage aspect): Longhorn replicas never scheduled on secondary-site nodes

    PostgreSQL must use Longhorn storage class for durability with proper fsync support.
    Validates: Requirements 3.2
    """
    path, expected, description = STORAGE_POLICY["postgresql"]
    data = load_yaml(path)
    actual = get_storage_class_from_helmrelease(data, "postgresql")
    assert actual == expected, (
        f"{description}\n"
        f"Expected storageClass '{expected}', got '{actual}'"
    )


def test_property_2_postgresql_affinity_uses_topology_labels():
    """
    PostgreSQL affinity must use topology labels (not hostnames) to select Primary Site nodes.
    Validates: Requirements 2.4, 3.2
    """
    path, _, _ = STORAGE_POLICY["postgresql"]
    data = load_yaml(path)
    affinity = (
        data.get("spec", {})
        .get("values", {})
        .get("primary", {})
        .get("affinity", {})
    )
    assert affinity, "PostgreSQL primary must define an affinity rule"

    node_affinity = affinity.get("nodeAffinity", {})
    required = node_affinity.get("requiredDuringSchedulingIgnoredDuringExecution", {})
    terms = required.get("nodeSelectorTerms", [])
    assert terms, "PostgreSQL nodeAffinity must have nodeSelectorTerms"

    # Collect all matchExpression keys used across all terms
    all_keys = [
        expr.get("key", "")
        for term in terms
        for expr in term.get("matchExpressions", [])
    ]

    # Must not use hostname-based selectors
    assert "kubernetes.io/hostname" not in all_keys, (
        "PostgreSQL affinity must not use kubernetes.io/hostname. "
        "Use topology.kubani.io/ labels instead (Req 2.4)"
    )

    # Must use topology labels
    topology_keys = [k for k in all_keys if k.startswith("topology.kubani.io/")]
    assert topology_keys, (
        "PostgreSQL affinity must use topology.kubani.io/ labels to select Primary Site nodes"
    )


def test_property_2_redis_uses_local_path():
    """
    Feature: cluster-stability, Property 2 (storage aspect): Longhorn replicas never scheduled on secondary-site nodes

    Redis must use local-path storage — it is a cache and fast restart is acceptable.
    Validates: Requirements 3.3
    """
    path, expected, description = STORAGE_POLICY["redis"]
    data = load_yaml(path)
    actual = get_storage_class_from_helmrelease(data, "redis")
    assert actual == expected, (
        f"{description}\n"
        f"Expected storageClass '{expected}', got '{actual}'"
    )


def test_property_2_qdrant_uses_longhorn():
    """
    Feature: cluster-stability, Property 2 (storage aspect): Longhorn replicas never scheduled on secondary-site nodes

    Qdrant must use Longhorn storage — vector data is expensive to rebuild.
    Validates: Requirements 3.4
    """
    path, expected, description = STORAGE_POLICY["qdrant"]
    data = load_yaml(path)
    actual = get_storage_class_from_pvc(data)
    assert actual == expected, (
        f"{description}\n"
        f"Expected storageClass '{expected}', got '{actual}'"
    )


def test_property_2_neo4j_uses_longhorn():
    """
    Feature: cluster-stability, Property 2 (storage aspect): Longhorn replicas never scheduled on secondary-site nodes

    Neo4j must use Longhorn storage — graph data is expensive to rebuild.
    Validates: Requirements 3.4
    """
    path, expected, description = STORAGE_POLICY["neo4j"]
    data = load_yaml(path)
    actual = get_storage_class_from_pvc(data)
    assert actual == expected, (
        f"{description}\n"
        f"Expected storageClass '{expected}', got '{actual}'"
    )


def test_property_2_vllm_nas_pvc_uses_static_nas_binding():
    """
    Feature: cluster-stability, Property 2 (storage aspect): Longhorn replicas never scheduled on secondary-site nodes

    vLLM model cache must use NAS-backed storage (static PV binding), not replicated block storage.
    An empty storageClassName with an explicit volumeName indicates a static NAS binding.
    Validates: Requirements 3.5
    """
    assert VLLM_NAS_PVC_PATH.exists(), f"vLLM NAS PVC not found at {VLLM_NAS_PVC_PATH}"
    data = load_yaml(VLLM_NAS_PVC_PATH)
    spec = data.get("spec", {})

    storage_class = spec.get("storageClassName", "MISSING")
    volume_name = spec.get("volumeName", "")

    assert storage_class == "", (
        f"vLLM NAS PVC must use storageClassName: '' for static NAS binding. "
        f"Got: '{storage_class}'"
    )
    assert volume_name, (
        "vLLM NAS PVC must specify a volumeName to bind to the NAS-backed PV"
    )
    assert "nas" in volume_name.lower(), (
        f"vLLM NAS PVC volumeName should reference a NAS PV. Got: '{volume_name}'"
    )
