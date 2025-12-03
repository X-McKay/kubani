"""Main TUI entry point for cluster monitoring."""

from cluster_manager.tui.app import ClusterTUI


def main() -> None:
    """Launch the cluster TUI."""
    app = ClusterTUI()
    app.run()


if __name__ == "__main__":
    main()
