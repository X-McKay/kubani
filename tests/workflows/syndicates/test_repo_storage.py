"""Tests for GitHub repo storage in Memory MCP."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestStoreRepoActivity:
    """Tests for store_repo_activity."""

    @pytest.mark.asyncio
    async def test_stores_repo_as_knowledge(self):
        """Test that repo is stored as knowledge entry."""
        from kubani.framework.temporal.memory import store_repo_activity

        mock_client = MagicMock()
        mock_memory = AsyncMock()
        mock_memory.store_knowledge.return_value = {"knowledge_id": "repo:abc123"}
        mock_memory.cache_set.return_value = {"success": True}
        mock_client.memory = mock_memory

        with patch(
            "kubani.framework.temporal.memory._get_memory_client",
            return_value=mock_client,
        ):
            result = await store_repo_activity(
                repo_url="https://github.com/openai/gpt-4",
                name="gpt-4",
                description="GPT-4 model implementation",
                stars=50000,
                language="Python",
                topics=["ai", "llm", "gpt"],
                ttl_days=14,
            )

        assert result["success"] is True
        assert result["repo_id"] is not None
        mock_memory.store_knowledge.assert_called_once()

    @pytest.mark.asyncio
    async def test_repo_topic_format(self):
        """Test that repo uses correct topic format."""
        from kubani.framework.temporal.memory import store_repo_activity

        mock_client = MagicMock()
        mock_memory = AsyncMock()
        mock_memory.store_knowledge.return_value = {"knowledge_id": "repo:test"}
        mock_memory.cache_set.return_value = {"success": True}
        mock_client.memory = mock_memory

        with patch(
            "kubani.framework.temporal.memory._get_memory_client",
            return_value=mock_client,
        ):
            await store_repo_activity(
                repo_url="https://github.com/user/repo",
                name="repo",
                description="Test repo",
                stars=100,
                language="Python",
                topics=["test"],
            )

        # Verify topic format is "repo:{owner}/{name}"
        call_kwargs = mock_memory.store_knowledge.call_args[1]
        assert call_kwargs["topic"].startswith("repo:")

    @pytest.mark.asyncio
    async def test_dedup_cache_set(self):
        """Test that deduplication cache is set."""
        from kubani.framework.temporal.memory import store_repo_activity

        mock_client = MagicMock()
        mock_memory = AsyncMock()
        mock_memory.store_knowledge.return_value = {"knowledge_id": "repo:test"}
        mock_memory.cache_set.return_value = {"success": True}
        mock_client.memory = mock_memory

        with patch(
            "kubani.framework.temporal.memory._get_memory_client",
            return_value=mock_client,
        ):
            await store_repo_activity(
                repo_url="https://github.com/user/repo",
                name="repo",
                description="Test repo",
                stars=100,
                language="Python",
                topics=["test"],
                ttl_days=14,
            )

        # Verify cache_set was called for deduplication
        mock_memory.cache_set.assert_called_once()
        call_kwargs = mock_memory.cache_set.call_args[1]
        assert call_kwargs["key"].startswith("repo:dedup:")
        assert call_kwargs["ttl_seconds"] == 14 * 86400


class TestCheckRepoExistsActivity:
    """Tests for check_repo_exists_activity."""

    @pytest.mark.asyncio
    async def test_returns_exists_true_when_cached(self):
        """Test that existing repo returns exists=True."""
        from kubani.framework.temporal.memory import check_repo_exists_activity

        mock_client = MagicMock()
        mock_memory = AsyncMock()
        mock_memory.cache_get.return_value = {"found": True, "value": {"url": "test"}}
        mock_client.memory = mock_memory

        with patch(
            "kubani.framework.temporal.memory._get_memory_client",
            return_value=mock_client,
        ):
            result = await check_repo_exists_activity("https://github.com/user/repo")

        assert result["exists"] is True

    @pytest.mark.asyncio
    async def test_returns_exists_false_when_not_cached(self):
        """Test that non-existing repo returns exists=False."""
        from kubani.framework.temporal.memory import check_repo_exists_activity

        mock_client = MagicMock()
        mock_memory = AsyncMock()
        mock_memory.cache_get.return_value = {"found": False}
        mock_client.memory = mock_memory

        with patch(
            "kubani.framework.temporal.memory._get_memory_client",
            return_value=mock_client,
        ):
            result = await check_repo_exists_activity("https://github.com/user/new-repo")

        assert result["exists"] is False


class TestNewsCollectionWorkflowRepoStorage:
    """Tests for repo storage in NewsCollectionWorkflow."""

    def test_store_repos_method_exists(self):
        """Test that _store_repos method exists."""
        from kubani.syndicates.news_digest.workflows.collection import NewsCollectionWorkflow

        workflow = NewsCollectionWorkflow()
        assert hasattr(workflow, "_store_repos")

    def test_repos_stored_count_in_result(self):
        """Test that CollectionResult has repos_stored field."""
        from kubani.syndicates.news_digest.workflows.collection import CollectionResult

        result = CollectionResult()
        assert hasattr(result, "repos_stored")
