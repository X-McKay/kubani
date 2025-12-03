"""Property-based tests for node model validation.

Feature: tailscale-k8s-cluster, Property 8: Minimal node definition requirements
Validates: Requirements 3.3
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cluster_manager.models.node import Node, NodeTaint


# Custom strategies for generating valid test data
@st.composite
def valid_hostname(draw):
    """Generate valid RFC 1123 hostnames."""
    # Generate hostname parts (labels)
    num_labels = draw(st.integers(min_value=1, max_value=3))
    labels = []
    for _ in range(num_labels):
        # Each label: alphanumeric, can contain hyphens but not at start/end
        length = draw(st.integers(min_value=1, max_value=10))
        if length == 1:
            label = draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789"))
        else:
            start = draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789"))
            middle = "".join(
                draw(
                    st.lists(
                        st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-"),
                        min_size=length - 2,
                        max_size=length - 2,
                    )
                )
            )
            end = draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789"))
            label = start + middle + end
        labels.append(label)
    return ".".join(labels)


@st.composite
def valid_tailscale_ip(draw):
    """Generate valid Tailscale IP addresses (100.64.0.0/10 range)."""
    # Tailscale uses 100.64.0.0 to 100.127.255.255
    octet2 = draw(st.integers(min_value=64, max_value=127))
    octet3 = draw(st.integers(min_value=0, max_value=255))
    octet4 = draw(st.integers(min_value=1, max_value=254))
    return f"100.{octet2}.{octet3}.{octet4}"


@st.composite
def minimal_node(draw):
    """Generate a node with only required fields."""
    hostname = draw(valid_hostname())
    ansible_host = draw(valid_tailscale_ip())
    tailscale_ip = draw(valid_tailscale_ip())
    role = draw(st.sampled_from(["control-plane", "worker"]))

    return Node(hostname=hostname, ansible_host=ansible_host, tailscale_ip=tailscale_ip, role=role)


@given(node=minimal_node())
def test_property_8_minimal_node_definition_requirements(node):
    """
    Feature: tailscale-k8s-cluster, Property 8: Minimal node definition requirements

    For any node definition in the inventory, only hostname, Tailscale IP, and role
    should be required fields, with all other fields being optional.

    Validates: Requirements 3.3
    """
    # The node should be valid with only required fields
    assert node.hostname
    assert node.ansible_host
    assert node.tailscale_ip
    assert node.role in ["control-plane", "worker"]

    # Optional fields should have default values
    assert node.reserved_cpu is None
    assert node.reserved_memory is None
    assert node.gpu is False
    assert node.node_labels == {}
    assert node.node_taints == []

    # Should be able to serialize and deserialize
    inventory_dict = node.to_inventory_dict()
    assert isinstance(inventory_dict, dict)
    assert "ansible_host" in inventory_dict
    assert "tailscale_ip" in inventory_dict

    # Should be able to round-trip through inventory format
    reconstructed = Node.from_inventory_dict(node.hostname, {**inventory_dict, "role": node.role})
    assert reconstructed.hostname == node.hostname
    assert reconstructed.ansible_host == node.ansible_host
    assert str(reconstructed.tailscale_ip) == str(node.tailscale_ip)
    assert reconstructed.role == node.role


@given(
    hostname=st.text(min_size=1, max_size=5).filter(
        lambda x: not x[0].isalnum() or not x[-1].isalnum() or ".." in x
    )
)
def test_invalid_hostname_rejected(hostname):
    """Invalid hostnames should be rejected."""
    with pytest.raises(ValueError):
        Node(hostname=hostname, ansible_host="100.64.0.1", tailscale_ip="100.64.0.1", role="worker")


@given(role=st.text().filter(lambda x: x not in ["control-plane", "worker"]))
def test_invalid_role_rejected(role):
    """Invalid roles should be rejected."""
    with pytest.raises(ValueError):
        Node(hostname="test-node", ansible_host="100.64.0.1", tailscale_ip="100.64.0.1", role=role)


@given(effect=st.text().filter(lambda x: x not in ["NoSchedule", "PreferNoSchedule", "NoExecute"]))
def test_invalid_taint_effect_rejected(effect):
    """Invalid taint effects should be rejected."""
    with pytest.raises(ValueError):
        NodeTaint(key="test", value="true", effect=effect)
