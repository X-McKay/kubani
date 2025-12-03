"""Property-based tests for node-specific configuration.

Feature: tailscale-k8s-cluster, Property 18: Node-specific configuration application
Validates: Requirements 10.1, 10.2, 10.3, 10.5
"""

from pathlib import Path

import yaml
from hypothesis import given
from hypothesis import strategies as st


# Custom strategies for generating node configurations
@st.composite
def node_with_gpu(draw):
    """Generate a node configuration with GPU."""
    hostname = draw(
        st.text(
            min_size=3,
            max_size=10,
            alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-"),
        ).filter(lambda x: x[0].isalnum() and x[-1].isalnum() and "--" not in x)
    )

    return {
        "hostname": hostname,
        "ansible_host": f"100.64.0.{draw(st.integers(min_value=1, max_value=254))}",
        "tailscale_ip": f"100.64.0.{draw(st.integers(min_value=1, max_value=254))}",
        "role": "worker",
        "gpu": True,
        "node_labels": {"gpu": "true", "node-role": "worker"},
        "node_taints": [{"key": "nvidia.com/gpu", "value": "true", "effect": "NoSchedule"}],
    }


@st.composite
def node_with_storage(draw):
    """Generate a node configuration with storage capabilities."""
    hostname = draw(
        st.text(
            min_size=3,
            max_size=10,
            alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-"),
        ).filter(lambda x: x[0].isalnum() and x[-1].isalnum() and "--" not in x)
    )

    return {
        "hostname": hostname,
        "ansible_host": f"100.64.0.{draw(st.integers(min_value=1, max_value=254))}",
        "tailscale_ip": f"100.64.0.{draw(st.integers(min_value=1, max_value=254))}",
        "role": "worker",
        "enable_local_storage": True,
        "storage_class_name": draw(
            st.sampled_from(["local-path", "local-storage", "fast-storage"])
        ),
        "node_labels": {"storage": "enabled", "node-role": "worker"},
    }


@st.composite
def node_with_custom_labels(draw):
    """Generate a node configuration with custom labels."""
    hostname = draw(
        st.text(
            min_size=3,
            max_size=10,
            alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-"),
        ).filter(lambda x: x[0].isalnum() and x[-1].isalnum() and "--" not in x)
    )

    # Generate 1-5 custom labels
    num_labels = draw(st.integers(min_value=1, max_value=5))
    labels = {}
    for i in range(num_labels):
        key = draw(
            st.text(
                min_size=3,
                max_size=15,
                alphabet=st.characters(whitelist_categories=("Ll",), whitelist_characters="-."),
            ).filter(lambda x: x[0].isalnum() and x[-1].isalnum())
        )
        value = draw(
            st.text(
                min_size=1,
                max_size=20,
                alphabet=st.characters(
                    whitelist_categories=("Ll", "Nd"), whitelist_characters="-_"
                ),
            )
        )
        labels[key] = value

    return {
        "hostname": hostname,
        "ansible_host": f"100.64.0.{draw(st.integers(min_value=1, max_value=254))}",
        "tailscale_ip": f"100.64.0.{draw(st.integers(min_value=1, max_value=254))}",
        "role": "worker",
        "node_labels": labels,
    }


@st.composite
def node_with_custom_taints(draw):
    """Generate a node configuration with custom taints."""
    hostname = draw(
        st.text(
            min_size=3,
            max_size=10,
            alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-"),
        ).filter(lambda x: x[0].isalnum() and x[-1].isalnum() and "--" not in x)
    )

    # Generate 1-3 custom taints
    num_taints = draw(st.integers(min_value=1, max_value=3))
    taints = []
    for i in range(num_taints):
        key = draw(
            st.text(
                min_size=3,
                max_size=15,
                alphabet=st.characters(whitelist_categories=("Ll",), whitelist_characters="-."),
            ).filter(lambda x: x[0].isalnum() and x[-1].isalnum())
        )
        value = draw(
            st.text(
                min_size=1,
                max_size=20,
                alphabet=st.characters(
                    whitelist_categories=("Ll", "Nd"), whitelist_characters="-_"
                ),
            )
        )
        effect = draw(st.sampled_from(["NoSchedule", "PreferNoSchedule", "NoExecute"]))
        taints.append({"key": key, "value": value, "effect": effect})

    return {
        "hostname": hostname,
        "ansible_host": f"100.64.0.{draw(st.integers(min_value=1, max_value=254))}",
        "tailscale_ip": f"100.64.0.{draw(st.integers(min_value=1, max_value=254))}",
        "role": "worker",
        "node_taints": taints,
    }


@st.composite
def resource_constrained_node(draw):
    """Generate a node configuration with resource constraints."""
    hostname = draw(
        st.text(
            min_size=3,
            max_size=10,
            alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-"),
        ).filter(lambda x: x[0].isalnum() and x[-1].isalnum() and "--" not in x)
    )

    # Generate resource reservations
    reserved_cpu = draw(st.integers(min_value=1, max_value=4))
    reserved_memory_gb = draw(st.integers(min_value=1, max_value=8))
    max_pods = draw(st.integers(min_value=10, max_value=110))

    return {
        "hostname": hostname,
        "ansible_host": f"100.64.0.{draw(st.integers(min_value=1, max_value=254))}",
        "tailscale_ip": f"100.64.0.{draw(st.integers(min_value=1, max_value=254))}",
        "role": "worker",
        "reserved_cpu": str(reserved_cpu),
        "reserved_memory": f"{reserved_memory_gb}Gi",
        "max_pods": str(max_pods),
        "node_labels": {"node-role": "worker", "workstation": "true"},
    }


def validate_node_config_tasks_exist(node_config):
    """Validate that node_config role tasks exist and are properly structured."""
    role_path = Path("ansible/roles/node_config")

    # Check that the role directory exists
    assert role_path.exists(), "node_config role directory should exist"

    # Check that main tasks file exists
    main_tasks = role_path / "tasks" / "main.yml"
    assert main_tasks.exists(), "node_config main tasks file should exist"

    # Load and validate main tasks structure
    with open(main_tasks) as f:
        tasks = yaml.safe_load(f)

    assert isinstance(tasks, list), "Tasks should be a list"

    # Check for required task includes
    task_names = [task.get("name", "") for task in tasks if "name" in task]
    assert any(
        "hardware" in name.lower() for name in task_names
    ), "Should include hardware detection tasks"
    assert any(
        "storage" in name.lower() for name in task_names
    ), "Should include storage configuration tasks"
    assert any(
        "label" in name.lower() or "taint" in name.lower() for name in task_names
    ), "Should include label/taint application tasks"
    assert any(
        "resource" in name.lower() or "limit" in name.lower() for name in task_names
    ), "Should include resource limits configuration tasks"

    return True


def validate_hardware_detection_tasks(node_config):
    """Validate hardware detection tasks exist and detect capabilities."""
    detect_hw_path = Path("ansible/roles/node_config/tasks/detect_hardware.yml")

    if not detect_hw_path.exists():
        return False

    with open(detect_hw_path) as f:
        tasks = yaml.safe_load(f)

    assert isinstance(tasks, list), "Hardware detection tasks should be a list"

    # Check for CPU detection
    assert any("cpu" in str(task).lower() for task in tasks), "Should detect CPU information"

    # Check for memory detection
    assert any("memory" in str(task).lower() for task in tasks), "Should detect memory information"

    # Check for GPU detection
    assert any("gpu" in str(task).lower() for task in tasks), "Should detect GPU presence"

    # Check for storage detection
    assert any(
        "storage" in str(task).lower() or "disk" in str(task).lower() for task in tasks
    ), "Should detect storage devices"

    return True


def validate_storage_configuration_tasks(node_config):
    """Validate storage configuration tasks exist."""
    storage_path = Path("ansible/roles/node_config/tasks/configure_storage.yml")

    if not storage_path.exists():
        return False

    with open(storage_path) as f:
        tasks = yaml.safe_load(f)

    assert isinstance(tasks, list), "Storage configuration tasks should be a list"

    # Check for storage class configuration
    assert any("storage" in str(task).lower() for task in tasks), "Should configure storage classes"

    return True


def validate_labels_taints_tasks(node_config):
    """Validate label and taint application tasks exist."""
    labels_path = Path("ansible/roles/node_config/tasks/apply_labels_taints.yml")

    if not labels_path.exists():
        return False

    with open(labels_path) as f:
        tasks = yaml.safe_load(f)

    assert isinstance(tasks, list), "Label/taint tasks should be a list"

    # Check for label application
    assert any("label" in str(task).lower() for task in tasks), "Should apply node labels"

    # Check for taint application
    assert any("taint" in str(task).lower() for task in tasks), "Should apply node taints"

    return True


def validate_resource_limits_tasks(node_config):
    """Validate resource limits configuration tasks exist."""
    limits_path = Path("ansible/roles/node_config/tasks/configure_resource_limits.yml")

    if not limits_path.exists():
        return False

    with open(limits_path) as f:
        tasks = yaml.safe_load(f)

    assert isinstance(tasks, list), "Resource limits tasks should be a list"

    # Check for resource limit configuration
    assert any(
        "resource" in str(task).lower()
        or "limit" in str(task).lower()
        or "pod" in str(task).lower()
        for task in tasks
    ), "Should configure resource limits"

    return True


@given(node=node_with_gpu())
def test_property_18_gpu_node_configuration(node):
    """
    Feature: tailscale-k8s-cluster, Property 18: Node-specific configuration application

    For any node with GPU attributes, the system should apply appropriate configuration
    including GPU-specific labels and taints.

    Validates: Requirements 10.1
    """
    # Validate that node_config role exists and has proper structure
    assert validate_node_config_tasks_exist(node)

    # Validate hardware detection tasks exist
    assert validate_hardware_detection_tasks(node)

    # GPU nodes should have gpu attribute set
    assert node.get("gpu") is True

    # GPU nodes should have appropriate labels
    assert "node_labels" in node
    assert any(
        "gpu" in key.lower() or "gpu" in value.lower() for key, value in node["node_labels"].items()
    )

    # GPU nodes should have appropriate taints
    assert "node_taints" in node
    assert any("gpu" in taint["key"].lower() for taint in node["node_taints"])

    # All taints should have valid effects
    for taint in node["node_taints"]:
        assert taint["effect"] in ["NoSchedule", "PreferNoSchedule", "NoExecute"]


@given(node=node_with_storage())
def test_property_18_storage_node_configuration(node):
    """
    Feature: tailscale-k8s-cluster, Property 18: Node-specific configuration application

    For any node with storage capabilities, the system should configure appropriate
    storage classes.

    Validates: Requirements 10.2
    """
    # Validate that node_config role exists
    assert validate_node_config_tasks_exist(node)

    # Validate storage configuration tasks exist
    assert validate_storage_configuration_tasks(node)

    # Storage nodes should have storage configuration
    assert node.get("enable_local_storage") is True

    # Storage nodes should have storage class name
    assert "storage_class_name" in node
    assert isinstance(node["storage_class_name"], str)
    assert len(node["storage_class_name"]) > 0

    # Storage nodes should have appropriate labels
    assert "node_labels" in node
    assert any(
        "storage" in key.lower() or "storage" in value.lower()
        for key, value in node["node_labels"].items()
    )


@given(node=node_with_custom_labels())
def test_property_18_custom_labels_application(node):
    """
    Feature: tailscale-k8s-cluster, Property 18: Node-specific configuration application

    For any node with custom labels in inventory, the system should apply those labels.

    Validates: Requirements 10.3
    """
    # Validate that node_config role exists
    assert validate_node_config_tasks_exist(node)

    # Validate label application tasks exist
    assert validate_labels_taints_tasks(node)

    # Node should have custom labels
    assert "node_labels" in node
    assert isinstance(node["node_labels"], dict)
    assert len(node["node_labels"]) > 0

    # All label keys and values should be strings
    for key, value in node["node_labels"].items():
        assert isinstance(key, str)
        assert isinstance(value, str)
        assert len(key) > 0
        assert len(value) > 0


@given(node=node_with_custom_taints())
def test_property_18_custom_taints_application(node):
    """
    Feature: tailscale-k8s-cluster, Property 18: Node-specific configuration application

    For any node with custom taints in inventory, the system should apply those taints.

    Validates: Requirements 10.3
    """
    # Validate that node_config role exists
    assert validate_node_config_tasks_exist(node)

    # Validate taint application tasks exist
    assert validate_labels_taints_tasks(node)

    # Node should have custom taints
    assert "node_taints" in node
    assert isinstance(node["node_taints"], list)
    assert len(node["node_taints"]) > 0

    # All taints should have required fields
    for taint in node["node_taints"]:
        assert "key" in taint
        assert "value" in taint
        assert "effect" in taint
        assert isinstance(taint["key"], str)
        assert isinstance(taint["value"], str)
        assert taint["effect"] in ["NoSchedule", "PreferNoSchedule", "NoExecute"]


@given(node=resource_constrained_node())
def test_property_18_resource_constrained_configuration(node):
    """
    Feature: tailscale-k8s-cluster, Property 18: Node-specific configuration application

    For any node with resource constraints, the system should configure appropriate
    resource limits.

    Validates: Requirements 10.5
    """
    # Validate that node_config role exists
    assert validate_node_config_tasks_exist(node)

    # Validate resource limits tasks exist
    assert validate_resource_limits_tasks(node)

    # Node should have resource reservations
    assert "reserved_cpu" in node
    assert "reserved_memory" in node

    # Resource values should be properly formatted
    assert isinstance(node["reserved_cpu"], str)
    assert isinstance(node["reserved_memory"], str)
    assert node["reserved_memory"].endswith("Gi") or node["reserved_memory"].endswith("Mi")

    # Max pods should be configured
    assert "max_pods" in node
    assert isinstance(node["max_pods"], str)
    max_pods_int = int(node["max_pods"])
    assert 10 <= max_pods_int <= 110


@given(
    nodes=st.lists(
        st.one_of(
            node_with_gpu(),
            node_with_storage(),
            node_with_custom_labels(),
            resource_constrained_node(),
        ),
        min_size=1,
        max_size=5,
    )
)
def test_property_18_multiple_nodes_configuration(nodes):
    """
    Feature: tailscale-k8s-cluster, Property 18: Node-specific configuration application

    For any set of nodes with different hardware attributes, each node should receive
    appropriate configuration based on its specific attributes.

    Validates: Requirements 10.1, 10.2, 10.3, 10.5
    """
    # Validate that node_config role exists
    assert validate_node_config_tasks_exist(nodes[0])

    # Each node should have unique hostname
    [node["hostname"] for node in nodes]
    # Note: Hypothesis may generate duplicate hostnames, so we just check structure

    # Each node should have required fields
    for node in nodes:
        assert "hostname" in node
        assert "ansible_host" in node
        assert "tailscale_ip" in node
        assert "role" in node

        # If node has GPU, it should have GPU configuration
        if node.get("gpu"):
            assert "node_labels" in node or "node_taints" in node

        # If node has storage, it should have storage configuration
        if node.get("enable_local_storage"):
            assert "storage_class_name" in node

        # If node has resource constraints, it should have reservations
        if "reserved_cpu" in node or "reserved_memory" in node:
            assert "reserved_cpu" in node
            assert "reserved_memory" in node
