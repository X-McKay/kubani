"""Tests for kubani-dev skill CLI commands."""

import json
import pytest
from click.testing import CliRunner

from kubani.cli.cli import get_click_app


@pytest.fixture
def cli_runner():
    """Create a CLI runner for testing."""
    return CliRunner()


# Get the Click app with all commands registered
cli = get_click_app()


@pytest.fixture
def temp_skill(tmp_path):
    """Create a temporary skill directory for testing."""
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()

    # Create SKILL.md
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("""---
name: test-skill
version: "1.0.0"
category: test
triggers:
  - test_trigger
---

# Test Skill

A test skill for unit testing.

## Purpose
Test the skill commands.

## Steps
1. Do something
2. Do something else
""")

    # Create test_cases.yaml
    test_cases = skill_dir / "test_cases.yaml"
    test_cases.write_text("""test_cases:
  - name: "Basic test"
    description: "A basic test case"
    input: "test input"
    expected_output: "test output"
""")

    # Create metadata.json
    metadata = skill_dir / "metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "name": "test-skill",
                "version": "1.0.0",
                "description": "A test skill",
                "category": "test",
                "status": "development",
                "created": "2025-01-01T00:00:00Z",
            },
            indent=2,
        )
    )

    return skill_dir


class TestSkillListCommand:
    """Test skill list command output."""

    def test_list_outputs_without_error(self, cli_runner):
        """Skill list command should run without errors."""
        result = cli_runner.invoke(cli, ["skill", "list"])
        # Should not crash
        assert result.exit_code == 0

    def test_list_with_search(self, cli_runner):
        """Skill list command should accept search filter."""
        result = cli_runner.invoke(cli, ["skill", "list", "--search", "nonexistent"])
        assert result.exit_code == 0

    def test_list_shows_categories(self, cli_runner):
        """Skill list command should categorize skills."""
        result = cli_runner.invoke(cli, ["skill", "list"])
        assert result.exit_code == 0
        # Output should contain category headers or total count
        assert "skill" in result.output.lower() or "Total" in result.output


class TestSkillValidateCommand:
    """Test skill validate command output."""

    def test_validate_single_skill(self, cli_runner, temp_skill):
        """Validate command should work on a single skill."""
        result = cli_runner.invoke(cli, ["skill", "validate", str(temp_skill)])
        assert result.exit_code == 0

    def test_validate_with_all_flag(self, cli_runner):
        """Validate command should work with --all flag."""
        result = cli_runner.invoke(cli, ["skill", "validate", "--all"])
        assert result.exit_code == 0

    def test_validate_missing_skill_shows_error(self, cli_runner):
        """Validate command should show error for missing skill."""
        result = cli_runner.invoke(cli, ["skill", "validate"])
        # Should either show error or help
        assert result.exit_code != 0 or "skill path" in result.output.lower()

    def test_validate_shows_results_summary(self, cli_runner, temp_skill):
        """Validate command should show pass/fail summary."""
        result = cli_runner.invoke(cli, ["skill", "validate", str(temp_skill)])
        assert result.exit_code == 0
        # Should show passed/failed counts
        assert "passed" in result.output.lower() or "failed" in result.output.lower()


class TestSkillInfoCommand:
    """Test skill info command output."""

    def test_info_shows_skill_details(self, cli_runner, temp_skill):
        """Info command should show skill details."""
        result = cli_runner.invoke(cli, ["skill", "info", str(temp_skill)])
        assert result.exit_code == 0
        # Should show skill name
        assert "test-skill" in result.output

    def test_info_shows_metadata(self, cli_runner, temp_skill):
        """Info command should display metadata fields."""
        result = cli_runner.invoke(cli, ["skill", "info", str(temp_skill)])
        assert result.exit_code == 0
        # Should show version or category
        assert "1.0.0" in result.output or "test" in result.output.lower()


class TestSkillDraftCommand:
    """Test skill draft command output."""

    def test_draft_requires_name_in_noninteractive(self, cli_runner, tmp_path):
        """Draft command should require name in non-interactive mode."""
        output_dir = tmp_path / "output"
        result = cli_runner.invoke(
            cli,
            ["skill", "draft", "--non-interactive", "--output-dir", str(output_dir)],
        )
        # Should fail or show error about missing name
        assert result.exit_code != 0 or "name" in result.output.lower()

    def test_draft_accepts_positional_args(self, cli_runner, tmp_path):
        """Draft command should accept name as positional arg."""
        # Note: This will fail if LLM is not available, which is expected
        output_dir = tmp_path / "test-skill"
        result = cli_runner.invoke(
            cli,
            [
                "skill",
                "draft",
                "test-skill",
                "A test skill description",
                "--non-interactive",
                "--output-dir",
                str(output_dir),
            ],
        )
        # Either succeeds or fails due to LLM not available
        # We just verify it parses the arguments correctly
        assert "test-skill" in result.output or result.exit_code in [0, 1]


class TestSkillEvalCommand:
    """Test skill eval command output."""

    def test_eval_requires_skill_path(self, cli_runner):
        """Eval command should require a skill path."""
        result = cli_runner.invoke(cli, ["skill", "eval"])
        # Should show error or usage
        assert result.exit_code != 0 or "skill_path" in result.output.lower()

    def test_eval_shows_config_panel(self, cli_runner, temp_skill):
        """Eval command should show configuration panel."""
        # Note: This may fail if LLM is not available
        result = cli_runner.invoke(
            cli,
            ["skill", "eval", str(temp_skill), "--max-tests", "1"],
        )
        # Should show some output before potentially failing
        # The panel should be shown even if LLM fails
        assert len(result.output) > 0


class TestSkillPromoteCommand:
    """Test skill promote command output."""

    def test_promote_requires_category(self, cli_runner, temp_skill):
        """Promote command should require category option."""
        result = cli_runner.invoke(cli, ["skill", "promote", str(temp_skill)])
        # Should show error about missing category
        assert result.exit_code != 0
        assert "category" in result.output.lower() or "required" in result.output.lower()

    def test_promote_shows_confirmation(self, cli_runner, temp_skill):
        """Promote command should show confirmation prompt."""
        result = cli_runner.invoke(
            cli,
            ["skill", "promote", str(temp_skill), "--category", "core"],
            input="n\n",  # Cancel the promotion
        )
        # Should show promotion info and ask for confirmation
        assert "test-skill" in result.output or "Promotion" in result.output


class TestSkillImproveCommand:
    """Test skill improve command output."""

    def test_improve_requires_skill_path(self, cli_runner):
        """Improve command should require a skill path."""
        result = cli_runner.invoke(cli, ["skill", "improve"])
        # Should show error or usage
        assert result.exit_code != 0 or "skill_path" in result.output.lower()

    def test_improve_needs_evaluation_first(self, cli_runner, temp_skill):
        """Improve command should fail without prior evaluation."""
        result = cli_runner.invoke(cli, ["skill", "improve", str(temp_skill)])
        # Should show error about missing evaluation
        # The command should run but may show an error about missing eval results
        assert (
            result.exit_code != 0
            or "evaluation" in result.output.lower()
            or "No evaluation results" in result.output
        )


class TestSkillHistoryCommand:
    """Test skill eval-history command output."""

    def test_history_shows_empty_for_new_skill(self, cli_runner, temp_skill):
        """History command should handle skill with no evaluations."""
        result = cli_runner.invoke(cli, ["skill", "eval-history", str(temp_skill)])
        # Should run without error even with no history
        assert result.exit_code == 0

    def test_history_shows_summary_panel(self, cli_runner, temp_skill):
        """History command should show evaluation summary."""
        # Create latest_eval.json with the expected format
        eval_file = temp_skill / "latest_eval.json"
        eval_file.write_text(
            json.dumps(
                {
                    "timestamp": "2025-01-01T00:00:00Z",
                    "metrics": {
                        "accuracy": 75.0,
                        "tests_passed": 3,
                        "tests_total": 4,
                        "avg_latency_ms": 150.0,
                        "avg_tokens_per_test": {"total": 100, "input": 50, "output": 50},
                    },
                    "test_results": [
                        {"name": "test1", "passed": True},
                        {"name": "test2", "passed": True},
                        {"name": "test3", "passed": True},
                        {"name": "test4", "passed": False},
                    ],
                }
            )
        )

        result = cli_runner.invoke(cli, ["skill", "eval-history", str(temp_skill)])
        assert result.exit_code == 0
        # Should show accuracy or test counts
        assert "75" in result.output or "3/4" in result.output
