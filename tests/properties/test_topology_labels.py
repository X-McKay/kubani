"""Property-based tests for topology label completeness.

Feature: cluster-stability, Property 1: Topology labels are complete after provisioning
Validates: Requirements 2.1, 10.2
"""

from pathlib import Path

import yaml

INVENTORY_PATH = Path("infrastructure/ansible/inventory/hosts.yml")

REQUIRED_TOPOLOGY_LABELS = [
    "topology.kubani.io/site",
    "topology.kubani.io/network-zone",
    "topology.kubani.io/usage-class",
]

VALID_SITE_VALUES = {"primary", "secondary"}
VALID_NETWORK_ZONE_VALUES = {"lan", "remote"}
VALID_USAGE_CLASS_VALUES = {"general", "inference", "constrained"}


def load_inventory() -> dict:
    """Load the Ansible inventory from hosts.yml."""
    assert INVENTORY_PATH.exists(), f"Inventory file not found at {INVENTORY_PATH}"
    with open(INVENTORY_PATH) as f:
        return yaml.safe_load(f)


def collect_all_hosts(inventory: dict) -> dict[str, dict]:
    """Collect all host entries from the inventory, flattening groups."""
    hosts: dict[str, dict] = {}

    def _walk(node: dict) -> None:
        if "hosts" in node:
            for hostname, host_vars in node["hosts"].items():
                # host_vars may be None (e.g. `osprey: {}` in bootstrap group)
                if host_vars is not None and hostname not in hosts:
                    hosts[hostname] = host_vars
        if "children" in node:
            for child in node["children"].values():
                if child:
                    _walk(child)

    _walk(inventory.get("all", inventory))
    return hosts


def test_property_1_all_hosts_have_topology_labels():
    """
    Feature: cluster-stability, Property 1: Topology labels are complete after provisioning

    For any node defined in the Ansible inventory, after provisioning completes, the
    Kubernetes node object must have all three required topology labels
    (topology.kubani.io/site, topology.kubani.io/network-zone,
    topology.kubani.io/usage-class) with non-empty values.

    Validates: Requirements 2.1, 10.2
    """
    inventory = load_inventory()
    hosts = collect_all_hosts(inventory)

    assert len(hosts) > 0, "Inventory must contain at least one host"

    for hostname, host_vars in hosts.items():
        topology_labels = host_vars.get("topology_labels")

        assert topology_labels is not None, (
            f"Host '{hostname}' is missing 'topology_labels'. "
            f"All hosts must define topology_labels with keys: {REQUIRED_TOPOLOGY_LABELS}"
        )

        assert isinstance(topology_labels, dict), (
            f"Host '{hostname}' topology_labels must be a dict, got {type(topology_labels)}"
        )

        for label_key in REQUIRED_TOPOLOGY_LABELS:
            assert label_key in topology_labels, (
                f"Host '{hostname}' is missing required topology label '{label_key}'. "
                f"Present labels: {list(topology_labels.keys())}"
            )

            value = topology_labels[label_key]
            assert value is not None and str(value).strip() != "", (
                f"Host '{hostname}' topology label '{label_key}' must have a non-empty value"
            )


def test_property_1_topology_label_values_are_valid():
    """
    For any node in the inventory, each topology label must have a value from the
    defined set of valid values.

    Validates: Requirements 2.1, 10.2
    """
    inventory = load_inventory()
    hosts = collect_all_hosts(inventory)

    for hostname, host_vars in hosts.items():
        topology_labels = host_vars.get("topology_labels", {})
        if not topology_labels:
            continue  # covered by the completeness test above

        site = topology_labels.get("topology.kubani.io/site")
        if site is not None:
            assert site in VALID_SITE_VALUES, (
                f"Host '{hostname}' has invalid site value '{site}'. "
                f"Must be one of: {VALID_SITE_VALUES}"
            )

        network_zone = topology_labels.get("topology.kubani.io/network-zone")
        if network_zone is not None:
            assert network_zone in VALID_NETWORK_ZONE_VALUES, (
                f"Host '{hostname}' has invalid network-zone value '{network_zone}'. "
                f"Must be one of: {VALID_NETWORK_ZONE_VALUES}"
            )

        usage_class = topology_labels.get("topology.kubani.io/usage-class")
        if usage_class is not None:
            assert usage_class in VALID_USAGE_CLASS_VALUES, (
                f"Host '{hostname}' has invalid usage-class value '{usage_class}'. "
                f"Must be one of: {VALID_USAGE_CLASS_VALUES}"
            )


def test_property_1_secondary_site_nodes_have_correct_zone():
    """
    For any node with site=secondary, the network-zone must be 'remote'.
    Primary site nodes must have network-zone 'lan'.

    Validates: Requirements 2.1, 2.3
    """
    inventory = load_inventory()
    hosts = collect_all_hosts(inventory)

    for hostname, host_vars in hosts.items():
        topology_labels = host_vars.get("topology_labels", {})
        if not topology_labels:
            continue

        site = topology_labels.get("topology.kubani.io/site")
        network_zone = topology_labels.get("topology.kubani.io/network-zone")

        if site == "secondary":
            assert network_zone == "remote", (
                f"Host '{hostname}' has site=secondary but network-zone='{network_zone}'. "
                f"Secondary site nodes must have network-zone=remote"
            )
        elif site == "primary":
            assert network_zone == "lan", (
                f"Host '{hostname}' has site=primary but network-zone='{network_zone}'. "
                f"Primary site nodes must have network-zone=lan"
            )
