"""
Temporal activities using federated agents.

These activities wrap the federated agent functionality for execution
by the Temporal worker. They replace the old activities.py which
directly instantiated agent classes.

The federated agents use skills to define WHAT to do and existing
implementation code for HOW to do it.
"""

import logging

from temporalio import activity

from news_monitor.federated import (
    NewsAnalystAgent,
    NewsCollectorAgent,
    NewsPublisherAgent,
)
from news_monitor.models import ProcessedArticle, RawArticle, TrendingTopic

logger = logging.getLogger(__name__)


# =============================================================================
# Collection Activities
# =============================================================================


@activity.defn
async def collect_articles(max_age_hours: int = 24) -> list[dict]:
    """
    Collect and filter articles using federated CollectorAgent.

    Executes skills:
    - news/collection/fetch-rss-feeds
    - news/collection/filter-duplicates

    Args:
        max_age_hours: Maximum age of articles to collect

    Returns:
        List of raw article dictionaries (already filtered for seen URLs)
    """
    logger.info(f"Starting collection (max_age={max_age_hours}h)")

    collector = NewsCollectorAgent(max_age_hours=max_age_hours)
    result = await collector.collect()

    logger.info(
        f"Collection complete: {result.total_collected} collected, "
        f"{result.seen_filtered} filtered, {len(result.articles)} new"
    )

    return [article.model_dump() for article in result.articles]


# =============================================================================
# Analysis Activities
# =============================================================================


@activity.defn
async def analyze_single_article(article_data: dict) -> dict | None:
    """
    Analyze a single article using federated AnalystAgent.

    Executes skill: news/diagnostic/analyze-article

    Args:
        article_data: Raw article dictionary

    Returns:
        Processed article dict, or None on failure
    """
    try:
        article = RawArticle(**article_data)
        analyst = NewsAnalystAgent(parallel_workers=1)

        result = await analyst.analyze_articles([article], deduplicate=False)

        if result.processed_articles:
            return result.processed_articles[0].model_dump()
        return None

    except Exception as e:
        title = article_data.get("title", "unknown")[:50]
        logger.warning(f"Failed to analyze '{title}...': {e}")
        return None


@activity.defn
async def analyze_articles_batch(
    raw_articles: list[dict],
    deduplicate: bool = True,
) -> list[dict]:
    """
    Analyze a batch of articles in parallel.

    Executes skill: news/diagnostic/analyze-article (parallelized)

    Args:
        raw_articles: List of raw article dictionaries
        deduplicate: Whether to filter and store unique articles

    Returns:
        List of processed article dictionaries
    """
    logger.info(f"Analyzing {len(raw_articles)} articles")

    articles = [RawArticle(**data) for data in raw_articles]
    analyst = NewsAnalystAgent()

    result = await analyst.analyze_articles(articles, deduplicate=deduplicate)

    logger.info(
        f"Analysis complete: {result.articles_analyzed} analyzed, {result.articles_failed} failed"
    )

    return [a.model_dump() for a in result.processed_articles]


@activity.defn
async def detect_breaking_news(processed_articles: list[dict]) -> list[dict]:
    """
    Detect breaking news articles.

    Executes skill: news/diagnostic/detect-breaking-news

    Args:
        processed_articles: List of processed article dictionaries

    Returns:
        List of breaking news articles
    """
    articles = [ProcessedArticle(**data) for data in processed_articles]
    analyst = NewsAnalystAgent()

    breaking = await analyst.detect_breaking_news(articles)

    if breaking:
        logger.info(f"Found {len(breaking)} breaking news articles")

    return [a.model_dump() for a in breaking]


@activity.defn
async def analyze_trends(processed_articles: list[dict]) -> list[dict]:
    """
    Analyze trends across articles.

    Executes skill: news/diagnostic/analyze-trends

    Args:
        processed_articles: List of processed article dictionaries

    Returns:
        List of trending topic dictionaries
    """
    articles = [ProcessedArticle(**data) for data in processed_articles]
    analyst = NewsAnalystAgent()

    trends = await analyst.analyze_trends(articles)

    logger.info(f"Identified {len(trends)} trends")

    return [t.model_dump() for t in trends]


# =============================================================================
# Publishing Activities
# =============================================================================


@activity.defn
async def compose_digest(
    processed_articles: list[dict],
    trends: list[dict],
    period_hours: int = 12,
) -> dict:
    """
    Compose a news digest.

    Executes skill: news/action/compose-digest

    Args:
        processed_articles: Articles for the digest
        trends: Trending topics
        period_hours: Hours covered

    Returns:
        News digest dictionary
    """
    logger.info(f"Composing digest from {len(processed_articles)} articles")

    articles = [ProcessedArticle(**data) for data in processed_articles]
    trending = [TrendingTopic(**data) for data in trends]

    publisher = NewsPublisherAgent()
    digest = await publisher.compose_digest(articles, trending, period_hours)

    return digest.model_dump()


@activity.defn
async def publish_digest(digest_data: dict) -> dict:
    """
    Publish a digest to Discord.

    Executes skill: news/action/publish-to-discord

    Args:
        digest_data: News digest dictionary

    Returns:
        Updated digest with message ID
    """
    from news_monitor.models import NewsDigest

    logger.info("Publishing digest to Discord")

    digest = NewsDigest(**digest_data)
    publisher = NewsPublisherAgent()

    result = await publisher.publish_digest(digest)

    if result.success and result.digest:
        return result.digest.model_dump()

    # Return original if publish failed
    return digest_data


@activity.defn
async def publish_breaking_alert(article_data: dict) -> str | None:
    """
    Publish a breaking news alert to Discord.

    Executes skill: news/action/publish-to-discord (breaking alert variant)

    Args:
        article_data: The breaking news article

    Returns:
        Discord message ID if successful
    """
    article = ProcessedArticle(**article_data)
    publisher = NewsPublisherAgent()

    result = await publisher.publish_breaking_alert(article)

    return result.message_id


# =============================================================================
# Combined Pipeline Activities
# =============================================================================


@activity.defn
async def run_full_pipeline(
    max_age_hours: int = 24,
    period_hours: int = 12,
) -> dict:
    """
    Run the complete news pipeline in a single activity.

    This combines collection, analysis, and publishing for simpler
    workflow orchestration.

    Args:
        max_age_hours: Maximum article age for collection
        period_hours: Hours covered by the digest

    Returns:
        Pipeline result with stats and digest info
    """
    # Step 1: Collect
    collector = NewsCollectorAgent(max_age_hours=max_age_hours)
    collection = await collector.collect()

    if not collection.articles:
        return {
            "success": True,
            "articles_collected": 0,
            "articles_processed": 0,
            "breaking_count": 0,
            "digest_published": False,
        }

    # Step 2: Analyze
    analyst = NewsAnalystAgent()
    analysis = await analyst.full_analysis(collection.articles)

    # Step 3: Publish breaking alerts
    for article in analysis.breaking_articles:
        publisher = NewsPublisherAgent()
        await publisher.publish_breaking_alert(article)

    # Step 4: Compose and publish digest
    publisher = NewsPublisherAgent()
    publish_result = await publisher.compose_and_publish(
        analysis.processed_articles,
        analysis.trends,
        period_hours,
    )

    return {
        "success": True,
        "articles_collected": collection.total_collected,
        "articles_processed": len(analysis.processed_articles),
        "breaking_count": len(analysis.breaking_articles),
        "trends_count": len(analysis.trends),
        "digest_published": publish_result.success,
        "digest_id": publish_result.digest.digest_id if publish_result.digest else None,
    }
