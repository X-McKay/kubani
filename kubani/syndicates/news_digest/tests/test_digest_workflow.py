"""Tests for NewsDigestWorkflow.

These tests verify the workflow logic by mocking Temporal activities.
For full integration tests, run with a Temporal test server.
"""

from kubani.syndicates.news_digest.workflows.digest import (
    DigestInput,
    DigestResult,
    NewsDigestWorkflow,
)


class TestDigestInput:
    """Test DigestInput dataclass."""

    def test_default_values(self):
        """DigestInput should have sensible defaults."""
        input = DigestInput()
        assert input.digest_type == "scheduled"
        assert input.lookback_hours == 12
        assert input.notify_channel == "ai-news"
        assert input.include_research is True
        assert input.include_repos is True
        assert input.correlation_id is None

    def test_custom_values(self):
        """DigestInput should accept custom values."""
        input = DigestInput(
            digest_type="morning",
            lookback_hours=24,
            notify_channel="custom-channel",
            include_research=False,
            include_repos=False,
            correlation_id="test-456",
        )
        assert input.digest_type == "morning"
        assert input.lookback_hours == 24
        assert input.notify_channel == "custom-channel"
        assert input.include_research is False
        assert input.include_repos is False
        assert input.correlation_id == "test-456"


class TestDigestResult:
    """Test DigestResult dataclass."""

    def test_default_values(self):
        """DigestResult should have sensible defaults."""
        result = DigestResult()
        assert result.articles_included == 0
        assert result.papers_included == 0
        assert result.repos_included == 0
        assert result.trends_identified == 0
        assert result.message_id is None
        assert result.success is True
        assert result.error is None

    def test_custom_values(self):
        """DigestResult should accept custom values."""
        result = DigestResult(
            articles_included=20,
            papers_included=5,
            repos_included=3,
            trends_identified=8,
            message_id="discord-msg-123",
            success=True,
            error=None,
        )
        assert result.articles_included == 20
        assert result.papers_included == 5
        assert result.repos_included == 3
        assert result.trends_identified == 8
        assert result.message_id == "discord-msg-123"


class TestNewsDigestWorkflowInit:
    """Test NewsDigestWorkflow initialization."""

    def test_workflow_initializes(self):
        """Workflow should initialize with default state."""
        workflow = NewsDigestWorkflow()
        assert workflow._result is not None
        assert workflow._result.success is True
        assert workflow._articles == []
        assert workflow._papers == []
        assert workflow._repos == []
        assert workflow._trends == []


class TestNewsDigestWorkflowResultBuilding:
    """Test result building logic."""

    def test_build_result_returns_dict(self):
        """_build_result should return a dictionary."""
        workflow = NewsDigestWorkflow()
        workflow._result.articles_included = 15
        workflow._result.trends_identified = 5
        workflow._result.success = True

        result = workflow._build_result()

        assert isinstance(result, dict)
        assert result["articles_included"] == 15
        assert result["trends_identified"] == 5
        assert result["success"] is True

    def test_build_result_includes_all_fields(self):
        """_build_result should include all DigestResult fields."""
        workflow = NewsDigestWorkflow()

        result = workflow._build_result()

        expected_keys = {
            "articles_included",
            "papers_included",
            "repos_included",
            "trends_identified",
            "message_id",
            "success",
            "error",
        }
        assert set(result.keys()) == expected_keys


class TestNewsDigestWorkflowParsing:
    """Test result parsing helpers."""

    def test_parse_json_from_valid_object(self):
        """Should parse JSON object from valid string."""
        workflow = NewsDigestWorkflow()
        json_str = '{"key": "value", "count": 42}'

        result = workflow._parse_json_from_result(json_str)

        assert result["key"] == "value"
        assert result["count"] == 42

    def test_parse_json_from_wrapped_object(self):
        """Should parse JSON object with surrounding text."""
        workflow = NewsDigestWorkflow()
        json_str = 'Here is the result: {"status": "ok"} End.'

        result = workflow._parse_json_from_result(json_str)

        assert result["status"] == "ok"

    def test_parse_json_from_invalid_string(self):
        """Should return empty dict for invalid JSON."""
        workflow = NewsDigestWorkflow()
        json_str = "This is not JSON"

        result = workflow._parse_json_from_result(json_str)

        assert result == {}

    def test_parse_json_array_from_valid_array(self):
        """Should parse JSON array from valid string."""
        workflow = NewsDigestWorkflow()
        json_str = '[{"id": 1}, {"id": 2}]'

        result = workflow._parse_json_array_from_result(json_str)

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2

    def test_parse_json_array_from_wrapped_array(self):
        """Should parse JSON array with surrounding text."""
        workflow = NewsDigestWorkflow()
        json_str = 'Results: [{"item": "a"}, {"item": "b"}] Done.'

        result = workflow._parse_json_array_from_result(json_str)

        assert len(result) == 2

    def test_parse_json_array_from_invalid_string(self):
        """Should return empty list for invalid JSON."""
        workflow = NewsDigestWorkflow()
        json_str = "Not a valid array"

        result = workflow._parse_json_array_from_result(json_str)

        assert result == []


class TestNewsDigestWorkflowQueries:
    """Test workflow queries."""

    def test_get_digest_stats_query(self):
        """get_digest_stats should return current statistics."""
        workflow = NewsDigestWorkflow()
        workflow._result.articles_included = 20
        workflow._result.papers_included = 5
        workflow._result.repos_included = 3
        workflow._result.trends_identified = 8
        workflow._trends = [
            {"topic": "GPT-5", "mention_count": 10},
            {"topic": "AI Safety", "mention_count": 5},
        ]

        stats = workflow.get_digest_stats()

        assert stats["articles_included"] == 20
        assert stats["papers_included"] == 5
        assert stats["repos_included"] == 3
        assert stats["trends_identified"] == 8
        assert len(stats["trends"]) == 2

    def test_get_top_trends_query(self):
        """get_top_trends should return trends sorted by mention count."""
        workflow = NewsDigestWorkflow()
        workflow._trends = [
            {"topic": "Low", "mention_count": 2},
            {"topic": "High", "mention_count": 10},
            {"topic": "Medium", "mention_count": 5},
        ]

        trends = workflow.get_top_trends()

        assert len(trends) == 3
        assert trends[0]["topic"] == "High"
        assert trends[1]["topic"] == "Medium"
        assert trends[2]["topic"] == "Low"

    def test_get_top_trends_limits_to_10(self):
        """get_top_trends should return at most 10 trends."""
        workflow = NewsDigestWorkflow()
        workflow._trends = [{"topic": f"Topic{i}", "mention_count": i} for i in range(15)]

        trends = workflow.get_top_trends()

        assert len(trends) == 10


# Note: Full workflow execution tests require Temporal test environment.
# The tests above verify the workflow logic in isolation.
# For integration tests, use temporalio.testing.WorkflowEnvironment:
#
# @pytest.mark.asyncio
# async def test_workflow_execution(sample_articles, sample_trends):
#     async with await WorkflowEnvironment.start_time_skipping() as env:
#         # Mock activities to return sample data
#         @activity.defn(name="query_articles_activity")
#         async def mock_query_articles(*args):
#             return {"success": True, "articles": sample_articles}
#
#         async with Worker(
#             env.client,
#             task_queue="test-queue",
#             workflows=[NewsDigestWorkflow],
#             activities=[mock_query_articles, ...],
#         ):
#             result = await env.client.execute_workflow(
#                 NewsDigestWorkflow.run,
#                 DigestInput(),
#                 id="test-digest",
#                 task_queue="test-queue",
#             )
#             assert result["success"] is True
