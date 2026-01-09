"""
Federated agent architecture for news-monitor.

This module implements the skills-based news monitoring system:

- **Skills**: Knowledge about news collection, analysis, and publishing
- **CollectorAgent**: Executes collection skills (fetch-rss-feeds, filter-duplicates)
- **AnalystAgent**: Executes diagnostic skills (analyze-article, detect-breaking-news, analyze-trends)
- **PublisherAgent**: Executes action skills (compose-digest, publish-to-discord)
- **ExplorerAgent**: Discovers new RSS sources based on coverage gaps

Example:
    from news_monitor.federated import (
        NewsCollectorAgent,
        NewsAnalystAgent,
        NewsPublisherAgent,
        run_collection,
        run_analysis,
        run_publish,
    )

    # Run collection pipeline
    collection = await run_collection(max_age_hours=24)

    # Run analysis on collected articles
    analysis = await run_analysis(collection.articles)

    # Publish digest
    result = await run_publish(
        analysis.processed_articles,
        analysis.trends,
        period_hours=12,
    )
"""

from news_monitor.federated.analyst import (
    AnalysisResult,
    NewsAnalystAgent,
    run_analysis,
)
from news_monitor.federated.collector import (
    CollectionResult,
    NewsCollectorAgent,
    run_collection,
)
from news_monitor.federated.explorer import (
    CoverageGap,
    NewsExplorerAgent,
    SourceProposal,
    run_news_explorer_cycle,
)
from news_monitor.federated.publisher import (
    NewsPublisherAgent,
    PublishResult,
    run_publish,
)
from news_monitor.federated.skills import (
    NEWS_SKILL_CATEGORIES,
    get_news_skill,
    get_news_skill_library,
    get_skill_body,
    get_skill_for_activity,
    list_news_skills,
    search_news_skills,
)

__all__ = [
    # Federated Agents
    "NewsCollectorAgent",
    "NewsAnalystAgent",
    "NewsPublisherAgent",
    "NewsExplorerAgent",
    # Result types
    "CollectionResult",
    "AnalysisResult",
    "PublishResult",
    "CoverageGap",
    "SourceProposal",
    # Runner functions
    "run_collection",
    "run_analysis",
    "run_publish",
    "run_news_explorer_cycle",
    # Skills
    "get_news_skill_library",
    "list_news_skills",
    "search_news_skills",
    "get_news_skill",
    "get_skill_body",
    "get_skill_for_activity",
    "NEWS_SKILL_CATEGORIES",
]
