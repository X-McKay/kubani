"""Tests for kubani UI components."""

import pytest

from kubani.cli.ui import (
    THEME,
    console,
    create_panel,
    create_progress,
    create_table,
    error,
    header,
    info,
    muted,
    print_divider,
    print_key_value,
    print_list,
    print_results_summary,
    spinner,
    success,
    warning,
)


class TestTheme:
    """Test that theme is properly configured."""

    def test_theme_has_required_styles(self):
        """Verify all required styles are defined in the theme."""
        assert "success" in THEME.styles
        assert "error" in THEME.styles
        assert "warning" in THEME.styles
        assert "info" in THEME.styles
        assert "muted" in THEME.styles
        assert "highlight" in THEME.styles
        assert "header" in THEME.styles

    def test_console_uses_theme(self):
        """Verify the global console uses our theme."""
        # The console should be configured with our theme
        assert console is not None


class TestStatusMessages:
    """Test status message formatting."""

    def test_success_message(self, mock_console, captured_output, monkeypatch):
        """Test success message contains checkmark and text."""
        monkeypatch.setattr("kubani.cli.ui.console", mock_console)
        success("Operation completed")
        output = captured_output()
        assert "\u2713" in output  # Checkmark
        assert "Operation completed" in output

    def test_error_message(self, mock_console, captured_output, monkeypatch):
        """Test error message contains X and text."""
        monkeypatch.setattr("kubani.cli.ui.console", mock_console)
        error("Something failed")
        output = captured_output()
        assert "\u2717" in output  # X mark
        assert "Something failed" in output

    def test_info_message(self, mock_console, captured_output, monkeypatch):
        """Test info message contains arrow and text."""
        monkeypatch.setattr("kubani.cli.ui.console", mock_console)
        info("Information here")
        output = captured_output()
        assert "\u2192" in output  # Arrow
        assert "Information here" in output

    def test_warning_message(self, mock_console, captured_output, monkeypatch):
        """Test warning message contains exclamation and text."""
        monkeypatch.setattr("kubani.cli.ui.console", mock_console)
        warning("Caution needed")
        output = captured_output()
        assert "!" in output
        assert "Caution needed" in output

    def test_muted_message(self, mock_console, captured_output, monkeypatch):
        """Test muted message renders text."""
        monkeypatch.setattr("kubani.cli.ui.console", mock_console)
        muted("Secondary info")
        output = captured_output()
        assert "Secondary info" in output

    def test_header_message(self, mock_console, captured_output, monkeypatch):
        """Test header message renders text."""
        monkeypatch.setattr("kubani.cli.ui.console", mock_console)
        header("Section Title")
        output = captured_output()
        assert "Section Title" in output


class TestTableCreation:
    """Test table creation helper."""

    def test_create_table_with_title(self):
        """Test creating a table with a title."""
        table = create_table(title="Test Table")
        assert table.title == "Test Table"

    def test_create_table_with_columns(self):
        """Test creating a table with columns."""
        table = create_table(title="Test", columns=["Name", "Status", "Score"])
        assert len(table.columns) == 3

    def test_create_table_no_columns(self):
        """Test creating a table without columns."""
        table = create_table(title="Empty")
        assert len(table.columns) == 0

    def test_create_table_show_lines(self):
        """Test creating a table with row lines."""
        table = create_table(show_lines=True)
        assert table.show_lines is True

    def test_create_table_hide_header(self):
        """Test creating a table without header."""
        table = create_table(show_header=False)
        assert table.show_header is False

    def test_add_rows_to_table(self):
        """Test adding rows to a created table."""
        table = create_table(columns=["Name", "Value"])
        table.add_row("key1", "value1")
        table.add_row("key2", "value2")
        assert table.row_count == 2


class TestPanelCreation:
    """Test panel creation helper."""

    def test_create_panel_basic(self):
        """Test creating a basic panel."""
        panel = create_panel("Content here")
        assert panel.renderable == "Content here"

    def test_create_panel_with_title(self):
        """Test creating a panel with title."""
        panel = create_panel("Content", title="My Title")
        assert panel.title == "My Title"

    def test_create_panel_with_subtitle(self):
        """Test creating a panel with subtitle."""
        panel = create_panel("Content", subtitle="v1.0")
        assert panel.subtitle == "v1.0"

    def test_create_panel_expand(self):
        """Test creating an expanded panel."""
        panel = create_panel("Content", expand=True)
        assert panel.expand is True


class TestSpinner:
    """Test spinner context manager."""

    def test_spinner_creates_progress(self):
        """Spinner should complete without error."""
        with spinner("Loading..."):
            pass  # Just verify it doesn't crash

    def test_spinner_with_operation(self):
        """Spinner should work during an operation."""
        result = 0
        with spinner("Calculating..."):
            result = sum(range(100))
        assert result == 4950

    def test_spinner_with_exception(self):
        """Spinner should clean up even on exception."""
        with pytest.raises(ValueError):
            with spinner("Will fail..."):
                raise ValueError("Test error")


class TestProgressBar:
    """Test progress bar components."""

    def test_create_progress_instance(self):
        """Test creating a progress instance."""
        progress = create_progress()
        assert progress is not None

    def test_progress_with_tasks(self):
        """Test progress with multiple tasks."""
        progress = create_progress()
        with progress:
            task1 = progress.add_task("Task 1", total=10)
            task2 = progress.add_task("Task 2", total=5)
            # Advance tasks
            for _ in range(10):
                progress.advance(task1)
            for _ in range(5):
                progress.advance(task2)
            # Tasks should be complete
            assert progress.tasks[0].completed == 10
            assert progress.tasks[1].completed == 5


class TestFormattedOutput:
    """Test formatted output helpers."""

    def test_print_key_value(self, mock_console, captured_output, monkeypatch):
        """Test key-value pair printing."""
        monkeypatch.setattr("kubani.cli.ui.console", mock_console)
        print_key_value("Name", "Test Value")
        output = captured_output()
        assert "Name" in output
        assert "Test Value" in output

    def test_print_list(self, mock_console, captured_output, monkeypatch):
        """Test bulleted list printing."""
        monkeypatch.setattr("kubani.cli.ui.console", mock_console)
        print_list(["Item 1", "Item 2", "Item 3"])
        output = captured_output()
        assert "Item 1" in output
        assert "Item 2" in output
        assert "Item 3" in output
        assert "\u2022" in output  # Bullet character

    def test_print_list_custom_bullet(self, mock_console, captured_output, monkeypatch):
        """Test bulleted list with custom bullet."""
        monkeypatch.setattr("kubani.cli.ui.console", mock_console)
        print_list(["Item 1", "Item 2"], bullet="-")
        output = captured_output()
        assert "-" in output

    def test_print_divider(self, mock_console, captured_output, monkeypatch):
        """Test divider line printing."""
        monkeypatch.setattr("kubani.cli.ui.console", mock_console)
        print_divider(width=40)
        output = captured_output()
        assert "\u2500" in output  # Line character


class TestResultsSummary:
    """Test results summary output."""

    def test_results_all_passed(self, mock_console, captured_output, monkeypatch):
        """Test results summary with all tests passed."""
        monkeypatch.setattr("kubani.cli.ui.console", mock_console)
        print_results_summary(passed=10, failed=0)
        output = captured_output()
        assert "10 passed" in output
        assert "0 failed" in output
        assert "100%" in output

    def test_results_with_failures(self, mock_console, captured_output, monkeypatch):
        """Test results summary with some failures."""
        monkeypatch.setattr("kubani.cli.ui.console", mock_console)
        print_results_summary(passed=8, failed=2)
        output = captured_output()
        assert "8 passed" in output
        assert "2 failed" in output
        assert "80%" in output

    def test_results_with_skipped(self, mock_console, captured_output, monkeypatch):
        """Test results summary with skipped tests."""
        monkeypatch.setattr("kubani.cli.ui.console", mock_console)
        print_results_summary(passed=5, failed=1, skipped=2)
        output = captured_output()
        assert "5 passed" in output
        assert "1 failed" in output
        assert "2 skipped" in output

    def test_results_with_time(self, mock_console, captured_output, monkeypatch):
        """Test results summary with total time."""
        monkeypatch.setattr("kubani.cli.ui.console", mock_console)
        print_results_summary(passed=5, failed=0, total_time=1.234)
        output = captured_output()
        assert "1.23s" in output
