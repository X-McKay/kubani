"""Tests for utils.py - shared utility functions.

These tests cover LLM output cleaning, SKILL.md parsing, test case validation,
and iteration persistence.
"""

import json

import pytest

from kubani.workflows.skill_auto.utils import (
    clean_llm_output,
    clean_markdown_output,
    clean_yaml_output,
    ensure_test_cases_structure,
    extract_json,
    format_skill_content,
    infer_skill_name,
    load_iteration_history,
    parse_skill_frontmatter,
    save_iteration_result,
    validate_test_case_yaml,
)

# =============================================================================
# Mock FileSystem for iteration persistence tests
# =============================================================================


class MockFileSystem:
    """In-memory filesystem for testing."""

    def __init__(self, files: dict[str, str] | None = None):
        self.files: dict[str, str] = files or {}
        self.dirs: set[str] = set()

    def read(self, path: str) -> str:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def write(self, path: str, content: str) -> None:
        self.files[path] = content

    def exists(self, path: str) -> bool:
        # Check if path is a file
        if path in self.files:
            return True
        # Check if path is in dirs
        if path in self.dirs:
            return True
        # Check if path is an implicit directory (has files under it)
        return any(file_path.startswith(path + "/") for file_path in self.files)

    def mkdir(self, path: str, parents: bool = True) -> None:
        self.dirs.add(path)

    def list_files(self, path: str, pattern: str = "*") -> list[str]:
        import fnmatch
        import os

        results = []
        for p in self.files:
            if p.startswith(path + "/"):
                filename = os.path.basename(p)
                if fnmatch.fnmatch(filename, pattern):
                    results.append(p)
        return results

    def move(self, src: str, dst: str) -> None:
        to_move = [(k, v) for k, v in self.files.items() if k.startswith(src)]
        for old_path, content in to_move:
            new_path = old_path.replace(src, dst, 1)
            self.files[new_path] = content
            del self.files[old_path]

    def copy(self, src: str, dst: str) -> None:
        self.files[dst] = self.files[src]

    def delete(self, path: str) -> None:
        self.files.pop(path, None)

    def list_dir(self, path: str) -> list[str]:
        import os

        return list(
            {
                os.path.basename(p.replace(path + "/", "").split("/")[0])
                for p in self.files
                if p.startswith(path + "/")
            }
        )


# =============================================================================
# JSON Extraction Tests
# =============================================================================


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

    def test_with_surrounding_text_before(self):
        """Extract JSON with text before it."""
        text = 'Here is the result: {"name": "test"}'
        assert extract_json(text) == {"name": "test"}

    def test_with_surrounding_text_after(self):
        """Extract JSON with text after it."""
        text = '{"name": "test"} and more text here'
        assert extract_json(text) == {"name": "test"}

    def test_markdown_code_block_with_json_tag(self):
        """Extract JSON from markdown code block with json tag."""
        text = '```json\n{"key": "value"}\n```'
        assert extract_json(text) == {"key": "value"}

    def test_markdown_code_block_without_tag(self):
        """Extract JSON from markdown code block without language tag."""
        text = '```\n{"key": "value"}\n```'
        assert extract_json(text) == {"key": "value"}

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

    def test_no_json_raises_error(self):
        """Raise ValueError when no JSON found."""
        with pytest.raises(ValueError, match="No JSON object found"):
            extract_json("no json here at all")

    def test_unbalanced_braces_raises_error(self):
        """Raise ValueError for unbalanced braces."""
        with pytest.raises(ValueError, match="Unbalanced braces"):
            extract_json('{"key": "value"')

    def test_python_dict_syntax_single_quotes(self):
        """Handle Python dict syntax with single quotes (common LLM output)."""
        text = "{'name': 'test-skill', 'description': 'A skill'}"
        result = extract_json(text)
        assert result["name"] == "test-skill"

    def test_empty_object(self):
        """Extract empty JSON object."""
        assert extract_json("{}") == {}


# =============================================================================
# LLM Output Cleaning Tests
# =============================================================================


class TestCleanYamlOutput:
    """Tests for clean_yaml_output function."""

    def test_removes_code_blocks(self):
        """Remove ```yaml code blocks."""
        text = "```yaml\nkey: value\n```"
        assert clean_yaml_output(text) == "key: value"

    def test_removes_thinking_tags(self):
        """Remove <think> tags."""
        text = "<think>thinking...</think>\nkey: value"
        assert clean_yaml_output(text) == "key: value"

    def test_handles_plain_yaml(self):
        """Pass through plain YAML unchanged."""
        text = "key: value\nother: data"
        assert clean_yaml_output(text) == "key: value\nother: data"

    def test_strips_whitespace(self):
        """Strip leading/trailing whitespace."""
        text = "  \nkey: value  \n  "
        assert clean_yaml_output(text) == "key: value"


class TestCleanMarkdownOutput:
    """Tests for clean_markdown_output function."""

    def test_removes_markdown_code_block(self):
        """Remove ```markdown code blocks."""
        text = "```markdown\n# Title\nContent\n```"
        assert "# Title" in clean_markdown_output(text)
        assert "```" not in clean_markdown_output(text)

    def test_removes_thinking_tags(self):
        """Remove <think> tags."""
        text = "<think>thinking...</think>\n# Title"
        assert clean_markdown_output(text) == "# Title"

    def test_handles_plain_markdown(self):
        """Pass through plain markdown unchanged."""
        text = "# Title\n\nContent here."
        assert clean_markdown_output(text) == "# Title\n\nContent here."


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


# =============================================================================
# SKILL.md Parsing Tests
# =============================================================================


class TestInferSkillName:
    """Tests for infer_skill_name function."""

    def test_simple_description(self):
        """Infer name from simple description."""
        assert infer_skill_name("diagnose OOM killed pods") == "diagnose-oom-killed-pods"

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


# =============================================================================
# Test Case Validation Tests
# =============================================================================


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


# =============================================================================
# Iteration Persistence Tests
# =============================================================================


class TestSaveIterationResult:
    """Tests for save_iteration_result function."""

    def test_saves_iteration_json(self):
        """Save iteration result to JSON file."""
        fs = MockFileSystem()

        result = save_iteration_result(
            fs=fs,
            skill_path="/skills/test-skill",
            iteration=1,
            score=0.85,
            improved=True,
            action="continue",
            metrics={"accuracy": 0.9, "latency_ms": 1000},
        )

        assert result["saved"] is True
        assert "/skills/test-skill/iteration_1.json" in result["file"]

        # Verify file content
        content = json.loads(fs.files["/skills/test-skill/iteration_1.json"])
        assert content["iteration"] == 1
        assert content["score"] == 0.85
        assert content["improved"] is True
        assert content["action"] == "continue"
        assert content["metrics"]["accuracy"] == 0.9

    def test_saves_with_error(self):
        """Save iteration result with error message."""
        fs = MockFileSystem()

        save_iteration_result(
            fs=fs,
            skill_path="/skills/test-skill",
            iteration=2,
            score=0.0,
            improved=False,
            action="failed",
            error="LLM timeout",
        )

        content = json.loads(fs.files["/skills/test-skill/iteration_2.json"])
        assert content["error"] == "LLM timeout"
        assert content["improved"] is False


class TestLoadIterationHistory:
    """Tests for load_iteration_history function."""

    def test_loads_all_iterations(self):
        """Load all iteration history files."""
        fs = MockFileSystem(
            {
                "/skills/test-skill/iteration_1.json": json.dumps({"iteration": 1, "score": 0.7}),
                "/skills/test-skill/iteration_2.json": json.dumps({"iteration": 2, "score": 0.8}),
                "/skills/test-skill/iteration_3.json": json.dumps({"iteration": 3, "score": 0.85}),
            }
        )

        history = load_iteration_history(fs, "/skills/test-skill")

        assert len(history) == 3
        assert history[0]["iteration"] == 1
        assert history[1]["iteration"] == 2
        assert history[2]["iteration"] == 3

    def test_sorted_by_iteration(self):
        """History is sorted by iteration number."""
        fs = MockFileSystem(
            {
                "/skills/test-skill/iteration_3.json": json.dumps({"iteration": 3, "score": 0.85}),
                "/skills/test-skill/iteration_1.json": json.dumps({"iteration": 1, "score": 0.7}),
            }
        )

        history = load_iteration_history(fs, "/skills/test-skill")

        assert history[0]["iteration"] == 1
        assert history[1]["iteration"] == 3

    def test_empty_for_nonexistent_path(self):
        """Return empty list for nonexistent skill path."""
        fs = MockFileSystem()
        history = load_iteration_history(fs, "/skills/nonexistent")
        assert history == []

    def test_skips_invalid_json(self):
        """Skip files with invalid JSON."""
        fs = MockFileSystem(
            {
                "/skills/test-skill/iteration_1.json": json.dumps({"iteration": 1, "score": 0.7}),
                "/skills/test-skill/iteration_2.json": "not valid json",
            }
        )

        history = load_iteration_history(fs, "/skills/test-skill")

        # Should only have iteration 1
        assert len(history) == 1
        assert history[0]["iteration"] == 1
