"""Tests for NewsCollectionWorkflow.

These tests verify the workflow logic by mocking Temporal activities.
For full integration tests, run with a Temporal test server.
"""

from kubani.syndicates.news_digest.workflows.collection import (
    CollectionInput,
    CollectionResult,
    NewsCollectionWorkflow,
)


class TestCollectionInput:
    """Test CollectionInput dataclass."""

    def test_default_values(self):
        """CollectionInput should have sensible defaults."""
        input = CollectionInput()
        assert input.check_breaking is True
        assert input.notify_channel == "ai-news-breaking"
        assert input.correlation_id is None

    def test_custom_values(self):
        """CollectionInput should accept custom values."""
        input = CollectionInput(
            check_breaking=False,
            notify_channel="custom-channel",
            correlation_id="test-123",
        )
        assert input.check_breaking is False
        assert input.notify_channel == "custom-channel"
        assert input.correlation_id == "test-123"


class TestCollectionResult:
    """Test CollectionResult dataclass."""

    def test_default_values(self):
        """CollectionResult should have sensible defaults."""
        result = CollectionResult()
        assert result.articles_collected == 0
        assert result.papers_collected == 0
        assert result.repos_collected == 0
        assert result.articles_stored == 0
        assert result.repos_stored == 0
        assert result.breaking_detected == 0
        assert result.success is True
        assert result.error is None

    def test_custom_values(self):
        """CollectionResult should accept custom values."""
        result = CollectionResult(
            articles_collected=10,
            papers_collected=5,
            repos_collected=3,
            articles_stored=8,
            repos_stored=2,
            breaking_detected=1,
            success=True,
            error=None,
        )
        assert result.articles_collected == 10
        assert result.papers_collected == 5
        assert result.repos_collected == 3


class TestNewsCollectionWorkflowInit:
    """Test NewsCollectionWorkflow initialization."""

    def test_workflow_initializes(self):
        """Workflow should initialize with default state."""
        workflow = NewsCollectionWorkflow()
        assert workflow._result is not None
        assert workflow._result.success is True
        assert workflow._breaking_articles == []


class TestNewsCollectionWorkflowResultBuilding:
    """Test result building logic."""

    def test_build_result_returns_dict(self):
        """_build_result should return a dictionary."""
        workflow = NewsCollectionWorkflow()
        workflow._result.articles_collected = 5
        workflow._result.papers_collected = 3
        workflow._result.success = True

        result = workflow._build_result()

        assert isinstance(result, dict)
        assert result["articles_collected"] == 5
        assert result["papers_collected"] == 3
        assert result["success"] is True

    def test_build_result_includes_all_fields(self):
        """_build_result should include all CollectionResult fields."""
        workflow = NewsCollectionWorkflow()

        result = workflow._build_result()

        expected_keys = {
            "articles_collected",
            "papers_collected",
            "repos_collected",
            "articles_stored",
            "repos_stored",
            "breaking_detected",
            "success",
            "error",
        }
        assert set(result.keys()) == expected_keys


class TestNewsCollectionWorkflowParsing:
    """Test result parsing helpers."""

    def test_parse_articles_from_valid_json(self):
        """Should parse articles from valid JSON array."""
        workflow = NewsCollectionWorkflow()
        json_str = '[{"title": "Test", "url": "https://example.com"}]'

        result = workflow._parse_articles_from_result(json_str)

        assert len(result) == 1
        assert result[0]["title"] == "Test"

    def test_parse_articles_from_wrapped_json(self):
        """Should parse articles from JSON with surrounding text."""
        workflow = NewsCollectionWorkflow()
        json_str = 'Here are the results: [{"title": "Test"}] Done.'

        result = workflow._parse_articles_from_result(json_str)

        assert len(result) == 1

    def test_parse_articles_from_invalid_json(self):
        """Should return empty list for invalid JSON."""
        workflow = NewsCollectionWorkflow()
        json_str = "This is not JSON"

        result = workflow._parse_articles_from_result(json_str)

        assert result == []

    def test_parse_papers_delegates_to_articles(self):
        """_parse_papers_from_result should use same logic as articles."""
        workflow = NewsCollectionWorkflow()
        json_str = '[{"arxiv_id": "123"}]'

        result = workflow._parse_papers_from_result(json_str)

        assert len(result) == 1
        assert result[0]["arxiv_id"] == "123"


class TestNewsCollectionWorkflowQueries:
    """Test workflow queries."""

    def test_get_collection_stats_query(self):
        """get_collection_stats should return current statistics."""
        workflow = NewsCollectionWorkflow()
        workflow._result.articles_collected = 10
        workflow._result.papers_collected = 5
        workflow._result.repos_collected = 3
        workflow._result.articles_stored = 8
        workflow._result.repos_stored = 2
        workflow._result.breaking_detected = 1

        stats = workflow.get_collection_stats()

        assert stats["articles_collected"] == 10
        assert stats["papers_collected"] == 5
        assert stats["repos_collected"] == 3
        assert stats["articles_stored"] == 8
        assert stats["repos_stored"] == 2
        assert stats["breaking_detected"] == 1


# Note: Full workflow execution tests require Temporal test environment.
# The tests above verify the workflow logic in isolation.
# For integration tests, use temporalio.testing.WorkflowEnvironment:
#
# @pytest.mark.asyncio
# async def test_workflow_execution():
#     async with await WorkflowEnvironment.start_time_skipping() as env:
#         async with Worker(
#             env.client,
#             task_queue="test-queue",
#             workflows=[NewsCollectionWorkflow],
#             activities=[...mocked activities...],
#         ):
#             result = await env.client.execute_workflow(
#                 NewsCollectionWorkflow.run,
#                 CollectionInput(),
#                 id="test-workflow",
#                 task_queue="test-queue",
#             )
#             assert result["success"] is True


class TestWorkerActivityRegistration:
    """Test that the worker registers all required activities."""

    def test_paper_activities_registered(self):
        """Worker must register paper dedup activities for collection to work."""
        from news_digest_syndicate.worker import get_activities

        activities = get_activities()
        activity_names = [a.__name__ for a in activities]

        assert "store_paper_activity" in activity_names
        assert "check_paper_exists_activity" in activity_names

    def test_all_collection_activities_registered(self):
        """Worker must register all activities used by collection workflow."""
        from news_digest_syndicate.worker import get_activities

        activities = get_activities()
        activity_names = [a.__name__ for a in activities]

        required = [
            "run_agent_activity",
            "collect_feeds_activity",
            "store_article_activity",
            "check_article_exists_activity",
            "store_paper_activity",
            "check_paper_exists_activity",
            "store_repo_activity",
            "check_repo_exists_activity",
            "send_breaking_news_activity",
            "publish_ui_activity",
        ]
        for name in required:
            assert name in activity_names, f"Missing activity: {name}"
