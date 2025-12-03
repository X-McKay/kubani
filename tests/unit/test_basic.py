"""Basic tests to verify project setup."""


def test_import_cluster_manager():
    """Test that cluster_manager package can be imported."""
    import cluster_manager

    assert cluster_manager.__version__ == "0.1.0"


def test_import_cli():
    """Test that CLI module can be imported."""
    from cluster_manager import cli

    assert cli.app is not None


def test_import_tui():
    """Test that TUI module can be imported."""
    from cluster_manager import tui

    assert tui.ClusterTUI is not None


def test_import_models():
    """Test that models module can be imported."""
    from cluster_manager import models

    # Module should exist even if empty
    assert models is not None
