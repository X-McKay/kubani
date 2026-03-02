"""Tests for NewsDigestWorkflow (section-based composition).

These tests verify the workflow logic by testing initialization, result
building, document grouping, pure section-preparation functions, prompt
building, fallback digest generation, and query methods in isolation.
"""

from kubani.syndicates.news_digest.workflows.digest import (
    MAX_ARTICLES,
    MAX_PAPERS,
    MAX_REPOS,
    DigestInput,
    DigestResult,
    NewsDigestWorkflow,
    build_section_prompt,
    build_synthesis_prompt,
    prepare_articles_context,
    prepare_papers_context,
    prepare_repos_context,
)

# =============================================================================
# Input / Output Dataclasses
# =============================================================================


class TestDigestInput:
    """Test DigestInput dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        input = DigestInput()
        assert input.digest_type == "scheduled"
        assert input.lookback_hours == 12
        assert input.notify_channel == "ai-news"
        assert input.min_importance == 3
        assert input.correlation_id is None

    def test_custom_values(self):
        """Should accept custom values."""
        input = DigestInput(
            digest_type="morning",
            lookback_hours=24,
            notify_channel="custom-channel",
            min_importance=5,
            correlation_id="test-123",
        )
        assert input.digest_type == "morning"
        assert input.lookback_hours == 24
        assert input.notify_channel == "custom-channel"
        assert input.min_importance == 5


class TestDigestResult:
    """Test DigestResult dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        result = DigestResult()
        assert result.articles_included == 0
        assert result.papers_included == 0
        assert result.repos_included == 0
        assert result.total_documents == 0
        assert result.sections_generated == 0
        assert result.message_id is None
        assert result.success is True
        assert result.error is None

    def test_custom_values(self):
        """Should accept custom values."""
        result = DigestResult(
            articles_included=10,
            papers_included=3,
            repos_included=2,
            total_documents=15,
            sections_generated=3,
            message_id="msg-123",
        )
        assert result.articles_included == 10
        assert result.total_documents == 15
        assert result.sections_generated == 3
        assert result.message_id == "msg-123"


# =============================================================================
# Workflow Init and Result Building
# =============================================================================


class TestNewsDigestWorkflowInit:
    """Test NewsDigestWorkflow initialization."""

    def test_initializes(self):
        """Workflow should initialize with default state."""
        wf = NewsDigestWorkflow()
        assert wf._result is not None
        assert wf._result.success is True
        assert wf._documents == []

    def test_build_result(self):
        """_build_result should return a complete dictionary."""
        wf = NewsDigestWorkflow()
        wf._result.articles_included = 10
        wf._result.papers_included = 3
        wf._result.repos_included = 2
        wf._result.total_documents = 15
        wf._result.sections_generated = 3
        wf._result.message_id = "msg-123"

        result = wf._build_result()

        assert isinstance(result, dict)
        assert result["articles_included"] == 10
        assert result["papers_included"] == 3
        assert result["repos_included"] == 2
        assert result["total_documents"] == 15
        assert result["sections_generated"] == 3
        assert result["message_id"] == "msg-123"
        assert result["success"] is True

    def test_build_result_includes_all_fields(self):
        """_build_result should include all expected fields."""
        wf = NewsDigestWorkflow()
        result = wf._build_result()

        expected_keys = {
            "articles_included",
            "papers_included",
            "repos_included",
            "total_documents",
            "sections_generated",
            "message_id",
            "success",
            "error",
        }
        assert set(result.keys()) == expected_keys


# =============================================================================
# Document Grouping
# =============================================================================


class TestNewsDigestWorkflowGrouping:
    """Test document grouping logic."""

    def test_group_documents(self, sample_analyzed_documents):
        """Should group documents by source type."""
        wf = NewsDigestWorkflow()
        grouped = wf._group_documents(sample_analyzed_documents)

        assert len(grouped["rss"]) == 1
        assert len(grouped["arxiv"]) == 1
        assert len(grouped["github"]) == 1

    def test_group_updates_result_counts(self, sample_analyzed_documents):
        """Grouping should update the result counters."""
        wf = NewsDigestWorkflow()
        wf._group_documents(sample_analyzed_documents)

        assert wf._result.articles_included == 1
        assert wf._result.papers_included == 1
        assert wf._result.repos_included == 1
        assert wf._result.total_documents == 3

    def test_group_empty_documents(self):
        """Should handle empty document list."""
        wf = NewsDigestWorkflow()
        grouped = wf._group_documents([])

        assert grouped == {"rss": [], "arxiv": [], "github": []}
        assert wf._result.total_documents == 0

    def test_group_unknown_source_defaults_to_rss(self):
        """Unknown source types should default to rss."""
        wf = NewsDigestWorkflow()
        docs = [{"source_type": "unknown", "title": "Test"}]
        grouped = wf._group_documents(docs)

        assert len(grouped["rss"]) == 1
        assert wf._result.articles_included == 1

    def test_group_all_same_type(self):
        """Should handle all documents being the same type."""
        wf = NewsDigestWorkflow()
        docs = [{"source_type": "rss", "title": f"Article {i}"} for i in range(5)]
        grouped = wf._group_documents(docs)

        assert len(grouped["rss"]) == 5
        assert len(grouped["arxiv"]) == 0
        assert len(grouped["github"]) == 0


# =============================================================================
# Pure Functions: Section Data Preparation
# =============================================================================


class TestPrepareArticlesContext:
    """Test prepare_articles_context pure function."""

    def test_basic_preparation(self, sample_analyzed_documents):
        """Should extract only the needed fields from articles."""
        articles = [d for d in sample_analyzed_documents if d["source_type"] == "rss"]
        result = prepare_articles_context(articles)

        assert len(result) == 1
        assert result[0]["title"] == "GPT-5 Released with Major Improvements"
        assert result[0]["summary"] == "OpenAI has released GPT-5 with significant improvements."
        assert result[0]["importance_score"] == 9
        # Should not include raw fields like document_id, source_uri, etc.
        assert "document_id" not in result[0]
        assert "source_uri" not in result[0]

    def test_sorted_by_importance(self):
        """Should sort by importance score descending."""
        articles = [
            {
                "title": "Low",
                "summary": "",
                "source_name": "",
                "importance_score": 3,
                "entities": [],
                "topics": [],
            },
            {
                "title": "High",
                "summary": "",
                "source_name": "",
                "importance_score": 9,
                "entities": [],
                "topics": [],
            },
            {
                "title": "Mid",
                "summary": "",
                "source_name": "",
                "importance_score": 6,
                "entities": [],
                "topics": [],
            },
        ]
        result = prepare_articles_context(articles)

        assert result[0]["title"] == "High"
        assert result[1]["title"] == "Mid"
        assert result[2]["title"] == "Low"

    def test_limits_to_max_articles(self):
        """Should limit to MAX_ARTICLES items."""
        articles = [
            {
                "title": f"Article {i}",
                "summary": "",
                "source_name": "",
                "importance_score": i,
                "entities": [],
                "topics": [],
            }
            for i in range(MAX_ARTICLES + 10)
        ]
        result = prepare_articles_context(articles)

        assert len(result) == MAX_ARTICLES

    def test_truncates_entities_and_topics(self):
        """Should truncate entities to 5 and topics to 3."""
        articles = [
            {
                "title": "Test",
                "summary": "",
                "source_name": "",
                "importance_score": 5,
                "entities": [f"entity_{i}" for i in range(20)],
                "topics": [f"topic_{i}" for i in range(10)],
            }
        ]
        result = prepare_articles_context(articles)

        assert len(result[0]["entities"]) == 5
        assert len(result[0]["topics"]) == 3

    def test_empty_input(self):
        """Should return empty list for empty input."""
        assert prepare_articles_context([]) == []


class TestPreparePapersContext:
    """Test prepare_papers_context pure function."""

    def test_basic_preparation(self, sample_analyzed_documents):
        """Should extract only the needed fields from papers."""
        papers = [d for d in sample_analyzed_documents if d["source_type"] == "arxiv"]
        result = prepare_papers_context(papers)

        assert len(result) == 1
        assert result[0]["title"] == "Advances in Transformer Architecture"
        assert "document_id" not in result[0]

    def test_limits_to_max_papers(self):
        """Should limit to MAX_PAPERS items."""
        papers = [
            {"title": f"Paper {i}", "summary": "", "importance_score": i, "topics": []}
            for i in range(MAX_PAPERS + 10)
        ]
        result = prepare_papers_context(papers)

        assert len(result) == MAX_PAPERS

    def test_empty_input(self):
        """Should return empty list for empty input."""
        assert prepare_papers_context([]) == []


class TestPrepareReposContext:
    """Test prepare_repos_context pure function."""

    def test_basic_preparation(self, sample_analyzed_documents):
        """Should extract only the needed fields from repos."""
        repos = [d for d in sample_analyzed_documents if d["source_type"] == "github"]
        result = prepare_repos_context(repos)

        assert len(result) == 1
        assert result[0]["title"] == "ml-toolkit"
        assert "document_id" not in result[0]

    def test_includes_metadata_selectively(self, sample_analyzed_documents):
        """Should include only stars, language, trending_score from metadata."""
        repos = [d for d in sample_analyzed_documents if d["source_type"] == "github"]
        result = prepare_repos_context(repos)

        metadata = result[0]["metadata"]
        assert metadata.get("stars") == 5000
        assert metadata.get("trending_score") == 0.85

    def test_limits_to_max_repos(self):
        """Should limit to MAX_REPOS items."""
        repos = [
            {"title": f"Repo {i}", "summary": "", "importance_score": i, "metadata": {}}
            for i in range(MAX_REPOS + 10)
        ]
        result = prepare_repos_context(repos)

        assert len(result) == MAX_REPOS

    def test_empty_input(self):
        """Should return empty list for empty input."""
        assert prepare_repos_context([]) == []


# =============================================================================
# Pure Functions: Prompt Building
# =============================================================================


class TestBuildSectionPrompt:
    """Test build_section_prompt pure function."""

    def test_includes_section_name(self):
        """Prompt should include the section name."""
        prompt = build_section_prompt("Top Stories", "Summarize news.", [{"title": "Test"}])
        assert "Top Stories" in prompt

    def test_includes_instructions(self):
        """Prompt should include the section instructions."""
        prompt = build_section_prompt("Top Stories", "Focus on AI news.", [{"title": "Test"}])
        assert "Focus on AI news." in prompt

    def test_includes_item_count(self):
        """Prompt should include the number of items."""
        items = [{"title": f"Item {i}"} for i in range(3)]
        prompt = build_section_prompt("Top Stories", "Instructions.", items)
        assert "3 items" in prompt

    def test_includes_json_data(self):
        """Prompt should include the serialized item data."""
        items = [{"title": "GPT-5 Released"}]
        prompt = build_section_prompt("Top Stories", "Instructions.", items)
        assert "GPT-5 Released" in prompt

    def test_includes_formatting_rules(self):
        """Prompt should include formatting rules."""
        prompt = build_section_prompt("Top Stories", "Instructions.", [])
        assert "Discord" in prompt
        assert "no JSON" in prompt.lower() or "no code fences" in prompt.lower()


class TestBuildSynthesisPrompt:
    """Test build_synthesis_prompt pure function."""

    def test_includes_all_sections(self):
        """Prompt should include all provided sections."""
        sections = {
            "Top Stories": "Article about GPT-5.",
            "Research Spotlight": "Paper about transformers.",
        }
        prompt = build_synthesis_prompt(sections, "morning", 12)

        assert "Top Stories" in prompt
        assert "Article about GPT-5." in prompt
        assert "Research Spotlight" in prompt
        assert "Paper about transformers." in prompt

    def test_includes_digest_metadata(self):
        """Prompt should include digest type and period."""
        prompt = build_synthesis_prompt({}, "evening", 24)
        assert "evening" in prompt
        assert "24" in prompt

    def test_skips_empty_sections(self):
        """Empty sections should not appear in the prompt."""
        sections = {
            "Top Stories": "Content here.",
            "Research Spotlight": "",
            "Tool Spotlight": "",
        }
        prompt = build_synthesis_prompt(sections, "scheduled", 12)

        assert "Top Stories" in prompt
        assert "Research Spotlight" not in prompt
        assert "Tool Spotlight" not in prompt

    def test_instructs_executive_summary(self):
        """Prompt should instruct the LLM to write an Executive Summary."""
        prompt = build_synthesis_prompt({"Top Stories": "Content."}, "scheduled", 12)
        assert "Executive Summary" in prompt


# =============================================================================
# Fallback Digest
# =============================================================================


class TestFallbackDigest:
    """Test the _fallback_digest method."""

    def test_includes_title(self):
        """Fallback should include the digest title."""
        wf = NewsDigestWorkflow()
        wf._result.total_documents = 5
        wf._result.sections_generated = 2
        input = DigestInput(digest_type="morning", lookback_hours=12)

        digest = wf._fallback_digest({"Top Stories": "Content."}, input)

        assert "# AI News Digest" in digest

    def test_includes_sections(self):
        """Fallback should include all non-empty sections."""
        wf = NewsDigestWorkflow()
        wf._result.total_documents = 5
        wf._result.sections_generated = 2
        input = DigestInput()

        sections = {
            "Top Stories": "Article content.",
            "Research Spotlight": "Paper content.",
        }
        digest = wf._fallback_digest(sections, input)

        assert "## Top Stories" in digest
        assert "Article content." in digest
        assert "## Research Spotlight" in digest
        assert "Paper content." in digest

    def test_skips_empty_sections(self):
        """Fallback should skip sections with empty content."""
        wf = NewsDigestWorkflow()
        wf._result.total_documents = 5
        wf._result.sections_generated = 1
        input = DigestInput()

        sections = {
            "Top Stories": "Content.",
            "Research Spotlight": "",
        }
        digest = wf._fallback_digest(sections, input)

        assert "## Top Stories" in digest
        assert "## Research Spotlight" not in digest

    def test_includes_footer(self):
        """Fallback should include a footer with stats."""
        wf = NewsDigestWorkflow()
        wf._result.total_documents = 10
        wf._result.sections_generated = 3
        input = DigestInput()

        digest = wf._fallback_digest({"Top Stories": "Content."}, input)

        assert "10 documents" in digest
        assert "3 sections" in digest


# =============================================================================
# Queries
# =============================================================================


class TestNewsDigestWorkflowQueries:
    """Test workflow queries."""

    def test_get_digest_stats(self):
        """get_digest_stats should return current statistics."""
        wf = NewsDigestWorkflow()
        wf._result.articles_included = 10
        wf._result.papers_included = 3
        wf._result.repos_included = 2
        wf._result.total_documents = 15
        wf._result.sections_generated = 3

        stats = wf.get_digest_stats()

        assert stats["articles_included"] == 10
        assert stats["papers_included"] == 3
        assert stats["repos_included"] == 2
        assert stats["total_documents"] == 15
        assert stats["sections_generated"] == 3

    def test_get_top_documents_empty(self):
        """get_top_documents should return empty list when no documents."""
        wf = NewsDigestWorkflow()
        top = wf.get_top_documents()
        assert top == []

    def test_get_top_documents_sorted(self, sample_analyzed_documents):
        """get_top_documents should return documents sorted by importance."""
        wf = NewsDigestWorkflow()
        wf._documents = sample_analyzed_documents

        top = wf.get_top_documents()

        assert len(top) == 3
        assert top[0]["importance_score"] == 9  # Highest first
        assert top[1]["importance_score"] == 7
        assert top[2]["importance_score"] == 6

    def test_get_top_documents_limited_to_10(self):
        """get_top_documents should return at most 10 documents."""
        wf = NewsDigestWorkflow()
        wf._documents = [{"title": f"Doc {i}", "importance_score": i} for i in range(20)]

        top = wf.get_top_documents()

        assert len(top) == 10
        assert top[0]["importance_score"] == 19  # Highest first


# =============================================================================
# strip_think_tags Utility
# =============================================================================


from kubani.framework.temporal.activities import strip_think_tags


class TestStripThinkTags:
    """Test strip_think_tags utility."""

    def test_strips_think_block_at_start(self):
        text = "<think>\nLet me analyze this.\n</think>\n\nThe result is here."
        assert strip_think_tags(text) == "The result is here."

    def test_strips_think_block_in_middle(self):
        text = "Before.\n<think>reasoning</think>\nAfter."
        assert strip_think_tags(text) == "Before.\nAfter."

    def test_strips_multiple_think_blocks(self):
        text = "<think>first</think>Hello<think>second</think>World"
        assert strip_think_tags(text) == "HelloWorld"

    def test_no_think_tags_unchanged(self):
        text = "Normal text without think tags."
        assert strip_think_tags(text) == "Normal text without think tags."

    def test_empty_string(self):
        assert strip_think_tags("") == ""

    def test_multiline_think_content(self):
        text = "<think>\nLine 1\nLine 2\nLine 3\n</think>\n\nActual output."
        assert strip_think_tags(text) == "Actual output."
