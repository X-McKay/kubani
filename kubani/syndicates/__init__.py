"""
Kubani Syndicates.

Syndicates are multi-agent orchestrations built on Temporal workflows.
Each syndicate coordinates agents through durable, observable workflows.

Usage:
    # Start a syndicate worker
    news-digest-worker    # News ingest, analyze, and digest workflows
    k8s-monitor-worker    # K8s cluster health monitoring

    # Or programmatically
    from kubani.syndicates.news_digest.workflows import (
        RSSIngestWorkflow,
        ArxivIngestWorkflow,
        GitHubIngestWorkflow,
        AnalyzeDocumentWorkflow,
        NewsDigestWorkflow,
    )
    from kubani.syndicates.k8s_monitor.workflows import K8sMonitorWorkflow
"""

from .k8s_monitor.workflows import K8sMonitorWorkflow
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
    # K8s Monitor workflow
    "K8sMonitorWorkflow",
]
