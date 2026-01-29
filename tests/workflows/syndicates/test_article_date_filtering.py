"""Tests for article date filtering in query_articles_activity.

These tests verify that the date filtering logic correctly filters articles
based on their published_at metadata against start_date and end_date bounds.
"""




class TestParseIsoDate:
    """Tests for the _parse_iso_date helper function."""

    def test_parse_full_iso_datetime(self):
        """Test parsing full ISO format with time."""
        from kubani.framework.temporal.memory import _parse_iso_date

        result = _parse_iso_date("2026-01-29T10:30:00")
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 29
        assert result.hour == 10
        assert result.minute == 30

    def test_parse_iso_with_z_suffix(self):
        """Test parsing ISO format ending in Z (UTC)."""
        from kubani.framework.temporal.memory import _parse_iso_date

        result = _parse_iso_date("2026-01-29T10:30:00Z")
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 29

    def test_parse_date_only(self):
        """Test parsing date-only format."""
        from kubani.framework.temporal.memory import _parse_iso_date

        result = _parse_iso_date("2026-01-29")
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 29
        assert result.hour == 0
        assert result.minute == 0

    def test_parse_invalid_date_returns_none(self):
        """Test that invalid date strings return None."""
        from kubani.framework.temporal.memory import _parse_iso_date

        assert _parse_iso_date("not-a-date") is None
        assert _parse_iso_date("") is None
        assert _parse_iso_date("2026/01/29") is None  # Wrong format

    def test_parse_none_returns_none(self):
        """Test that None input returns None."""
        from kubani.framework.temporal.memory import _parse_iso_date

        assert _parse_iso_date(None) is None

    def test_parse_iso_with_microseconds(self):
        """Test parsing ISO format with microseconds."""
        from kubani.framework.temporal.memory import _parse_iso_date

        result = _parse_iso_date("2026-01-29T10:30:00.123456")
        assert result is not None
        assert result.year == 2026

    def test_parse_iso_with_timezone_offset(self):
        """Test parsing ISO format with timezone offset."""
        from kubani.framework.temporal.memory import _parse_iso_date

        result = _parse_iso_date("2026-01-29T10:30:00+00:00")
        assert result is not None
        assert result.year == 2026


class TestDateFilteringLogic:
    """Tests for the date filtering logic in _filter_articles_by_date."""

    def test_filter_articles_before_start_date(self):
        """Test that articles before start_date are filtered out."""
        from kubani.framework.temporal.memory import _filter_articles_by_date

        articles = [
            {"title": "Old Article", "metadata": {"published_at": "2026-01-01T10:00:00"}},
            {"title": "New Article", "metadata": {"published_at": "2026-01-20T10:00:00"}},
        ]

        filtered = _filter_articles_by_date(
            articles,
            start_date="2026-01-15",
            end_date=None,
        )

        assert len(filtered) == 1
        assert filtered[0]["title"] == "New Article"

    def test_filter_articles_after_end_date(self):
        """Test that articles after end_date are filtered out."""
        from kubani.framework.temporal.memory import _filter_articles_by_date

        articles = [
            {"title": "Old Article", "metadata": {"published_at": "2026-01-01T10:00:00"}},
            {"title": "New Article", "metadata": {"published_at": "2026-01-20T10:00:00"}},
        ]

        filtered = _filter_articles_by_date(
            articles,
            start_date=None,
            end_date="2026-01-10",
        )

        assert len(filtered) == 1
        assert filtered[0]["title"] == "Old Article"

    def test_filter_articles_within_date_range(self):
        """Test that only articles within date range are included."""
        from kubani.framework.temporal.memory import _filter_articles_by_date

        articles = [
            {"title": "Too Old", "metadata": {"published_at": "2026-01-01T10:00:00"}},
            {"title": "In Range", "metadata": {"published_at": "2026-01-15T10:00:00"}},
            {"title": "Too New", "metadata": {"published_at": "2026-01-30T10:00:00"}},
        ]

        filtered = _filter_articles_by_date(
            articles,
            start_date="2026-01-10",
            end_date="2026-01-20",
        )

        assert len(filtered) == 1
        assert filtered[0]["title"] == "In Range"

    def test_include_articles_with_missing_published_at(self):
        """Test that articles with missing published_at are included."""
        from kubani.framework.temporal.memory import _filter_articles_by_date

        articles = [
            {"title": "No Date", "metadata": {}},
            {"title": "Has Date", "metadata": {"published_at": "2026-01-01T10:00:00"}},
        ]

        filtered = _filter_articles_by_date(
            articles,
            start_date="2026-01-15",
            end_date=None,
        )

        # "No Date" should be included (can't determine range)
        # "Has Date" should be filtered out (before start_date)
        assert len(filtered) == 1
        assert filtered[0]["title"] == "No Date"

    def test_include_articles_with_invalid_date_strings(self):
        """Test that articles with invalid date strings are included."""
        from kubani.framework.temporal.memory import _filter_articles_by_date

        articles = [
            {"title": "Invalid Date", "metadata": {"published_at": "not-a-date"}},
            {"title": "Valid Old", "metadata": {"published_at": "2026-01-01T10:00:00"}},
        ]

        filtered = _filter_articles_by_date(
            articles,
            start_date="2026-01-15",
            end_date=None,
        )

        # "Invalid Date" should be included (can't determine range)
        # "Valid Old" should be filtered out (before start_date)
        assert len(filtered) == 1
        assert filtered[0]["title"] == "Invalid Date"

    def test_no_filtering_when_no_date_bounds(self):
        """Test that no filtering happens when no date bounds are provided."""
        from kubani.framework.temporal.memory import _filter_articles_by_date

        articles = [
            {"title": "Article 1", "metadata": {"published_at": "2026-01-01T10:00:00"}},
            {"title": "Article 2", "metadata": {"published_at": "2026-01-20T10:00:00"}},
        ]

        filtered = _filter_articles_by_date(
            articles,
            start_date=None,
            end_date=None,
        )

        assert len(filtered) == 2

    def test_include_articles_with_none_published_at(self):
        """Test that articles with None published_at are included."""
        from kubani.framework.temporal.memory import _filter_articles_by_date

        articles = [
            {"title": "None Date", "metadata": {"published_at": None}},
            {"title": "Has Date", "metadata": {"published_at": "2026-01-01T10:00:00"}},
        ]

        filtered = _filter_articles_by_date(
            articles,
            start_date="2026-01-15",
            end_date=None,
        )

        assert len(filtered) == 1
        assert filtered[0]["title"] == "None Date"

    def test_empty_article_list(self):
        """Test filtering an empty article list."""
        from kubani.framework.temporal.memory import _filter_articles_by_date

        filtered = _filter_articles_by_date(
            [],
            start_date="2026-01-15",
            end_date="2026-01-20",
        )

        assert filtered == []

    def test_article_without_metadata(self):
        """Test articles without metadata dict are included."""
        from kubani.framework.temporal.memory import _filter_articles_by_date

        articles = [
            {"title": "No Metadata"},
            {"title": "Has Metadata", "metadata": {"published_at": "2026-01-01T10:00:00"}},
        ]

        filtered = _filter_articles_by_date(
            articles,
            start_date="2026-01-15",
            end_date=None,
        )

        assert len(filtered) == 1
        assert filtered[0]["title"] == "No Metadata"
