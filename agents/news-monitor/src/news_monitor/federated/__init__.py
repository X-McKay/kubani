"""
Federated agent architecture for news-monitor.

This module implements source discovery and coverage gap analysis:
- NewsExplorerAgent: Discovers new RSS sources based on coverage gaps
- SourceProposal: Proposed new source for approval

Example:
    from news_monitor.federated import NewsExplorerAgent

    explorer = NewsExplorerAgent()
    gaps = await explorer.analyze_coverage_gaps()
    proposals = await explorer.discover_sources(gaps[0])
"""

from news_monitor.federated.explorer import (
    CoverageGap,
    NewsExplorerAgent,
    SourceProposal,
    run_news_explorer_cycle,
)

__all__ = [
    "NewsExplorerAgent",
    "CoverageGap",
    "SourceProposal",
    "run_news_explorer_cycle",
]
