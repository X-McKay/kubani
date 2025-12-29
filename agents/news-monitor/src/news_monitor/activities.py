"""
Temporal activities for the news monitor workflow.

Each activity wraps agent functionality for execution by the Temporal worker.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from temporalio import activity

from news_monitor.agents.analyst import ContentAnalystAgent
from news_monitor.agents.collector import RSSCollectorAgent
from news_monitor.agents.composer import DigestComposerAgent
from news_monitor.agents.publisher import DiscordPublisherAgent
from news_monitor.agents.trends import TrendAnalyzerAgent
from news_monitor.memory import (
    is_duplicate_article,
    is_url_seen,
    store_article,
    store_digest_record,
)
from news_monitor.models import NewsDigest, ProcessedArticle, RawArticle, TrendingTopic

logger = logging.getLogger(__name__)

# Number of parallel workers for article processing
MAX_PARALLEL_WORKERS = 8


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
async def filter_seen_urls(raw_articles: list[dict]) -> list[dict]:
    """
    Fast pre-filter to remove articles we've already processed.

    Uses Redis for O(1) lookup. This prevents wasting LLM calls on
    articles we've seen before.

    Args:
        raw_articles: List of raw article dictionaries

    Returns:
        List of articles not yet seen
    """
    logger.info(f"Pre-filtering {len(raw_articles)} articles for seen URLs")

    unseen = []
    seen_count = 0

    for article_data in raw_articles:
        url = article_data.get("url", "")
        if not is_url_seen(url):
            unseen.append(article_data)
        else:
            seen_count += 1

    logger.info(f"Pre-filter: {seen_count} already seen, {len(unseen)} new articles")

    return unseen


def _process_single_article(article_data: dict, analyst: ContentAnalystAgent) -> dict | None:
    """
    Process a single article. Returns None on failure.

    This is a helper function for parallel processing.
    """
    try:
        article = RawArticle(**article_data)
        processed = analyst.analyze_article(article)
        return processed.model_dump()
    except Exception as e:
        title = article_data.get("title", "unknown")[:50]
        logger.warning(f"Failed to process article '{title}...': {e}")
        return None


@activity.defn
async def process_articles(raw_articles: list[dict]) -> list[dict]:
    """
    Process and analyze collected articles in parallel.

    Uses ThreadPoolExecutor for parallel LLM calls. Individual article
    failures are logged but don't stop processing of other articles.

    Args:
        raw_articles: List of raw article dictionaries

    Returns:
        List of processed article dictionaries (excludes failures)
    """
    logger.info(f"Processing {len(raw_articles)} articles with {MAX_PARALLEL_WORKERS} workers")

    analyst = ContentAnalystAgent()
    processed = []
    failed_count = 0

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
        # Submit all articles for processing
        future_to_article = {
            executor.submit(_process_single_article, article_data, analyst): article_data
            for article_data in raw_articles
        }

        # Collect results as they complete
        for future in as_completed(future_to_article):
            result = future.result()
            if result is not None:
                processed.append(result)
            else:
                failed_count += 1

    logger.info(f"Processed {len(processed)} articles successfully, {failed_count} failed")

    return processed


@activity.defn
async def deduplicate_single_article(article_data: dict) -> dict | None:
    """
    Check if a single article is a duplicate and store it if unique.

    This activity processes one article at a time, allowing Temporal to:
    - Handle timeouts per-article (not per-batch)
    - Retry individual articles on failure
    - Process articles in parallel

    Args:
        article_data: Single processed article dictionary

    Returns:
        The article dictionary if unique, None if duplicate
    """
    article = ProcessedArticle(**article_data)
    title_preview = article.title[:50] if article.title else "unknown"

    if is_duplicate_article(article):
        logger.debug(f"Filtered duplicate: {title_preview}...")
        return None

    # Store in memory for future deduplication
    store_article(article)
    logger.debug(f"Stored unique article: {title_preview}...")

    return article.model_dump()


@activity.defn
async def deduplicate_articles(processed_articles: list[dict]) -> list[dict]:
    """
    Filter out duplicate articles using memory.

    DEPRECATED: Use deduplicate_single_article in parallel from the workflow
    for better timeout handling. This function is kept for backward compatibility.

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
