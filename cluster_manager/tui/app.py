"""Main TUI application for cluster monitoring."""

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.timer import Timer
from textual.widgets import DataTable, Footer, Header, Static

from cluster_manager.logging_config import get_logger
from cluster_manager.models.cluster import ClusterState, NodeStatus, ServiceStatus

logger = get_logger(__name__)


class NodesWidget(Static):
    """Widget displaying cluster nodes information."""

    def __init__(self, *args, **kwargs):
        """Initialize the nodes widget."""
        super().__init__(*args, **kwargs)
        self._nodes: list[NodeStatus] = []
        self._table: DataTable | None = None

    def compose(self) -> ComposeResult:
        """Compose the nodes widget."""
        table = DataTable(cursor_type="row")
        table.add_columns("Name", "Role", "Status", "CPU", "Memory", "Tailscale IP")
        yield table

    def on_mount(self) -> None:
        """Initialize the nodes table."""
        self.border_title = "Nodes"
        self._table = self.query_one(DataTable)

    def update_nodes(self, nodes: list[NodeStatus]) -> None:
        """Update the nodes table with new data.

        Args:
            nodes: List of NodeStatus objects to display
        """
        self._nodes = nodes

        if self._table is None:
            return

        # Clear existing rows
        self._table.clear()

        # Add rows for each node
        for node in nodes:
            # Format CPU and memory usage
            cpu_str = f"{node.cpu_usage:.1f}%"
            memory_str = f"{node.memory_usage:.1f}%"

            # Create status text with color coding
            if node.status == "Ready":
                status_text = Text(node.status, style="green")
            elif node.status == "NotReady":
                status_text = Text(node.status, style="red")
            else:  # Unknown
                status_text = Text(node.status, style="yellow")

            # Add row to table
            self._table.add_row(
                node.name, node.role, status_text, cpu_str, memory_str, node.tailscale_ip
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection to show detail view.

        Args:
            event: Row selection event
        """
        if event.row_key is None:
            return

        # Get the row index
        row_index = event.cursor_row

        if 0 <= row_index < len(self._nodes):
            node = self._nodes[row_index]
            self._show_node_details(node)

    def _show_node_details(self, node: NodeStatus) -> None:
        """Show detailed information about a node.

        Args:
            node: NodeStatus object to display details for
        """
        # For now, just show a notification with node details
        # In a full implementation, this would open a modal or detail panel
        details = (
            f"Node: {node.name}\n"
            f"Role: {node.role}\n"
            f"Status: {node.status}\n"
            f"CPU: {node.cpu_usage:.1f}%\n"
            f"Memory: {node.memory_usage:.1f}%\n"
            f"Tailscale IP: {node.tailscale_ip}\n"
            f"Kubelet Version: {node.kubelet_version}\n"
            f"Last Heartbeat: {node.last_heartbeat}"
        )
        self.app.notify(details, title=f"Node Details: {node.name}", timeout=10)


class ServicesWidget(Static):
    """Widget displaying cluster services information."""

    def __init__(self, *args, **kwargs):
        """Initialize the services widget."""
        super().__init__(*args, **kwargs)
        self._services: list = []
        self._table: DataTable | None = None

    def compose(self) -> ComposeResult:
        """Compose the services widget."""
        table = DataTable(cursor_type="row")
        table.add_columns("Namespace", "Name", "Pods", "Status")
        yield table

    def on_mount(self) -> None:
        """Initialize the services table."""
        self.border_title = "Services"
        self._table = self.query_one(DataTable)

    def update_services(self, services: list) -> None:
        """Update the services table with new data.

        Args:
            services: List of ServiceStatus objects to display
        """
        self._services = services

        if self._table is None:
            return

        # Clear existing rows
        self._table.clear()

        # Add rows for each service
        for service in services:
            # Create health status text with color coding
            if service.health_status == "Healthy":
                status_text = Text(service.health_status, style="green")
            elif service.health_status == "Degraded":
                status_text = Text(service.health_status, style="yellow")
            elif service.health_status == "Unhealthy":
                status_text = Text(service.health_status, style="red")
            else:  # Unknown
                status_text = Text(service.health_status, style="dim")

            # Add row to table
            self._table.add_row(service.namespace, service.name, service.pod_count, status_text)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection to show detail view.

        Args:
            event: Row selection event
        """
        if event.row_key is None:
            return

        # Get the row index
        row_index = event.cursor_row

        if 0 <= row_index < len(self._services):
            service = self._services[row_index]
            self._show_service_details(service)

    def _show_service_details(self, service) -> None:
        """Show detailed information about a service.

        Args:
            service: ServiceStatus object to display details for
        """
        # For now, just show a notification with service details
        # In a full implementation, this would open a modal or detail panel
        details = (
            f"Service: {service.name}\n"
            f"Namespace: {service.namespace}\n"
            f"Pod Count: {service.pod_count}\n"
            f"Health Status: {service.health_status}"
        )
        self.app.notify(details, title=f"Service Details: {service.name}", timeout=10)


class EventsWidget(Static):
    """Widget displaying cluster events."""

    def compose(self) -> ComposeResult:
        """Compose the events widget."""
        yield Static("No events yet", id="events-content")

    def on_mount(self) -> None:
        """Initialize the events widget."""
        self.border_title = "Events"


class ClusterTUI(App):
    """Terminal UI for Kubernetes cluster monitoring."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-container {
        height: 100%;
        layout: vertical;
    }

    NodesWidget {
        height: 40%;
        border: solid $primary;
        margin: 1;
    }

    ServicesWidget {
        height: 30%;
        border: solid $primary;
        margin: 1;
    }

    EventsWidget {
        height: 30%;
        border: solid $primary;
        margin: 1;
    }

    DataTable {
        height: 100%;
    }

    #loading-indicator {
        width: 100%;
        height: 3;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("r", "refresh", "Refresh", priority=True),
        Binding("h", "help", "Help", priority=True),
        Binding("escape", "quit", "Quit", show=False),
    ]

    def __init__(self, cluster_name: str = "homelab", refresh_interval: int = 5, api_client=None):
        """Initialize the TUI.

        Args:
            cluster_name: Name of the cluster to display
            refresh_interval: Auto-refresh interval in seconds
            api_client: Optional Kubernetes API client for fetching cluster state
        """
        super().__init__()
        self.cluster_name = cluster_name
        self.refresh_interval = refresh_interval
        self.api_client = api_client
        self._refresh_timer: Timer | None = None
        self._is_refreshing: bool = False
        self._last_cluster_state: ClusterState | None = None
        self._connection_error: bool = False

    def compose(self) -> ComposeResult:
        """Compose the TUI layout."""
        yield Header(show_clock=True)
        with Container(id="main-container"):
            yield NodesWidget()
            yield ServicesWidget()
            yield EventsWidget()
        yield Footer()

    def on_mount(self) -> None:
        """Set up the TUI when mounted."""
        self.title = f"Cluster: {self.cluster_name}"
        self.sub_title = "Press Q to quit, R to refresh, H for help"

        # Set up auto-refresh timer
        self._refresh_timer = self.set_interval(
            self.refresh_interval, self._auto_refresh, name="auto_refresh"
        )

        # Initial data load
        self.refresh_data()

    def action_quit(self) -> None:
        """Quit the application."""
        # Stop the refresh timer before exiting
        if self._refresh_timer is not None:
            self._refresh_timer.stop()
        self.exit()

    def action_refresh(self) -> None:
        """Manually refresh the data."""
        self.refresh_data()

    def action_help(self) -> None:
        """Show help information."""
        help_text = (
            "Keyboard Shortcuts:\n"
            "  Q / ESC - Quit application\n"
            "  R - Manually refresh data\n"
            "  H - Show this help\n"
            "  ↑/↓ - Navigate tables\n"
            "  Enter - View details\n\n"
            f"Auto-refresh: Every {self.refresh_interval} seconds"
        )
        self.notify(help_text, title="Help", timeout=10)

    def _auto_refresh(self) -> None:
        """Auto-refresh callback for timer.

        This is called by the timer and delegates to refresh_data.
        """
        self.refresh_data()

    def refresh_data(self) -> None:
        """Refresh cluster data from Kubernetes API.

        This method handles:
        - Fetching data from Kubernetes API
        - Updating display widgets
        - Handling API connection errors gracefully
        - Showing loading indicators during refresh
        """
        # Prevent concurrent refreshes
        if self._is_refreshing:
            logger.debug("Refresh already in progress, skipping")
            return

        self._is_refreshing = True

        try:
            # Show loading indicator
            self._show_loading(True)

            # Fetch cluster state
            cluster_state = self._fetch_cluster_state()

            if cluster_state is not None:
                # Update widgets with new data
                self._update_display(cluster_state)

                # Store the last successful state
                self._last_cluster_state = cluster_state

                # Clear connection error flag
                if self._connection_error:
                    self._connection_error = False
                    self.notify("Connection restored", severity="information")
            else:
                # Handle connection error
                self._handle_connection_error()

        except Exception as e:
            # Handle unexpected errors
            logger.error(f"Error refreshing data: {e}", exc_info=True)
            self._handle_connection_error()

        finally:
            # Hide loading indicator
            self._show_loading(False)
            self._is_refreshing = False

    def _fetch_cluster_state(self) -> ClusterState | None:
        """Fetch current cluster state from Kubernetes API.

        Returns:
            ClusterState object if successful, None if connection fails
        """
        try:
            if self.api_client is None:
                # No API client configured, return mock data for testing
                logger.debug("No API client configured, using mock data")
                return None

            logger.debug("Fetching cluster state from Kubernetes API")

            # Fetch cluster state from Kubernetes API
            cluster_state = ClusterState.from_kubernetes_api(self.api_client, self.cluster_name)

            logger.debug(
                f"Successfully fetched cluster state: "
                f"{len(cluster_state.nodes)} nodes, {len(cluster_state.pods)} pods"
            )

            return cluster_state

        except ConnectionRefusedError as e:
            logger.warning(f"Connection refused to Kubernetes API: {e}")
            return None
        except ConnectionError as e:
            logger.warning(f"Connection error fetching cluster state: {e}")
            return None
        except TimeoutError as e:
            logger.warning(f"Timeout fetching cluster state: {e}")
            return None
        except PermissionError as e:
            logger.error(f"Permission denied accessing Kubernetes API: {e}")
            self.notify(
                "Permission denied accessing Kubernetes API. Check your kubeconfig permissions.",
                title="Permission Error",
                severity="error",
            )
            return None
        except FileNotFoundError as e:
            logger.error(f"Kubeconfig file not found: {e}")
            self.notify(
                "Kubeconfig file not found. "
                "Ensure the cluster is provisioned and kubeconfig is available.",
                title="Configuration Error",
                severity="error",
            )
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching cluster state: {e}", exc_info=True)
            return None

    def _update_display(self, cluster_state: ClusterState) -> None:
        """Update display widgets with new cluster state.

        Args:
            cluster_state: Current cluster state to display
        """
        try:
            # Update nodes widget
            nodes_widget = self.query_one(NodesWidget)
            nodes_widget.update_nodes(cluster_state.nodes)

            # Update services widget
            services_widget = self.query_one(ServicesWidget)
            # Convert pods to services for display
            services = self._pods_to_services(cluster_state.pods)
            services_widget.update_services(services)

            logger.debug(
                f"Display updated: {len(cluster_state.nodes)} nodes, {len(services)} services"
            )

        except Exception as e:
            logger.error(f"Error updating display: {e}", exc_info=True)

    def _pods_to_services(self, pods: list) -> list:
        """Convert pod list to service status list for display.

        Args:
            pods: List of PodStatus objects

        Returns:
            List of ServiceStatus objects grouped by namespace/name
        """
        # Group pods by namespace and extract unique services
        # This is a simplified implementation
        services = []

        # In a real implementation, we would query actual services
        # For now, we group pods by namespace
        namespaces = {}
        for pod in pods:
            if pod.namespace not in namespaces:
                namespaces[pod.namespace] = []
            namespaces[pod.namespace].append(pod)

        # Create service status for each namespace
        for namespace, ns_pods in namespaces.items():
            running = sum(1 for p in ns_pods if p.status == "Running")
            total = len(ns_pods)

            health = "Healthy" if running == total else "Degraded"
            if running == 0:
                health = "Unhealthy"

            services.append(
                ServiceStatus(
                    name=f"{namespace}-pods",
                    namespace=namespace,
                    pod_count=f"{running}/{total}",
                    health_status=health,
                )
            )

        return services

    def _handle_connection_error(self) -> None:
        """Handle Kubernetes API connection errors gracefully.

        This method:
        - Shows error notification (only once)
        - Keeps displaying last known state
        - Continues auto-refresh attempts
        """
        if not self._connection_error:
            self._connection_error = True
            self.notify(
                "Unable to connect to Kubernetes API. "
                "Displaying last known state. "
                "Will retry automatically.",
                title="Connection Error",
                severity="warning",
                timeout=10,
            )
            logger.warning("Kubernetes API connection error")

        # If we have a last known state, keep displaying it
        if self._last_cluster_state is not None:
            logger.debug("Using last known cluster state")
            # Display is already showing last state, no update needed

    def _show_loading(self, show: bool) -> None:
        """Show or hide loading indicator.

        Args:
            show: True to show loading indicator, False to hide
        """
        # Update subtitle to show loading status
        if show:
            self.sub_title = "Loading... | Press Q to quit, R to refresh, H for help"
        else:
            self.sub_title = "Press Q to quit, R to refresh, H for help"
