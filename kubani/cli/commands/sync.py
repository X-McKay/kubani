"""Legacy sync command - deprecated in favor of push/pull and registry-first workflow.

This module provides backward compatibility for the old sync command while directing
users to the new registry-first commands.
"""

import asyncio
import sys
from pathlib import Path
from typing import Annotated

import typer

from kubani.cli.ui import console, warning

app = typer.Typer(help="[DEPRECATED] Sync resources to registry - use migrate/export instead")


def _show_deprecation_warning():
    """Show the deprecation warning message."""
    warning(
        "The 'sync' command is deprecated.\n"
        "\n"
        "Use the new registry-first commands instead:\n"
        "  kubani pull skill <name>     # Pull from registry\n"
        "  kubani push skill <path>     # Push to registry\n"
        "  kubani promote skill <name>  # Promote version\n"
        "  kubani export to-git         # Export to Git\n"
        "\n"
        "For one-time migration from filesystem:\n"
        "  kubani migrate to-registry\n"
    )
    console.print()


@app.callback(invoke_without_command=True)
def deprecation_warning(ctx: typer.Context):
    """Show deprecation warning for sync command."""
    _show_deprecation_warning()

    if ctx.invoked_subcommand is None:
        raise typer.Exit(1)


# Keep old commands working temporarily for backwards compatibility
@app.command("all")
def sync_all(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be synced")] = False,
    skills: Annotated[bool, typer.Option("--skills/--no-skills", help="Sync skills")] = True,
    agents: Annotated[bool, typer.Option("--agents/--no-agents", help="Sync agents")] = True,
    mcp: Annotated[
        bool, typer.Option("--mcp/--no-mcp", help="Sync MCP servers and policies")
    ] = True,
    registry_url: Annotated[
        str, typer.Option("--registry-url", envvar="REGISTRY_URL", help="Registry URL")
    ] = "http://localhost:8000",
):
    """[DEPRECATED] Sync all resources to the registry."""
    _show_deprecation_warning()

    # Import and run the old sync logic
    from kubani.cli.sync import RegistrySync, print_sync_results

    def find_project_root() -> Path:
        current = Path.cwd()
        while current != current.parent:
            if (current / "agents").exists() and (current / "skills").exists():
                return current
            current = current.parent
        return Path.cwd()

    project_root = find_project_root()
    syncer = RegistrySync(project_root, registry_url)

    results = asyncio.run(
        syncer.sync_all(
            dry_run=dry_run,
            skills=skills,
            agents=agents,
            mcp=mcp,
        )
    )

    print_sync_results(results)

    total_failed = sum(r.failed for r in results.values())
    if total_failed > 0:
        sys.exit(1)


@app.command("skills")
def sync_skills(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be synced")] = False,
    registry_url: Annotated[
        str, typer.Option("--registry-url", envvar="REGISTRY_URL", help="Registry URL")
    ] = "http://localhost:8000",
):
    """[DEPRECATED] Sync skills to the registry."""
    _show_deprecation_warning()
    warning("Use 'kubani migrate to-registry --no-agents --no-syndicates' instead.")

    from kubani.cli.sync import RegistrySync, print_sync_results

    def find_project_root() -> Path:
        current = Path.cwd()
        while current != current.parent:
            if (current / "agents").exists() and (current / "skills").exists():
                return current
            current = current.parent
        return Path.cwd()

    project_root = find_project_root()
    syncer = RegistrySync(project_root, registry_url)

    results = asyncio.run(syncer.sync_skills(dry_run=dry_run))
    print_sync_results({"skills": results})

    if results.failed > 0:
        sys.exit(1)


@app.command("agents")
def sync_agents(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be synced")] = False,
    registry_url: Annotated[
        str, typer.Option("--registry-url", envvar="REGISTRY_URL", help="Registry URL")
    ] = "http://localhost:8000",
):
    """[DEPRECATED] Sync agents to the registry."""
    _show_deprecation_warning()
    warning("Use 'kubani migrate to-registry --no-skills --no-syndicates' instead.")

    from kubani.cli.sync import RegistrySync, print_sync_results

    def find_project_root() -> Path:
        current = Path.cwd()
        while current != current.parent:
            if (current / "agents").exists() and (current / "skills").exists():
                return current
            current = current.parent
        return Path.cwd()

    project_root = find_project_root()
    syncer = RegistrySync(project_root, registry_url)

    results = asyncio.run(syncer.sync_agents(dry_run=dry_run))
    print_sync_results({"agents": results})

    if results.failed > 0:
        sys.exit(1)
