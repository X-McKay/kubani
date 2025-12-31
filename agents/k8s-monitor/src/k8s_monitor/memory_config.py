"""
Memory configuration for k8s-monitor agent.

Provides Kubernetes-specific graph prompts and mem0 configuration
for remediation memory using Qdrant + Neo4j.

This module contains domain-specific configuration that was previously
in core_agents but has been moved here to keep core domain-agnostic.
"""

import os
from typing import Any

from core_agents import get_graph_mem0_config

# K8s-specific graph prompt for remediation memory
K8S_GRAPH_PROMPT = """
Extract entities and relationships relevant to Kubernetes operations:

Entities to capture:
- Pods, Deployments, Services, Namespaces
- Issues (OOMKilled, CrashLoopBackOff, ImagePullError, etc.)
- Fixes (restart, scale, resource adjustment, config change)
- Outcomes (resolved, partially resolved, failed)

Relationships to capture:
- AFFECTS: Issue affects Pod/Deployment
- FIXED_BY: Issue was fixed by a specific action
- RESULTED_IN: Fix resulted in an outcome
- CAUSED_BY: Issue was caused by another issue or condition
- SIMILAR_TO: Issue is similar to a previous issue
"""


def get_k8s_graph_mem0_config(
    collection_name: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Build a mem0 configuration optimized for Kubernetes remediation memory.

    Uses Qdrant for vector similarity search and Neo4j for graph-based
    relationship tracking with a custom prompt tuned for K8s entities.

    Args:
        collection_name: Qdrant collection name (default: from env or 'k8s-remediation')
        **kwargs: Additional arguments passed to get_graph_mem0_config()

    Returns:
        Dict configuration for K8s-focused graph memory
    """
    _collection_name = collection_name or os.environ.get("QDRANT_COLLECTION", "k8s-remediation")
    return get_graph_mem0_config(
        collection_name=_collection_name,
        graph_custom_prompt=K8S_GRAPH_PROMPT,
        **kwargs,
    )
