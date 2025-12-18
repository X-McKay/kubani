"""Tests for RSS feed configuration."""

from news_monitor.feeds import (
    FEEDS,
    FeedCategory,
    get_enabled_feeds,
    get_feeds_by_category,
    is_ai_relevant,
)


def test_feeds_not_empty():
    """Verify we have feeds configured."""
    assert len(FEEDS) > 0


def test_all_feeds_have_urls():
    """All feeds should have valid URLs."""
    for feed in FEEDS:
        assert feed.url.startswith("http"), f"{feed.name} has invalid URL"


def test_get_enabled_feeds_sorted_by_priority():
    """Enabled feeds should be sorted by priority (highest first)."""
    feeds = get_enabled_feeds()
    priorities = [f.priority for f in feeds]
    assert priorities == sorted(priorities, reverse=True)


def test_get_feeds_by_category():
    """Should filter feeds by category."""
    company_blogs = get_feeds_by_category(FeedCategory.COMPANY_BLOGS)
    assert len(company_blogs) > 0
    for feed in company_blogs:
        assert feed.category == FeedCategory.COMPANY_BLOGS


def test_is_ai_relevant_matches_keywords():
    """Should detect AI-relevant content."""
    assert is_ai_relevant("OpenAI releases new GPT model")
    assert is_ai_relevant("Claude 4 announced by Anthropic")
    assert is_ai_relevant("New machine learning breakthrough")
    assert is_ai_relevant("Large language model safety research")


def test_is_ai_relevant_rejects_unrelated():
    """Should reject non-AI content."""
    assert not is_ai_relevant("New smartphone released")
    assert not is_ai_relevant("Stock market update")
    assert not is_ai_relevant("Weather forecast for tomorrow")


def test_hacker_news_feed_included():
    """Hacker News should be in the feed list."""
    feed_names = [f.name.lower() for f in FEEDS]
    assert any("hacker news" in name for name in feed_names)


def test_company_blogs_high_priority():
    """Company blogs should have high priority."""
    company_blogs = get_feeds_by_category(FeedCategory.COMPANY_BLOGS)
    for feed in company_blogs:
        assert feed.priority >= 7, f"{feed.name} should have high priority"
