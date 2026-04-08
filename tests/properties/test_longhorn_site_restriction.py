"""Property-based tests for Longhorn site restriction.

Feature: cluster-stability, Property 2: Longhorn replicas never scheduled on secondary-site nodes
Validates: Requirements 2.3, 3.1
"""

from pathlib import Path

import yaml

LONGHORN_HELMRELEASE_PATH = Path(
    "infrastructure/gitops/infrastructure/longhorn/helmrelease.yaml"
)

# Longhorn's defaultSettings.nodeSelector format is "key:value" (colon-separated string)
EXPECTED_NODE_SELECTOR = "topology.kubani.io/site:primary"


def load_longhorn_helmrelease() -> dict:
    """Load the Longhorn HelmRelease YAML."""
    assert LONGHORN_HELMRELEASE_PATH.exists(), (
        f"Longhorn HelmRelease not found at {LONGHORN_HELMRELEASE_PATH}"
    )
    with open(LONGHORN_HELMRELEASE_PATH) as f:
        return yaml.safe_load(f)


def test_property_2_longhorn_helmrelease_exists():
    """The Longhorn HelmRelease file must exist."""
    assert LONGHORN_HELMRELEASE_PATH.exists(), (
        f"Longhorn HelmRelease not found at {LONGHORN_HELMRELEASE_PATH}"
    )


def test_property_2_longhorn_node_selector_restricts_to_primary_site():
    """
    Feature: cluster-stability, Property 2: Longhorn replicas never scheduled on secondary-site nodes

    For any Longhorn volume in the cluster, none of its replicas should be scheduled
    on a node where topology.kubani.io/site is 'secondary'. This is enforced by the
    nodeSelector in Longhorn's defaultSettings, which restricts instance managers and
    replica scheduling to nodes labeled topology.kubani.io/site=primary.

    Validates: Requirements 2.3, 3.1
    """
    helmrelease = load_longhorn_helmrelease()

    values = helmrelease.get("spec", {}).get("values", {})
    assert values, "Longhorn HelmRelease must have a spec.values section"

    default_settings = values.get("defaultSettings", {})
    assert default_settings is not None, (
        "Longhorn HelmRelease must have spec.values.defaultSettings"
    )

    node_selector = default_settings.get("nodeSelector")
    assert node_selector is not None, (
        "Longhorn defaultSettings must define a nodeSelector to restrict replica placement. "
        "Without this, Longhorn may schedule replicas on osprey (secondary site), "
        "causing cross-site replication traffic."
    )

    assert node_selector == EXPECTED_NODE_SELECTOR, (
        f"Longhorn nodeSelector must be '{EXPECTED_NODE_SELECTOR}' to restrict replicas "
        f"to Primary Site nodes only. Got: '{node_selector}'. "
        f"This prevents Longhorn from scheduling replicas on osprey (secondary site)."
    )


def test_property_2_longhorn_default_replica_count_is_set():
    """
    Longhorn must have an explicit defaultReplicaCount to ensure replicas are
    distributed across Primary Site nodes.

    Validates: Requirements 3.1
    """
    helmrelease = load_longhorn_helmrelease()

    default_settings = (
        helmrelease.get("spec", {}).get("values", {}).get("defaultSettings", {})
    )

    replica_count = default_settings.get("defaultReplicaCount")
    assert replica_count is not None, (
        "Longhorn defaultSettings must define defaultReplicaCount"
    )
    assert isinstance(replica_count, int) and replica_count >= 1, (
        f"Longhorn defaultReplicaCount must be a positive integer, got: {replica_count}"
    )


def test_property_2_longhorn_not_default_storage_class():
    """
    Longhorn must not be the default storage class, to prevent accidental PVCs
    from landing on Longhorn when local-path is more appropriate.

    Validates: Requirements 3.1
    """
    helmrelease = load_longhorn_helmrelease()

    persistence = (
        helmrelease.get("spec", {}).get("values", {}).get("persistence", {})
    )

    default_class = persistence.get("defaultClass")
    assert default_class is False, (
        f"Longhorn persistence.defaultClass must be false to prevent accidental "
        f"Longhorn PVCs. Got: {default_class}"
    )
