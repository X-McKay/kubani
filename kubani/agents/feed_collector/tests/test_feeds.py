"""Tests for RSS feed configuration and accessibility."""

import httpx
import pytest

from agents.feed_collector.feeds import FEEDS, get_enabled_feeds


class TestFeedURLs:
    """Test that all enabled feed URLs are accessible."""

    @pytest.mark.asyncio
    async def test_all_enabled_feeds_accessible(self):
        """Verify all enabled feed URLs return 200-299 status codes."""
        enabled_feeds = get_enabled_feeds()

        # Use a browser-like user agent to avoid 403 errors from some feeds
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        }
        async with httpx.AsyncClient(
            timeout=10.0, follow_redirects=True, headers=headers
        ) as client:
            results = []
            for feed in enabled_feeds:
                try:
                    response = await client.get(feed.url)
                    results.append((feed.name, feed.url, response.status_code))
                    # Allow 200-299 status codes
                    assert 200 <= response.status_code < 300, (
                        f"Feed '{feed.name}' returned {response.status_code}: {feed.url}"
                    )
                except Exception as e:
                    pytest.fail(f"Feed '{feed.name}' failed: {e}")

        # Print summary
        print("\n=== Feed Validation Results ===")
        for name, url, status in results:
            print(f"✓ {name}: {status} - {url}")

    def test_no_duplicate_feed_names(self):
        """Ensure all feed names are unique."""
        names = [f.name for f in FEEDS]
        assert len(names) == len(set(names)), "Duplicate feed names found"

    def test_no_duplicate_feed_urls(self):
        """Ensure all feed URLs are unique."""
        urls = [f.url for f in FEEDS]
        assert len(urls) == len(set(urls)), "Duplicate feed URLs found"

    def test_all_feeds_have_valid_priority(self):
        """Ensure all feeds have priority between 1-10."""
        for feed in FEEDS:
            assert 1 <= feed.priority <= 10, (
                f"Feed '{feed.name}' has invalid priority {feed.priority}"
            )
