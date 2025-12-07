"""TUI module for cluster monitoring."""

from cluster_manager.tui.app import ClusterTUI, EventsWidget, NodesWidget, ServicesWidget

__all__ = ["ClusterTUI", "NodesWidget", "ServicesWidget", "EventsWidget", "main"]


def main() -> None:
    """Main entry point for the cluster TUI."""
    import os
    from pathlib import Path

    from kubernetes import client, config

    api_client = None
    try:
        # Try to load kubeconfig, expanding ~ in path
        kubeconfig = os.environ.get("KUBECONFIG", "~/.kube/config")
        kubeconfig_path = Path(kubeconfig).expanduser()

        if kubeconfig_path.exists():
            config.load_kube_config(config_file=str(kubeconfig_path))
            api_client = client.CoreV1Api()
        else:
            # Try default location
            config.load_kube_config()
            api_client = client.CoreV1Api()
    except Exception:
        api_client = None

    app = ClusterTUI(api_client=api_client)
    app.run()
