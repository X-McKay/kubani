"""Tests for AnalyzeDocumentWorkflow.

These tests verify the workflow logic by testing initialization, result
building, and query methods in isolation.
"""

from kubani.syndicates.news_digest.workflows.analyze import (
    AnalyzeDocumentWorkflow,
    AnalyzeInput,
    AnalyzeResult,
)


class TestAnalyzeInput:
    """Test AnalyzeInput dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        input = AnalyzeInput()
        assert input.documents is None
        assert input.max_documents == 50
        assert input.correlation_id is None

    def test_custom_values(self):
        """Should accept custom values."""
        docs = [{"document_id": "1"}]
        input = AnalyzeInput(
            documents=docs,
            max_documents=10,
            correlation_id="test-123",
        )
        assert input.documents == docs
        assert input.max_documents == 10

    def test_empty_documents_list(self):
        """Should accept an empty documents list."""
        input = AnalyzeInput(documents=[])
        assert input.documents == []


class TestAnalyzeResult:
    """Test AnalyzeResult dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        result = AnalyzeResult()
        assert result.documents_received == 0
        assert result.documents_analyzed == 0
        assert result.documents_stored == 0
        assert result.relationships_created == 0
        assert result.success is True
        assert result.error is None

    def test_custom_values(self):
        """Should accept custom values."""
        result = AnalyzeResult(
            documents_received=10,
            documents_analyzed=8,
            documents_stored=8,
            relationships_created=24,
        )
        assert result.documents_received == 10
        assert result.relationships_created == 24


class TestAnalyzeDocumentWorkflowInit:
    """Test AnalyzeDocumentWorkflow initialization."""

    def test_initializes(self):
        """Workflow should initialize with default state."""
        wf = AnalyzeDocumentWorkflow()
        assert wf._result is not None
        assert wf._result.success is True
        assert wf._result.documents_received == 0

    def test_build_result(self):
        """_build_result should return a complete dictionary."""
        wf = AnalyzeDocumentWorkflow()
        wf._result.documents_received = 10
        wf._result.documents_analyzed = 8
        wf._result.documents_stored = 8
        wf._result.relationships_created = 24

        result = wf._build_result()

        assert isinstance(result, dict)
        assert result["documents_received"] == 10
        assert result["documents_analyzed"] == 8
        assert result["documents_stored"] == 8
        assert result["relationships_created"] == 24
        assert result["success"] is True
        assert result["error"] is None

    def test_build_result_includes_all_fields(self):
        """_build_result should include all expected fields."""
        wf = AnalyzeDocumentWorkflow()
        result = wf._build_result()

        expected_keys = {
            "documents_received",
            "documents_analyzed",
            "documents_stored",
            "relationships_created",
            "success",
            "error",
        }
        assert set(result.keys()) == expected_keys


class TestAnalyzeDocumentWorkflowQueries:
    """Test workflow queries."""

    def test_get_analysis_stats(self):
        """get_analysis_stats should return current statistics."""
        wf = AnalyzeDocumentWorkflow()
        wf._result.documents_received = 10
        wf._result.documents_analyzed = 8
        wf._result.documents_stored = 7
        wf._result.relationships_created = 21

        stats = wf.get_analysis_stats()

        assert stats["documents_received"] == 10
        assert stats["documents_analyzed"] == 8
        assert stats["documents_stored"] == 7
        assert stats["relationships_created"] == 21
