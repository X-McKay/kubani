"""
News Digest Module.

Provides enhanced digest formats and feedback handling:

- Executive Brief: Structured 5-minute executive brief format
- Breaking News: Urgent news handling with separate channel
- Feedback: Emoji-based feedback collection and preference learning

Usage:
    from news_monitor.digest import (
        ExecutiveBriefComposer,
        ExecutiveBrief,
        BreakingNewsHandler,
        FeedbackCollector,
        PreferenceLearner,
    )

    # Compose executive brief
    composer = ExecutiveBriefComposer()
    brief = await composer.compose_executive_brief(articles, trends, start, end)

    # Post as single message
    message = brief.to_discord_message()

    # Or post as granular messages with reactions
    messages = brief.to_granular_messages()
    for msg in messages:
        post_to_discord(msg["content"], reactions=msg["reactions"])

    # Handle breaking news
    handler = BreakingNewsHandler()
    item = await handler.process_article(article)

    # Collect feedback
    collector = FeedbackCollector()
    await collector.record_reaction(message_id, channel_id, user_id, "👍")

    # Learn preferences
    learner = PreferenceLearner(collector)
    await learner.update_preferences()
    boost = learner.get_topic_boost("llm")
"""

from news_monitor.digest.breaking_news import (
    BreakingNewsClassifier,
    BreakingNewsHandler,
    BreakingNewsItem,
    RelevanceFilter,
)
from news_monitor.digest.executive_brief import (
    ContentCategory,
    DeepDive,
    ExecutiveBrief,
    ExecutiveBriefComposer,
    MiniBrief,
    NewsUrgency,
    SecurityAlert,
    TrendIndicator,
)
from news_monitor.digest.feedback import (
    EMOJI_MAPPING,
    FeedbackAggregation,
    FeedbackCollector,
    FeedbackEvent,
    FeedbackType,
    PreferenceLearner,
    SourcePreference,
    TopicPreference,
)

__all__ = [
    # Executive Brief
    "ExecutiveBriefComposer",
    "ExecutiveBrief",
    "DeepDive",
    "MiniBrief",
    "SecurityAlert",
    "TrendIndicator",
    "ContentCategory",
    "NewsUrgency",
    # Breaking News
    "BreakingNewsHandler",
    "BreakingNewsClassifier",
    "BreakingNewsItem",
    "RelevanceFilter",
    # Feedback
    "FeedbackCollector",
    "FeedbackEvent",
    "FeedbackType",
    "FeedbackAggregation",
    "PreferenceLearner",
    "TopicPreference",
    "SourcePreference",
    "EMOJI_MAPPING",
]
