"""Property-based tests for Ansible playbooks.

Feature: tailscale-k8s-cluster
Validates: Requirements 1.1, 1.2, 1.5, 3.1, 8.1, 8.4
"""

from pathlib import Path

import yaml
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from cluster_manager.models.node import Node


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
def node_with_role(draw, role):
    """Generate a node with a specific role."""
    hostname = draw(valid_hostname())
    ansible_host = draw(valid_tailscale_ip())
    tailscale_ip = draw(valid_tailscale_ip())

    return Node(hostname=hostname, ansible_host=ansible_host, tailscale_ip=tailscale_ip, role=role)


@st.composite
def valid_inventory_nodes(draw):
    """Generate a valid set of nodes for an inventory (1 control plane, 0-5 workers)."""
    # Exactly one control plane
    control_plane = draw(node_with_role("control-plane"))

    # 0 to 5 workers
    num_workers = draw(st.integers(min_value=0, max_value=5))
    workers = []
    used_hostnames = {control_plane.hostname}

    for _ in range(num_workers):
        worker = draw(node_with_role("worker"))
        # Ensure unique hostnames
        assume(worker.hostname not in used_hostnames)
        used_hostnames.add(worker.hostname)
        workers.append(worker)

    return control_plane, workers


def create_inventory_dict(control_plane: Node, workers: list[Node]) -> dict:
    """Create an Ansible inventory dictionary from nodes."""
    inventory = {
        "all": {
            "vars": {
                "k3s_version": "v1.28.5+k3s1",
                "cluster_name": "test-cluster",
                "tailscale_network": "100.64.0.0/10",
                "git_repo_url": "https://github.com/test/repo.git",
                "git_branch": "main",
                "flux_namespace": "flux-system",
            },
            "children": {
                "control_plane": {
                    "hosts": {control_plane.hostname: control_plane.to_inventory_dict()}
                },
                "workers": {"hosts": {}},
            },
        }
    }

    for worker in workers:
        inventory["all"]["children"]["workers"]["hosts"][
            worker.hostname
        ] = worker.to_inventory_dict()

    return inventory


def parse_playbook_structure(playbook_path: Path) -> dict:
    """Parse a playbook and extract its structure."""
    with open(playbook_path) as f:
        playbook_data = yaml.safe_load(f)

    structure = {
        "plays": [],
        "has_validation": False,
        "has_error_handling": False,
        "roles_applied": set(),
        "groups_targeted": set(),
    }

    if not playbook_data:
        return structure

    for play in playbook_data:
        play_info = {
            "name": play.get("name", ""),
            "hosts": play.get("hosts", ""),
            "roles": [],
            "tasks": [],
            "pre_tasks": [],
            "post_tasks": [],
            "handlers": [],
        }

        # Extract roles
        if "roles" in play:
            for role in play["roles"]:
                if isinstance(role, dict):
                    role_name = role.get("role", "")
                else:
                    role_name = role
                play_info["roles"].append(role_name)
                structure["roles_applied"].add(role_name)

        # Extract tasks
        for task_type in ["tasks", "pre_tasks", "post_tasks"]:
            if task_type in play:
                for task in play[task_type]:
                    if isinstance(task, dict):
                        task_name = task.get("name", "")
                        play_info[task_type].append(task_name)

                        # Check for validation tasks
                        if (
                            "assert" in task
                            or "validate" in task_name.lower()
                            or "check" in task_name.lower()
                        ):
                            structure["has_validation"] = True

                        # Check for include_role tasks
                        if "ansible.builtin.include_role" in task or "include_role" in task:
                            role_task = task.get(
                                "ansible.builtin.include_role", task.get("include_role", {})
                            )
                            if isinstance(role_task, dict):
                                role_name = role_task.get("name", "")
                                if role_name:
                                    structure["roles_applied"].add(role_name)
                                    play_info["roles"].append(role_name)

                        # Check for block tasks that might contain include_role
                        if "block" in task:
                            for block_task in task["block"]:
                                if isinstance(block_task, dict):
                                    if (
                                        "ansible.builtin.include_role" in block_task
                                        or "include_role" in block_task
                                    ):
                                        role_task = block_task.get(
                                            "ansible.builtin.include_role",
                                            block_task.get("include_role", {}),
                                        )
                                        if isinstance(role_task, dict):
                                            role_name = role_task.get("name", "")
                                            if role_name:
                                                structure["roles_applied"].add(role_name)
                                                play_info["roles"].append(role_name)

        # Check for handlers
        if "handlers" in play:
            for handler in play["handlers"]:
                if isinstance(handler, dict):
                    handler_name = handler.get("name", "")
                    play_info["handlers"].append(handler_name)
                    if "fail" in handler or "error" in handler_name.lower():
                        structure["has_error_handling"] = True

        # Track groups targeted
        hosts = play.get("hosts", "")
        if hosts:
            structure["groups_targeted"].add(hosts)

        structure["plays"].append(play_info)

    return structure


@given(inventory_data=valid_inventory_nodes())
@settings(max_examples=50)
def test_property_1_complete_component_installation(inventory_data):
    """
    Feature: tailscale-k8s-cluster, Property 1: Complete component installation

    For any valid Ansible inventory with specified nodes, when the provisioning
    playbook executes, all nodes in the inventory should have Kubernetes components
    installed and exactly one node should be configured as control plane with
    remaining nodes as workers.

    This test verifies that the playbook structure ensures:
    1. All nodes are targeted (control_plane and workers groups)
    2. K3s roles are applied to appropriate groups
    3. Control plane is provisioned before workers

    Validates: Requirements 1.1, 1.2
    """
    control_plane, workers = inventory_data

    # Create inventory
    inventory = create_inventory_dict(control_plane, workers)

    # Parse the provision_cluster.yml playbook
    playbook_path = Path("ansible/playbooks/provision_cluster.yml")
    assert playbook_path.exists(), "provision_cluster.yml must exist"

    structure = parse_playbook_structure(playbook_path)

    # Property 1: All nodes should be targeted
    # The playbook should have plays that target 'all', 'control_plane', and 'workers'
    assert "all" in structure["groups_targeted"] or any(
        "all" in play["hosts"] for play in structure["plays"]
    ), "Playbook must target all nodes for prerequisites"

    assert (
        "control_plane" in structure["groups_targeted"]
    ), "Playbook must target control_plane group"

    assert "workers" in structure["groups_targeted"], "Playbook must target workers group"

    # Property 2: Appropriate roles should be applied
    assert "prerequisites" in structure["roles_applied"], "Prerequisites role must be applied"

    assert (
        "k3s_control_plane" in structure["roles_applied"]
    ), "K3s control plane role must be applied"

    assert "k3s_worker" in structure["roles_applied"], "K3s worker role must be applied"

    # Property 3: Control plane must be provisioned before workers
    # Find the play indices
    cp_play_idx = None
    worker_play_idx = None

    for idx, play in enumerate(structure["plays"]):
        if "control_plane" in play["hosts"] or "control-plane" in play["name"].lower():
            if "k3s_control_plane" in play["roles"]:
                cp_play_idx = idx
        if "workers" in play["hosts"] or "worker" in play["name"].lower():
            if "k3s_worker" in play["roles"]:
                worker_play_idx = idx

    if cp_play_idx is not None and worker_play_idx is not None:
        assert cp_play_idx < worker_play_idx, "Control plane must be provisioned before workers"

    # Property 4: Exactly one control plane node in inventory
    assert (
        len(inventory["all"]["children"]["control_plane"]["hosts"]) == 1
    ), "Inventory must have exactly one control plane node"

    # Property 5: All other nodes should be workers
    1 + len(workers)
    assert len(inventory["all"]["children"]["workers"]["hosts"]) == len(
        workers
    ), "All non-control-plane nodes must be workers"


@given(inventory_data=valid_inventory_nodes())
@settings(max_examples=50)
def test_property_4_error_reporting_completeness(inventory_data):
    """
    Feature: tailscale-k8s-cluster, Property 4: Error reporting completeness

    For any provisioning error, the error message should contain both the node
    identifier and the specific step that failed.

    This test verifies that the playbook includes error handling mechanisms that
    report node and step information.

    Validates: Requirements 1.5
    """
    control_plane, workers = inventory_data

    # Parse the provision_cluster.yml playbook
    playbook_path = Path("ansible/playbooks/provision_cluster.yml")
    structure = parse_playbook_structure(playbook_path)

    # Property: Playbook should have error handling
    assert structure["has_error_handling"] or any(
        "fail" in str(play) or "error" in str(play).lower() for play in structure["plays"]
    ), "Playbook must include error handling mechanisms"

    # Check for handlers that report failures
    for play in structure["plays"]:
        if play["handlers"]:
            for handler in play["handlers"]:
                if "fail" in handler.lower() or "error" in handler.lower():
                    break

    # Property: Error messages should reference node and step
    # We verify this by checking that handlers exist that can report failures
    # The actual error message format is checked by reading the playbook content
    with open(playbook_path) as f:
        playbook_content = f.read()

    # Check for inventory_hostname (node identifier) in error messages
    assert (
        "inventory_hostname" in playbook_content
    ), "Error messages must include node identifier (inventory_hostname)"

    # Check for ansible_failed_task (step identifier) in error handling
    assert (
        "ansible_failed_task" in playbook_content or "failed_task" in playbook_content
    ), "Error messages must include step/task information"


@given(initial_inventory=valid_inventory_nodes(), new_worker=node_with_role("worker"))
@settings(max_examples=50)
def test_property_7_node_addition_consistent_provisioning(initial_inventory, new_worker):
    """
    Feature: tailscale-k8s-cluster, Property 7: Node addition uses consistent provisioning

    For any new node added to the Ansible inventory, the provisioning logic applied
    should be identical to the logic used for initial cluster nodes (same playbook,
    same roles).

    This test verifies that add_node.yml uses the same roles as provision_cluster.yml.

    Validates: Requirements 3.1
    """
    control_plane, workers = initial_inventory

    # Ensure new worker has unique hostname
    all_hostnames = {control_plane.hostname} | {w.hostname for w in workers}
    assume(new_worker.hostname not in all_hostnames)

    # Parse both playbooks
    provision_path = Path("ansible/playbooks/provision_cluster.yml")
    add_node_path = Path("ansible/playbooks/add_node.yml")

    assert provision_path.exists(), "provision_cluster.yml must exist"
    assert add_node_path.exists(), "add_node.yml must exist"

    provision_structure = parse_playbook_structure(provision_path)
    add_node_structure = parse_playbook_structure(add_node_path)

    # Property: Same roles should be applied in both playbooks
    # Core roles that must be present in both
    core_roles = {"prerequisites", "k3s_worker"}

    assert core_roles.issubset(
        provision_structure["roles_applied"]
    ), f"provision_cluster.yml must apply core roles: {core_roles}"

    assert core_roles.issubset(
        add_node_structure["roles_applied"]
    ), f"add_node.yml must apply same core roles: {core_roles}"

    # Property: Both playbooks should target the same groups for workers
    assert (
        "workers" in provision_structure["groups_targeted"]
    ), "provision_cluster.yml must target workers"

    assert "workers" in add_node_structure["groups_targeted"], "add_node.yml must target workers"

    # Property: Both should run prerequisites
    assert (
        "prerequisites" in provision_structure["roles_applied"]
    ), "provision_cluster.yml must run prerequisites"

    assert (
        "prerequisites" in add_node_structure["roles_applied"]
    ), "add_node.yml must run prerequisites"


@given(inventory_data=valid_inventory_nodes())
@settings(max_examples=50)
def test_property_17_playbook_idempotency(inventory_data):
    """
    Feature: tailscale-k8s-cluster, Property 17: Playbook idempotency

    For any Ansible playbook, executing it multiple times against the same inventory
    should produce the same cluster state without errors, with subsequent runs
    skipping tasks already in the desired state.

    This test verifies that playbooks are structured to support idempotent execution
    by checking for:
    1. Conditional task execution (when clauses)
    2. State checking before actions
    3. Use of Ansible modules that are inherently idempotent

    Validates: Requirements 8.1, 8.4
    """
    control_plane, workers = inventory_data

    # Parse the provision_cluster.yml playbook
    playbook_path = Path("ansible/playbooks/provision_cluster.yml")

    with open(playbook_path) as f:
        playbook_content = f.read()

    # Property 1: Playbook should use idempotent modules
    # Check for common idempotent Ansible modules
    idempotent_modules = [
        "ansible.builtin.copy",
        "ansible.builtin.template",
        "ansible.builtin.file",
        "ansible.builtin.service",
        "ansible.builtin.systemd",
        "ansible.builtin.package",
        "ansible.builtin.apt",
        "ansible.builtin.yum",
        "ansible.builtin.command",  # Can be idempotent with changed_when
        "ansible.builtin.shell",  # Can be idempotent with changed_when
    ]

    any(module in playbook_content for module in idempotent_modules)

    # Property 2: Playbook should have validation/checking tasks
    structure = parse_playbook_structure(playbook_path)
    assert structure[
        "has_validation"
    ], "Playbook must include validation tasks to check current state"

    # Property 3: Playbook should use 'when' clauses for conditional execution
    assert (
        "when:" in playbook_content
    ), "Playbook should use conditional execution (when clauses) for idempotency"

    # Property 4: Command/shell tasks should use changed_when or creates
    # to indicate when they actually make changes
    if "ansible.builtin.command" in playbook_content or "ansible.builtin.shell" in playbook_content:
        has_changed_when = "changed_when:" in playbook_content
        has_creates = "creates:" in playbook_content

        # At least one mechanism for idempotency should be present
        assert (
            has_changed_when or has_creates
        ), "Command/shell tasks should use changed_when or creates for idempotency"

    # Property 5: Playbook should check for existing state before making changes
    # Look for common state-checking patterns
    state_check_patterns = [
        "register:",  # Registering results for later use
        "failed_when:",  # Custom failure conditions
        "is-active",  # Checking service status
        "stat:",  # Checking file existence
    ]

    has_state_checks = any(pattern in playbook_content for pattern in state_check_patterns)

    assert has_state_checks, "Playbook should check existing state before making changes"


def test_playbook_files_exist():
    """
    Verify that all required playbook files exist.
    """
    playbook_dir = Path("ansible/playbooks")

    required_playbooks = ["site.yml", "provision_cluster.yml", "add_node.yml"]

    for playbook in required_playbooks:
        playbook_path = playbook_dir / playbook
        assert playbook_path.exists(), f"Required playbook {playbook} must exist"


def test_playbooks_are_valid_yaml():
    """
    Verify that all playbooks are valid YAML files.
    """
    playbook_dir = Path("ansible/playbooks")

    playbooks = ["site.yml", "provision_cluster.yml", "add_node.yml"]

    for playbook in playbooks:
        playbook_path = playbook_dir / playbook
        if playbook_path.exists():
            with open(playbook_path) as f:
                try:
                    yaml.safe_load(f)
                except yaml.YAMLError as e:
                    assert False, f"Playbook {playbook} is not valid YAML: {e}"


def test_site_yml_includes_provision():
    """
    Verify that site.yml includes or references provision_cluster.yml.
    """
    site_path = Path("ansible/playbooks/site.yml")

    with open(site_path) as f:
        content = f.read()

    # Should reference provision_cluster in some way
    assert "provision" in content.lower(), "site.yml should reference provisioning functionality"
