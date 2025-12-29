"""News monitor agents for collecting, analyzing, and publishing AI news."""

from news_monitor.agents.analyst import ContentAnalystAgent
from news_monitor.agents.collector import RSSCollectorAgent
from news_monitor.agents.composer import DigestComposerAgent
from news_monitor.agents.publisher import DiscordPublisherAgent
from news_monitor.agents.trends import TrendAnalyzerAgent

__all__ = [
    "RSSCollectorAgent",
    "ContentAnalystAgent",
    "TrendAnalyzerAgent",
    "DigestComposerAgent",
    "DiscordPublisherAgent",
]
