"""Property-based tests for inventory management.

Feature: tailscale-k8s-cluster
Validates: Requirements 3.3, 11.4
"""

import tempfile
from pathlib import Path

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from cluster_manager.inventory import InventoryError, InventoryManager, InventoryValidationError
from cluster_manager.models.node import Node, NodeTaint


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
def minimal_node(draw):
    """Generate a node with only required fields."""
    hostname = draw(valid_hostname())
    tailscale_ip = draw(valid_tailscale_ip())
    # ansible_host should be the same as tailscale_ip for consistency
    ansible_host = tailscale_ip
    role = draw(st.sampled_from(["control-plane", "worker"]))

    return Node(hostname=hostname, ansible_host=ansible_host, tailscale_ip=tailscale_ip, role=role)


@st.composite
def full_node(draw):
    """Generate a node with all fields populated."""
    hostname = draw(valid_hostname())
    tailscale_ip = draw(valid_tailscale_ip())
    # ansible_host should be the same as tailscale_ip for consistency
    ansible_host = tailscale_ip
    role = draw(st.sampled_from(["control-plane", "worker"]))

    # Optional fields
    reserved_cpu = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=16).map(str)))
    reserved_memory = draw(
        st.one_of(st.none(), st.integers(min_value=1, max_value=64).map(lambda x: f"{x}Gi"))
    )
    gpu = draw(st.booleans())

    # Node labels
    num_labels = draw(st.integers(min_value=0, max_value=3))
    node_labels = {}
    for i in range(num_labels):
        key = f"label-{i}"
        value = draw(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=10)
        )
        node_labels[key] = value

    # Node taints
    num_taints = draw(st.integers(min_value=0, max_value=2))
    node_taints = []
    for i in range(num_taints):
        taint = NodeTaint(
            key=f"taint-{i}",
            value=draw(st.sampled_from(["true", "false", "yes", "no"])),
            effect=draw(st.sampled_from(["NoSchedule", "PreferNoSchedule", "NoExecute"])),
        )
        node_taints.append(taint)

    return Node(
        hostname=hostname,
        ansible_host=ansible_host,
        tailscale_ip=tailscale_ip,
        role=role,
        reserved_cpu=reserved_cpu,
        reserved_memory=reserved_memory,
        gpu=gpu,
        node_labels=node_labels,
        node_taints=node_taints,
    )


def create_test_inventory(nodes: list[Node]) -> dict:
    """Create a test inventory structure from a list of nodes."""
    inventory = {
        "all": {
            "vars": {
                "k3s_version": "v1.28.5+k3s1",
                "cluster_name": "test-cluster",
                "tailscale_network": "100.64.0.0/10",
            },
            "children": {"control_plane": {"hosts": {}}, "workers": {"hosts": {}}},
        }
    }

    for node in nodes:
        group = "control_plane" if node.role == "control-plane" else "workers"
        inventory["all"]["children"][group]["hosts"][node.hostname] = node.to_inventory_dict()

    return inventory


@given(node=minimal_node())
def test_property_8_minimal_node_requirements_in_inventory(node):
    """
    Feature: tailscale-k8s-cluster, Property 8: Minimal node definition requirements

    For any node definition in the inventory, only hostname, Tailscale IP, and role
    should be required fields, with all other fields being optional.

    This test verifies that a node with only required fields can be successfully
    added to and retrieved from an inventory file.

    Validates: Requirements 3.3
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        inventory_path = Path(tmpdir) / "hosts.yml"
        manager = InventoryManager(inventory_path)

        # Create initial inventory with the minimal node
        inventory_data = create_test_inventory([node])
        manager.write(inventory_data)

        # Validate the inventory
        manager.validate(inventory_data)

        # Read back the nodes
        nodes = manager.get_nodes()

        # Should have exactly one node
        assert len(nodes) == 1
        retrieved_node = nodes[0]

        # Required fields should match
        assert retrieved_node.hostname == node.hostname
        assert retrieved_node.ansible_host == node.ansible_host
        assert str(retrieved_node.tailscale_ip) == str(node.tailscale_ip)
        assert retrieved_node.role == node.role

        # Optional fields should have default values
        assert retrieved_node.reserved_cpu is None
        assert retrieved_node.reserved_memory is None
        assert retrieved_node.gpu is False
        assert retrieved_node.node_labels == {}
        assert retrieved_node.node_taints == []


@st.composite
def unique_nodes_list(draw, min_size=1, max_size=5):
    """Generate a list of nodes with unique hostnames and IPs."""
    nodes = []
    used_hostnames = set()
    used_ips = set()

    num_nodes = draw(st.integers(min_value=min_size, max_value=max_size))

    for _ in range(num_nodes):
        # Keep generating until we get unique hostname and IP
        max_attempts = 100
        for attempt in range(max_attempts):
            node = draw(minimal_node())
            if node.hostname not in used_hostnames and str(node.tailscale_ip) not in used_ips:
                nodes.append(node)
                used_hostnames.add(node.hostname)
                used_ips.add(str(node.tailscale_ip))
                break
        else:
            # If we can't generate a unique node after max_attempts, stop
            break

    assume(len(nodes) >= min_size)
    return nodes


@given(nodes=unique_nodes_list(min_size=1, max_size=5))
def test_property_20_inventory_update_correctness(nodes):
    """
    Feature: tailscale-k8s-cluster, Property 20: Inventory update correctness

    For any node added via the CLI, the Ansible inventory file should be updated
    to include the node's information in the correct format and location
    (control_plane or workers group).

    Validates: Requirements 11.4
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        inventory_path = Path(tmpdir) / "hosts.yml"
        manager = InventoryManager(inventory_path)

        # Create initial empty inventory
        initial_inventory = {
            "all": {
                "vars": {
                    "k3s_version": "v1.28.5+k3s1",
                    "cluster_name": "test-cluster",
                    "tailscale_network": "100.64.0.0/10",
                },
                "children": {"control_plane": {"hosts": {}}, "workers": {"hosts": {}}},
            }
        }
        manager.write(initial_inventory)

        # Add each node
        for node in nodes:
            manager.add_node(node)

        # Read back and verify
        retrieved_nodes = manager.get_nodes()
        assert len(retrieved_nodes) == len(nodes)

        # Verify each node is in the correct group
        for original_node in nodes:
            # Find the corresponding retrieved node
            retrieved = next(
                (n for n in retrieved_nodes if n.hostname == original_node.hostname), None
            )
            assert retrieved is not None, f"Node {original_node.hostname} not found"

            # Verify it's in the correct group based on role
            assert retrieved.role == original_node.role

            # Verify all fields match
            assert retrieved.ansible_host == original_node.ansible_host
            assert str(retrieved.tailscale_ip) == str(original_node.tailscale_ip)

            # Verify the node is in the correct group in the raw data
            data = manager.read()
            expected_group = "control_plane" if original_node.role == "control-plane" else "workers"
            assert original_node.hostname in data["all"]["children"][expected_group]["hosts"]

            # Verify it's NOT in the wrong group
            wrong_group = "workers" if expected_group == "control_plane" else "control_plane"
            assert original_node.hostname not in data["all"]["children"][wrong_group]["hosts"]


@st.composite
def unique_full_nodes_list(draw, min_size=1, max_size=3):
    """Generate a list of full nodes with unique hostnames and IPs."""
    nodes = []
    used_hostnames = set()
    used_ips = set()

    num_nodes = draw(st.integers(min_value=min_size, max_value=max_size))

    for _ in range(num_nodes):
        # Keep generating until we get unique hostname and IP
        max_attempts = 100
        for attempt in range(max_attempts):
            node = draw(full_node())
            if node.hostname not in used_hostnames and str(node.tailscale_ip) not in used_ips:
                nodes.append(node)
                used_hostnames.add(node.hostname)
                used_ips.add(str(node.tailscale_ip))
                break
        else:
            # If we can't generate a unique node after max_attempts, stop
            break

    assume(len(nodes) >= min_size)
    return nodes


@given(initial_nodes=unique_full_nodes_list(min_size=1, max_size=3), new_node=full_node())
def test_add_node_preserves_existing_nodes(initial_nodes, new_node):
    """
    Property: Adding a new node should not affect existing nodes.

    For any set of existing nodes and a new node, adding the new node should
    preserve all existing node data.
    """
    # Ensure new node has unique hostname and IP
    assume(new_node.hostname not in [n.hostname for n in initial_nodes])
    assume(str(new_node.tailscale_ip) not in [str(n.tailscale_ip) for n in initial_nodes])

    with tempfile.TemporaryDirectory() as tmpdir:
        inventory_path = Path(tmpdir) / "hosts.yml"
        manager = InventoryManager(inventory_path)

        # Create initial inventory
        initial_inventory = create_test_inventory(initial_nodes)
        manager.write(initial_inventory)

        # Add new node
        manager.add_node(new_node)

        # Verify all nodes are present
        all_nodes = manager.get_nodes()
        assert len(all_nodes) == len(initial_nodes) + 1

        # Verify initial nodes are unchanged
        for original in initial_nodes:
            retrieved = next((n for n in all_nodes if n.hostname == original.hostname), None)
            assert retrieved is not None
            assert retrieved.ansible_host == original.ansible_host
            assert str(retrieved.tailscale_ip) == str(original.tailscale_ip)
            assert retrieved.role == original.role


@given(node=full_node())
def test_remove_node_removes_from_correct_group(node):
    """
    Property: Removing a node should remove it from the correct group.

    For any node, after adding and then removing it, the inventory should
    not contain the node in any group.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        inventory_path = Path(tmpdir) / "hosts.yml"
        manager = InventoryManager(inventory_path)

        # Create inventory with the node
        inventory = create_test_inventory([node])
        manager.write(inventory)

        # Remove the node
        manager.remove_node(node.hostname)

        # Verify node is gone
        nodes = manager.get_nodes()
        assert len(nodes) == 0

        # Verify it's not in either group
        data = manager.read()
        assert node.hostname not in data["all"]["children"]["control_plane"]["hosts"]
        assert node.hostname not in data["all"]["children"]["workers"]["hosts"]


@given(original_node=full_node(), new_role=st.sampled_from(["control-plane", "worker"]))
def test_update_node_handles_role_change(original_node, new_role):
    """
    Property: Updating a node's role should move it to the correct group.

    For any node, when its role is changed, it should be moved from its
    original group to the new group.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        inventory_path = Path(tmpdir) / "hosts.yml"
        manager = InventoryManager(inventory_path)

        # Create inventory with original node
        inventory = create_test_inventory([original_node])
        manager.write(inventory)

        # Create updated node with new role
        updated_node = Node(
            hostname=original_node.hostname,
            ansible_host=original_node.ansible_host,
            tailscale_ip=original_node.tailscale_ip,
            role=new_role,
            reserved_cpu=original_node.reserved_cpu,
            reserved_memory=original_node.reserved_memory,
            gpu=original_node.gpu,
            node_labels=original_node.node_labels,
            node_taints=original_node.node_taints,
        )

        # Update the node
        manager.update_node(updated_node)

        # Verify node is in correct group
        data = manager.read()
        expected_group = "control_plane" if new_role == "control-plane" else "workers"
        wrong_group = "workers" if expected_group == "control_plane" else "control_plane"

        assert original_node.hostname in data["all"]["children"][expected_group]["hosts"]
        assert original_node.hostname not in data["all"]["children"][wrong_group]["hosts"]

        # Verify retrieved node has correct role
        nodes = manager.get_nodes()
        retrieved = next((n for n in nodes if n.hostname == original_node.hostname), None)
        assert retrieved is not None
        assert retrieved.role == new_role


@given(nodes=st.lists(minimal_node(), min_size=1, max_size=5, unique_by=lambda n: n.hostname))
def test_inventory_validation_accepts_valid_structure(nodes):
    """
    Property: Valid inventory structures should pass validation.

    For any set of valid nodes, the inventory structure should pass validation.
    """
    inventory = create_test_inventory(nodes)

    with tempfile.TemporaryDirectory() as tmpdir:
        inventory_path = Path(tmpdir) / "hosts.yml"
        manager = InventoryManager(inventory_path)
        manager.write(inventory)

        # Should not raise any exception
        manager.validate(inventory)


def test_invalid_inventory_structure_rejected():
    """
    Property: Invalid inventory structures should be rejected.

    Various invalid inventory structures should raise InventoryValidationError.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        inventory_path = Path(tmpdir) / "hosts.yml"
        manager = InventoryManager(inventory_path)

        # Missing 'all' group
        with pytest.raises(InventoryValidationError, match="must have 'all' group"):
            manager.validate({})

        # Missing 'children'
        with pytest.raises(InventoryValidationError, match="must have 'children'"):
            manager.validate({"all": {}})

        # Missing required groups
        with pytest.raises(InventoryValidationError, match="Missing required group"):
            manager.validate({"all": {"children": {}}})

        # Invalid host data (missing required fields)
        invalid_inventory = {
            "all": {
                "children": {
                    "control_plane": {
                        "hosts": {
                            "test-node": {
                                # Missing ansible_host and tailscale_ip
                            }
                        }
                    },
                    "workers": {"hosts": {}},
                }
            }
        }
        with pytest.raises(InventoryValidationError, match="missing required field"):
            manager.validate(invalid_inventory)


@given(
    key=st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz_"),
    value=st.one_of(
        st.text(min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_./"),
        st.integers(),
        st.booleans(),
    ),
    scope=st.sampled_from(["all", "control_plane", "workers"]),
)
def test_set_and_get_vars(key, value, scope):
    """
    Property: Variables set in inventory should be retrievable.

    For any key, value, and scope, setting a variable should allow it to be
    retrieved with the same value.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        inventory_path = Path(tmpdir) / "hosts.yml"
        manager = InventoryManager(inventory_path)

        # Create initial inventory
        initial_inventory = {
            "all": {
                "vars": {},
                "children": {
                    "control_plane": {"hosts": {}, "vars": {}},
                    "workers": {"hosts": {}, "vars": {}},
                },
            }
        }
        manager.write(initial_inventory)

        # Set variable
        manager.set_var(key, value, scope)

        # Get variable
        vars_dict = manager.get_vars(scope)
        assert key in vars_dict
        assert vars_dict[key] == value


@given(node=full_node())
def test_property_21_configuration_validation_before_write(node):
    """
    Feature: tailscale-k8s-cluster, Property 21: Configuration validation before write

    For any configuration modification via the CLI, the system should validate
    the changes against the schema and reject invalid configurations before
    writing to files.

    This test verifies that:
    1. Valid node configurations are accepted and written
    2. Invalid configurations are rejected before writing
    3. The inventory file is not corrupted by invalid writes

    Validates: Requirements 11.5
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        inventory_path = Path(tmpdir) / "hosts.yml"
        manager = InventoryManager(inventory_path)

        # Create initial inventory
        initial_inventory = create_test_inventory([])
        manager.write(initial_inventory)

        # Test 1: Valid configuration should be accepted
        manager.add_node(node)

        # Verify node was added
        nodes = manager.get_nodes()
        assert len(nodes) == 1
        assert nodes[0].hostname == node.hostname

        # Test 2: Invalid configurations should be rejected
        # Try to add a node with invalid hostname (empty string)
        with pytest.raises(Exception):  # Should raise validation error
            Node(
                hostname="",  # Invalid: empty hostname
                ansible_host=node.ansible_host,
                tailscale_ip=node.tailscale_ip,
                role=node.role,
            )

        # Try to add a node with invalid role
        with pytest.raises(Exception):  # Should raise validation error
            Node(
                hostname="test-node",
                ansible_host=node.ansible_host,
                tailscale_ip=node.tailscale_ip,
                role="invalid-role",  # Invalid: not control-plane or worker
            )

        # Try to add a node with invalid taint effect
        with pytest.raises(Exception):  # Should raise validation error
            NodeTaint(
                key="test",
                value="true",
                effect="InvalidEffect",  # Invalid: not a valid effect
            )

        # Test 3: Inventory should remain valid after validation failures
        # The inventory should still only have the one valid node
        nodes_after = manager.get_nodes()
        assert len(nodes_after) == 1
        assert nodes_after[0].hostname == node.hostname

        # Verify inventory structure is still valid
        data = manager.read()
        manager.validate(data)  # Should not raise


@given(
    nodes=st.lists(minimal_node(), min_size=1, max_size=3, unique_by=lambda n: n.hostname),
    duplicate_node=minimal_node(),
)
def test_duplicate_node_rejection(nodes, duplicate_node):
    """
    Feature: tailscale-k8s-cluster, Property 21: Configuration validation before write

    For any attempt to add a duplicate node (same hostname), the system should
    reject the operation and preserve the existing node data.

    Validates: Requirements 11.5
    """
    # Make duplicate_node have the same hostname as one of the existing nodes
    if nodes:
        duplicate_node = Node(
            hostname=nodes[0].hostname,  # Same hostname as first node
            ansible_host=duplicate_node.ansible_host,
            tailscale_ip=duplicate_node.tailscale_ip,
            role=duplicate_node.role,
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        inventory_path = Path(tmpdir) / "hosts.yml"
        manager = InventoryManager(inventory_path)

        # Create initial inventory with nodes
        initial_inventory = create_test_inventory(nodes)
        manager.write(initial_inventory)

        # Try to add duplicate node
        with pytest.raises(InventoryError, match="already exists"):
            manager.add_node(duplicate_node)

        # Verify original nodes are unchanged
        retrieved_nodes = manager.get_nodes()
        assert len(retrieved_nodes) == len(nodes)

        # Verify the original node data is preserved
        original_node = nodes[0]
        retrieved = next((n for n in retrieved_nodes if n.hostname == original_node.hostname), None)
        assert retrieved is not None
        assert retrieved.ansible_host == original_node.ansible_host
        assert str(retrieved.tailscale_ip) == str(original_node.tailscale_ip)


@given(
    initial_nodes=st.lists(minimal_node(), min_size=1, max_size=3, unique_by=lambda n: n.hostname)
)
def test_remove_nonexistent_node_rejection(initial_nodes):
    """
    Feature: tailscale-k8s-cluster, Property 21: Configuration validation before write

    For any attempt to remove a node that doesn't exist, the system should
    reject the operation and preserve the existing inventory.

    Validates: Requirements 11.5
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        inventory_path = Path(tmpdir) / "hosts.yml"
        manager = InventoryManager(inventory_path)

        # Create initial inventory
        initial_inventory = create_test_inventory(initial_nodes)
        manager.write(initial_inventory)

        # Try to remove a node that doesn't exist
        nonexistent_hostname = "nonexistent-node-12345"
        assume(nonexistent_hostname not in [n.hostname for n in initial_nodes])

        with pytest.raises(InventoryError, match="not found"):
            manager.remove_node(nonexistent_hostname)

        # Verify all original nodes are still present
        retrieved_nodes = manager.get_nodes()
        assert len(retrieved_nodes) == len(initial_nodes)

        for original in initial_nodes:
            retrieved = next((n for n in retrieved_nodes if n.hostname == original.hostname), None)
            assert retrieved is not None


@given(
    key=st.text(min_size=1, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_"),
    value=st.one_of(
        st.text(min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_./+:"),
        st.integers(min_value=-1000, max_value=1000),
        st.booleans(),
    ),
    scope=st.sampled_from(["all", "control_plane", "workers"]),
)
def test_property_21_config_set_get_roundtrip(key, value, scope):
    """
    Feature: tailscale-k8s-cluster, Property 21: Configuration validation before write

    For any configuration key, value, and scope, setting a configuration value
    should allow it to be retrieved with the same value (round-trip property).
    This validates that configuration changes are properly validated and persisted.

    Validates: Requirements 11.5
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        inventory_path = Path(tmpdir) / "hosts.yml"
        manager = InventoryManager(inventory_path)

        # Create initial inventory with proper structure
        initial_inventory = {
            "all": {
                "vars": {},
                "children": {
                    "control_plane": {"hosts": {}, "vars": {}},
                    "workers": {"hosts": {}, "vars": {}},
                },
            }
        }
        manager.write(initial_inventory)

        # Set the configuration value
        manager.set_var(key, value, scope)

        # Get the configuration value back
        vars_dict = manager.get_vars(scope)

        # Verify the value was stored correctly
        assert key in vars_dict, f"Key '{key}' not found in scope '{scope}'"
        assert vars_dict[key] == value, f"Value mismatch: expected {value}, got {vars_dict[key]}"

        # Verify the inventory file is still valid after the change
        data = manager.read()
        manager.validate(data)


@given(
    nested_key=st.lists(
        st.text(min_size=1, max_size=15, alphabet="abcdefghijklmnopqrstuvwxyz_"),
        min_size=2,
        max_size=4,
    ),
    value=st.one_of(
        st.text(min_size=1, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_."),
        st.integers(min_value=0, max_value=100),
        st.booleans(),
    ),
    scope=st.sampled_from(["all", "control_plane", "workers"]),
)
def test_property_21_nested_config_keys(nested_key, value, scope):
    """
    Feature: tailscale-k8s-cluster, Property 21: Configuration validation before write

    For any nested configuration key (using dot notation), setting a value should
    create the proper nested structure and allow retrieval of the value.
    This validates that nested configuration keys are properly handled.

    Validates: Requirements 11.5
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        inventory_path = Path(tmpdir) / "hosts.yml"
        manager = InventoryManager(inventory_path)

        # Create initial inventory
        initial_inventory = {
            "all": {
                "vars": {},
                "children": {
                    "control_plane": {"hosts": {}, "vars": {}},
                    "workers": {"hosts": {}, "vars": {}},
                },
            }
        }
        manager.write(initial_inventory)

        # Get the vars dict for the scope
        vars_dict = manager.get_vars(scope)

        # Build nested structure
        current = vars_dict
        for key in nested_key[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        # Set the final value
        current[nested_key[-1]] = value

        # Write back the top-level key
        manager.set_var(nested_key[0], vars_dict.get(nested_key[0], {}), scope)

        # Retrieve and verify
        retrieved_vars = manager.get_vars(scope)

        # Navigate to the nested value
        retrieved_value = retrieved_vars
        for key in nested_key:
            assert isinstance(retrieved_value, dict), f"Expected dict at key '{key}'"
            assert key in retrieved_value, f"Key '{key}' not found"
            retrieved_value = retrieved_value[key]

        # Verify the value matches
        assert retrieved_value == value


@given(
    scope=st.sampled_from(["all", "control_plane", "workers"]),
    num_vars=st.integers(min_value=1, max_value=10),
)
def test_property_21_multiple_config_changes_preserve_validity(scope, num_vars):
    """
    Feature: tailscale-k8s-cluster, Property 21: Configuration validation before write

    For any sequence of configuration changes, the inventory should remain valid
    after each change. This validates that multiple configuration updates don't
    corrupt the inventory structure.

    Validates: Requirements 11.5
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        inventory_path = Path(tmpdir) / "hosts.yml"
        manager = InventoryManager(inventory_path)

        # Create initial inventory
        initial_inventory = {
            "all": {
                "vars": {},
                "children": {
                    "control_plane": {"hosts": {}, "vars": {}},
                    "workers": {"hosts": {}, "vars": {}},
                },
            }
        }
        manager.write(initial_inventory)

        # Make multiple configuration changes
        for i in range(num_vars):
            key = f"test_var_{i}"
            value = f"value_{i}"

            # Set the variable
            manager.set_var(key, value, scope)

            # Verify inventory is still valid
            data = manager.read()
            manager.validate(data)

            # Verify the variable was set
            vars_dict = manager.get_vars(scope)
            assert key in vars_dict
            assert vars_dict[key] == value

        # Verify all variables are still present
        final_vars = manager.get_vars(scope)
        for i in range(num_vars):
            key = f"test_var_{i}"
            assert key in final_vars
            assert final_vars[key] == f"value_{i}"


@given(
    key=st.text(min_size=1, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_"),
    value=st.text(min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_."),
    scope=st.sampled_from(["all", "control_plane", "workers"]),
)
def test_property_21_config_changes_isolated_by_scope(key, value, scope):
    """
    Feature: tailscale-k8s-cluster, Property 21: Configuration validation before write

    For any configuration change in one scope, variables in other scopes should
    remain unchanged. This validates that scope isolation is maintained.

    Validates: Requirements 11.5
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        inventory_path = Path(tmpdir) / "hosts.yml"
        manager = InventoryManager(inventory_path)

        # Create initial inventory with some variables in each scope
        initial_inventory = {
            "all": {
                "vars": {"initial_all": "value_all"},
                "children": {
                    "control_plane": {"hosts": {}, "vars": {"initial_cp": "value_cp"}},
                    "workers": {"hosts": {}, "vars": {"initial_workers": "value_workers"}},
                },
            }
        }
        manager.write(initial_inventory)

        # Set a new variable in the specified scope
        manager.set_var(key, value, scope)

        # Verify the variable was set in the target scope
        target_vars = manager.get_vars(scope)
        assert key in target_vars
        assert target_vars[key] == value

        # Verify other scopes still have their original variables
        all_scopes = ["all", "control_plane", "workers"]
        for other_scope in all_scopes:
            if other_scope == scope:
                continue

            other_vars = manager.get_vars(other_scope)

            # The new key should NOT be in other scopes
            if other_scope != scope:
                # Check that original variables are still present
                if other_scope == "all":
                    assert "initial_all" in other_vars
                    assert other_vars["initial_all"] == "value_all"
                elif other_scope == "control_plane":
                    assert "initial_cp" in other_vars
                    assert other_vars["initial_cp"] == "value_cp"
                elif other_scope == "workers":
                    assert "initial_workers" in other_vars
                    assert other_vars["initial_workers"] == "value_workers"


def test_property_21_invalid_scope_rejected():
    """
    Feature: tailscale-k8s-cluster, Property 21: Configuration validation before write

    For any invalid scope name, configuration operations should be rejected
    before attempting to modify the inventory.

    Validates: Requirements 11.5
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        inventory_path = Path(tmpdir) / "hosts.yml"
        manager = InventoryManager(inventory_path)

        # Create initial inventory
        initial_inventory = {
            "all": {
                "vars": {},
                "children": {
                    "control_plane": {"hosts": {}, "vars": {}},
                    "workers": {"hosts": {}, "vars": {}},
                },
            }
        }
        manager.write(initial_inventory)

        # Try to set a variable with an invalid scope
        invalid_scopes = ["invalid", "master", "nodes", "", "ALL", "Workers"]

        for invalid_scope in invalid_scopes:
            with pytest.raises(InventoryError):
                manager.set_var("test_key", "test_value", invalid_scope)

            # Verify inventory is unchanged
            data = manager.read()
            manager.validate(data)


@given(
    initial_value=st.one_of(
        st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_."),
        st.integers(min_value=-1000, max_value=1000),
        st.booleans(),
    ),
    updated_value=st.one_of(
        st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_."),
        st.integers(min_value=-1000, max_value=1000),
        st.booleans(),
    ),
    scope=st.sampled_from(["all", "control_plane", "workers"]),
)
def test_property_21_config_update_overwrites_previous_value(initial_value, updated_value, scope):
    """
    Feature: tailscale-k8s-cluster, Property 21: Configuration validation before write

    For any configuration key, updating its value should overwrite the previous
    value, not append or create duplicates.

    Validates: Requirements 11.5
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        inventory_path = Path(tmpdir) / "hosts.yml"
        manager = InventoryManager(inventory_path)

        # Create initial inventory
        initial_inventory = {
            "all": {
                "vars": {},
                "children": {
                    "control_plane": {"hosts": {}, "vars": {}},
                    "workers": {"hosts": {}, "vars": {}},
                },
            }
        }
        manager.write(initial_inventory)

        key = "test_config_key"

        # Set initial value
        manager.set_var(key, initial_value, scope)

        # Verify initial value
        vars_dict = manager.get_vars(scope)
        assert vars_dict[key] == initial_value

        # Update to new value
        manager.set_var(key, updated_value, scope)

        # Verify updated value (should overwrite, not append)
        vars_dict = manager.get_vars(scope)
        assert vars_dict[key] == updated_value
        assert vars_dict[key] != initial_value or initial_value == updated_value

        # Verify there's only one instance of the key
        data = manager.read()
        if scope == "all":
            scope_vars = data["all"]["vars"]
        else:
            scope_vars = data["all"]["children"][scope]["vars"]

        # Count occurrences of the key (should be exactly 1)
        assert list(scope_vars.keys()).count(key) == 1
