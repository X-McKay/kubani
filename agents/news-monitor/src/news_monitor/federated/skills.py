"""
News domain skills - knowledge about when/how to process news.

Skills are KNOWLEDGE, not executable code. They define:
- Preconditions: When to apply this skill
- Actions: What steps to take
- Success criteria: How to verify it worked
- Failure handling: What to do if it doesn't work

Skills are authored as markdown in skills/news/ and synced to Qdrant
during deployment. At runtime, skills are retrieved from Qdrant only.
"""

import logging

from core_agents.skills.unified import (
    AgentSkill,
    SkillSearchResult,
    UnifiedSkillLibrary,
)

logger = logging.getLogger(__name__)

# Cached library instance for news operations
_news_library: UnifiedSkillLibrary | None = None
_initialized: bool = False


async def get_news_skill_library() -> UnifiedSkillLibrary:
    """
    Get the skill library configured for news skills.

    This does NOT sync skills from filesystem - skills should already
    be registered in Qdrant during deployment. Use `sync_news_skills()`
    for initial registration.
    """
    global _news_library, _initialized

    if _news_library is None:
        _news_library = UnifiedSkillLibrary()

    # Initialize connection to Qdrant (but don't sync from filesystem)
    if not _initialized:
        await _news_library._ensure_initialized()
        _initialized = True
        logger.info("News skill library connected to Qdrant")

    return _news_library


async def sync_news_skills() -> list[str]:
    """
    Sync news skills from filesystem to Qdrant.

    This should be called during deployment (e.g., from a Job or init container),
    NOT at runtime. Skills are authored as SKILL.md files in the skills/news/
    directory.

    Returns:
        List of skill IDs that were synced.
    """
    global _news_library, _initialized

    if _news_library is None:
        _news_library = UnifiedSkillLibrary()

    synced = await _news_library.sync()
    _initialized = True
    logger.info(f"Synced {len(synced)} news skills to Qdrant")
    return synced


async def list_news_skills(category: str | None = None) -> list[AgentSkill]:
    """
    List all news domain skills.

    Args:
        category: Optional category filter (collection, diagnostic, action)

    Returns:
        List of news skills
    """
    library = await get_news_skill_library()
    return await library.list_all(domain="news", category=category)


async def search_news_skills(
    query: str,
    category: str | None = None,
    limit: int = 5,
    min_confidence: float = 0.3,
) -> list[SkillSearchResult]:
    """
    Semantic search for news skills matching a query.

    Args:
        query: Natural language description of what you want to do
        category: Optional category filter
        limit: Maximum results
        min_confidence: Minimum skill confidence threshold

    Returns:
        List of matching skills with similarity scores
    """
    library = await get_news_skill_library()
    return await library.search(
        query=query,
        domain="news",
        category=category,
        limit=limit,
        min_confidence=min_confidence,
    )


async def get_news_skill(skill_id: str) -> AgentSkill | None:
    """
    Get a specific news skill by ID.

    Args:
        skill_id: Skill ID (e.g., 'news/collection/fetch-rss-feeds')

    Returns:
        The skill if found, None otherwise
    """
    library = await get_news_skill_library()
    return await library.get(skill_id)


async def get_skill_body(skill_id: str) -> str | None:
    """
    Get the full markdown body of a skill.

    Useful for loading skill instructions into agent context.

    Args:
        skill_id: Skill ID

    Returns:
        Full markdown content if found
    """
    library = await get_news_skill_library()
    return await library.get_body(skill_id)


# Skill categories for the news domain
NEWS_SKILL_CATEGORIES = {
    "collection": "Gather articles from sources",
    "diagnostic": "Analyze and classify content",
    "action": "Publish or export content",
}


async def get_skill_for_activity(activity_name: str) -> AgentSkill | None:
    """
    Find the skill that matches a Temporal activity.

    Maps activity names to their corresponding skills:
    - collect_rss_feeds -> news/collection/fetch-rss-feeds
    - filter_seen_urls -> news/collection/filter-duplicates
    - process_single_article -> news/diagnostic/analyze-article
    - check_breaking_news -> news/diagnostic/detect-breaking-news
    - analyze_trends -> news/diagnostic/analyze-trends
    - compose_digest -> news/action/compose-digest
    - publish_digest -> news/action/publish-to-discord

    Args:
        activity_name: Name of the Temporal activity

    Returns:
        Matching skill if found
    """
    activity_to_skill = {
        "collect_rss_feeds": "news/collection/fetch-rss-feeds",
        "filter_seen_urls": "news/collection/filter-duplicates",
        "process_single_article": "news/diagnostic/analyze-article",
        "process_articles": "news/diagnostic/analyze-article",
        "check_breaking_news": "news/diagnostic/detect-breaking-news",
        "analyze_trends": "news/diagnostic/analyze-trends",
        "compose_digest": "news/action/compose-digest",
        "publish_digest": "news/action/publish-to-discord",
        "publish_breaking_alert": "news/action/publish-to-discord",
    }

    skill_id = activity_to_skill.get(activity_name)
    if skill_id:
        return await get_news_skill(skill_id)
    return None
