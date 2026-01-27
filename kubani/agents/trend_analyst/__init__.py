"""Trend Analyst Agent - Analyzes trends over historical data."""

from .agent import (
    EntityTrend,
    HistoricalSnapshot,
    TrendAnalysis,
    TrendAnalystAgent,
    VelocityClass,
)

__all__ = [
    "TrendAnalystAgent",
    "TrendAnalysis",
    "EntityTrend",
    "VelocityClass",
    "HistoricalSnapshot",
]
