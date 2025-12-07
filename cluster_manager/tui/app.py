"""Main TUI application for cluster monitoring."""

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.timer import Timer
from textual.widgets import DataTable, Footer, Header, Static

from cluster_manager.logging_config import get_logger
from cluster_manager.models.cluster import ClusterState, NodeStatus, ServiceStatus

logger = get_logger(__name__)


class ClusterTUI(App):
    """Terminal UI for Kubernetes cluster monitoring."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-container {
        height: 100%;
    }

    #nodes-container {
        height: 40%;
        border: solid $primary;
        margin: 1;
    }

    #services-container {
        height: 30%;
        border: solid $primary;
        margin: 1;
    }

    #events-container {
        height: 30%;
        border: solid $primary;
        margin: 1;
    }

    DataTable {
        height: 100%;
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
        self._node_data: list[NodeStatus] = []
        self._service_data: list[ServiceStatus] = []

    def compose(self) -> ComposeResult:
        """Compose the TUI layout."""
        yield Header(show_clock=True)
        with Vertical(id="main-container"):
            with Container(id="nodes-container"):
                yield DataTable(id="nodes-table", cursor_type="row")
            with Container(id="services-container"):
                yield DataTable(id="services-table", cursor_type="row")
            with Container(id="events-container"):
                yield Static("No events yet", id="events-content")
        yield Footer()

    def on_mount(self) -> None:
        """Set up the TUI when mounted."""
        self.title = f"Cluster: {self.cluster_name}"
        self.sub_title = "Press Q to quit, R to refresh, H for help"

        # Set up border titles
        self.query_one("#nodes-container").border_title = "Nodes"
        self.query_one("#services-container").border_title = "Services"
        self.query_one("#events-container").border_title = "Events"

        # Set up table columns
        nodes_table = self.query_one("#nodes-table", DataTable)
        nodes_table.add_columns("Name", "Role", "Status", "CPU", "Memory", "Tailscale IP")

        services_table = self.query_one("#services-table", DataTable)
        services_table.add_columns("Namespace", "Name", "Pods", "Status")

        # Set up auto-refresh timer
        self._refresh_timer = self.set_interval(
            self.refresh_interval, self._auto_refresh, name="auto_refresh"
        )

        # Initial data load
        self.refresh_data()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection to show detail view."""
        table = event.data_table
        row_index = event.cursor_row

        if table.id == "nodes-table" and 0 <= row_index < len(self._node_data):
            node = self._node_data[row_index]
            self._show_node_details(node)
        elif table.id == "services-table" and 0 <= row_index < len(self._service_data):
            service = self._service_data[row_index]
            self._show_service_details(service)

    def _show_node_details(self, node: NodeStatus) -> None:
        """Show detailed information about a node."""
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
        self.notify(details, title=f"Node Details: {node.name}", timeout=10)

    def _show_service_details(self, service: ServiceStatus) -> None:
        """Show detailed information about a service."""
        details = (
            f"Service: {service.name}\n"
            f"Namespace: {service.namespace}\n"
            f"Pod Count: {service.pod_count}\n"
            f"Health Status: {service.health_status}"
        )
        self.notify(details, title=f"Service Details: {service.name}", timeout=10)

    def action_quit(self) -> None:
        """Quit the application."""
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
        """Auto-refresh callback for timer."""
        self.refresh_data()

    def refresh_data(self) -> None:
        """Refresh cluster data from Kubernetes API."""
        if self._is_refreshing:
            logger.debug("Refresh already in progress, skipping")
            return

        self._is_refreshing = True

        try:
            self._show_loading(True)
            cluster_state = self._fetch_cluster_state()

            if cluster_state is not None:
                self._update_display(cluster_state)
                self._last_cluster_state = cluster_state

                if self._connection_error:
                    self._connection_error = False
                    self.notify("Connection restored", severity="information")
            else:
                self._handle_connection_error()

        except Exception as e:
            logger.error(f"Error refreshing data: {e}", exc_info=True)
            self._handle_connection_error()

        finally:
            self._show_loading(False)
            self._is_refreshing = False

    def _fetch_cluster_state(self) -> ClusterState | None:
        """Fetch current cluster state from Kubernetes API."""
        try:
            if self.api_client is None:
                logger.debug("No API client configured, using mock data")
                return None

            logger.debug("Fetching cluster state from Kubernetes API")
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
        """Update display widgets with new cluster state."""
        try:
            # Update nodes table
            self._node_data = cluster_state.nodes
            nodes_table = self.query_one("#nodes-table", DataTable)
            nodes_table.clear()

            for node in cluster_state.nodes:
                cpu_str = f"{node.cpu_usage:.1f}%"
                memory_str = f"{node.memory_usage:.1f}%"

                if node.status == "Ready":
                    status_text = Text(node.status, style="green")
                elif node.status == "NotReady":
                    status_text = Text(node.status, style="red")
                else:
                    status_text = Text(node.status, style="yellow")

                nodes_table.add_row(
                    node.name, node.role, status_text, cpu_str, memory_str, node.tailscale_ip
                )

            # Update services table
            self._service_data = self._pods_to_services(cluster_state.pods)
            services_table = self.query_one("#services-table", DataTable)
            services_table.clear()

            for service in self._service_data:
                if service.health_status == "Healthy":
                    status_text = Text(service.health_status, style="green")
                elif service.health_status == "Degraded":
                    status_text = Text(service.health_status, style="yellow")
                elif service.health_status == "Unhealthy":
                    status_text = Text(service.health_status, style="red")
                else:
                    status_text = Text(service.health_status, style="dim")

                services_table.add_row(
                    service.namespace, service.name, service.pod_count, status_text
                )

            logger.debug(
                f"Display updated: {len(cluster_state.nodes)} nodes, {len(self._service_data)} services"
            )

        except Exception as e:
            logger.error(f"Error updating display: {e}", exc_info=True)

    def _pods_to_services(self, pods: list) -> list[ServiceStatus]:
        """Convert pod list to service status list for display."""
        services = []
        namespaces: dict[str, list] = {}

        for pod in pods:
            if pod.namespace not in namespaces:
                namespaces[pod.namespace] = []
            namespaces[pod.namespace].append(pod)

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
        """Handle Kubernetes API connection errors gracefully."""
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

        if self._last_cluster_state is not None:
            logger.debug("Using last known cluster state")

    def _show_loading(self, show: bool) -> None:
        """Show or hide loading indicator."""
        if show:
            self.sub_title = "Loading... | Press Q to quit, R to refresh, H for help"
        else:
            self.sub_title = "Press Q to quit, R to refresh, H for help"


# Keep old widget classes for backwards compatibility with imports
NodesWidget = Container
ServicesWidget = Container
EventsWidget = Container
