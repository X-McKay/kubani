"""Tests for News Digest Temporal workflows.

These tests verify the workflow definitions compile correctly and
that the input/output types are properly structured. Full integration
tests require a running Temporal server.
"""


class TestNewsCollectionWorkflow:
    """Tests for NewsCollectionWorkflow."""

    def test_workflow_imports(self):
        """Test that workflow can be imported."""
        from kubani.syndicates.news_digest.workflows import NewsCollectionWorkflow

        assert NewsCollectionWorkflow is not None
        assert hasattr(NewsCollectionWorkflow, "run")

    def test_workflow_has_observability(self):
        """Test that workflow inherits from ObservableWorkflowMixin."""
        from kubani.syndicates.news_digest.workflows.collection import (
            NewsCollectionWorkflow,
        )

        instance = NewsCollectionWorkflow()
        assert hasattr(instance, "_init_observability")
        assert hasattr(instance, "_set_status")
        assert hasattr(instance, "_log_event")
        assert hasattr(instance, "_wait_if_paused")

    def test_collection_input_structure(self):
        """Test CollectionInput dataclass structure."""
        from kubani.syndicates.news_digest.workflows.collection import CollectionInput

        # Create with defaults
        input_data = CollectionInput()

        assert input_data.check_breaking is True
        assert input_data.notify_channel == "ai-news-breaking"
        assert input_data.correlation_id is None

    def test_collection_input_custom_config(self):
        """Test CollectionInput with custom configuration."""
        from kubani.syndicates.news_digest.workflows.collection import CollectionInput

        input_data = CollectionInput(
            check_breaking=False,
            notify_channel="custom-channel",
            correlation_id="corr-123",
        )

        assert input_data.check_breaking is False
        assert input_data.notify_channel == "custom-channel"
        assert input_data.correlation_id == "corr-123"

    def test_collection_result_structure(self):
        """Test CollectionResult dataclass structure."""
        from kubani.syndicates.news_digest.workflows.collection import CollectionResult

        result = CollectionResult()

        assert result.articles_collected == 0
        assert result.papers_collected == 0
        assert result.repos_collected == 0
        assert result.articles_stored == 0
        assert result.breaking_detected == 0
        assert result.success is True
        assert result.error is None

    def test_workflow_queries(self):
        """Test that workflow has query methods."""
        from kubani.syndicates.news_digest.workflows.collection import (
            NewsCollectionWorkflow,
        )

        instance = NewsCollectionWorkflow()

        # Collection-specific queries
        assert hasattr(instance, "get_collection_stats")
        # Standard queries from mixin
        assert hasattr(instance, "get_status")
        assert hasattr(instance, "get_events")


class TestNewsDigestWorkflow:
    """Tests for NewsDigestWorkflow."""

    def test_workflow_imports(self):
        """Test that workflow can be imported."""
        from kubani.syndicates.news_digest.workflows import NewsDigestWorkflow

        assert NewsDigestWorkflow is not None
        assert hasattr(NewsDigestWorkflow, "run")

    def test_workflow_has_observability(self):
        """Test that workflow inherits from ObservableWorkflowMixin."""
        from kubani.syndicates.news_digest.workflows.digest import NewsDigestWorkflow

        instance = NewsDigestWorkflow()
        assert hasattr(instance, "_init_observability")
        assert hasattr(instance, "_set_status")
        assert hasattr(instance, "_log_event")

    def test_digest_input_structure(self):
        """Test DigestInput dataclass structure."""
        from kubani.syndicates.news_digest.workflows.digest import DigestInput

        # Create with defaults
        input_data = DigestInput()

        assert input_data.digest_type == "scheduled"
        assert input_data.lookback_hours == 12
        assert input_data.notify_channel == "ai-news"
        assert input_data.include_research is True
        assert input_data.include_repos is True
        assert input_data.correlation_id is None

    def test_digest_input_custom_config(self):
        """Test DigestInput with custom configuration."""
        from kubani.syndicates.news_digest.workflows.digest import DigestInput

        input_data = DigestInput(
            digest_type="morning",
            lookback_hours=6,
            notify_channel="morning-digest",
            include_research=False,
            include_repos=False,
            correlation_id="digest-123",
        )

        assert input_data.digest_type == "morning"
        assert input_data.lookback_hours == 6
        assert input_data.notify_channel == "morning-digest"
        assert input_data.include_research is False
        assert input_data.include_repos is False

    def test_digest_result_structure(self):
        """Test DigestResult dataclass structure."""
        from kubani.syndicates.news_digest.workflows.digest import DigestResult

        result = DigestResult()

        assert result.articles_included == 0
        assert result.papers_included == 0
        assert result.repos_included == 0
        assert result.trends_identified == 0
        assert result.message_id is None
        assert result.success is True
        assert result.error is None

    def test_workflow_queries(self):
        """Test that workflow has query methods."""
        from kubani.syndicates.news_digest.workflows.digest import NewsDigestWorkflow

        instance = NewsDigestWorkflow()

        # Digest-specific queries
        assert hasattr(instance, "get_digest_stats")
        assert hasattr(instance, "get_top_trends")
        # Standard queries from mixin
        assert hasattr(instance, "get_status")
        assert hasattr(instance, "get_events")


class TestNewsWorkerRegistration:
    """Tests for News Digest worker registration."""

    def test_get_workflows(self):
        """Test that get_workflows returns correct workflows."""
        from kubani.syndicates.news_digest.src.news_digest_syndicate.worker import (
            get_workflows,
        )

        workflows = get_workflows()

        assert len(workflows) == 2
        workflow_names = [w.__name__ for w in workflows]
        assert "NewsCollectionWorkflow" in workflow_names
        assert "NewsDigestWorkflow" in workflow_names

    def test_get_activities(self):
        """Test that get_activities returns correct activities."""
        from kubani.syndicates.news_digest.src.news_digest_syndicate.worker import (
            get_activities,
        )

        activities = get_activities()

        # Should have the core activities
        assert len(activities) >= 5
        activity_names = [a.__name__ for a in activities]
        assert "run_agent_activity" in activity_names
        assert "store_article_activity" in activity_names
        assert "query_articles_activity" in activity_names
