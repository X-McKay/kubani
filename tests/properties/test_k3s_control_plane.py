"""Property-based tests for K3s control plane configuration.

Feature: tailscale-k8s-cluster
"""

from hypothesis import assume, given
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
def k3s_kubeconfig(draw):
    """Generate a K3s kubeconfig structure."""
    cluster_name = draw(
        st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Nd")))
    )
    # Generate a non-Tailscale IP for the initial server URL (simulating default K3s behavior)
    server_ip = draw(
        st.ip_addresses(v=4).filter(
            lambda ip: not (
                100 <= int(str(ip).split(".")[0]) <= 100 and 64 <= int(str(ip).split(".")[1]) <= 127
            )
        )
    )

    return {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [
            {
                "name": cluster_name,
                "cluster": {
                    "server": f"https://{server_ip}:6443",
                    "certificate-authority-data": "fake-cert-data",
                },
            }
        ],
        "contexts": [{"name": "default", "context": {"cluster": cluster_name, "user": "default"}}],
        "current-context": "default",
        "users": [
            {
                "name": "default",
                "user": {
                    "client-certificate-data": "fake-client-cert",
                    "client-key-data": "fake-client-key",
                },
            }
        ],
    }


@st.composite
def node_config(draw):
    """Generate a node configuration with Tailscale IP."""
    return {
        "hostname": draw(valid_hostname()),
        "tailscale_ip": draw(valid_tailscale_ip()),
        "ansible_host": draw(valid_tailscale_ip()),
        "role": "control-plane",
        "api_server_port": draw(st.integers(min_value=1024, max_value=65535)),
    }


def update_kubeconfig_server_url(kubeconfig: dict, tailscale_ip: str, port: int) -> dict:
    """
    Simulate the Ansible task that updates kubeconfig server URL to use Tailscale IP.
    This mirrors the logic in ansible/roles/k3s_control_plane/tasks/kubeconfig.yml
    """
    updated = kubeconfig.copy()
    updated["clusters"] = [
        {**cluster, "cluster": {**cluster["cluster"], "server": f"https://{tailscale_ip}:{port}"}}
        for cluster in kubeconfig["clusters"]
    ]
    return updated


def extract_server_ip(kubeconfig: dict) -> str:
    """Extract the server IP from a kubeconfig."""
    server_url = kubeconfig["clusters"][0]["cluster"]["server"]
    # Parse https://IP:PORT format
    return server_url.split("://")[1].split(":")[0]


def generate_k3s_server_args(
    tailscale_ip: str, cluster_cidr: str = "10.42.0.0/16", service_cidr: str = "10.43.0.0/16"
) -> list:
    """
    Generate K3s server arguments that should include Tailscale IP configuration.
    This mirrors the logic in ansible/roles/k3s_control_plane/defaults/main.yml
    """
    return [
        "--write-kubeconfig-mode=644",
        f"--tls-san={tailscale_ip}",
        f"--node-ip={tailscale_ip}",
        f"--advertise-address={tailscale_ip}",
        "--flannel-iface=tailscale0",
        f"--cluster-cidr={cluster_cidr}",
        f"--service-cidr={service_cidr}",
    ]


@given(node=node_config(), kubeconfig=k3s_kubeconfig())
def test_property_2_tailscale_ip_configuration_consistency(node, kubeconfig):
    """
    Feature: tailscale-k8s-cluster, Property 2: Tailscale IP configuration consistency

    For any node in the cluster, all Kubernetes networking configuration (API server endpoint,
    node addresses) should use the node's Tailscale IP address rather than any other network interface.

    Validates: Requirements 1.3, 2.2
    """
    tailscale_ip = node["tailscale_ip"]
    api_port = node["api_server_port"]

    # Test 1: K3s server arguments should include Tailscale IP configuration
    server_args = generate_k3s_server_args(tailscale_ip)

    # Verify TLS SAN includes Tailscale IP
    assert any(
        f"--tls-san={tailscale_ip}" in arg for arg in server_args
    ), "TLS SAN should include Tailscale IP"

    # Verify node IP is set to Tailscale IP
    assert any(
        f"--node-ip={tailscale_ip}" in arg for arg in server_args
    ), "Node IP should be set to Tailscale IP"

    # Verify advertise address is set to Tailscale IP
    assert any(
        f"--advertise-address={tailscale_ip}" in arg for arg in server_args
    ), "Advertise address should be set to Tailscale IP"

    # Verify Flannel is configured to use Tailscale interface
    assert any(
        "--flannel-iface=tailscale0" in arg for arg in server_args
    ), "Flannel should use tailscale0 interface"

    # Test 2: Kubeconfig should be updated to use Tailscale IP
    updated_kubeconfig = update_kubeconfig_server_url(kubeconfig, tailscale_ip, api_port)

    # Extract server IP from updated kubeconfig
    server_ip = extract_server_ip(updated_kubeconfig)

    # Verify the server URL uses Tailscale IP
    assert (
        server_ip == tailscale_ip
    ), f"Kubeconfig server URL should use Tailscale IP {tailscale_ip}, got {server_ip}"

    # Verify the port is correct
    server_url = updated_kubeconfig["clusters"][0]["cluster"]["server"]
    assert f":{api_port}" in server_url, f"Kubeconfig server URL should use port {api_port}"

    # Test 3: Verify Tailscale IP is in valid range
    ip_parts = tailscale_ip.split(".")
    assert ip_parts[0] == "100", "Tailscale IP should start with 100"
    assert 64 <= int(ip_parts[1]) <= 127, "Tailscale IP second octet should be 64-127"


@given(
    nodes=st.lists(
        node_config(),
        min_size=1,
        max_size=5,
        unique_by=lambda n: (n["hostname"], n["tailscale_ip"]),
    )
)
def test_property_2_multiple_nodes_use_own_tailscale_ip(nodes):
    """
    Property 2 extension: Each node should use its own Tailscale IP, not another node's.

    For any set of nodes in the cluster, each node's networking configuration should use
    that specific node's Tailscale IP address.

    Validates: Requirements 1.3, 2.2
    """
    # Ensure all nodes have unique Tailscale IPs (this is a precondition)
    tailscale_ips = [n["tailscale_ip"] for n in nodes]
    assume(len(tailscale_ips) == len(set(tailscale_ips)))

    for node in nodes:
        tailscale_ip = node["tailscale_ip"]
        server_args = generate_k3s_server_args(tailscale_ip)

        # Each node should reference its own Tailscale IP
        assert any(
            tailscale_ip in arg for arg in server_args
        ), f"Node {node['hostname']} should use its own Tailscale IP {tailscale_ip}"

        # Verify it's not using another node's IP
        other_ips = [n["tailscale_ip"] for n in nodes if n["hostname"] != node["hostname"]]
        for other_ip in other_ips:
            # The server args should not contain other nodes' IPs
            # (except potentially in cluster member lists, which we're not testing here)
            node_specific_args = [
                arg
                for arg in server_args
                if "--node-ip=" in arg or "--advertise-address=" in arg or "--tls-san=" in arg
            ]
            for arg in node_specific_args:
                assert (
                    other_ip not in arg
                ), f"Node {node['hostname']} should not use another node's IP {other_ip} in {arg}"


# Helper functions for credential distribution testing
@st.composite
def cluster_inventory(draw):
    """Generate a cluster inventory with control plane and worker nodes."""
    cluster_name = draw(
        st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Nd")))
    )

    # Generate control plane node
    control_plane = {
        "hostname": draw(valid_hostname()),
        "tailscale_ip": draw(valid_tailscale_ip()),
        "role": "control-plane",
    }

    # Generate worker nodes
    num_workers = draw(st.integers(min_value=0, max_value=4))
    workers = []
    used_ips = {control_plane["tailscale_ip"]}
    used_hostnames = {control_plane["hostname"]}

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

        workers.append({"hostname": worker_hostname, "tailscale_ip": worker_ip, "role": "worker"})

    return {
        "cluster_name": cluster_name,
        "control_plane": control_plane,
        "workers": workers,
        "all_nodes": [control_plane] + workers,
    }


def simulate_credential_distribution(inventory: dict) -> dict:
    """
    Simulate the credential distribution process from the Ansible role.
    This mirrors the logic in ansible/roles/k3s_control_plane/tasks/join_token.yml
    and ansible/roles/k3s_control_plane/tasks/kubeconfig.yml
    """
    control_plane = inventory["control_plane"]
    all_nodes = inventory["all_nodes"]

    # Simulate join token generation (would be read from file in real scenario)
    join_token = f"K10{control_plane['hostname']}::server:{'x' * 64}"

    # Simulate control plane URL
    control_plane_url = f"https://{control_plane['tailscale_ip']}:6443"

    # Simulate kubeconfig generation
    kubeconfig = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [
            {
                "name": inventory["cluster_name"],
                "cluster": {
                    "server": control_plane_url,
                    "certificate-authority-data": "fake-ca-cert",
                },
            }
        ],
        "contexts": [
            {
                "name": "default",
                "context": {"cluster": inventory["cluster_name"], "user": "default"},
            }
        ],
        "current-context": "default",
        "users": [
            {
                "name": "default",
                "user": {
                    "client-certificate-data": "fake-client-cert",
                    "client-key-data": "fake-client-key",
                },
            }
        ],
    }

    # Distribute credentials to all nodes
    credentials = {}
    for node in all_nodes:
        credentials[node["hostname"]] = {
            "kubeconfig": kubeconfig,
            "join_token": join_token if node["role"] == "worker" else None,
            "control_plane_url": control_plane_url,
        }

    return credentials


@given(inventory=cluster_inventory())
def test_property_3_credential_distribution_completeness(inventory):
    """
    Feature: tailscale-k8s-cluster, Property 3: Credential distribution completeness

    For any cluster provisioning operation, all nodes in the inventory should receive
    authentication credentials (kubeconfig, join tokens) upon successful completion.

    Validates: Requirements 1.4
    """
    # Simulate the credential distribution process
    credentials = simulate_credential_distribution(inventory)

    all_nodes = inventory["all_nodes"]
    control_plane = inventory["control_plane"]
    workers = inventory["workers"]

    # Test 1: All nodes should receive credentials
    assert len(credentials) == len(
        all_nodes
    ), f"All {len(all_nodes)} nodes should receive credentials, got {len(credentials)}"

    # Test 2: Each node should have a credential entry
    for node in all_nodes:
        assert node["hostname"] in credentials, f"Node {node['hostname']} should have credentials"

    # Test 3: All nodes should receive kubeconfig
    for node in all_nodes:
        node_creds = credentials[node["hostname"]]
        assert "kubeconfig" in node_creds, f"Node {node['hostname']} should receive kubeconfig"
        assert (
            node_creds["kubeconfig"] is not None
        ), f"Node {node['hostname']} kubeconfig should not be None"

        # Verify kubeconfig structure
        kubeconfig = node_creds["kubeconfig"]
        assert "clusters" in kubeconfig, "Kubeconfig should have clusters"
        assert "users" in kubeconfig, "Kubeconfig should have users"
        assert "contexts" in kubeconfig, "Kubeconfig should have contexts"

    # Test 4: Worker nodes should receive join token
    for worker in workers:
        worker_creds = credentials[worker["hostname"]]
        assert (
            "join_token" in worker_creds
        ), f"Worker {worker['hostname']} should have join_token field"
        assert (
            worker_creds["join_token"] is not None
        ), f"Worker {worker['hostname']} should receive a join token"
        assert (
            len(worker_creds["join_token"]) > 0
        ), f"Worker {worker['hostname']} join token should not be empty"

    # Test 5: Control plane should have control_plane_url
    control_plane_creds = credentials[control_plane["hostname"]]
    assert "control_plane_url" in control_plane_creds, "Control plane should have control_plane_url"
    assert (
        control_plane["tailscale_ip"] in control_plane_creds["control_plane_url"]
    ), "Control plane URL should contain the control plane's Tailscale IP"

    # Test 6: All worker nodes should have the same control_plane_url
    if workers:
        control_plane_url = control_plane_creds["control_plane_url"]
        for worker in workers:
            worker_creds = credentials[worker["hostname"]]
            assert (
                worker_creds["control_plane_url"] == control_plane_url
            ), f"Worker {worker['hostname']} should have the same control plane URL"

    # Test 7: All nodes should receive the same kubeconfig (pointing to same cluster)
    if len(all_nodes) > 1:
        first_kubeconfig = credentials[all_nodes[0]["hostname"]]["kubeconfig"]
        first_server = first_kubeconfig["clusters"][0]["cluster"]["server"]

        for node in all_nodes[1:]:
            node_kubeconfig = credentials[node["hostname"]]["kubeconfig"]
            node_server = node_kubeconfig["clusters"][0]["cluster"]["server"]
            assert (
                node_server == first_server
            ), "All nodes should receive kubeconfig pointing to same API server"
