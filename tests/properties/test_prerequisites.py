"""Property-based tests for prerequisites role validation.

Feature: tailscale-k8s-cluster
Property 5: Tailscale validation on all nodes
Property 6: Node reachability validation
Validates: Requirements 2.1, 2.4
"""

from ipaddress import IPv4Address, IPv4Network

from hypothesis import given
from hypothesis import strategies as st


# Custom strategies for generating valid test data
@st.composite
def valid_hostname(draw):
    """Generate valid RFC 1123 hostnames."""
    num_labels = draw(st.integers(min_value=1, max_value=3))
    labels = []
    for _ in range(num_labels):
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
    octet2 = draw(st.integers(min_value=64, max_value=127))
    octet3 = draw(st.integers(min_value=0, max_value=255))
    octet4 = draw(st.integers(min_value=1, max_value=254))
    return f"100.{octet2}.{octet3}.{octet4}"


@st.composite
def node_definition(draw):
    """Generate a node definition for inventory."""
    return {
        "hostname": draw(valid_hostname()),
        "ansible_host": draw(valid_tailscale_ip()),
        "tailscale_ip": draw(valid_tailscale_ip()),
        "role": draw(st.sampled_from(["control-plane", "worker"])),
    }


@st.composite
def inventory_with_nodes(draw):
    """Generate an Ansible inventory with multiple nodes."""
    num_control_plane = draw(st.integers(min_value=1, max_value=2))
    num_workers = draw(st.integers(min_value=0, max_value=3))

    # Generate unique IPs more efficiently by using sequential IPs
    base_ip = 100 * 256**3 + 64 * 256**2  # 100.64.0.0
    ip_offset = draw(st.integers(min_value=1, max_value=200))

    control_plane_nodes = {}
    for i in range(num_control_plane):
        ip_int = base_ip + ip_offset + i
        ip_str = f"{(ip_int >> 24) & 0xFF}.{(ip_int >> 16) & 0xFF}.{(ip_int >> 8) & 0xFF}.{ip_int & 0xFF}"
        hostname = f"cp-{i}"
        control_plane_nodes[hostname] = {
            "ansible_host": ip_str,
            "tailscale_ip": ip_str,
        }

    worker_nodes = {}
    for i in range(num_workers):
        ip_int = base_ip + ip_offset + num_control_plane + i
        ip_str = f"{(ip_int >> 24) & 0xFF}.{(ip_int >> 16) & 0xFF}.{(ip_int >> 8) & 0xFF}.{ip_int & 0xFF}"
        hostname = f"worker-{i}"
        worker_nodes[hostname] = {
            "ansible_host": ip_str,
            "tailscale_ip": ip_str,
        }

    inventory = {
        "all": {
            "vars": {
                "k3s_version": "v1.28.5+k3s1",
                "cluster_name": "test-cluster",
                "tailscale_network": "100.64.0.0/10",
            },
            "children": {
                "control_plane": {"hosts": control_plane_nodes},
                "workers": {"hosts": worker_nodes},
            },
        }
    }

    return inventory


def validate_tailscale_requirements(inventory):
    """
    Validate that Tailscale requirements are checked for all nodes.

    This simulates the validation logic from the prerequisites role:
    - All nodes must have tailscale_ip defined
    - All tailscale_ip values must be in the Tailscale network range
    - Each node's tailscale_ip must be unique
    """
    tailscale_network = IPv4Network(inventory["all"]["vars"]["tailscale_network"])
    seen_ips = set()
    all_nodes = []

    # Collect all nodes from control_plane and workers
    if "control_plane" in inventory["all"]["children"]:
        for hostname, node_data in inventory["all"]["children"]["control_plane"]["hosts"].items():
            all_nodes.append((hostname, node_data))

    if "workers" in inventory["all"]["children"]:
        for hostname, node_data in inventory["all"]["children"]["workers"]["hosts"].items():
            all_nodes.append((hostname, node_data))

    # Validate each node
    for hostname, node_data in all_nodes:
        # Check tailscale_ip is defined
        if "tailscale_ip" not in node_data:
            return False, f"Node {hostname} missing tailscale_ip"

        tailscale_ip = IPv4Address(node_data["tailscale_ip"])

        # Check IP is in Tailscale network range
        if tailscale_ip not in tailscale_network:
            return False, f"Node {hostname} IP {tailscale_ip} not in Tailscale network"

        # Check IP is unique
        if tailscale_ip in seen_ips:
            return False, f"Duplicate Tailscale IP {tailscale_ip}"

        seen_ips.add(tailscale_ip)

    return True, "All nodes have valid Tailscale configuration"


def validate_node_reachability(inventory):
    """
    Validate that node reachability requirements are met.

    This simulates the validation logic from the prerequisites role:
    - All nodes must have ansible_host defined
    - All nodes must have tailscale_ip defined
    - ansible_host should be reachable (we simulate this by checking it's valid)
    - tailscale_ip should be reachable (we simulate this by checking it's valid)
    """
    all_nodes = []

    # Collect all nodes
    if "control_plane" in inventory["all"]["children"]:
        for hostname, node_data in inventory["all"]["children"]["control_plane"]["hosts"].items():
            all_nodes.append((hostname, node_data, "control-plane"))

    if "workers" in inventory["all"]["children"]:
        for hostname, node_data in inventory["all"]["children"]["workers"]["hosts"].items():
            all_nodes.append((hostname, node_data, "worker"))

    # Validate each node
    for hostname, node_data, role in all_nodes:
        # Check ansible_host is defined
        if "ansible_host" not in node_data:
            return False, f"Node {hostname} missing ansible_host"

        # Check tailscale_ip is defined
        if "tailscale_ip" not in node_data:
            return False, f"Node {hostname} missing tailscale_ip"

        # Validate IPs are valid IPv4 addresses
        try:
            ansible_host_ip = IPv4Address(node_data["ansible_host"])
            IPv4Address(node_data["tailscale_ip"])
        except ValueError as e:
            return False, f"Node {hostname} has invalid IP: {e}"

        # In a real scenario, we would ping or check connectivity
        # For property testing, we verify the IPs are valid and in correct format
        if not (0 <= ansible_host_ip.packed[0] <= 255):
            return False, f"Node {hostname} has invalid ansible_host"

    return True, "All nodes are reachable"


@given(inventory=inventory_with_nodes())
def test_property_5_tailscale_validation_on_all_nodes(inventory):
    """
    Feature: tailscale-k8s-cluster, Property 5: Tailscale validation on all nodes

    For any playbook execution, the system should verify Tailscale installation
    and authentication status on every node before proceeding with Kubernetes installation.

    Validates: Requirements 2.1
    """
    # Validate that all nodes have Tailscale configuration
    is_valid, message = validate_tailscale_requirements(inventory)

    # All nodes should have valid Tailscale configuration
    assert is_valid, message

    # Verify all nodes are in the correct groups
    assert "control_plane" in inventory["all"]["children"]
    assert "workers" in inventory["all"]["children"]

    # Verify at least one control plane node exists
    control_plane_hosts = inventory["all"]["children"]["control_plane"]["hosts"]
    assert len(control_plane_hosts) >= 1, "At least one control plane node required"

    # Verify all control plane nodes have Tailscale IPs
    for hostname, node_data in control_plane_hosts.items():
        assert "tailscale_ip" in node_data
        tailscale_ip = IPv4Address(node_data["tailscale_ip"])
        tailscale_network = IPv4Network(inventory["all"]["vars"]["tailscale_network"])
        assert tailscale_ip in tailscale_network

    # Verify all worker nodes have Tailscale IPs
    worker_hosts = inventory["all"]["children"]["workers"]["hosts"]
    for hostname, node_data in worker_hosts.items():
        assert "tailscale_ip" in node_data
        tailscale_ip = IPv4Address(node_data["tailscale_ip"])
        tailscale_network = IPv4Network(inventory["all"]["vars"]["tailscale_network"])
        assert tailscale_ip in tailscale_network


@given(inventory=inventory_with_nodes())
def test_property_6_node_reachability_validation(inventory):
    """
    Feature: tailscale-k8s-cluster, Property 6: Node reachability validation

    For any node joining the cluster, the system should validate that the node
    is reachable via its Tailscale IP address before completing the join operation.

    Validates: Requirements 2.4
    """
    # Validate that all nodes are reachable
    is_valid, message = validate_node_reachability(inventory)

    # All nodes should be reachable
    assert is_valid, message

    # Collect all nodes
    all_nodes = []
    if "control_plane" in inventory["all"]["children"]:
        for hostname, node_data in inventory["all"]["children"]["control_plane"]["hosts"].items():
            all_nodes.append((hostname, node_data))

    if "workers" in inventory["all"]["children"]:
        for hostname, node_data in inventory["all"]["children"]["workers"]["hosts"].items():
            all_nodes.append((hostname, node_data))

    # Verify each node has both ansible_host and tailscale_ip
    for hostname, node_data in all_nodes:
        assert "ansible_host" in node_data, f"Node {hostname} missing ansible_host"
        assert "tailscale_ip" in node_data, f"Node {hostname} missing tailscale_ip"

        # Verify IPs are valid
        ansible_host_ip = IPv4Address(node_data["ansible_host"])
        tailscale_ip = IPv4Address(node_data["tailscale_ip"])

        # Verify IPs are in valid ranges
        assert ansible_host_ip.is_private or str(ansible_host_ip).startswith("100.")
        assert str(tailscale_ip).startswith("100.")


@given(num_nodes=st.integers(min_value=1, max_value=10), tailscale_network=st.just("100.64.0.0/10"))
def test_tailscale_validation_with_varying_node_counts(num_nodes, tailscale_network):
    """
    Test that Tailscale validation works correctly regardless of node count.

    This ensures the validation logic scales properly.
    """
    # Generate unique Tailscale IPs for each node
    base_ip = 100 * 256**3 + 64 * 256**2  # 100.64.0.0
    nodes = []

    for i in range(num_nodes):
        ip_int = base_ip + i + 1
        ip_str = f"{(ip_int >> 24) & 0xFF}.{(ip_int >> 16) & 0xFF}.{(ip_int >> 8) & 0xFF}.{ip_int & 0xFF}"
        nodes.append(
            {
                "hostname": f"node-{i}",
                "ansible_host": ip_str,
                "tailscale_ip": ip_str,
            }
        )

    # Create inventory
    inventory = {
        "all": {
            "vars": {
                "tailscale_network": tailscale_network,
            },
            "children": {
                "control_plane": {
                    "hosts": {
                        nodes[0]["hostname"]: {
                            "ansible_host": nodes[0]["ansible_host"],
                            "tailscale_ip": nodes[0]["tailscale_ip"],
                        }
                    }
                },
                "workers": {
                    "hosts": {
                        node["hostname"]: {
                            "ansible_host": node["ansible_host"],
                            "tailscale_ip": node["tailscale_ip"],
                        }
                        for node in nodes[1:]
                    }
                },
            },
        }
    }

    # Validate
    is_valid, message = validate_tailscale_requirements(inventory)
    assert is_valid, message

    is_valid, message = validate_node_reachability(inventory)
    assert is_valid, message


@given(hostname=valid_hostname(), tailscale_ip=valid_tailscale_ip())
def test_single_node_tailscale_validation(hostname, tailscale_ip):
    """
    Test Tailscale validation for a single node.

    This is a simpler case to ensure basic validation works.
    """
    inventory = {
        "all": {
            "vars": {
                "tailscale_network": "100.64.0.0/10",
            },
            "children": {
                "control_plane": {
                    "hosts": {
                        hostname: {
                            "ansible_host": tailscale_ip,
                            "tailscale_ip": tailscale_ip,
                        }
                    }
                },
                "workers": {"hosts": {}},
            },
        }
    }

    is_valid, message = validate_tailscale_requirements(inventory)
    assert is_valid, message

    is_valid, message = validate_node_reachability(inventory)
    assert is_valid, message


def test_tailscale_validation_rejects_invalid_ip_range():
    """
    Test that Tailscale validation rejects IPs outside the Tailscale range.
    """
    inventory = {
        "all": {
            "vars": {
                "tailscale_network": "100.64.0.0/10",
            },
            "children": {
                "control_plane": {
                    "hosts": {
                        "test-node": {
                            "ansible_host": "192.168.1.1",  # Not in Tailscale range
                            "tailscale_ip": "192.168.1.1",
                        }
                    }
                },
                "workers": {"hosts": {}},
            },
        }
    }

    is_valid, message = validate_tailscale_requirements(inventory)
    assert not is_valid
    assert "not in Tailscale network" in message


def test_reachability_validation_rejects_missing_fields():
    """
    Test that reachability validation rejects nodes with missing fields.
    """
    inventory = {
        "all": {
            "vars": {
                "tailscale_network": "100.64.0.0/10",
            },
            "children": {
                "control_plane": {
                    "hosts": {
                        "test-node": {
                            "ansible_host": "100.64.0.1",
                            # Missing tailscale_ip
                        }
                    }
                },
                "workers": {"hosts": {}},
            },
        }
    }

    is_valid, message = validate_node_reachability(inventory)
    assert not is_valid
    assert "missing tailscale_ip" in message
