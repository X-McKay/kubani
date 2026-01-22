"""
Kubernetes Service Discovery.

Automatically discovers and registers Kubernetes services as endpoints
in the registry, enabling service discovery across the cluster.
"""

import asyncio
import logging
from typing import Any

from ..db import Endpoint
from ..db.session import get_session_factory

logger = logging.getLogger(__name__)

# Namespaces to watch for services
WATCHED_NAMESPACES = ["ai-agents", "vllm", "temporal", "database", "flux-system"]

# Service type inference based on name patterns and labels
SERVICE_TYPE_PATTERNS = {
    "llm": ["llm", "vllm", "openai"],
    "embeddings": ["embed"],
    "mcp": ["mcp"],
    "temporal": ["temporal"],
    "database": ["postgres", "postgresql", "redis", "qdrant", "neo4j"],
    "monitoring": ["prometheus", "grafana", "loki"],
    "registry": ["registry"],
}


def infer_service_type(name: str, labels: dict[str, str] | None = None) -> str:
    """
    Infer service type from name and labels.

    Args:
        name: Service name
        labels: Service labels

    Returns:
        Inferred service type
    """
    name_lower = name.lower()

    # Check labels first
    if labels and "app.kubernetes.io/component" in labels:
        component = labels["app.kubernetes.io/component"]
        for svc_type, patterns in SERVICE_TYPE_PATTERNS.items():
            if any(p in component.lower() for p in patterns):
                return svc_type

    # Check name patterns
    for svc_type, patterns in SERVICE_TYPE_PATTERNS.items():
        if any(p in name_lower for p in patterns):
            return svc_type

    return "service"  # Default type


def build_internal_url(service: Any, namespace: str) -> str:
    """
    Build internal cluster URL for a service.

    Args:
        service: Kubernetes Service object
        namespace: Service namespace

    Returns:
        Internal URL (e.g., http://service-name.namespace.svc:port)
    """
    name = service.metadata.name
    ports = service.spec.ports or []

    if not ports:
        return f"http://{name}.{namespace}.svc"

    # Use first port (usually the main service port)
    port = ports[0].port
    return f"http://{name}.{namespace}.svc:{port}"


async def discover_kubernetes_services(
    session_factory: Any,
    namespaces: list[str] | None = None,
) -> int:
    """
    Discover Kubernetes services and register them as endpoints.

    Args:
        session_factory: Database session factory
        namespaces: Namespaces to scan (defaults to WATCHED_NAMESPACES)

    Returns:
        Number of endpoints registered/updated
    """
    try:
        from kubernetes import client, config
    except ImportError:
        logger.warning(
            "kubernetes package not installed. "
            "Service discovery disabled. Install with: pip install kubernetes"
        )
        return 0

    namespaces = namespaces or WATCHED_NAMESPACES
    count = 0

    try:
        # Load in-cluster config, fall back to local kubeconfig
        try:
            config.load_incluster_config()
            logger.debug("Using in-cluster Kubernetes config")
        except config.ConfigException:
            config.load_kube_config()
            logger.debug("Using local Kubernetes config")

        v1 = client.CoreV1Api()
        networking_v1 = client.NetworkingV1Api()

        # Build a map of ingresses for external URLs
        ingress_map: dict[str, str] = {}
        try:
            ingresses = networking_v1.list_ingress_for_all_namespaces()
            for ingress in ingresses.items:
                if not ingress.spec.rules:
                    continue
                for rule in ingress.spec.rules:
                    if not rule.http or not rule.http.paths:
                        continue
                    for path in rule.http.paths:
                        backend = path.backend
                        if backend.service:
                            svc_name = backend.service.name
                            svc_ns = ingress.metadata.namespace
                            key = f"{svc_ns}/{svc_name}"
                            scheme = "https" if ingress.spec.tls else "http"
                            ingress_map[key] = f"{scheme}://{rule.host}"
        except Exception as e:
            logger.warning("Failed to list ingresses: %s", e)

        # Discover services in each namespace
        async with session_factory() as session:
            for ns in namespaces:
                try:
                    services = v1.list_namespaced_service(ns)
                except Exception as e:
                    logger.warning("Failed to list services in namespace %s: %s", ns, e)
                    continue

                for svc in services.items:
                    # Skip system services
                    name = svc.metadata.name
                    if name.startswith("kubernetes") or name == "default":
                        continue

                    labels = svc.metadata.labels or {}
                    endpoint_id = f"{name}-{ns}"

                    # Build URLs
                    internal_url = build_internal_url(svc, ns)
                    external_url = ingress_map.get(f"{ns}/{name}")

                    # Infer service type
                    service_type = infer_service_type(name, labels)

                    # Determine health check path based on type
                    health_paths = {
                        "llm": "/health",
                        "embeddings": "/health",
                        "temporal": "/health",
                        "database": "/health",
                        "mcp": "/health",
                        "registry": "/health",
                    }
                    health_path = health_paths.get(service_type, "/health")

                    # Check if endpoint exists
                    existing = await session.get(Endpoint, endpoint_id)

                    if existing:
                        # Update existing (preserve manual changes to status)
                        existing.internal_url = internal_url
                        if external_url:
                            existing.external_url = external_url
                        existing.service_type = service_type
                        existing.namespace = ns
                        # Merge metadata
                        existing_metadata = existing.metadata_ or {}
                        existing_metadata["discovered"] = True
                        existing_metadata["labels"] = labels
                        existing.metadata_ = existing_metadata
                    else:
                        # Create new endpoint
                        endpoint = Endpoint(
                            id=endpoint_id,
                            name=name,
                            service_type=service_type,
                            internal_url=internal_url,
                            external_url=external_url,
                            health_check_path=health_path,
                            namespace=ns,
                            environment="production",
                            status="unknown",
                            metadata_={"discovered": True, "labels": labels},
                        )
                        session.add(endpoint)

                    count += 1

            await session.commit()

        logger.info("Discovered %d services from Kubernetes", count)
        return count

    except Exception as e:
        logger.error("Service discovery failed: %s", e)
        return 0


async def run_discovery_loop(
    session_factory: Any,
    interval_seconds: int = 300,
) -> None:
    """
    Run service discovery in a loop.

    Args:
        session_factory: Database session factory
        interval_seconds: Interval between discovery runs (default: 5 minutes)
    """
    logger.info("Starting service discovery loop (interval: %ds)", interval_seconds)

    while True:
        try:
            count = await discover_kubernetes_services(session_factory)
            logger.debug("Discovery cycle complete: %d services", count)
        except asyncio.CancelledError:
            logger.info("Service discovery loop cancelled")
            break
        except Exception as e:
            logger.error("Discovery loop error: %s", e)

        await asyncio.sleep(interval_seconds)


async def start_discovery_service() -> asyncio.Task | None:
    """
    Start the service discovery background task.

    Returns:
        The background task, or None if discovery is disabled.
    """
    import os

    # Check if discovery is enabled
    if os.getenv("KUBANI_DISCOVERY_ENABLED", "true").lower() != "true":
        logger.info("Service discovery disabled via KUBANI_DISCOVERY_ENABLED")
        return None

    interval = int(os.getenv("KUBANI_DISCOVERY_INTERVAL", "300"))
    session_factory = get_session_factory()

    # Run initial discovery
    try:
        count = await discover_kubernetes_services(session_factory)
        logger.info("Initial discovery complete: %d services", count)
    except Exception as e:
        logger.warning("Initial discovery failed: %s", e)

    # Start background loop
    task = asyncio.create_task(
        run_discovery_loop(session_factory, interval),
        name="service-discovery",
    )
    return task
