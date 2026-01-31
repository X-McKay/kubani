"""
Trend Analyst Agent - Analyzes trends over historical data.

Usage:
    from kubani.agents.trend_analyst import TrendAnalystAgent

    agent = TrendAnalystAgent()
    analysis = await agent.analyze_trends(current_entities, historical_data)
"""

from .agent import (
    EntityTrend,
    TrendAnalysis,
    TrendAnalystAgent,
)

__all__ = [
    "TrendAnalystAgent",
    "TrendAnalysis",
    "EntityTrend",
]
