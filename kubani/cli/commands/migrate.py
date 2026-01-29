"""Migration command for moving resources to the registry."""

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import typer
import yaml

from kubani.cli.oci import KubaniOCIClient, get_oci_client
from kubani.cli.registry_client import RegistryClient, get_registry_client
from kubani.cli.ui import console, error, info, muted, success, warning

logger = logging.getLogger(__name__)

app = typer.Typer(help="Migrate resources to the registry")


@app.command("to-registry")
def migrate_to_registry(
    project_root: Annotated[Path, typer.Option("--root", "-r", help="Project root")] = Path("."),
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Preview changes")] = False,
    skills: Annotated[bool, typer.Option("--skills/--no-skills", help="Migrate skills")] = True,
    agents: Annotated[bool, typer.Option("--agents/--no-agents", help="Migrate agents")] = True,
    syndicates: Annotated[
        bool, typer.Option("--syndicates/--no-syndicates", help="Migrate syndicates")
    ] = True,
):
    """
    Migrate existing filesystem resources to the registry.

    This is a one-time migration that:
    1. Scans the filesystem for existing skills, agents, and syndicates
    2. Packages each as a tarball
    3. Pushes to the OCI registry
    4. Registers metadata in PostgreSQL with status=production
    """
    asyncio.run(_migrate_to_registry(project_root, dry_run, skills, agents, syndicates))


async def _migrate_to_registry(
    project_root: Path,
    dry_run: bool,
    migrate_skills: bool,
    migrate_agents: bool,
    migrate_syndicates: bool,
):
    """Run the migration."""
    project_root = project_root.resolve()

    if not (project_root / "kubani").exists():
        error(f"Not a Kubani project root: {project_root}")
        raise typer.Exit(1)

    results = {
        "skills": {"migrated": 0, "skipped": 0, "failed": 0},
        "agents": {"migrated": 0, "skipped": 0, "failed": 0},
        "syndicates": {"migrated": 0, "skipped": 0, "failed": 0},
    }

    registry = get_registry_client()
    oci = get_oci_client()

    # Migrate skills
    if migrate_skills:
        info("Migrating skills...")
        skills_dir = project_root / "kubani" / "skills"
        if skills_dir.exists():
            results["skills"] = await _migrate_skills(skills_dir, registry, oci, dry_run)
        else:
            warning(f"Skills directory not found: {skills_dir}")

    # Migrate agents
    if migrate_agents:
        info("Migrating agents...")
        agents_dir = project_root / "kubani" / "agents"
        if agents_dir.exists():
            results["agents"] = await _migrate_agents(agents_dir, registry, oci, dry_run)
        else:
            warning(f"Agents directory not found: {agents_dir}")

    # Migrate syndicates
    if migrate_syndicates:
        info("Migrating syndicates...")
        syndicates_dir = project_root / "kubani" / "syndicates"
        if syndicates_dir.exists():
            results["syndicates"] = await _migrate_syndicates(
                syndicates_dir, registry, oci, dry_run
            )
        else:
            warning(f"Syndicates directory not found: {syndicates_dir}")

    # Print summary
    console.print()
    console.print("[bold]Migration Summary[/bold]")
    console.print()

    for resource_type, counts in results.items():
        status = "✅" if counts["failed"] == 0 else "⚠️"
        console.print(
            f"  {status} {resource_type}: "
            f"[green]{counts['migrated']} migrated[/green], "
            f"[yellow]{counts['skipped']} skipped[/yellow], "
            f"[red]{counts['failed']} failed[/red]"
        )

    if dry_run:
        console.print()
        warning("Dry run - no changes made")


async def _migrate_skills(
    skills_dir: Path,
    registry: RegistryClient,
    oci: KubaniOCIClient,
    dry_run: bool,
) -> dict:
    """Migrate all skills from the filesystem."""
    counts = {"migrated": 0, "skipped": 0, "failed": 0}

    # Find all SKILL.md files
    skill_files = list(skills_dir.rglob("SKILL.md"))
    info(f"Found {len(skill_files)} skills")

    for skill_md in skill_files:
        skill_dir = skill_md.parent

        try:
            # Parse skill metadata
            metadata = _parse_skill_md(skill_md)
            name = metadata.get("name", skill_dir.name)

            # Derive domain/category from path
            rel_path = skill_dir.relative_to(skills_dir)
            parts = rel_path.parts

            if len(parts) >= 2:
                domain = parts[0]
                category = parts[1]
            elif len(parts) >= 1:
                domain = parts[0]
                category = "general"
            else:
                domain = "general"
                category = "general"

            skill_id = f"{domain}/{category}/{name}"

            # Check if already migrated
            existing = await registry.get_skill(skill_id)
            if existing and existing.get("current_version"):
                muted(f"  Skipping {skill_id} (already in registry)")
                counts["skipped"] += 1
                continue

            if dry_run:
                info(f"  Would migrate: {skill_id}")
                counts["migrated"] += 1
                continue

            # Push to OCI
            version = metadata.get("version", "1.0.0")
            oci_result = oci.push(
                source_dir=skill_dir,
                resource_type="skill",
                name=name,
                tag=f"v{version}",
            )

            # Register in PostgreSQL
            if not existing:
                await registry.create_skill(
                    skill_id=skill_id,
                    name=name,
                    description=metadata.get("description"),
                    domain=domain,
                    category=category,
                    oci_repository=oci_result.repository,
                    created_by="migration",
                    metadata={
                        "domain": domain,
                        "category": category,
                        **metadata.get("metadata", {}),
                    },
                )

            # Create version with production status
            await registry.create_skill_version(
                skill_id=skill_id,
                version=version,
                oci_tag=f"v{version}",
                oci_digest=oci_result.digest,
                created_by="migration",
                changelog="Migrated from filesystem",
            )

            # Promote directly to production
            await registry.promote_skill_version(
                skill_id=skill_id,
                version=version,
                target_status="testing",
                promoted_by="migration",
            )
            await registry.promote_skill_version(
                skill_id=skill_id,
                version=version,
                target_status="staging",
                promoted_by="migration",
            )
            await registry.promote_skill_version(
                skill_id=skill_id,
                version=version,
                target_status="production",
                promoted_by="migration",
            )

            success(f"  Migrated: {skill_id}:{version}")
            counts["migrated"] += 1

        except Exception as e:
            error(f"  Failed to migrate {skill_dir}: {e}")
            logger.exception(f"Migration failed for {skill_dir}")
            counts["failed"] += 1

    return counts


async def _migrate_agents(
    agents_dir: Path,
    registry: RegistryClient,
    oci: KubaniOCIClient,
    dry_run: bool,
) -> dict:
    """Migrate all agents from the filesystem."""
    counts = {"migrated": 0, "skipped": 0, "failed": 0}

    # Find all agent directories (have config.yaml or pyproject.toml)
    for agent_dir in agents_dir.iterdir():
        if not agent_dir.is_dir():
            continue

        config_file = agent_dir / "config.yaml"
        pyproject_file = agent_dir / "pyproject.toml"

        if not config_file.exists() and not pyproject_file.exists():
            continue

        try:
            # Parse agent metadata
            if config_file.exists():
                config = yaml.safe_load(config_file.read_text())
                name = config.get("name", agent_dir.name)
                version = config.get("version", "1.0.0")
                description = config.get("description", "")
            else:
                import tomllib

                pyproject = tomllib.loads(pyproject_file.read_text())
                project = pyproject.get("project", {})
                name = project.get("name", agent_dir.name)
                version = project.get("version", "1.0.0")
                description = project.get("description", "")

            # Skip core-agents (it's a library)
            if name == "core-agents":
                muted(f"  Skipping {name} (library)")
                counts["skipped"] += 1
                continue

            # Check if already migrated
            existing = await registry.get_agent(name)
            if existing and existing.get("current_version"):
                muted(f"  Skipping {name} (already in registry)")
                counts["skipped"] += 1
                continue

            if dry_run:
                info(f"  Would migrate: {name}")
                counts["migrated"] += 1
                continue

            # Push to OCI
            oci_result = oci.push(
                source_dir=agent_dir,
                resource_type="agent",
                name=name,
                tag=f"v{version}",
            )

            # Register in PostgreSQL (agents table already exists)
            # We need to add/update with OCI info
            await registry._request(
                "POST",
                "/agents",
                json={
                    "id": name,
                    "name": name,
                    "description": description,
                    "version": version,
                    "current_version": version,
                    "oci_repository": oci_result.repository,
                    "status": "production",
                    "metadata": {"source": "migration"},
                },
            )

            # Create agent version
            await registry.create_agent_version(
                agent_id=name,
                version=version,
                oci_tag=f"v{version}",
                oci_digest=oci_result.digest,
                created_by="migration",
                changelog="Migrated from filesystem",
            )

            success(f"  Migrated: {name}:{version}")
            counts["migrated"] += 1

        except Exception as e:
            error(f"  Failed to migrate {agent_dir.name}: {e}")
            logger.exception(f"Migration failed for {agent_dir}")
            counts["failed"] += 1

    return counts


async def _migrate_syndicates(
    syndicates_dir: Path,
    registry: RegistryClient,
    oci: KubaniOCIClient,
    dry_run: bool,
) -> dict:
    """Migrate all syndicates from the filesystem."""
    counts = {"migrated": 0, "skipped": 0, "failed": 0}

    # Find all syndicate directories
    for syndicate_dir in syndicates_dir.iterdir():
        if not syndicate_dir.is_dir():
            continue

        config_file = syndicate_dir / "config.yaml"
        if not config_file.exists():
            continue

        try:
            # Parse syndicate metadata
            config = yaml.safe_load(config_file.read_text())
            name = config.get("name", syndicate_dir.name)
            version = config.get("version", "1.0.0")
            description = config.get("description", "")
            agent_refs = [{"agent": a, "version": "latest"} for a in config.get("agents", [])]

            # Check if already migrated
            existing = await registry.get_syndicate(name)
            if existing and existing.get("current_version"):
                muted(f"  Skipping {name} (already in registry)")
                counts["skipped"] += 1
                continue

            if dry_run:
                info(f"  Would migrate: {name}")
                counts["migrated"] += 1
                continue

            # Push to OCI
            oci_result = oci.push(
                source_dir=syndicate_dir,
                resource_type="syndicate",
                name=name,
                tag=f"v{version}",
            )

            # Register in PostgreSQL
            await registry.create_syndicate(
                syndicate_id=name,
                name=name,
                description=description,
                oci_repository=oci_result.repository,
                created_by="migration",
                metadata={"source": "migration"},
            )

            # Create syndicate version
            await registry.create_syndicate_version(
                syndicate_id=name,
                version=version,
                oci_tag=f"v{version}",
                oci_digest=oci_result.digest,
                agent_refs=agent_refs,
                created_by="migration",
                changelog="Migrated from filesystem",
            )

            success(f"  Migrated: {name}:{version}")
            counts["migrated"] += 1

        except Exception as e:
            error(f"  Failed to migrate {syndicate_dir.name}: {e}")
            logger.exception(f"Migration failed for {syndicate_dir}")
            counts["failed"] += 1

    return counts


def _parse_skill_md(path: Path) -> dict:
    """Parse SKILL.md frontmatter."""
    content = path.read_text()
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return yaml.safe_load(parts[1]) or {}
    return {}
