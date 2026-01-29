"""
Kubani CLI UI Components

Provides a consistent, visually appealing interface for kubani CLI commands.
Uses Rich for styling, tables, panels, spinners, and progress bars.
"""

from contextlib import contextmanager
from typing import Any, Generator, Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.theme import Theme


# Kubani color theme
THEME = Theme(
    {
        "success": "bold green",
        "error": "bold red",
        "warning": "bold yellow",
        "info": "bold cyan",
        "muted": "dim",
        "highlight": "bold magenta",
        "header": "bold blue",
    }
)

# Global console instance with theme
console = Console(theme=THEME)


# =============================================================================
# Status Messages
# =============================================================================


def success(msg: str) -> None:
    """Print a success message with green checkmark."""
    console.print(f"[success]\u2713[/success] {msg}")


def error(msg: str) -> None:
    """Print an error message with red X."""
    console.print(f"[error]\u2717[/error] {msg}")


def info(msg: str) -> None:
    """Print an info message with arrow."""
    console.print(f"[info]\u2192[/info] {msg}")


def warning(msg: str) -> None:
    """Print a warning message with exclamation."""
    console.print(f"[warning]![/warning] {msg}")


def muted(msg: str) -> None:
    """Print a muted/secondary message."""
    console.print(f"[muted]{msg}[/muted]")


def header(msg: str) -> None:
    """Print a header/title message."""
    console.print(f"[header]{msg}[/header]")


# =============================================================================
# Spinners
# =============================================================================


@contextmanager
def spinner(message: str) -> Generator[None, None, None]:
    """
    Show an animated spinner during long operations.

    Usage:
        with spinner("Loading..."):
            do_something_slow()
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(message, total=None)
        yield


@contextmanager
def status_spinner(message: str) -> Generator[Any, None, None]:
    """
    Show a status spinner that can be updated.

    Usage:
        with status_spinner("Processing...") as status:
            status.update("Step 1...")
            do_step_1()
            status.update("Step 2...")
            do_step_2()
    """
    with console.status(message) as status:
        yield status


# =============================================================================
# Progress Bars
# =============================================================================


@contextmanager
def progress_bar(
    description: str = "Processing...",
    total: Optional[int] = None,
) -> Generator[tuple[Progress, int], None, None]:
    """
    Show a progress bar for multi-step operations.

    Usage:
        with progress_bar("Syncing files...", total=10) as (progress, task_id):
            for item in items:
                process(item)
                progress.advance(task_id)

    Returns:
        Tuple of (Progress instance, task_id)
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task(description, total=total)
        yield progress, task_id


def create_progress() -> Progress:
    """
    Create a reusable Progress instance for complex workflows.

    Usage:
        progress = create_progress()
        with progress:
            task1 = progress.add_task("Task 1", total=10)
            task2 = progress.add_task("Task 2", total=5)
            # Update tasks as needed
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    )


# =============================================================================
# Tables
# =============================================================================


def create_table(
    title: Optional[str] = None,
    columns: Optional[list[str]] = None,
    show_header: bool = True,
    show_lines: bool = False,
) -> Table:
    """
    Create a styled table.

    Args:
        title: Optional table title
        columns: List of column names to add
        show_header: Whether to show column headers
        show_lines: Whether to show row separator lines

    Returns:
        Table instance ready for adding rows
    """
    table = Table(
        title=title,
        show_header=show_header,
        header_style="bold cyan",
        show_lines=show_lines,
    )

    if columns:
        for col in columns:
            table.add_column(col)

    return table


def print_table(table: Table) -> None:
    """Print a table to the console."""
    console.print(table)


# =============================================================================
# Panels
# =============================================================================


def create_panel(
    content: str,
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    style: str = "cyan",
    expand: bool = False,
) -> Panel:
    """
    Create a styled panel (boxed content).

    Args:
        content: The content to display in the panel
        title: Optional panel title
        subtitle: Optional panel subtitle
        style: Border style/color
        expand: Whether to expand to full width

    Returns:
        Panel instance
    """
    return Panel(
        content,
        title=title,
        subtitle=subtitle,
        border_style=style,
        expand=expand,
    )


def print_panel(
    content: str,
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    style: str = "cyan",
    expand: bool = False,
) -> None:
    """Print a panel to the console."""
    console.print(create_panel(content, title, subtitle, style, expand))


# =============================================================================
# Formatted Output
# =============================================================================


def print_key_value(key: str, value: str, key_style: str = "bold") -> None:
    """Print a key-value pair with styling."""
    console.print(f"[{key_style}]{key}:[/{key_style}] {value}")


def print_list(items: list[str], bullet: str = "\u2022", indent: int = 2) -> None:
    """Print a bulleted list."""
    for item in items:
        console.print(f"{' ' * indent}{bullet} {item}")


def print_divider(char: str = "\u2500", width: int = 60) -> None:
    """Print a horizontal divider line."""
    console.print(f"[muted]{char * width}[/muted]")


def print_blank() -> None:
    """Print a blank line."""
    console.print()


# =============================================================================
# Welcome/Banner
# =============================================================================


def print_banner(
    title: str,
    subtitle: Optional[str] = None,
    version: Optional[str] = None,
) -> None:
    """
    Print a welcome banner for the CLI.

    Args:
        title: Main title text
        subtitle: Optional subtitle/tagline
        version: Optional version string
    """
    content_lines = [f"[bold]{title}[/bold]"]

    if subtitle:
        content_lines.append(f"[muted]{subtitle}[/muted]")

    if version:
        content_lines.append(f"[info]v{version}[/info]")

    content = "\n".join(content_lines)
    console.print(
        Panel(
            content,
            border_style="blue",
            expand=False,
            padding=(0, 2),
        )
    )


# =============================================================================
# Results Display
# =============================================================================


def print_results_summary(
    passed: int,
    failed: int,
    skipped: int = 0,
    total_time: Optional[float] = None,
) -> None:
    """
    Print a test/evaluation results summary.

    Args:
        passed: Number of passed items
        failed: Number of failed items
        skipped: Number of skipped items
        total_time: Optional total time in seconds
    """
    total = passed + failed + skipped

    parts = [
        f"[success]{passed} passed[/success]",
        f"[error]{failed} failed[/error]",
    ]

    if skipped > 0:
        parts.append(f"[warning]{skipped} skipped[/warning]")

    if total_time is not None:
        parts.append(f"[muted]({total_time:.2f}s)[/muted]")

    # Calculate pass rate
    if total > 0:
        pass_rate = (passed / total) * 100
        if pass_rate == 100:
            rate_style = "success"
        elif pass_rate >= 80:
            rate_style = "warning"
        else:
            rate_style = "error"
        parts.append(f"[{rate_style}]{pass_rate:.0f}%[/{rate_style}]")

    console.print(" | ".join(parts))


# =============================================================================
# Confirmation and Input
# =============================================================================


def confirm(message: str, default: bool = True) -> bool:
    """
    Ask for confirmation with styled prompt.

    This is a styled wrapper around click.confirm for consistency.
    For interactive menus, use questionary instead.
    """
    import click

    return click.confirm(message, default=default)


def prompt(message: str, default: Optional[str] = None) -> str:
    """
    Ask for text input with styled prompt.

    This is a styled wrapper around click.prompt for consistency.
    For interactive menus, use questionary instead.
    """
    import click

    return click.prompt(message, default=default)
