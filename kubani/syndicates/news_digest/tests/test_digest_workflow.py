"""Tests for NewsDigestWorkflow (section-based composition).

These tests verify the workflow logic by testing initialization, result
building, topic clustering, pure section-preparation functions, prompt
building, digest composition, and query methods in isolation.
"""

from kubani.framework.temporal.activities import strip_think_tags
from kubani.syndicates.news_digest.activities import _split_discord_message
from kubani.syndicates.news_digest.workflows.digest import (
    MAX_ARTICLES,
    DigestInput,
    DigestResult,
    NewsDigestWorkflow,
    _section_instructions,
    build_section_prompt,
    cluster_by_topics,
    compose_digest,
    prepare_articles_context,
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
# Topic Clustering Integration (replaces old source-type grouping)
# =============================================================================


class TestSectionInstructions:
    """Test _section_instructions helper."""

    def test_includes_section_name(self):
        result = _section_instructions("AI Agents")
        assert "AI Agents" in result

    def test_asks_for_significance(self):
        result = _section_instructions("Security")
        assert "why it matters" in result

    def test_asks_for_connections(self):
        result = _section_instructions("Tools")
        assert "connections" in result.lower()

    def test_asks_for_depth(self):
        """Instructions should request 2-4 sentences, not 1-2."""
        result = _section_instructions("AI Agents")
        assert "2-4 sentences" in result

    def test_asks_for_implications(self):
        """Instructions should ask for broader implications."""
        result = _section_instructions("AI Agents")
        assert "implications" in result.lower()


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
        assert result[0]["url"] == "https://example.com/article1"
        # Should not include raw fields like document_id, source_uri, etc.
        assert "document_id" not in result[0]
        assert "source_uri" not in result[0]

    def test_url_is_empty_string_when_missing(self):
        """url field should be empty string when source_uri is absent."""
        articles = [
            {
                "title": "Test",
                "summary": "",
                "source_name": "",
                "importance_score": 5,
                "entities": [],
                "topics": [],
            }
        ]
        result = prepare_articles_context(articles)
        assert result[0]["url"] == ""

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
        assert "no reasoning" in prompt.lower()

    def test_asks_for_insights(self):
        """Prompt should ask for why-it-matters insights."""
        prompt = build_section_prompt("Top Stories", "Instructions.", [])
        assert "why it matters" in prompt

    def test_asks_for_connections(self):
        """Prompt should encourage noting connections between stories."""
        prompt = build_section_prompt("Top Stories", "Instructions.", [])
        assert "connections" in prompt.lower()

    def test_asks_for_source_links(self):
        """Prompt should instruct LLM to include markdown source links."""
        prompt = build_section_prompt("Top Stories", "Instructions.", [])
        assert "[Title](url)" in prompt or ("url" in prompt and "**[" in prompt)

    def test_allows_up_to_10_bullets(self):
        """Prompt should allow up to 10 bullets, not cap at 8."""
        prompt = build_section_prompt("Top Stories", "Instructions.", [])
        assert "10" in prompt
        assert "3-8" not in prompt

    def test_asks_for_multi_sentence(self):
        """Prompt should ask for 2-4 sentences per story."""
        prompt = build_section_prompt("Top Stories", "Instructions.", [])
        assert "2-4 sentences" in prompt


class TestComposeDigest:
    """Test compose_digest pure function."""

    def test_includes_title_and_type(self):
        """Digest should include the title with digest type."""
        result = compose_digest({"AI Agents": "Content."}, "daily", 12, 5)
        assert "# AI News Digest" in result
        assert "Daily" in result

    def test_includes_all_sections(self):
        """Digest should include all non-empty sections with headers."""
        sections = {
            "AI Agents": "Agent news content.",
            "Open Source": "OSS content.",
        }
        result = compose_digest(sections, "morning", 12, 10)

        assert "## AI Agents" in result
        assert "Agent news content." in result
        assert "## Open Source" in result
        assert "OSS content." in result

    def test_skips_empty_sections(self):
        """Empty sections should not appear."""
        sections = {
            "AI Agents": "Content.",
            "Security": "",
        }
        result = compose_digest(sections, "daily", 12, 5)

        assert "## AI Agents" in result
        assert "## Security" not in result

    def test_footer_has_stats(self):
        """Footer should show document count, section count, and period."""
        result = compose_digest({"AI Agents": "Content."}, "daily", 12, 15)
        assert "15 sources" in result
        assert "1 topics" in result
        assert "12h" in result

    def test_stays_under_discord_limit_with_small_input(self):
        """A typical digest should be under 2000 chars."""
        sections = {
            "AI Agents": "Short section about agents.",
            "Open Source": "Short section about OSS.",
        }
        result = compose_digest(sections, "daily", 12, 8)
        assert len(result) < 2000


# =============================================================================
# Discord Message Splitting
# =============================================================================


class TestSplitDiscordMessage:
    """Test _split_discord_message helper."""

    def test_short_message_single_chunk(self):
        """Messages under 2000 chars should be a single chunk."""
        chunks = _split_discord_message("Hello world")
        assert len(chunks) == 1
        assert chunks[0] == "Hello world"

    def test_long_message_splits(self):
        """Messages over 2000 chars should be split into chunks."""
        # Create a message with many lines
        lines = [f"Line {i}: " + "x" * 50 for i in range(50)]
        text = "\n".join(lines)
        assert len(text) > 2000

        chunks = _split_discord_message(text)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk) <= 2000

    def test_preserves_all_content(self):
        """All content should be preserved across chunks."""
        lines = [f"Line {i}" for i in range(100)]
        text = "\n".join(lines)
        chunks = _split_discord_message(text)
        rejoined = "\n".join(chunks)
        assert rejoined == text

    def test_empty_message(self):
        """Empty message should return single empty chunk."""
        chunks = _split_discord_message("")
        assert chunks == [""]


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
# Topic-Based Clustering
# =============================================================================


class TestClusterByTopics:
    """Test cluster_by_topics pure function with concrete examples."""

    def test_empty_input(self):
        """Should return empty dict for empty input."""
        assert cluster_by_topics([]) == {}

    def test_two_clear_topic_groups(self):
        """Two docs share 'AI agents', two share 'security' -> 2 clusters."""
        docs = [
            {
                "title": "Agent framework released",
                "topics": ["AI agents", "tools"],
                "importance_score": 8,
            },
            {
                "title": "New agent benchmark",
                "topics": ["AI agents", "benchmarks"],
                "importance_score": 7,
            },
            {"title": "CVE in ML lib", "topics": ["security", "ML"], "importance_score": 6},
            {
                "title": "Supply chain attack",
                "topics": ["security", "open source"],
                "importance_score": 5,
            },
        ]
        clusters = cluster_by_topics(docs)

        # Should have 2 clusters (AI agents and security)
        assert len(clusters) == 2
        # All 4 docs accounted for
        all_titles = {d["title"] for docs_list in clusters.values() for d in docs_list}
        assert all_titles == {
            "Agent framework released",
            "New agent benchmark",
            "CVE in ML lib",
            "Supply chain attack",
        }
        # Each cluster has 2 docs
        for docs_list in clusters.values():
            assert len(docs_list) == 2

    def test_sorted_by_importance_within_cluster(self):
        """Docs within each cluster should be sorted by importance descending."""
        docs = [
            {"title": "Low", "topics": ["AI agents"], "importance_score": 3},
            {"title": "High", "topics": ["AI agents"], "importance_score": 9},
            {"title": "Mid", "topics": ["AI agents"], "importance_score": 6},
        ]
        clusters = cluster_by_topics(docs)

        # Only one topic, so one cluster
        assert len(clusters) == 1
        section = list(clusters.values())[0]
        assert [d["title"] for d in section] == ["High", "Mid", "Low"]

    def test_single_doc_topic_goes_to_catch_all(self):
        """A topic with only 1 document shouldn't get its own section."""
        docs = [
            {"title": "A", "topics": ["AI agents"], "importance_score": 8},
            {"title": "B", "topics": ["AI agents"], "importance_score": 7},
            {"title": "C", "topics": ["rare topic"], "importance_score": 6},
        ]
        clusters = cluster_by_topics(docs)

        # "AI agents" cluster + "Notable Mentions" for the orphan
        assert len(clusters) == 2
        assert "Notable Mentions" in clusters
        assert len(clusters["Notable Mentions"]) == 1
        assert clusters["Notable Mentions"][0]["title"] == "C"

    def test_no_topics_all_to_catch_all(self):
        """Documents without any topics should all go to one catch-all."""
        docs = [
            {"title": "A", "topics": [], "importance_score": 8},
            {"title": "B", "topics": [], "importance_score": 7},
        ]
        clusters = cluster_by_topics(docs)

        assert len(clusters) == 1
        section_name = list(clusters.keys())[0]
        assert len(clusters[section_name]) == 2

    def test_max_four_topic_sections_plus_catch_all(self):
        """Should cap at 4 topic sections; leftovers go to catch-all."""
        # 6 topics with 4 docs each = 24 docs. Only top 4 topics become sections.
        docs = [
            {"title": f"Doc {i}", "topics": [f"topic_{i % 6}"], "importance_score": i}
            for i in range(24)
        ]
        clusters = cluster_by_topics(docs)
        # 4 topic sections + possible 1 catch-all for topics that didn't make the cut
        assert len(clusters) <= 5
        # The 4 non-catch-all sections should be the most common topics
        topic_sections = [k for k in clusters if k != "Notable Mentions"]
        assert len(topic_sections) <= 4

    def test_doc_assigned_to_highest_ranked_topic(self):
        """Doc matching multiple top topics goes to the most common one."""
        docs = [
            # "LLM" appears in 3 docs, "tools" in 2
            {"title": "A", "topics": ["LLM"], "importance_score": 8},
            {"title": "B", "topics": ["LLM", "tools"], "importance_score": 7},
            {"title": "C", "topics": ["LLM"], "importance_score": 6},
            {"title": "D", "topics": ["tools"], "importance_score": 5},
            {"title": "E", "topics": ["tools", "LLM"], "importance_score": 4},
        ]
        clusters = cluster_by_topics(docs)

        # "LLM" is the top topic (3 mentions), "tools" second (2 mentions)
        # Doc B has both ["LLM", "tools"] — should go to LLM (higher-ranked)
        # Doc E has both ["tools", "LLM"] — should also go to LLM (higher-ranked)
        llm_section = clusters.get("Llm", [])
        assert len(llm_section) >= 3  # A, B, C at minimum; E also goes here
        llm_titles = {d["title"] for d in llm_section}
        assert "B" in llm_titles  # B assigned to LLM, not tools

    def test_section_names_are_title_cased(self):
        """Section names should be title-cased versions of the topic."""
        docs = [
            {"title": "A", "topics": ["open source"], "importance_score": 8},
            {"title": "B", "topics": ["open source"], "importance_score": 7},
        ]
        clusters = cluster_by_topics(docs)
        assert "Open Source" in clusters

    def test_single_dominant_topic(self):
        """When all docs share one topic, create one section."""
        docs = [
            {"title": "A", "topics": ["LLM", "tools"], "importance_score": 8},
            {"title": "B", "topics": ["LLM", "security"], "importance_score": 7},
            {"title": "C", "topics": ["LLM"], "importance_score": 6},
        ]
        clusters = cluster_by_topics(docs)
        # All 3 docs match "LLM", should be 1 cluster
        assert len(clusters) == 1
        assert len(list(clusters.values())[0]) == 3


# =============================================================================
# strip_think_tags Utility
# =============================================================================


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
