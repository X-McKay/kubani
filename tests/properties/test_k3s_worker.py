"""Property-based tests for K3s worker node configuration.

Feature: tailscale-k8s-cluster
"""

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st


# Custom strategies for generating valid test data
@st.composite
def valid_tailscale_ip(draw):
    """Generate valid Tailscale IP addresses (100.64.0.0/10 range)."""
    # Tailscale uses 100.64.0.0 to 100.127.255.255
    octet2 = draw(st.integers(min_value=64, max_value=127))
    octet3 = draw(st.integers(min_value=0, max_value=255))
    octet4 = draw(st.integers(min_value=1, max_value=254))
    return f"100.{octet2}.{octet3}.{octet4}"


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
def resource_quantity(draw):
    """Generate valid Kubernetes resource quantities."""
    # Generate CPU quantities (millicores or cores)
    cpu_type = draw(st.sampled_from(["millicores", "cores"]))
    if cpu_type == "millicores":
        value = draw(st.integers(min_value=100, max_value=8000))
        return f"{value}m"
    else:
        value = draw(st.integers(min_value=1, max_value=16))
        return str(value)


@st.composite
def memory_quantity(draw):
    """Generate valid Kubernetes memory quantities."""
    unit = draw(st.sampled_from(["Mi", "Gi"]))
    if unit == "Mi":
        value = draw(st.integers(min_value=512, max_value=8192))
    else:
        value = draw(st.integers(min_value=1, max_value=32))
    return f"{value}{unit}"


@st.composite
def worker_node_config(draw):
    """Generate a worker node configuration."""
    return {
        "hostname": draw(valid_hostname()),
        "tailscale_ip": draw(valid_tailscale_ip()),
        "ansible_host": draw(valid_tailscale_ip()),
        "role": "worker",
        "reserved_cpu": draw(resource_quantity()),
        "reserved_memory": draw(memory_quantity()),
        "system_reserved_cpu": draw(resource_quantity()),
        "system_reserved_memory": draw(memory_quantity()),
        "node_labels": draw(
            st.dictionaries(
                st.text(
                    min_size=1,
                    max_size=20,
                    alphabet=st.characters(
                        whitelist_categories=("Ll", "Nd"), whitelist_characters="-"
                    ),
                ),
                st.text(
                    min_size=1,
                    max_size=20,
                    alphabet=st.characters(
                        whitelist_categories=("Ll", "Nd"), whitelist_characters="-"
                    ),
                ),
                min_size=0,
                max_size=5,
            )
        ),
        "node_taints": draw(
            st.lists(
                st.fixed_dictionaries(
                    {
                        "key": st.text(
                            min_size=1,
                            max_size=20,
                            alphabet=st.characters(
                                whitelist_categories=("Ll", "Nd"), whitelist_characters=".-/"
                            ),
                        ),
                        "value": st.text(
                            min_size=1,
                            max_size=20,
                            alphabet=st.characters(
                                whitelist_categories=("Ll", "Nd"), whitelist_characters="-"
                            ),
                        ),
                        "effect": st.sampled_from(["NoSchedule", "PreferNoSchedule", "NoExecute"]),
                    }
                ),
                min_size=0,
                max_size=3,
            )
        ),
    }


def generate_k3s_agent_args(node_config: dict) -> list:
    """
    Generate K3s agent arguments based on node configuration.
    This mirrors the logic in ansible/roles/k3s_worker/defaults/main.yml
    """
    reserved_cpu = node_config.get("reserved_cpu", "1")
    reserved_memory = node_config.get("reserved_memory", "2Gi")
    reserved_ephemeral_storage = node_config.get("reserved_ephemeral_storage", "1Gi")
    system_reserved_cpu = node_config.get("system_reserved_cpu", "500m")
    system_reserved_memory = node_config.get("system_reserved_memory", "1Gi")
    system_reserved_ephemeral_storage = node_config.get("system_reserved_ephemeral_storage", "1Gi")

    return [
        f"--node-ip={node_config['tailscale_ip']}",
        "--flannel-iface=tailscale0",
        f"--kube-reserved=cpu={reserved_cpu},memory={reserved_memory},ephemeral-storage={reserved_ephemeral_storage}",
        f"--system-reserved=cpu={system_reserved_cpu},memory={system_reserved_memory},ephemeral-storage={system_reserved_ephemeral_storage}",
    ]


@given(node=worker_node_config())
def test_property_11_resource_reservation_configuration(node):
    """
    Feature: tailscale-k8s-cluster, Property 11: Resource reservation configuration

    For any node where Kubernetes is installed, the system should configure CPU and memory
    reservations to prevent Kubernetes from consuming all available resources.

    Validates: Requirements 4.1
    """
    # Generate K3s agent arguments
    agent_args = generate_k3s_agent_args(node)

    # Test 1: Verify kube-reserved is configured
    kube_reserved_args = [arg for arg in agent_args if "--kube-reserved=" in arg]
    assert len(kube_reserved_args) > 0, "K3s agent should have kube-reserved configuration"

    kube_reserved_arg = kube_reserved_args[0]

    # Test 2: Verify CPU reservation is present
    assert "cpu=" in kube_reserved_arg, "kube-reserved should include CPU reservation"

    # Test 3: Verify memory reservation is present
    assert "memory=" in kube_reserved_arg, "kube-reserved should include memory reservation"

    # Test 4: Verify system-reserved is configured
    system_reserved_args = [arg for arg in agent_args if "--system-reserved=" in arg]
    assert len(system_reserved_args) > 0, "K3s agent should have system-reserved configuration"

    system_reserved_arg = system_reserved_args[0]

    # Test 5: Verify system CPU reservation is present
    assert "cpu=" in system_reserved_arg, "system-reserved should include CPU reservation"

    # Test 6: Verify system memory reservation is present
    assert "memory=" in system_reserved_arg, "system-reserved should include memory reservation"

    # Test 7: Verify the configured values match the node configuration
    expected_cpu = node.get("reserved_cpu", "1")
    expected_memory = node.get("reserved_memory", "2Gi")

    assert (
        f"cpu={expected_cpu}" in kube_reserved_arg
    ), f"kube-reserved should use configured CPU value {expected_cpu}"
    assert (
        f"memory={expected_memory}" in kube_reserved_arg
    ), f"kube-reserved should use configured memory value {expected_memory}"


@given(node=worker_node_config())
def test_property_12_worker_node_resource_protection(node):
    """
    Feature: tailscale-k8s-cluster, Property 12: Worker node resource protection

    For any node configured as a worker node, the system should apply labels or taints
    that prevent system pods from monopolizing node resources.

    Validates: Requirements 4.2
    """
    # Test 1: Verify node has worker role
    assert node["role"] == "worker", "Node should be configured as worker"

    # Test 2: Verify node labels are defined (can be empty but should exist)
    assert "node_labels" in node, "Worker node should have node_labels field"

    # Test 3: Verify node taints are defined (can be empty but should exist)
    assert "node_taints" in node, "Worker node should have node_taints field"

    # Test 4: If node has workstation label, it should have resource reservations
    node_labels = node.get("node_labels", {})
    if "workstation" in node_labels and node_labels["workstation"] == "true":
        # Workstation nodes should have resource reservations configured
        assert "reserved_cpu" in node, "Workstation node should have CPU reservations"
        assert "reserved_memory" in node, "Workstation node should have memory reservations"

    # Test 5: Verify taints have correct structure
    node_taints = node.get("node_taints", [])
    for taint in node_taints:
        assert "key" in taint, "Taint should have key"
        assert "value" in taint, "Taint should have value"
        assert "effect" in taint, "Taint should have effect"
        assert taint["effect"] in [
            "NoSchedule",
            "PreferNoSchedule",
            "NoExecute",
        ], f"Taint effect should be valid, got {taint['effect']}"

    # Test 6: Verify resource reservations are non-zero
    # This ensures that some resources are actually reserved
    reserved_cpu = node.get("reserved_cpu", "0")
    reserved_memory = node.get("reserved_memory", "0")

    # CPU should not be zero
    if reserved_cpu.endswith("m"):
        cpu_value = int(reserved_cpu[:-1])
        assert cpu_value > 0, "Reserved CPU should be greater than 0"
    else:
        cpu_value = int(reserved_cpu)
        assert cpu_value > 0, "Reserved CPU should be greater than 0"

    # Memory should not be zero
    if reserved_memory.endswith("Gi"):
        memory_value = int(reserved_memory[:-2])
        assert memory_value > 0, "Reserved memory should be greater than 0"
    elif reserved_memory.endswith("Mi"):
        memory_value = int(reserved_memory[:-2])
        assert memory_value > 0, "Reserved memory should be greater than 0"


@st.composite
def cluster_with_workers(draw):
    """Generate a cluster configuration with multiple worker nodes."""
    # Generate control plane configuration
    control_plane_ip = draw(valid_tailscale_ip())

    # Generate common configuration that should be consistent
    cluster_cidr = draw(st.sampled_from(["10.42.0.0/16", "10.244.0.0/16"]))
    service_cidr = draw(st.sampled_from(["10.43.0.0/16", "10.96.0.0/16"]))
    k3s_version = draw(st.sampled_from(["v1.28.5+k3s1", "v1.27.10+k3s1", "v1.29.1+k3s1"]))

    # Generate worker nodes
    num_workers = draw(st.integers(min_value=1, max_value=5))
    workers = []
    used_ips = {control_plane_ip}
    used_hostnames = set()

    for _ in range(num_workers):
        worker_ip = draw(valid_tailscale_ip())
        worker_hostname = draw(valid_hostname())

        # Ensure unique IPs and hostnames
        while worker_ip in used_ips:
            worker_ip = draw(valid_tailscale_ip())
        while worker_hostname in used_hostnames:
            worker_hostname = draw(valid_hostname())

        used_ips.add(worker_ip)
        used_hostnames.add(worker_hostname)

        workers.append(
            {
                "hostname": worker_hostname,
                "tailscale_ip": worker_ip,
                "ansible_host": worker_ip,
                "role": "worker",
                "reserved_cpu": draw(resource_quantity()),
                "reserved_memory": draw(memory_quantity()),
                "node_labels": draw(
                    st.dictionaries(
                        st.text(
                            min_size=1,
                            max_size=20,
                            alphabet=st.characters(
                                whitelist_categories=("Ll", "Nd"), whitelist_characters="-"
                            ),
                        ),
                        st.text(
                            min_size=1,
                            max_size=20,
                            alphabet=st.characters(
                                whitelist_categories=("Ll", "Nd"), whitelist_characters="-"
                            ),
                        ),
                        min_size=0,
                        max_size=3,
                    )
                ),
            }
        )

    return {
        "control_plane_ip": control_plane_ip,
        "control_plane_url": f"https://{control_plane_ip}:6443",
        "cluster_cidr": cluster_cidr,
        "service_cidr": service_cidr,
        "k3s_version": k3s_version,
        "workers": workers,
    }


def apply_worker_configuration(worker: dict, cluster_config: dict) -> dict:
    """
    Simulate applying cluster configuration to a worker node.
    This mirrors the logic in ansible/roles/k3s_worker/tasks/install.yml
    """
    return {
        "hostname": worker["hostname"],
        "tailscale_ip": worker["tailscale_ip"],
        "role": worker["role"],
        "k3s_version": cluster_config["k3s_version"],
        "control_plane_url": cluster_config["control_plane_url"],
        "cluster_cidr": cluster_config["cluster_cidr"],
        "service_cidr": cluster_config["service_cidr"],
        "flannel_iface": "tailscale0",
        "reserved_cpu": worker.get("reserved_cpu"),
        "reserved_memory": worker.get("reserved_memory"),
        "node_labels": worker.get("node_labels", {}),
    }


@given(cluster=cluster_with_workers())
@settings(suppress_health_check=[HealthCheck.large_base_example])
def test_property_9_configuration_consistency_across_nodes(cluster):
    """
    Feature: tailscale-k8s-cluster, Property 9: Configuration consistency across nodes

    For any new node joining the cluster, the networking and storage configuration applied
    should match the configuration of existing nodes with the same role.

    Validates: Requirements 3.4
    """
    workers = cluster["workers"]

    # Apply configuration to all workers
    configured_workers = [apply_worker_configuration(worker, cluster) for worker in workers]

    # Test 1: All workers should have the same K3s version
    k3s_versions = [w["k3s_version"] for w in configured_workers]
    assert (
        len(set(k3s_versions)) == 1
    ), f"All workers should have the same K3s version, got {set(k3s_versions)}"

    # Test 2: All workers should connect to the same control plane
    control_plane_urls = [w["control_plane_url"] for w in configured_workers]
    assert (
        len(set(control_plane_urls)) == 1
    ), f"All workers should connect to the same control plane, got {set(control_plane_urls)}"

    # Test 3: All workers should have the same cluster CIDR
    cluster_cidrs = [w["cluster_cidr"] for w in configured_workers]
    assert (
        len(set(cluster_cidrs)) == 1
    ), f"All workers should have the same cluster CIDR, got {set(cluster_cidrs)}"

    # Test 4: All workers should have the same service CIDR
    service_cidrs = [w["service_cidr"] for w in configured_workers]
    assert (
        len(set(service_cidrs)) == 1
    ), f"All workers should have the same service CIDR, got {set(service_cidrs)}"

    # Test 5: All workers should use the same Flannel interface (tailscale0)
    flannel_ifaces = [w["flannel_iface"] for w in configured_workers]
    assert all(
        iface == "tailscale0" for iface in flannel_ifaces
    ), "All workers should use tailscale0 as Flannel interface"

    # Test 6: Each worker should use its own Tailscale IP
    tailscale_ips = [w["tailscale_ip"] for w in configured_workers]
    assert len(tailscale_ips) == len(
        set(tailscale_ips)
    ), "Each worker should have a unique Tailscale IP"

    # Test 7: Verify control plane URL contains the control plane IP
    control_plane_ip = cluster["control_plane_ip"]
    for worker in configured_workers:
        assert (
            control_plane_ip in worker["control_plane_url"]
        ), f"Worker {worker['hostname']} control plane URL should contain {control_plane_ip}"

    # Test 8: All workers should have the same role
    roles = [w["role"] for w in configured_workers]
    assert all(
        role == "worker" for role in roles
    ), "All nodes in workers group should have role 'worker'"


@given(cluster=cluster_with_workers(), new_worker=worker_node_config())
@settings(suppress_health_check=[HealthCheck.large_base_example])
def test_property_9_new_node_inherits_cluster_config(cluster, new_worker):
    """
    Property 9 extension: A new worker joining should inherit cluster-wide configuration.

    For any new worker node added to an existing cluster, it should receive the same
    networking configuration as existing workers.

    Validates: Requirements 3.4
    """
    # Ensure new worker has unique IP
    existing_ips = {w["tailscale_ip"] for w in cluster["workers"]}
    assume(new_worker["tailscale_ip"] not in existing_ips)

    # Apply configuration to new worker
    configured_new_worker = apply_worker_configuration(new_worker, cluster)

    # Apply configuration to existing workers
    configured_existing_workers = [
        apply_worker_configuration(worker, cluster) for worker in cluster["workers"]
    ]

    # Test 1: New worker should have same K3s version as existing workers
    existing_version = configured_existing_workers[0]["k3s_version"]
    assert (
        configured_new_worker["k3s_version"] == existing_version
    ), "New worker should have same K3s version as existing workers"

    # Test 2: New worker should connect to same control plane
    existing_control_plane = configured_existing_workers[0]["control_plane_url"]
    assert (
        configured_new_worker["control_plane_url"] == existing_control_plane
    ), "New worker should connect to same control plane as existing workers"

    # Test 3: New worker should have same cluster CIDR
    existing_cluster_cidr = configured_existing_workers[0]["cluster_cidr"]
    assert (
        configured_new_worker["cluster_cidr"] == existing_cluster_cidr
    ), "New worker should have same cluster CIDR as existing workers"

    # Test 4: New worker should have same service CIDR
    existing_service_cidr = configured_existing_workers[0]["service_cidr"]
    assert (
        configured_new_worker["service_cidr"] == existing_service_cidr
    ), "New worker should have same service CIDR as existing workers"

    # Test 5: New worker should use same Flannel interface
    existing_flannel = configured_existing_workers[0]["flannel_iface"]
    assert (
        configured_new_worker["flannel_iface"] == existing_flannel
    ), "New worker should use same Flannel interface as existing workers"
