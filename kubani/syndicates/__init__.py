"""
Kubani Syndicates.

Syndicates are multi-agent orchestrations built on Temporal workflows.
Each syndicate coordinates agents through durable, observable workflows.

Architecture:
    Syndicates use two patterns:
    - Workflow pattern: Deterministic sequences for known procedures
    - Swarm pattern: Emergent behavior for complex investigations

Usage:
    # Start a syndicate worker
    news-digest-worker    # News ingest, analyze, and digest workflows
    k8s-monitor-worker    # K8s remediation and investigation workflows

    # Or programmatically
    from kubani.syndicates.news_digest.workflows import (
        RSSIngestWorkflow,
        ArxivIngestWorkflow,
        GitHubIngestWorkflow,
        AnalyzeDocumentWorkflow,
        NewsDigestWorkflow,
    )
    from kubani.syndicates.k8s_monitor.workflows import (
        K8sRemediationWorkflow,
        K8sInvestigationSwarm,
    )

Each syndicate has:
- Its own Temporal namespace for isolation
- A dedicated task queue
- Observable workflows with status queries and pause/resume signals
"""

# Export workflows from syndicates
from .k8s_monitor.workflows import K8sInvestigationSwarm, K8sRemediationWorkflow
from .news_digest.workflows import (
    AnalyzeDocumentWorkflow,
    ArxivIngestWorkflow,
    GitHubIngestWorkflow,
    NewsDigestWorkflow,
    RSSIngestWorkflow,
)

__all__ = [
    # News Digest workflows
    "RSSIngestWorkflow",
    "ArxivIngestWorkflow",
    "GitHubIngestWorkflow",
    "AnalyzeDocumentWorkflow",
    "NewsDigestWorkflow",
    # K8s Monitor workflows
    "K8sRemediationWorkflow",
    "K8sInvestigationSwarm",
]
