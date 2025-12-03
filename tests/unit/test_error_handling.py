"""Tests for error handling across components."""

import pytest

from cluster_manager.exceptions import (
    ClusterManagerError,
    ConfigurationError,
    KubernetesError,
    TailscaleError,
    ValidationError,
)
from cluster_manager.inventory import InventoryError, InventoryValidationError
from cluster_manager.logging_config import get_logger, setup_logging


def test_custom_exception_with_details():
    """Test that custom exceptions support message and details."""
    error = TailscaleError("Tailscale command failed", "Run: sudo tailscale up")

    assert error.message == "Tailscale command failed"
    assert error.details == "Run: sudo tailscale up"
    assert "Tailscale command failed" in str(error)
    assert "Run: sudo tailscale up" in str(error)


def test_custom_exception_without_details():
    """Test that custom exceptions work without details."""
    error = ValidationError("Invalid input")

    assert error.message == "Invalid input"
    assert error.details is None
    assert str(error) == "Invalid input"


def test_exception_hierarchy():
    """Test that all custom exceptions inherit from ClusterManagerError."""
    assert issubclass(TailscaleError, ClusterManagerError)
    assert issubclass(KubernetesError, ClusterManagerError)
    assert issubclass(ValidationError, ClusterManagerError)
    assert issubclass(ConfigurationError, ClusterManagerError)
    assert issubclass(InventoryError, ClusterManagerError)
    assert issubclass(InventoryValidationError, InventoryError)


def test_logging_setup():
    """Test that logging can be configured."""
    # Should not raise any exceptions
    setup_logging(level="INFO", verbose=False)

    logger = get_logger("test")
    assert logger is not None
    assert logger.name == "test"


def test_logging_with_verbose():
    """Test that verbose mode sets DEBUG level."""
    setup_logging(verbose=True)

    logger = get_logger("test")
    # Logger should be configured for DEBUG level
    logger.debug("This is a debug message")
    logger.info("This is an info message")


def test_inventory_error_messages():
    """Test that inventory errors have helpful messages."""
    from cluster_manager.inventory import InventoryManager

    # Test with non-existent file
    mgr = InventoryManager("nonexistent.yml")

    with pytest.raises(InventoryError) as exc_info:
        mgr.read()

    error_msg = str(exc_info.value)
    assert "not found" in error_msg.lower()
    assert "nonexistent.yml" in error_msg


def test_tailscale_error_context():
    """Test that Tailscale errors provide context."""
    error = TailscaleError(
        "Tailscale is not installed", "Install from https://tailscale.com/download"
    )

    full_message = error.format_message()
    assert "Tailscale is not installed" in full_message
    assert "https://tailscale.com/download" in full_message
    assert "Details:" in full_message


def test_exception_can_be_caught_as_base_class():
    """Test that specific exceptions can be caught as ClusterManagerError."""
    try:
        raise TailscaleError("Test error")
    except ClusterManagerError as e:
        assert isinstance(e, TailscaleError)
        assert e.message == "Test error"


def test_multiple_exception_types():
    """Test that different exception types can be distinguished."""
    tailscale_err = TailscaleError("Tailscale error")
    k8s_err = KubernetesError("Kubernetes error")
    validation_err = ValidationError("Validation error")

    assert not isinstance(tailscale_err, type(k8s_err))
    assert not isinstance(k8s_err, type(validation_err))

    # But all are ClusterManagerError
    assert isinstance(tailscale_err, ClusterManagerError)
    assert isinstance(k8s_err, ClusterManagerError)
    assert isinstance(validation_err, ClusterManagerError)
