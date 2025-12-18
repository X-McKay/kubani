"""
Temporal activities for the news monitor workflow.

Each activity wraps agent functionality for execution by the Temporal worker.
"""

import logging
from datetime import datetime, timedelta

from temporalio import activity

from news_monitor.agents.analyst import ContentAnalystAgent
from news_monitor.agents.collector import RSSCollectorAgent
from news_monitor.agents.composer import DigestComposerAgent
from news_monitor.agents.publisher import DiscordPublisherAgent
from news_monitor.agents.trends import TrendAnalyzerAgent
from news_monitor.memory import is_duplicate_article, store_article, store_digest_record
from news_monitor.models import NewsDigest, ProcessedArticle, RawArticle, TrendingTopic

logger = logging.getLogger(__name__)


@activity.defn
async def collect_rss_feeds(max_age_hours: int = 24) -> list[dict]:
    """
    Collect articles from all configured RSS feeds.

    Args:
        max_age_hours: Maximum age of articles to collect

    Returns:
        List of raw article dictionaries
    """
    logger.info("Starting RSS feed collection")

    with RSSCollectorAgent(max_age_hours=max_age_hours) as collector:
        articles = collector.collect_all(filter_ai_relevant=True)

    logger.info(f"Collected {len(articles)} articles")

    # Convert to dicts for serialization
    return [article.model_dump() for article in articles]


@activity.defn
async def process_articles(raw_articles: list[dict]) -> list[dict]:
    """
    Process and analyze collected articles.

    Args:
        raw_articles: List of raw article dictionaries

    Returns:
        List of processed article dictionaries
    """
    logger.info(f"Processing {len(raw_articles)} articles")

    # Convert back to models
    articles = [RawArticle(**data) for data in raw_articles]

    analyst = ContentAnalystAgent()
    processed = analyst.analyze_batch(articles)

    logger.info(f"Processed {len(processed)} articles")

    return [article.model_dump() for article in processed]


@activity.defn
async def deduplicate_articles(processed_articles: list[dict]) -> list[dict]:
    """
    Filter out duplicate articles using memory.

    Args:
        processed_articles: List of processed article dictionaries

    Returns:
        List of unique article dictionaries
    """
    logger.info(f"Deduplicating {len(processed_articles)} articles")

    articles = [ProcessedArticle(**data) for data in processed_articles]
    unique_articles = []

    for article in articles:
        if not is_duplicate_article(article):
            unique_articles.append(article)
            # Store in memory for future deduplication
            store_article(article)
        else:
            logger.debug(f"Filtered duplicate: {article.title[:50]}...")

    logger.info(f"After deduplication: {len(unique_articles)} articles")

    return [article.model_dump() for article in unique_articles]


@activity.defn
async def analyze_trends(processed_articles: list[dict]) -> list[dict]:
    """
    Analyze trends in the current batch of articles.

    Args:
        processed_articles: List of processed article dictionaries

    Returns:
        List of trending topic dictionaries
    """
    logger.info("Analyzing trends")

    articles = [ProcessedArticle(**data) for data in processed_articles]

    analyzer = TrendAnalyzerAgent()
    trends = analyzer.analyze_trends(articles)

    logger.info(f"Identified {len(trends)} trends")

    return [trend.model_dump() for trend in trends]


@activity.defn
async def compose_digest(
    processed_articles: list[dict],
    trends: list[dict],
    period_hours: int = 12,
) -> dict:
    """
    Compose a news digest from processed articles.

    Args:
        processed_articles: List of processed article dictionaries
        trends: List of trending topic dictionaries
        period_hours: Hours covered by this digest

    Returns:
        News digest dictionary
    """
    logger.info("Composing digest")

    articles = [ProcessedArticle(**data) for data in processed_articles]
    trending_topics = [TrendingTopic(**data) for data in trends]

    period_end = datetime.utcnow()
    period_start = period_end - timedelta(hours=period_hours)

    composer = DigestComposerAgent()
    digest = composer.compose_digest(articles, trending_topics, period_start, period_end)

    return digest.model_dump()


@activity.defn
async def publish_digest(digest_data: dict) -> dict:
    """
    Publish the digest to Discord.

    Args:
        digest_data: News digest dictionary

    Returns:
        Updated digest dictionary with message ID
    """
    logger.info("Publishing digest to Discord")

    digest = NewsDigest(**digest_data)

    composer = DigestComposerAgent()
    formatted = composer.format_for_discord(digest)

    publisher = DiscordPublisherAgent()
    message_id = publisher.publish_digest(digest, formatted)

    if message_id:
        digest.published = True
        digest.discord_message_id = message_id

        # Store digest record in memory
        store_digest_record(
            digest.digest_id,
            [a.url for s in digest.sections for a in s.articles] if digest.sections else [],
            [t.topic for t in digest.trending_topics],
            message_id,
        )

    return digest.model_dump()


@activity.defn
async def check_breaking_news(processed_articles: list[dict]) -> list[dict]:
    """
    Check for breaking news that should trigger immediate alerts.

    Args:
        processed_articles: List of processed article dictionaries

    Returns:
        List of breaking news articles
    """
    articles = [ProcessedArticle(**data) for data in processed_articles]

    breaking = [a for a in articles if a.is_breaking and a.importance_score >= 8]

    if breaking:
        logger.info(f"Found {len(breaking)} breaking news articles")

    return [article.model_dump() for article in breaking]


@activity.defn
async def publish_breaking_alert(article_data: dict) -> str | None:
    """
    Publish a breaking news alert to Discord.

    Args:
        article_data: The breaking news article dictionary

    Returns:
        Discord message ID if successful
    """
    logger.info("Publishing breaking news alert")

    article = ProcessedArticle(**article_data)

    composer = DigestComposerAgent()
    formatted = composer.format_breaking_alert(
        article,
        reason="High-importance breaking news detected",
    )

    publisher = DiscordPublisherAgent()
    message_id = publisher.publish_breaking_alert(article, formatted)

    return message_id
