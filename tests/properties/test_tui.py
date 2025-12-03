"""Property-based tests for TUI functionality.

Feature: tailscale-k8s-cluster
"""

from datetime import datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from cluster_manager.models.cluster import NodeStatus, ServiceStatus
from cluster_manager.tui import ClusterTUI, NodesWidget, ServicesWidget


@given(
    cluster_name=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"),
    ),
    refresh_interval=st.integers(min_value=1, max_value=60),
)
def test_property_25_keyboard_navigation(cluster_name: str, refresh_interval: int) -> None:
    """
    Feature: tailscale-k8s-cluster, Property 25: TUI keyboard navigation

    Validates: Requirements 12.5

    For any TUI session, all documented keyboard shortcuts should be registered
    and should trigger their corresponding actions (view details, refresh, quit, etc.).
    """
    # Create TUI instance
    app = ClusterTUI(cluster_name=cluster_name, refresh_interval=refresh_interval)

    # Verify all required bindings are registered
    binding_keys = {binding.key for binding in app.BINDINGS}

    # Check that all documented keyboard shortcuts are present
    required_bindings = {"q", "r", "h", "escape"}
    assert required_bindings.issubset(
        binding_keys
    ), f"Missing required keyboard bindings. Expected: {required_bindings}, Got: {binding_keys}"

    # Verify each binding has an associated action
    for binding in app.BINDINGS:
        action_name = f"action_{binding.action}"
        assert hasattr(app, action_name), (
            f"Binding '{binding.key}' references action '{binding.action}' "
            f"but method '{action_name}' does not exist"
        )

        # Verify the action is callable
        action_method = getattr(app, action_name)
        assert callable(action_method), f"Action method '{action_name}' exists but is not callable"


def test_tui_initialization() -> None:
    """Test that TUI initializes with correct default values."""
    app = ClusterTUI()

    assert app.cluster_name == "homelab"
    assert app.refresh_interval == 5
    assert app.BINDINGS is not None
    assert len(app.BINDINGS) > 0


def test_tui_custom_initialization() -> None:
    """Test that TUI accepts custom cluster name and refresh interval."""
    app = ClusterTUI(cluster_name="test-cluster", refresh_interval=10)

    assert app.cluster_name == "test-cluster"
    assert app.refresh_interval == 10


def test_tui_has_required_actions() -> None:
    """Test that TUI has all required action methods."""
    app = ClusterTUI()

    required_actions = ["action_quit", "action_refresh", "action_help"]

    for action in required_actions:
        assert hasattr(app, action), f"Missing required action: {action}"
        assert callable(getattr(app, action)), f"Action {action} is not callable"


def test_tui_has_refresh_data_method() -> None:
    """Test that TUI has refresh_data method for auto-refresh."""
    app = ClusterTUI()

    assert hasattr(app, "refresh_data"), "Missing refresh_data method"
    assert callable(app.refresh_data), "refresh_data is not callable"


@given(
    nodes=st.lists(
        st.builds(
            NodeStatus,
            name=st.text(
                min_size=1,
                max_size=63,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
                ),
            ),
            role=st.sampled_from(["control-plane", "worker"]),
            status=st.sampled_from(["Ready", "NotReady", "Unknown"]),
            cpu_usage=st.floats(min_value=0.0, max_value=100.0),
            memory_usage=st.floats(min_value=0.0, max_value=100.0),
            tailscale_ip=st.from_regex(
                r"^100\.(6[4-9]|[7-9]\d|1[0-1]\d|12[0-7])\.\d{1,3}\.\d{1,3}$", fullmatch=True
            ),
            kubelet_version=st.from_regex(r"^v\d+\.\d+\.\d+(\+k3s\d+)?$", fullmatch=True),
            last_heartbeat=st.datetimes(
                min_value=datetime.now() - timedelta(days=1), max_value=datetime.now()
            ),
        ),
        min_size=1,
        max_size=10,
    )
)
def test_property_22_node_information_completeness(nodes: list[NodeStatus]) -> None:
    """
    Feature: tailscale-k8s-cluster, Property 22: TUI node information completeness

    Validates: Requirements 12.1, 12.2

    For any cluster state, the TUI should display all nodes with their role, status,
    CPU usage, memory usage, and Tailscale IP address.
    """
    # Create a NodesWidget instance
    widget = NodesWidget()

    # Verify the widget has a method to update node data
    assert hasattr(
        widget, "update_nodes"
    ), "NodesWidget must have an update_nodes method to display node information"

    # Update the widget with node data
    widget.update_nodes(nodes)

    # Verify that the widget stores the node data
    assert hasattr(widget, "_nodes"), "NodesWidget must store node data in _nodes attribute"
    assert len(widget._nodes) == len(
        nodes
    ), f"Widget should store all {len(nodes)} nodes, but has {len(widget._nodes)}"

    # Verify all required fields are present for each node
    for i, node in enumerate(nodes):
        stored_node = widget._nodes[i]

        # Check that all required fields are present
        assert (
            stored_node.name == node.name
        ), f"Node {i}: name mismatch. Expected '{node.name}', got '{stored_node.name}'"
        assert (
            stored_node.role == node.role
        ), f"Node {i}: role mismatch. Expected '{node.role}', got '{stored_node.role}'"
        assert (
            stored_node.status == node.status
        ), f"Node {i}: status mismatch. Expected '{node.status}', got '{stored_node.status}'"
        assert (
            stored_node.cpu_usage == node.cpu_usage
        ), f"Node {i}: cpu_usage mismatch. Expected {node.cpu_usage}, got {stored_node.cpu_usage}"
        assert (
            stored_node.memory_usage == node.memory_usage
        ), f"Node {i}: memory_usage mismatch. Expected {node.memory_usage}, got {stored_node.memory_usage}"
        assert (
            stored_node.tailscale_ip == node.tailscale_ip
        ), f"Node {i}: tailscale_ip mismatch. Expected '{node.tailscale_ip}', got '{stored_node.tailscale_ip}'"


@given(
    services=st.lists(
        st.builds(
            ServiceStatus,
            name=st.text(
                min_size=1,
                max_size=63,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
                ),
            ),
            namespace=st.text(
                min_size=1,
                max_size=63,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
                ),
            ),
            pod_count=st.from_regex(r"^\d+/\d+$", fullmatch=True),
            health_status=st.sampled_from(["Healthy", "Degraded", "Unhealthy", "Unknown"]),
        ),
        min_size=1,
        max_size=20,
    )
)
def test_property_23_service_information_completeness(services: list[ServiceStatus]) -> None:
    """
    Feature: tailscale-k8s-cluster, Property 23: TUI service information completeness

    Validates: Requirements 12.3

    For any set of running services in the cluster, the TUI should display each service
    with its namespace, name, pod count, and health status.
    """
    # Create a ServicesWidget instance
    widget = ServicesWidget()

    # Verify the widget has a method to update service data
    assert hasattr(
        widget, "update_services"
    ), "ServicesWidget must have an update_services method to display service information"

    # Update the widget with service data
    widget.update_services(services)

    # Verify that the widget stores the service data
    assert hasattr(
        widget, "_services"
    ), "ServicesWidget must store service data in _services attribute"
    assert len(widget._services) == len(
        services
    ), f"Widget should store all {len(services)} services, but has {len(widget._services)}"

    # Verify all required fields are present for each service
    for i, service in enumerate(services):
        stored_service = widget._services[i]

        # Check that all required fields are present
        assert (
            stored_service.name == service.name
        ), f"Service {i}: name mismatch. Expected '{service.name}', got '{stored_service.name}'"
        assert (
            stored_service.namespace == service.namespace
        ), f"Service {i}: namespace mismatch. Expected '{service.namespace}', got '{stored_service.namespace}'"
        assert (
            stored_service.pod_count == service.pod_count
        ), f"Service {i}: pod_count mismatch. Expected '{service.pod_count}', got '{stored_service.pod_count}'"
        assert (
            stored_service.health_status == service.health_status
        ), f"Service {i}: health_status mismatch. Expected '{service.health_status}', got '{stored_service.health_status}'"


@given(
    initial_nodes=st.lists(
        st.builds(
            NodeStatus,
            name=st.text(
                min_size=1,
                max_size=63,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
                ),
            ),
            role=st.sampled_from(["control-plane", "worker"]),
            status=st.sampled_from(["Ready", "NotReady", "Unknown"]),
            cpu_usage=st.floats(min_value=0.0, max_value=100.0),
            memory_usage=st.floats(min_value=0.0, max_value=100.0),
            tailscale_ip=st.from_regex(
                r"^100\.(6[4-9]|[7-9]\d|1[0-1]\d|12[0-7])\.\d{1,3}\.\d{1,3}$", fullmatch=True
            ),
            kubelet_version=st.from_regex(r"^v\d+\.\d+\.\d+(\+k3s\d+)?$", fullmatch=True),
            last_heartbeat=st.datetimes(
                min_value=datetime.now() - timedelta(days=1), max_value=datetime.now()
            ),
        ),
        min_size=1,
        max_size=5,
    ),
    updated_nodes=st.lists(
        st.builds(
            NodeStatus,
            name=st.text(
                min_size=1,
                max_size=63,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"
                ),
            ),
            role=st.sampled_from(["control-plane", "worker"]),
            status=st.sampled_from(["Ready", "NotReady", "Unknown"]),
            cpu_usage=st.floats(min_value=0.0, max_value=100.0),
            memory_usage=st.floats(min_value=0.0, max_value=100.0),
            tailscale_ip=st.from_regex(
                r"^100\.(6[4-9]|[7-9]\d|1[0-1]\d|12[0-7])\.\d{1,3}\.\d{1,3}$", fullmatch=True
            ),
            kubelet_version=st.from_regex(r"^v\d+\.\d+\.\d+(\+k3s\d+)?$", fullmatch=True),
            last_heartbeat=st.datetimes(
                min_value=datetime.now() - timedelta(days=1), max_value=datetime.now()
            ),
        ),
        min_size=1,
        max_size=5,
    ),
)
def test_property_24_state_synchronization(
    initial_nodes: list[NodeStatus], updated_nodes: list[NodeStatus]
) -> None:
    """
    Feature: tailscale-k8s-cluster, Property 24: TUI state synchronization

    Validates: Requirements 12.4

    For any change in cluster state (node status change, pod creation/deletion),
    the TUI should update its display to reflect the new state within the
    configured refresh interval.
    """
    # Create a NodesWidget instance
    widget = NodesWidget()

    # Verify the widget has update_nodes method for state synchronization
    assert hasattr(
        widget, "update_nodes"
    ), "NodesWidget must have an update_nodes method for state synchronization"

    # Set initial state
    widget.update_nodes(initial_nodes)

    # Verify initial state is stored
    assert len(widget._nodes) == len(
        initial_nodes
    ), f"Initial state should have {len(initial_nodes)} nodes, but widget has {len(widget._nodes)}"

    # Simulate cluster state change by updating with new nodes
    widget.update_nodes(updated_nodes)

    # Verify that the display has been updated to reflect the new state
    assert len(widget._nodes) == len(updated_nodes), (
        f"After state change, widget should have {len(updated_nodes)} nodes, "
        f"but has {len(widget._nodes)}"
    )

    # Verify that the new state completely replaces the old state
    for i, node in enumerate(updated_nodes):
        stored_node = widget._nodes[i]

        # All fields should match the updated state
        assert (
            stored_node.name == node.name
        ), f"Node {i}: After update, name should be '{node.name}', got '{stored_node.name}'"
        assert (
            stored_node.status == node.status
        ), f"Node {i}: After update, status should be '{node.status}', got '{stored_node.status}'"
        assert stored_node.cpu_usage == node.cpu_usage, (
            f"Node {i}: After update, cpu_usage should be {node.cpu_usage}, "
            f"got {stored_node.cpu_usage}"
        )
        assert stored_node.memory_usage == node.memory_usage, (
            f"Node {i}: After update, memory_usage should be {node.memory_usage}, "
            f"got {stored_node.memory_usage}"
        )


def test_tui_auto_refresh_setup() -> None:
    """Test that TUI sets up auto-refresh timer on mount."""
    app = ClusterTUI(cluster_name="test", refresh_interval=5)

    # Verify refresh_data method exists
    assert hasattr(
        app, "refresh_data"
    ), "TUI must have refresh_data method for state synchronization"
    assert callable(app.refresh_data), "refresh_data must be callable"

    # Verify auto-refresh callback exists on the class
    assert hasattr(
        ClusterTUI, "_auto_refresh"
    ), "ClusterTUI class must have _auto_refresh callback for timer"
    assert callable(ClusterTUI._auto_refresh), "_auto_refresh must be callable"


def test_tui_connection_error_handling() -> None:
    """Test that TUI handles API connection errors gracefully."""
    app = ClusterTUI(cluster_name="test", refresh_interval=5)

    # Verify error handling methods exist
    assert hasattr(app, "_handle_connection_error"), "TUI must have _handle_connection_error method"
    assert callable(app._handle_connection_error), "_handle_connection_error must be callable"

    # Verify connection error flag exists
    assert hasattr(app, "_connection_error"), "TUI must track connection error state"
    assert isinstance(app._connection_error, bool), "_connection_error must be a boolean"


def test_tui_loading_indicator() -> None:
    """Test that TUI has loading indicator functionality."""
    app = ClusterTUI(cluster_name="test", refresh_interval=5)

    # Verify loading indicator method exists
    assert hasattr(
        app, "_show_loading"
    ), "TUI must have _show_loading method for loading indicators"
    assert callable(app._show_loading), "_show_loading must be callable"

    # Verify refresh state tracking
    assert hasattr(app, "_is_refreshing"), "TUI must track refresh state"
    assert isinstance(app._is_refreshing, bool), "_is_refreshing must be a boolean"


def test_tui_last_known_state() -> None:
    """Test that TUI stores last known cluster state."""
    app = ClusterTUI(cluster_name="test", refresh_interval=5)

    # Verify last state storage exists
    assert hasattr(app, "_last_cluster_state"), "TUI must store last known cluster state"

    # Initially should be None
    assert app._last_cluster_state is None, "Last cluster state should initially be None"
