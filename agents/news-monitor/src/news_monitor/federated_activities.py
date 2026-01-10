"""
Temporal activities using federated agents.

These activities wrap the federated agent functionality for execution
by the Temporal worker. They replace the old activities.py which
directly instantiated agent classes.

The federated agents use skills to define WHAT to do and existing
implementation code for HOW to do it.

Enhanced with:
- Shared agent pattern for efficiency (singleton instances)
- Support for personalized digest generation
- User profile integration
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
async def compose_personalized_digest(
    user_id: str,
    processed_articles: list[dict],
    trends: list[dict],
    period_hours: int = 12,
) -> dict:
    """
    Compose a personalized news digest for a specific user.

    Uses user profile to:
    - Filter and rank articles by relevance
    - Include user-specific trends
    - Customize digest format

    Args:
        user_id: User identifier
        processed_articles: All available articles
        trends: Trending topics
        period_hours: Hours covered

    Returns:
        Personalized news digest dictionary
    """
    from news_monitor.user_profiles import (
        PersonalizedDigestGenerator,
        UserProfileManager,
    )

    logger.info(f"Composing personalized digest for user {user_id}")

    # Get user profile and generate personalized content
    profile_manager = UserProfileManager()
    generator = PersonalizedDigestGenerator(profile_manager)

    articles = [ProcessedArticle(**data) for data in processed_articles]
    trending = [TrendingTopic(**data) for data in trends]

    # Generate personalized digest data
    personalized = await generator.generate_personalized_digest(
        user_id, articles, trending
    )

    # Compose the actual digest using publisher
    publisher = NewsPublisherAgent()
    digest = await publisher.compose_digest(
        personalized["articles"],
        personalized["trends"],
        period_hours,
    )

    # Add personalization metadata
    result = digest.model_dump()
    result["personalized_for"] = user_id
    result["profile_topics"] = personalized["profile_topics"]

    return result


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


@activity.defn
async def record_user_feedback(
    user_id: str,
    article_id: str,
    positive: bool,
    article_topics: list[str] | None = None,
    article_source: str = "",
) -> bool:
    """
    Record user feedback on an article for profile refinement.

    This feedback is used to improve future personalized digests.

    Args:
        user_id: User identifier
        article_id: Article identifier
        positive: True for thumbs-up, False for thumbs-down
        article_topics: Topics associated with the article
        article_source: Source domain of the article

    Returns:
        True if feedback was recorded successfully
    """
    from news_monitor.user_profiles import UserProfileManager

    logger.info(f"Recording {'positive' if positive else 'negative'} feedback from {user_id}")

    try:
        profile_manager = UserProfileManager()
        await profile_manager.record_feedback(
            user_id=user_id,
            article_id=article_id,
            positive=positive,
            topics=article_topics or [],
            source=article_source,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to record feedback: {e}")
        return False


# =============================================================================
# Full Pipeline Activities
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


# =============================================================================
# Shared Agent Pattern (Optional Enhancement)
# =============================================================================
# The shared_agents module provides a singleton pattern for agent instances.
# This can be enabled for production use to improve efficiency:
#
# from news_monitor.shared_agents import get_shared_agents
#
# agents = get_shared_agents()
# result = await agents.collector.collect()
#
# Benefits:
# - Avoids repeated agent initialization overhead
# - Maintains warm MCP connections
# - Better memory utilization across invocations
#
# For testing, the direct instantiation pattern (used above) is preferred
# as it allows easier mocking of agent classes.
