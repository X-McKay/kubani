"""
Content Analyst Agent - Analyzes content for insights and trends.

Usage:
    from agents.content_analyst import ContentAnalystAgent

    agent = ContentAnalystAgent()
    result = await agent.full_analysis(articles)
"""

from agents.content_analyst.agent import (
    AnalysisResult,
    ContentAnalystAgent,
    ProcessedArticle,
    TrendingTopic,
)

__all__ = [
    "ContentAnalystAgent",
    "AnalysisResult",
    "ProcessedArticle",
    "TrendingTopic",
]
