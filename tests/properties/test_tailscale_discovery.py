"""Property-based tests for Tailscale node discovery.

Feature: tailscale-k8s-cluster, Property 19: Tailscale node discovery
Validates: Requirements 11.2, 11.3
"""

import json
import subprocess
from unittest.mock import Mock, patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cluster_manager.tailscale import TailscaleDiscovery, TailscaleNode


# Custom strategies for generating test data
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
def tailscale_peer_data(draw):
    """Generate mock Tailscale peer data."""
    hostname = draw(valid_hostname())
    ip = draw(valid_tailscale_ip())
    online = draw(st.booleans())
    os = draw(st.sampled_from(["linux", "darwin", "windows", None]))

    return {
        "DNSName": f"{hostname}.tailnet-name.ts.net.",
        "HostName": hostname,
        "TailscaleIPs": [ip],
        "Online": online,
        "OS": os,
    }


@st.composite
def tailscale_status_json(draw):
    """Generate mock Tailscale status JSON output."""
    # Generate self data first
    self_hostname = draw(valid_hostname())
    self_ip = draw(valid_tailscale_ip())
    self_os = draw(st.sampled_from(["linux", "darwin", "windows"]))

    # Track the extracted hostname (first part before dot) for uniqueness
    self_extracted_hostname = self_hostname.split(".")[0]
    used_extracted_hostnames = {self_extracted_hostname}

    # Generate 0-10 peers with unique extracted hostnames (different from self)
    num_peers = draw(st.integers(min_value=0, max_value=10))
    peers = {}

    for i in range(num_peers):
        peer_id = f"peer{i}"

        # Keep trying to generate a peer with a unique extracted hostname
        attempts = 0
        while attempts < 20:
            peer_data = draw(tailscale_peer_data())
            extracted_hostname = peer_data["DNSName"].split(".")[0]

            if extracted_hostname not in used_extracted_hostnames:
                used_extracted_hostnames.add(extracted_hostname)
                peers[peer_id] = peer_data
                break

            attempts += 1

    return {
        "Peer": peers,
        "Self": {
            "DNSName": f"{self_hostname}.tailnet-name.ts.net.",
            "HostName": self_hostname,
            "TailscaleIPs": [self_ip],
            "OS": self_os,
        },
    }


@given(status_data=tailscale_status_json())
def test_property_19_tailscale_node_discovery(status_data):
    """
    Feature: tailscale-k8s-cluster, Property 19: Tailscale node discovery

    For any execution of the CLI discover command, the system should query the
    Tailscale network and return a list of available nodes with their hostnames,
    IP addresses, and cluster membership status.

    Validates: Requirements 11.2, 11.3
    """
    # Mock the subprocess call to return our test data
    mock_result = Mock()
    mock_result.stdout = json.dumps(status_data)
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        # Execute discovery
        nodes = TailscaleDiscovery.discover_nodes()

        # Verify subprocess was called correctly
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["tailscale", "status", "--json"]
        assert call_args[1]["capture_output"] is True
        assert call_args[1]["text"] is True
        assert call_args[1]["check"] is True

        # Calculate expected number of nodes (peers + self)
        expected_count = len(status_data["Peer"]) + 1  # +1 for self
        assert len(nodes) == expected_count

        # Verify all nodes have required attributes
        for node in nodes:
            assert isinstance(node, TailscaleNode)
            assert node.hostname  # Must have hostname
            assert node.tailscale_ip  # Must have IP
            assert isinstance(node.online, bool)  # Must have online status

            # Verify IP is in Tailscale range (100.64.0.0/10)
            ip_str = str(node.tailscale_ip)
            parts = ip_str.split(".")
            assert parts[0] == "100"
            assert 64 <= int(parts[1]) <= 127

        # Verify self node is included and marked as online
        self_hostname = status_data["Self"]["DNSName"].split(".")[0]
        self_nodes = [n for n in nodes if n.hostname == self_hostname]
        assert len(self_nodes) == 1
        assert self_nodes[0].online is True

        # Verify peer nodes match the input data
        for peer_id, peer_data in status_data["Peer"].items():
            peer_hostname = peer_data["DNSName"].split(".")[0]
            peer_ip = peer_data["TailscaleIPs"][0]
            peer_online = peer_data["Online"]

            matching_nodes = [n for n in nodes if n.hostname == peer_hostname]
            assert len(matching_nodes) == 1

            node = matching_nodes[0]
            assert str(node.tailscale_ip) == peer_ip
            assert node.online == peer_online


@given(
    nodes=st.lists(
        st.builds(
            TailscaleNode,
            hostname=valid_hostname(),
            tailscale_ip=valid_tailscale_ip(),
            online=st.booleans(),
            os=st.sampled_from(["linux", "darwin", "windows", None]),
        ),
        min_size=0,
        max_size=20,
    ),
    online_only=st.booleans(),
    hostname_pattern=st.one_of(st.none(), st.text(min_size=1, max_size=10)),
)
def test_filter_nodes_correctness(nodes, online_only, hostname_pattern):
    """
    Test that filter_nodes correctly filters based on criteria.

    For any list of nodes and filter criteria, the filtered result should
    only contain nodes matching all specified criteria.
    """
    filtered = TailscaleDiscovery.filter_nodes(
        nodes, online_only=online_only, hostname_pattern=hostname_pattern
    )

    # All filtered nodes should be in the original list
    for node in filtered:
        assert node in nodes

    # Verify online_only filter
    if online_only:
        for node in filtered:
            assert node.online is True

    # Verify hostname pattern filter
    if hostname_pattern:
        pattern_lower = hostname_pattern.lower()
        for node in filtered:
            assert pattern_lower in node.hostname.lower()

    # Verify no valid nodes were incorrectly filtered out
    for node in nodes:
        should_be_included = True

        if online_only and not node.online:
            should_be_included = False

        if hostname_pattern and hostname_pattern.lower() not in node.hostname.lower():
            should_be_included = False

        if should_be_included:
            assert node in filtered


def test_tailscale_not_installed():
    """Test error handling when Tailscale is not installed."""
    from cluster_manager.exceptions import TailscaleError

    with patch("subprocess.run", side_effect=FileNotFoundError()):
        with pytest.raises(TailscaleError, match="Tailscale is not installed"):
            TailscaleDiscovery.discover_nodes()


def test_tailscale_command_fails():
    """Test error handling when Tailscale command fails."""
    from cluster_manager.exceptions import TailscaleError

    with patch(
        "subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "tailscale", stderr="error message"),
    ):
        with pytest.raises(TailscaleError, match="Tailscale command failed"):
            TailscaleDiscovery.discover_nodes()


def test_tailscale_timeout():
    """Test error handling when Tailscale command times out."""
    from cluster_manager.exceptions import TailscaleError

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("tailscale", 10)):
        with pytest.raises(TailscaleError, match="Tailscale command timed out"):
            TailscaleDiscovery.discover_nodes()


def test_invalid_json_response():
    """Test error handling when Tailscale returns invalid JSON."""
    from cluster_manager.exceptions import TailscaleError

    mock_result = Mock()
    mock_result.stdout = "not valid json"

    with patch("subprocess.run", return_value=mock_result):
        with pytest.raises(TailscaleError, match="Failed to parse Tailscale status output"):
            TailscaleDiscovery.discover_nodes()


def test_empty_tailscale_network():
    """Test handling of empty Tailscale network (only self, no peers)."""
    status_data = {
        "Peer": {},
        "Self": {
            "DNSName": "localhost.tailnet.ts.net.",
            "HostName": "localhost",
            "TailscaleIPs": ["100.64.0.1"],
            "OS": "linux",
        },
    }

    mock_result = Mock()
    mock_result.stdout = json.dumps(status_data)

    with patch("subprocess.run", return_value=mock_result):
        nodes = TailscaleDiscovery.discover_nodes()

        assert len(nodes) == 1
        assert nodes[0].hostname == "localhost"
        assert str(nodes[0].tailscale_ip) == "100.64.0.1"
        assert nodes[0].online is True
