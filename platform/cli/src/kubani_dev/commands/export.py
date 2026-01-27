"""Export command for syncing registry to Git."""

import asyncio
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from kubani_dev.oci import get_oci_client
from kubani_dev.registry_client import get_registry_client
from kubani_dev.ui import console, error, info, muted, success

logger = logging.getLogger(__name__)

app = typer.Typer(help="Export resources from registry to Git")


@app.command("to-git")
def export_to_git(
    project_root: Annotated[Path, typer.Option("--root", "-r", help="Project root")] = Path("."),
    commit: Annotated[bool, typer.Option("--commit/--no-commit", help="Create Git commit")] = True,
    push: Annotated[bool, typer.Option("--push/--no-push", help="Push to remote")] = False,
    skills: Annotated[bool, typer.Option("--skills/--no-skills", help="Export skills")] = True,
    agents: Annotated[bool, typer.Option("--agents/--no-agents", help="Export agents")] = True,
    syndicates: Annotated[
        bool, typer.Option("--syndicates/--no-syndicates", help="Export syndicates")
    ] = True,
):
    """
    Export production resources from the registry to Git.

    This creates a snapshot of all production resources for version control
    and disaster recovery.
    """
    asyncio.run(_export_to_git(project_root, commit, push, skills, agents, syndicates))


async def _export_to_git(
    project_root: Path,
    do_commit: bool,
    do_push: bool,
    export_skills: bool,
    export_agents: bool,
    export_syndicates: bool,
):
    """Run the export."""
    project_root = project_root.resolve()

    registry = get_registry_client()
    oci = get_oci_client()

    changes = []

    # Export skills
    if export_skills:
        info("Exporting skills...")
        skills_dir = project_root / "kubani" / "skills"
        skill_changes = await _export_skills(skills_dir, registry, oci)
        changes.extend(skill_changes)

    # Export agents
    if export_agents:
        info("Exporting agents...")
        agents_dir = project_root / "kubani" / "agents"
        agent_changes = await _export_agents(agents_dir, registry, oci)
        changes.extend(agent_changes)

    # Export syndicates
    if export_syndicates:
        info("Exporting syndicates...")
        syndicates_dir = project_root / "kubani" / "syndicates"
        syndicate_changes = await _export_syndicates(syndicates_dir, registry, oci)
        changes.extend(syndicate_changes)

    if not changes:
        info("No changes to export")
        return

    console.print()
    info(f"Exported {len(changes)} resources")

    # Git operations
    if do_commit:
        # Stage all changes
        subprocess.run(["git", "add", "-A"], cwd=project_root, check=True)

        # Check if there are changes to commit
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=project_root,
            capture_output=True,
        )

        if result.returncode != 0:
            # There are changes
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            commit_msg = f"sync: export from registry ({timestamp})\n\n"
            commit_msg += "Exported resources:\n"
            for change in changes[:20]:  # Limit to 20 in commit message
                commit_msg += f"  - {change}\n"
            if len(changes) > 20:
                commit_msg += f"  ... and {len(changes) - 20} more\n"

            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=project_root,
                check=True,
            )
            success("Created Git commit")

            if do_push:
                subprocess.run(["git", "push"], cwd=project_root, check=True)
                success("Pushed to remote")
        else:
            muted("No changes to commit")


async def _export_skills(
    skills_dir: Path,
    registry,
    oci,
) -> list[str]:
    """Export all production skills."""
    changes = []

    # Get all production skills
    skills = await registry.list_skills(status="production")

    for skill in skills:
        current_version = skill.get("current_version")
        if not current_version:
            continue

        version_info = await registry.get_skill_version(
            skill["id"],
            version=current_version,
        )

        if not version_info or not version_info.get("oci_tag"):
            continue

        # Determine output path
        domain = skill.get("metadata", {}).get("domain", "general")
        category = skill.get("metadata", {}).get("category", "general")
        output_dir = skills_dir / domain / category / skill["name"]

        # Pull from OCI
        try:
            oci.pull(
                resource_type="skill",
                name=skill["name"],
                tag=version_info["oci_tag"],
                dest_dir=output_dir,
            )
            changes.append(f"skill:{skill['id']}:{current_version}")
            muted(f"  Exported {skill['id']}:{current_version}")
        except Exception as e:
            error(f"  Failed to export {skill['id']}: {e}")

    return changes


async def _export_agents(agents_dir: Path, registry, oci) -> list[str]:
    """Export all production agents."""
    changes = []

    # Get all agents with current_version
    agents = await registry._request("GET", "/agents")

    for agent in agents:
        current_version = agent.get("current_version")
        if not current_version:
            continue

        name = agent["name"]
        output_dir = agents_dir / name

        try:
            oci.pull(
                resource_type="agent",
                name=name,
                tag=f"v{current_version}",
                dest_dir=output_dir,
            )
            changes.append(f"agent:{name}:{current_version}")
            muted(f"  Exported {name}:{current_version}")
        except Exception as e:
            error(f"  Failed to export {name}: {e}")

    return changes


async def _export_syndicates(syndicates_dir: Path, registry, oci) -> list[str]:
    """Export all production syndicates."""
    changes = []

    # Get all syndicates
    syndicates = await registry._request("GET", "/syndicates")

    for syndicate in syndicates:
        current_version = syndicate.get("current_version")
        if not current_version:
            continue

        name = syndicate["name"]
        output_dir = syndicates_dir / name

        try:
            oci.pull(
                resource_type="syndicate",
                name=name,
                tag=f"v{current_version}",
                dest_dir=output_dir,
            )
            changes.append(f"syndicate:{name}:{current_version}")
            muted(f"  Exported {name}:{current_version}")
        except Exception as e:
            error(f"  Failed to export {name}: {e}")

    return changes


# Scheduled job entry point
def run_scheduled_export():
    """Entry point for scheduled export job."""
    import os

    project_root = Path(os.environ.get("KUBANI_PROJECT_ROOT", "/app/kubani"))

    asyncio.run(
        _export_to_git(
            project_root=project_root,
            do_commit=True,
            do_push=True,
            export_skills=True,
            export_agents=True,
            export_syndicates=True,
        )
    )


if __name__ == "__main__":
    run_scheduled_export()
