"""Background services for the registry."""

from .discovery import (
    discover_kubernetes_services,
    run_discovery_loop,
    start_discovery_service,
)

__all__ = [
    "discover_kubernetes_services",
    "run_discovery_loop",
    "start_discovery_service",
]
