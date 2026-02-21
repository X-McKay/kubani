"""Cluster configuration for integration and E2E tests.

This module provides configuration for connecting to cluster-deployed services
(vLLM, Temporal, Redis, PostgreSQL, Qdrant, Neo4j) for testing in a
production-like environment.
"""

import os
import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ClusterConfig:
    """Configuration for cluster service endpoints.
    
    Attributes:
        vllm_endpoint: vLLM API endpoint URL
        temporal_endpoint: Temporal server endpoint
        redis_endpoint: Redis server endpoint
        postgres_endpoint: PostgreSQL connection string
        qdrant_endpoint: Qdrant vector DB endpoint
        neo4j_endpoint: Neo4j graph DB endpoint
        kubeconfig_path: Path to kubeconfig file
        namespace: Kubernetes namespace for services
    """
    
    vllm_endpoint: str
    temporal_endpoint: str
    redis_endpoint: str
    postgres_endpoint: str
    qdrant_endpoint: str
    neo4j_endpoint: str
    kubeconfig_path: str
    namespace: str = "kubani"
    
    @property
    def is_cluster_mode(self) -> bool:
        """Check if running in cluster mode vs local mode."""
        return not self.vllm_endpoint.startswith("http://localhost")


def load_cluster_config(
    kubeconfig_path: Optional[str] = None,
    namespace: str = "kubani",
    use_local_fallback: bool = True,
) -> ClusterConfig:
    """Load cluster configuration from environment or kubeconfig.
    
    Priority order:
    1. Environment variables (VLLM_ENDPOINT, TEMPORAL_HOST, etc.)
    2. config/local.yaml
    3. Kubeconfig service resolution
    4. Local fallback (if use_local_fallback=True)
    
    Args:
        kubeconfig_path: Path to kubeconfig file (defaults to ~/.kube/config)
        namespace: Kubernetes namespace for services
        use_local_fallback: If True, fall back to localhost endpoints
        
    Returns:
        ClusterConfig with resolved endpoints
        
    Raises:
        ValueError: If cluster config cannot be loaded and fallback is disabled
    """
    # Try environment variables first
    vllm_endpoint = os.getenv("VLLM_ENDPOINT")
    temporal_endpoint = os.getenv("TEMPORAL_HOST")
    redis_endpoint = os.getenv("REDIS_URL")
    postgres_endpoint = os.getenv("NEXUS_DATABASE_URL")
    qdrant_endpoint = os.getenv("QDRANT_URL")
    neo4j_endpoint = os.getenv("NEO4J_URI")
    
    # If all environment variables are set, use them
    if all([vllm_endpoint, temporal_endpoint, redis_endpoint, postgres_endpoint]):
        return ClusterConfig(
            vllm_endpoint=vllm_endpoint,
            temporal_endpoint=temporal_endpoint,
            redis_endpoint=redis_endpoint,
            postgres_endpoint=postgres_endpoint,
            qdrant_endpoint=qdrant_endpoint or "http://localhost:6333",
            neo4j_endpoint=neo4j_endpoint or "bolt://localhost:7687",
            kubeconfig_path=kubeconfig_path or str(Path.home() / ".kube" / "config"),
            namespace=namespace,
        )
    
    # Try to load from config/local.yaml
    config_from_yaml = _load_from_config_file()
    if config_from_yaml:
        return config_from_yaml
    
    # Try to load from kubeconfig
    if kubeconfig_path is None:
        kubeconfig_path = str(Path.home() / ".kube" / "config")
    
    kubeconfig_file = Path(kubeconfig_path)
    if kubeconfig_file.exists():
        try:
            config = _parse_kubeconfig(kubeconfig_file, namespace)
            if config:
                return config
        except Exception as e:
            if not use_local_fallback:
                raise ValueError(f"Failed to parse kubeconfig: {e}") from e
    
    # Fall back to local endpoints
    if use_local_fallback:
        return ClusterConfig(
            vllm_endpoint="http://localhost:8000/v1",
            temporal_endpoint="localhost:7233",
            redis_endpoint="redis://localhost:6379",
            postgres_endpoint="postgresql://postgres:postgres@localhost:5432/nexus",
            qdrant_endpoint="http://localhost:6333",
            neo4j_endpoint="bolt://localhost:7687",
            kubeconfig_path=kubeconfig_path,
            namespace=namespace,
        )
    
    raise ValueError(
        "Could not load cluster configuration. "
        "Set environment variables or provide valid kubeconfig."
    )


def _load_from_config_file() -> Optional[ClusterConfig]:
    """Load cluster configuration from config/local.yaml.
    
    Returns:
        ClusterConfig if config file exists and has required fields, None otherwise
    """
    try:
        # Try to find config/local.yaml relative to project root
        config_paths = [
            Path("config/local.yaml"),
            Path(__file__).parent.parent.parent / "config" / "local.yaml",
        ]
        
        config_file = None
        for path in config_paths:
            if path.exists():
                config_file = path
                break
        
        if not config_file:
            return None
        
        with open(config_file) as f:
            config = yaml.safe_load(f)
        
        # Extract service configurations
        llm_config = config.get("llm", {})
        temporal_config = config.get("temporal", {})
        redis_config = config.get("memory", {}).get("redis", {})
        neo4j_config = config.get("memory", {}).get("neo4j", {})
        qdrant_config = config.get("memory", {}).get("qdrant", {})
        
        # Build endpoints from config
        vllm_endpoint = llm_config.get("api_url")
        
        # Temporal endpoint
        temporal_host = temporal_config.get("host", "")
        # Convert internal DNS to Tailscale IP if needed
        if "cluster.local" in temporal_host:
            temporal_endpoint = "100.71.65.62:7233"
        else:
            temporal_endpoint = temporal_host
        
        # Redis endpoint
        redis_host = redis_config.get("host", "")
        redis_port = redis_config.get("port", 6379)
        redis_password = redis_config.get("password", "")
        
        # Convert DNS to Tailscale IP if needed
        if ".almckay.io" in redis_host or "cluster.local" in redis_host:
            redis_host = "100.71.65.62"
        
        if redis_password:
            redis_endpoint = f"redis://:{redis_password}@{redis_host}:{redis_port}"
        else:
            redis_endpoint = f"redis://{redis_host}:{redis_port}"
        
        # PostgreSQL endpoint
        # Extract base host for PostgreSQL (same cluster as Redis)
        postgres_host = redis_host  # Use same Tailscale IP
        # Use nexus user with password from cluster
        postgres_endpoint = f"postgresql://nexus:nexus_password_123@{postgres_host}:5432/nexus"
        
        # Qdrant endpoint - use ingress with HTTP (HTTPS not supported)
        qdrant_host = qdrant_config.get("host", "")
        qdrant_api_key = qdrant_config.get("api_key", "")
        if ".almckay.io" in qdrant_host:
            # Use ingress endpoint with HTTP (not HTTPS)
            qdrant_endpoint = f"http://{qdrant_host}"
        elif "cluster.local" in qdrant_host:
            # Use Tailscale IP
            qdrant_endpoint = "http://100.71.65.62:6333"
        else:
            qdrant_endpoint = f"http://{qdrant_host}:6333"
        
        # Store Qdrant API key in environment for tests to use
        if qdrant_api_key:
            os.environ.setdefault("QDRANT_API_KEY", qdrant_api_key)
        
        # Neo4j endpoint
        neo4j_uri = neo4j_config.get("uri", "")
        neo4j_password = neo4j_config.get("password", "")
        # Convert DNS to Tailscale IP if needed
        if ".almckay.io" in neo4j_uri or "cluster.local" in neo4j_uri:
            neo4j_uri = "bolt://100.71.65.62:7687"
        
        # Store Neo4j password in environment for tests to use
        if neo4j_password:
            os.environ.setdefault("NEO4J_PASSWORD", neo4j_password)
        
        # Only return config if we have the essential endpoints
        if vllm_endpoint and temporal_endpoint:
            return ClusterConfig(
                vllm_endpoint=vllm_endpoint,
                temporal_endpoint=temporal_endpoint,
                redis_endpoint=redis_endpoint,
                postgres_endpoint=postgres_endpoint,
                qdrant_endpoint=qdrant_endpoint or "http://localhost:6333",
                neo4j_endpoint=neo4j_uri or "bolt://localhost:7687",
                kubeconfig_path=str(Path.home() / ".kube" / "config"),
                namespace="kubani",
            )
        
        return None
        
    except Exception:
        return None


def _parse_kubeconfig(kubeconfig_path: Path, namespace: str) -> Optional[ClusterConfig]:
    """Parse kubeconfig and resolve service endpoints.
    
    Args:
        kubeconfig_path: Path to kubeconfig file
        namespace: Kubernetes namespace
        
    Returns:
        ClusterConfig if services can be resolved, None otherwise
    """
    try:
        with open(kubeconfig_path) as f:
            kubeconfig = yaml.safe_load(f)
        
        # Get current context
        current_context = kubeconfig.get("current-context")
        if not current_context:
            return None
        
        # Find cluster info
        contexts = kubeconfig.get("contexts", [])
        context = next((c for c in contexts if c["name"] == current_context), None)
        if not context:
            return None
        
        cluster_name = context["context"]["cluster"]
        clusters = kubeconfig.get("clusters", [])
        cluster = next((c for c in clusters if c["name"] == cluster_name), None)
        if not cluster:
            return None
        
        # Get cluster server URL
        server_url = cluster["cluster"]["server"]
        
        # For now, we'll construct service endpoints based on common patterns
        # In a real implementation, you might query the cluster for service endpoints
        
        # Extract base domain from server URL
        # Example: https://100.71.65.62:6443 -> 100.71.65.62
        import re
        match = re.search(r'https?://([^:]+)', server_url)
        if not match:
            return None
        
        base_host = match.group(1)
        
        # Construct service endpoints
        # These are example patterns - adjust based on your cluster setup
        return ClusterConfig(
            vllm_endpoint=f"http://{base_host}:8000/v1",
            temporal_endpoint=f"{base_host}:7233",
            redis_endpoint=f"redis://{base_host}:6379",
            postgres_endpoint=f"postgresql://nexus:nexus@{base_host}:5432/nexus",
            qdrant_endpoint=f"http://{base_host}:6333",
            neo4j_endpoint=f"bolt://{base_host}:7687",
            kubeconfig_path=str(kubeconfig_path),
            namespace=namespace,
        )
        
    except Exception:
        return None


def get_service_endpoint(
    service_name: str,
    namespace: str = "kubani",
    kubeconfig_path: Optional[str] = None,
) -> Optional[str]:
    """Get endpoint for a specific service from cluster.
    
    Args:
        service_name: Name of the service (e.g., "vllm", "temporal")
        namespace: Kubernetes namespace
        kubeconfig_path: Path to kubeconfig file
        
    Returns:
        Service endpoint URL or None if not found
    """
    try:
        config = load_cluster_config(
            kubeconfig_path=kubeconfig_path,
            namespace=namespace,
            use_local_fallback=False,
        )
        
        service_map = {
            "vllm": config.vllm_endpoint,
            "temporal": config.temporal_endpoint,
            "redis": config.redis_endpoint,
            "postgres": config.postgres_endpoint,
            "qdrant": config.qdrant_endpoint,
            "neo4j": config.neo4j_endpoint,
        }
        
        return service_map.get(service_name)
        
    except Exception:
        return None


def is_cluster_available(config: Optional[ClusterConfig] = None) -> bool:
    """Check if cluster services are available.
    
    Args:
        config: ClusterConfig to check (loads default if None)
        
    Returns:
        True if cluster is available, False otherwise
    """
    if config is None:
        try:
            config = load_cluster_config(use_local_fallback=False)
        except ValueError:
            return False
    
    # Simple check: see if we can resolve cluster endpoints
    return config.is_cluster_mode
