"""Tests for core.py - pure functions with no I/O dependencies.

These tests run instantly without any mocking required.
"""

import pytest

from kubani.workflows.skill_auto.core import (
    clean_llm_output,
    compute_score,
    create_no_overlap_result,
    detect_regression,
    ensure_test_cases_structure,
    extract_json,
    format_skill_content,
    infer_skill_name,
    is_plateau,
    parse_overlap_response,
    parse_skill_frontmatter,
    validate_test_case_yaml,
)
from kubani.workflows.skill_auto.models import EvalMetrics


class TestExtractJson:
    """Tests for extract_json function."""

    def test_simple_object(self):
        """Extract simple JSON object."""
        text = '{"key": "value"}'
        assert extract_json(text) == {"key": "value"}

    def test_nested_braces(self):
        """Extract JSON with nested objects."""
        text = '{"outer": {"inner": {"deep": 1}}}'
        result = extract_json(text)
        assert result == {"outer": {"inner": {"deep": 1}}}

    def test_deeply_nested(self):
        """Extract deeply nested JSON."""
        text = '{"a": {"b": {"c": {"d": {"e": 5}}}}}'
        result = extract_json(text)
        assert result["a"]["b"]["c"]["d"]["e"] == 5

    def test_with_surrounding_text_before(self):
        """Extract JSON with text before it."""
        text = 'Here is the result: {"name": "test"}'
        assert extract_json(text) == {"name": "test"}

    def test_with_surrounding_text_after(self):
        """Extract JSON with text after it."""
        text = '{"name": "test"} and more text here'
        assert extract_json(text) == {"name": "test"}

    def test_with_surrounding_text_both(self):
        """Extract JSON with text before and after."""
        text = 'Prefix text {"name": "test"} suffix text'
        assert extract_json(text) == {"name": "test"}

    def test_markdown_code_block_with_json_tag(self):
        """Extract JSON from markdown code block with json tag."""
        text = '```json\n{"key": "value"}\n```'
        assert extract_json(text) == {"key": "value"}

    def test_markdown_code_block_without_tag(self):
        """Extract JSON from markdown code block without language tag."""
        text = '```\n{"key": "value"}\n```'
        assert extract_json(text) == {"key": "value"}

    def test_multiple_objects_takes_first(self):
        """When multiple JSON objects present, take the first."""
        text = '{"first": 1} {"second": 2}'
        assert extract_json(text) == {"first": 1}

    def test_multiple_objects_with_text(self):
        """Multiple objects with surrounding text."""
        text = 'Result 1: {"a": 1} and Result 2: {"b": 2}'
        assert extract_json(text) == {"a": 1}

    def test_json_with_arrays(self):
        """Extract JSON containing arrays."""
        text = '{"items": [1, 2, 3], "nested": [{"a": 1}]}'
        result = extract_json(text)
        assert result["items"] == [1, 2, 3]
        assert result["nested"] == [{"a": 1}]

    def test_json_with_strings_containing_braces(self):
        """Handle strings that contain brace characters."""
        text = '{"code": "function() { return {}; }"}'
        result = extract_json(text)
        assert result["code"] == "function() { return {}; }"

    def test_json_with_escaped_quotes(self):
        """Handle escaped quotes in strings."""
        text = '{"message": "He said \\"hello\\""}'
        result = extract_json(text)
        assert result["message"] == 'He said "hello"'

    def test_json_with_newlines_in_strings(self):
        """Handle newlines in JSON strings."""
        text = '{"text": "line1\\nline2"}'
        result = extract_json(text)
        assert result["text"] == "line1\nline2"

    def test_no_json_raises_error(self):
        """Raise ValueError when no JSON found."""
        with pytest.raises(ValueError, match="No JSON object found"):
            extract_json("no json here at all")

    def test_unbalanced_braces_raises_error(self):
        """Raise ValueError for unbalanced braces."""
        with pytest.raises(ValueError, match="Unbalanced braces"):
            extract_json('{"key": "value"')

    def test_invalid_json_raises_error(self):
        """Raise ValueError for invalid JSON syntax."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            extract_json("{key: value}")  # Missing quotes

    def test_python_dict_syntax_single_quotes(self):
        """Handle Python dict syntax with single quotes (common LLM output)."""
        text = "{'name': 'test-skill', 'description': 'A skill'}"
        result = extract_json(text)
        assert result["name"] == "test-skill"
        assert result["description"] == "A skill"

    def test_python_dict_with_nested_structures(self):
        """Handle nested Python dict syntax."""
        text = "{'inputs': {'param': {'type': 'string', 'required': True}}}"
        result = extract_json(text)
        assert result["inputs"]["param"]["type"] == "string"
        assert result["inputs"]["param"]["required"] is True

    def test_empty_object(self):
        """Extract empty JSON object."""
        assert extract_json("{}") == {}

    def test_whitespace_in_json(self):
        """Handle whitespace in JSON."""
        text = """
        {
            "key": "value",
            "number": 42
        }
        """
        result = extract_json(text)
        assert result == {"key": "value", "number": 42}

    def test_real_world_llm_response(self):
        """Test with realistic LLM response format."""
        text = """I'll analyze the skill and provide the structure.

```json
{
    "name": "diagnose-oom",
    "description": "Diagnose OOMKilled pods",
    "inputs": {"pod_name": {"type": "string"}}
}
```

This structure covers the main use cases."""
        result = extract_json(text)
        assert result["name"] == "diagnose-oom"
        assert result["inputs"]["pod_name"]["type"] == "string"


class TestCleanLlmOutput:
    """Tests for clean_llm_output function."""

    def test_removes_think_tags(self):
        """Remove <think> tags from output."""
        text = "<think>Let me think...</think>The answer is 42"
        assert clean_llm_output(text) == "The answer is 42"

    def test_removes_code_block_markers(self):
        """Remove code block markers."""
        text = "```yaml\nkey: value\n```"
        assert clean_llm_output(text) == "key: value"

    def test_strips_whitespace(self):
        """Strip leading/trailing whitespace."""
        text = "  \n  content  \n  "
        assert clean_llm_output(text) == "content"

    def test_handles_plain_text(self):
        """Pass through plain text unchanged."""
        text = "Just plain text"
        assert clean_llm_output(text) == "Just plain text"


class TestComputeScore:
    """Tests for compute_score function."""

    def test_perfect_accuracy_fast_latency(self, perfect_metrics):
        """Perfect accuracy and fast latency gives score close to 1.0."""
        score = compute_score(perfect_metrics)
        assert score == pytest.approx(1.0, rel=0.01)

    def test_zero_accuracy(self):
        """Zero accuracy gives only latency component."""
        metrics = EvalMetrics(
            accuracy=0.0,
            latency_ms=1000.0,
            tests_passed=0,
            tests_total=5,
            critic_confidence=0.0,
        )
        score = compute_score(metrics)
        # Only latency component: 0.3 * (3000/1000) = 0.3 * 1.0 = 0.3 (capped)
        assert score == pytest.approx(0.3, rel=0.01)

    def test_slow_latency(self, poor_metrics):
        """Slow latency reduces score."""
        score = compute_score(poor_metrics)
        # accuracy: 0.2 * 0.7 = 0.14
        # latency: 3000/5000 = 0.6 * 0.3 = 0.18
        # total: 0.32
        assert score == pytest.approx(0.32, rel=0.01)

    def test_score_between_zero_and_one(self, sample_metrics):
        """Score is always between 0 and 1."""
        score = compute_score(sample_metrics)
        assert 0.0 <= score <= 1.0

    def test_very_fast_latency_capped(self):
        """Very fast latency is capped at baseline."""
        metrics = EvalMetrics(
            accuracy=0.8,
            latency_ms=10.0,  # Very fast
            tests_passed=4,
            tests_total=5,
            critic_confidence=0.8,
        )
        score = compute_score(metrics)
        # accuracy: 0.8 * 0.7 = 0.56
        # latency: min(3000/10, 1.0) * 0.3 = 1.0 * 0.3 = 0.3
        # total: 0.86
        assert score == pytest.approx(0.86, rel=0.01)


class TestIsPlateau:
    """Tests for is_plateau function."""

    def test_not_enough_history(self, iteration_history):
        """Not enough history returns False."""
        short_history = iteration_history[:1]
        assert is_plateau(short_history) is False

    def test_improving_not_plateau(self, iteration_history):
        """Clear improvement is not a plateau."""
        assert is_plateau(iteration_history) is False

    def test_plateau_detected(self, plateau_history):
        """Detect plateau when improvement is minimal."""
        assert is_plateau(plateau_history) is True

    def test_empty_history(self):
        """Empty history is not a plateau."""
        assert is_plateau([]) is False

    def test_custom_threshold(self, plateau_history):
        """Custom threshold changes detection."""
        # With very low threshold, even small improvements count
        assert is_plateau(plateau_history, threshold=0.001) is False


class TestDetectRegression:
    """Tests for detect_regression function."""

    def test_no_history(self):
        """No history means no regression."""
        result = detect_regression([], 0.5)
        assert result["is_regression"] is False
        assert result["best_score"] == 0.5

    def test_improvement_not_regression(self, iteration_history):
        """Higher score than history is not regression."""
        result = detect_regression(iteration_history, 0.9)
        assert result["is_regression"] is False

    def test_small_drop_not_regression(self, iteration_history):
        """Small drop (< 20%) is not regression."""
        # Best score in history is 0.75
        result = detect_regression(iteration_history, 0.65)  # ~13% drop
        assert result["is_regression"] is False

    def test_large_drop_is_regression(self, iteration_history):
        """Large drop (> 20%) is regression."""
        # Best score in history is 0.75
        result = detect_regression(iteration_history, 0.5)  # ~33% drop
        assert result["is_regression"] is True
        assert result["drop_percentage"] == pytest.approx(33.3, rel=0.1)
        assert result["best_score"] == 0.75
        assert result["best_iteration"] == 3

    def test_custom_threshold(self, iteration_history):
        """Custom threshold changes detection."""
        # 13% drop with 10% threshold should be regression
        result = detect_regression(iteration_history, 0.65, threshold=0.10)
        assert result["is_regression"] is True


class TestInferSkillName:
    """Tests for infer_skill_name function."""

    def test_simple_description(self):
        """Infer name from simple description."""
        assert infer_skill_name("diagnose OOM killed pods") == "diagnose-oom-killed-pods"

    def test_filters_non_alphanumeric(self):
        """Filter out words containing non-alphanumeric characters."""
        # Words with punctuation attached (like "the,") are filtered out
        assert infer_skill_name("fix the broken code") == "fix-the-broken-code"
        # Words with punctuation are excluded entirely
        assert infer_skill_name("fix broken!") == "fix"

    def test_truncates_long_names(self):
        """Truncate names longer than 30 chars."""
        name = infer_skill_name("this is a very long description")
        assert len(name) <= 30

    def test_lowercase(self):
        """Convert to lowercase."""
        assert infer_skill_name("Diagnose OOM") == "diagnose-oom"

    def test_takes_first_four_words(self):
        """Only take first four words."""
        name = infer_skill_name("one two three four five six")
        assert name == "one-two-three-four"


class TestParseSkillFrontmatter:
    """Tests for parse_skill_frontmatter function."""

    def test_valid_frontmatter(self):
        """Parse valid YAML frontmatter."""
        content = """---
name: my-skill
version: 1.0.0
triggers:
  - event_a
  - event_b
---

# My Skill

Content here.
"""
        result = parse_skill_frontmatter(content)
        assert result["name"] == "my-skill"
        assert result["version"] == "1.0.0"
        assert result["triggers"] == ["event_a", "event_b"]

    def test_no_frontmatter(self):
        """Return empty dict when no frontmatter."""
        content = "# My Skill\n\nNo frontmatter here."
        assert parse_skill_frontmatter(content) == {}

    def test_invalid_yaml(self):
        """Return empty dict for invalid YAML."""
        content = """---
invalid: yaml: content
---
"""
        assert parse_skill_frontmatter(content) == {}

    def test_incomplete_frontmatter(self):
        """Return empty dict for incomplete frontmatter."""
        content = """---
name: incomplete
"""
        assert parse_skill_frontmatter(content) == {}


class TestFormatSkillContent:
    """Tests for format_skill_content function."""

    def test_basic_formatting(self, sample_skill_spec):
        """Format basic skill spec into SKILL.md."""
        content = format_skill_content(sample_skill_spec)

        # Check frontmatter
        assert "name: diagnose-oom" in content
        assert "version: 0.1.0" in content
        assert "category: _development" in content

        # Check title
        assert "# Diagnose Oom" in content

        # Check sections
        assert "## Inputs" in content
        assert "## Outputs" in content
        assert "## Steps" in content
        assert "## Error Handling" in content

        # Check content
        assert "pod_name" in content
        assert "Check pod events" in content

    def test_empty_spec(self):
        """Handle empty spec gracefully."""
        content = format_skill_content({"name": "empty-skill"})
        assert "name: empty-skill" in content
        assert "## Steps" in content


class TestValidateTestCaseYaml:
    """Tests for validate_test_case_yaml function."""

    def test_valid_yaml(self, valid_test_cases_yaml):
        """Accept valid test cases YAML."""
        is_valid, error = validate_test_case_yaml(valid_test_cases_yaml)
        assert is_valid is True
        assert error is None

    def test_missing_test_cases_key(self):
        """Reject YAML without test_cases key."""
        yaml_str = "other_key: value"
        is_valid, error = validate_test_case_yaml(yaml_str)
        assert is_valid is False
        assert "test_cases" in error

    def test_missing_name_field(self, invalid_test_cases_yaml):
        """Reject test case without name field."""
        is_valid, error = validate_test_case_yaml(invalid_test_cases_yaml)
        assert is_valid is False
        assert "name" in error

    def test_invalid_yaml_syntax(self):
        """Reject invalid YAML syntax."""
        yaml_str = "invalid: yaml: content:"
        is_valid, error = validate_test_case_yaml(yaml_str)
        assert is_valid is False
        assert "syntax" in error.lower()

    def test_empty_yaml(self):
        """Reject empty YAML."""
        is_valid, error = validate_test_case_yaml("")
        assert is_valid is False

    def test_test_cases_not_list(self):
        """Reject when test_cases is not a list."""
        yaml_str = "test_cases: not_a_list"
        is_valid, error = validate_test_case_yaml(yaml_str)
        assert is_valid is False
        assert "list" in error


class TestEnsureTestCasesStructure:
    """Tests for ensure_test_cases_structure function."""

    def test_wraps_list_in_test_cases(self):
        """Wrap bare list in test_cases key."""
        yaml_str = "- name: test1\n- name: test2"
        result = ensure_test_cases_structure(yaml_str)
        assert "test_cases:" in result

    def test_preserves_existing_structure(self, valid_test_cases_yaml):
        """Preserve YAML that already has test_cases."""
        result = ensure_test_cases_structure(valid_test_cases_yaml)
        assert "test_cases:" in result

    def test_handles_invalid_yaml(self):
        """Return original for invalid YAML."""
        yaml_str = "invalid yaml: :"
        result = ensure_test_cases_structure(yaml_str)
        assert result == yaml_str


class TestOverlapHelpers:
    """Tests for overlap detection helpers."""

    def test_create_no_overlap_result(self):
        """Create result indicating no overlap."""
        result = create_no_overlap_result("Test reason")
        assert result.has_overlap is False
        assert result.confidence == 1.0
        assert result.overlapping_skills == []
        assert result.reasoning == "Test reason"
        assert result.recommendation == "proceed"

    def test_parse_overlap_response_valid(self):
        """Parse valid overlap response."""
        response = """{
            "has_overlap": true,
            "confidence": 0.85,
            "overlapping_skills": ["skill-a", "skill-b"],
            "reasoning": "Both handle similar tasks",
            "recommendation": "merge"
        }"""
        result = parse_overlap_response(response)
        assert result.has_overlap is True
        assert result.confidence == 0.85
        assert result.overlapping_skills == ["skill-a", "skill-b"]
        assert result.recommendation == "merge"

    def test_parse_overlap_response_invalid(self):
        """Handle invalid overlap response gracefully."""
        response = "Not valid JSON at all"
        result = parse_overlap_response(response)
        assert result.has_overlap is False
        assert result.confidence == 0.0
        assert "Failed" in result.reasoning
