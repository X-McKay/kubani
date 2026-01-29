"""Registry management commands for skills, agents, and syndicates.

Provides CLI commands for pushing to and pulling from the OCI registry,
as well as promoting resources through the lifecycle stages.
"""

import asyncio
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="registry",
    help="Manage skills, agents, and syndicates in the OCI registry",
    no_args_is_help=True,
)

console = Console()

ResourceType = Literal["skill", "agent", "syndicate"]


def find_project_root() -> Path:
    """Find the kubani project root directory."""
    current = Path.cwd()
    while current != current.parent:
        if (current / "agents").exists() or (current / "skills").exists():
            return current
        current = current.parent
    return Path.cwd()


@app.command()
def push(
    resource_type: Annotated[str, typer.Argument(help="Resource type: skill, agent, or syndicate")],
    name: Annotated[str, typer.Argument(help="Resource name")],
    version: Annotated[str, typer.Argument(help="Version tag (e.g., v1.0.0)")],
    source: Annotated[Path, typer.Option("--source", "-s", help="Source directory")] = None,
    changelog: Annotated[
        str, typer.Option("--changelog", "-c", help="Changelog for this version")
    ] = None,
    registry_url: Annotated[
        str, typer.Option("--registry-url", envvar="REGISTRY_URL", help="Registry API URL")
    ] = "https://metadata.almckay.io",
    oci_registry: Annotated[
        str, typer.Option("--oci-registry", envvar="KUBANI_OCI_REGISTRY", help="OCI registry URL")
    ] = "registry.almckay.io",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be pushed")] = False,
):
    """Push a resource to the OCI registry and register metadata."""
    from kubani.cli.oci import KubaniOCIClient, OCIPushResult
    from kubani.cli.registry_client import RegistryClient

    if resource_type not in ("skill", "agent", "syndicate"):
        console.print(f"[red]Invalid resource type: {resource_type}[/red]")
        console.print("Valid types: skill, agent, syndicate")
        raise typer.Exit(1)

    # Determine source directory
    project_root = find_project_root()
    if source is None:
        if resource_type == "skill":
            source = project_root / "skills" / name
        elif resource_type == "agent":
            source = project_root / "agents" / name
        else:
            source = project_root / "syndicates" / name

    if not source.is_dir():
        console.print(f"[red]Source directory not found: {source}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Pushing {resource_type} '{name}' v{version}[/bold]")
    console.print(f"  Source: {source}")
    console.print(f"  OCI Registry: {oci_registry}")
    console.print(f"  API Registry: {registry_url}")

    if dry_run:
        console.print("\n[yellow]Dry run - no changes made[/yellow]")
        return

    # Push to OCI registry
    console.print("\n[dim]Packaging and pushing to OCI registry...[/dim]")
    oci_client = KubaniOCIClient(registry_url=oci_registry)

    try:
        result: OCIPushResult = oci_client.push(
            source_dir=source,
            resource_type=resource_type,  # type: ignore
            name=name,
            tag=version,
        )
        console.print(f"[green]✓ Pushed to OCI: {result.repository}:{result.tag}[/green]")
        console.print(f"  Digest: {result.digest}")
        console.print(f"  Size: {result.size_bytes:,} bytes")
    except Exception as e:
        console.print(f"[red]✗ Failed to push to OCI registry: {e}[/red]")
        raise typer.Exit(1)

    # Register version in metadata registry
    console.print("\n[dim]Registering version in metadata registry...[/dim]")

    async def register_version():
        client = RegistryClient(registry_url=registry_url)
        if resource_type == "skill":
            # Ensure skill exists
            try:
                await client.get_skill(name)
            except Exception:
                await client.create_skill(
                    name=name,
                    description=f"Skill: {name}",
                    category="general",
                )
            # Create version
            return await client.create_skill_version(
                skill_name=name,
                version=version,
                oci_tag=version,
                oci_digest=result.digest,
                created_by="cli:kubani",
                changelog=changelog,
            )
        elif resource_type == "agent":
            # Ensure agent exists
            try:
                await client.get_agent(name)
            except Exception:
                await client.create_agent(
                    id=name,
                    name=name,
                    description=f"Agent: {name}",
                )
            # Create version
            return await client.create_agent_version(
                agent_id=name,
                version=version,
                oci_tag=version,
                oci_digest=result.digest,
                created_by="cli:kubani",
                changelog=changelog,
            )
        else:  # syndicate
            # Ensure syndicate exists
            try:
                await client.get_syndicate(name)
            except Exception:
                await client.create_syndicate(
                    id=name,
                    name=name,
                    description=f"Syndicate: {name}",
                )
            # Create version
            return await client.create_syndicate_version(
                syndicate_id=name,
                version=version,
                oci_tag=version,
                oci_digest=result.digest,
                created_by="cli:kubani",
                changelog=changelog,
            )

    try:
        version_info = asyncio.run(register_version())
        console.print(f"[green]✓ Registered version: {version_info.version}[/green]")
        console.print(f"  Status: {version_info.status}")
    except Exception as e:
        console.print(f"[red]✗ Failed to register version: {e}[/red]")
        raise typer.Exit(1)

    console.print(
        f"\n[green bold]Successfully pushed {resource_type} '{name}' v{version}[/green bold]"
    )


@app.command()
def pull(
    resource_type: Annotated[str, typer.Argument(help="Resource type: skill, agent, or syndicate")],
    name: Annotated[str, typer.Argument(help="Resource name")],
    version: Annotated[
        str, typer.Argument(help="Version tag (e.g., v1.0.0 or 'latest')")
    ] = "latest",
    dest: Annotated[Path, typer.Option("--dest", "-d", help="Destination directory")] = None,
    registry_url: Annotated[
        str, typer.Option("--registry-url", envvar="REGISTRY_URL", help="Registry API URL")
    ] = "https://metadata.almckay.io",
    oci_registry: Annotated[
        str, typer.Option("--oci-registry", envvar="KUBANI_OCI_REGISTRY", help="OCI registry URL")
    ] = "registry.almckay.io",
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Overwrite existing directory")
    ] = False,
):
    """Pull a resource from the OCI registry."""
    import shutil

    from kubani.cli.oci import KubaniOCIClient
    from kubani.cli.registry_client import RegistryClient

    if resource_type not in ("skill", "agent", "syndicate"):
        console.print(f"[red]Invalid resource type: {resource_type}[/red]")
        console.print("Valid types: skill, agent, syndicate")
        raise typer.Exit(1)

    # Determine destination directory
    project_root = find_project_root()
    if dest is None:
        if resource_type == "skill":
            dest = project_root / "skills" / name
        elif resource_type == "agent":
            dest = project_root / "agents" / name
        else:
            dest = project_root / "syndicates" / name

    # Resolve 'latest' version
    if version == "latest":
        console.print(f"[dim]Resolving latest version for {resource_type} '{name}'...[/dim]")

        async def get_latest_version():
            client = RegistryClient(registry_url=registry_url)
            if resource_type == "skill":
                return await client.get_skill_version(name, "latest")
            elif resource_type == "agent":
                return await client.get_agent_version(name, "latest")
            else:
                return await client.get_syndicate_version(name, "latest")

        try:
            version_info = asyncio.run(get_latest_version())
            version = version_info.version
            console.print(f"  Latest version: {version}")
        except Exception as e:
            console.print(f"[red]✗ Failed to resolve latest version: {e}[/red]")
            raise typer.Exit(1)

    console.print(f"[bold]Pulling {resource_type} '{name}' v{version}[/bold]")
    console.print(f"  Destination: {dest}")

    # Check if destination exists
    if dest.exists():
        if force:
            console.print(f"[yellow]Removing existing directory: {dest}[/yellow]")
            shutil.rmtree(dest)
        else:
            console.print(f"[red]Destination already exists: {dest}[/red]")
            console.print("Use --force to overwrite")
            raise typer.Exit(1)

    # Pull from OCI registry
    console.print("\n[dim]Pulling from OCI registry...[/dim]")
    oci_client = KubaniOCIClient(registry_url=oci_registry)

    try:
        result = oci_client.pull(
            resource_type=resource_type,  # type: ignore
            name=name,
            tag=version,
            dest_dir=dest,
        )
        console.print(f"[green]✓ Pulled to: {result.extracted_path}[/green]")
        console.print(f"  Digest: {result.digest}")
    except Exception as e:
        console.print(f"[red]✗ Failed to pull from OCI registry: {e}[/red]")
        raise typer.Exit(1)

    console.print(
        f"\n[green bold]Successfully pulled {resource_type} '{name}' v{version}[/green bold]"
    )


@app.command()
def promote(
    resource_type: Annotated[str, typer.Argument(help="Resource type: skill, agent, or syndicate")],
    name: Annotated[str, typer.Argument(help="Resource name")],
    version: Annotated[str, typer.Argument(help="Version to promote")],
    promoted_by: Annotated[
        str, typer.Option("--by", "-b", help="Who is promoting")
    ] = "cli:kubani",
    registry_url: Annotated[
        str, typer.Option("--registry-url", envvar="REGISTRY_URL", help="Registry API URL")
    ] = "https://metadata.almckay.io",
):
    """Promote a resource version to the next lifecycle stage.

    Lifecycle: draft -> testing -> staging -> production
    """
    from kubani.cli.registry_client import RegistryClient

    if resource_type not in ("skill", "agent", "syndicate"):
        console.print(f"[red]Invalid resource type: {resource_type}[/red]")
        console.print("Valid types: skill, agent, syndicate")
        raise typer.Exit(1)

    async def do_promote():
        client = RegistryClient(registry_url=registry_url)
        if resource_type == "skill":
            current = await client.get_skill_version(name, version)
            promoted = await client.promote_skill_version(name, version, promoted_by)
        elif resource_type == "agent":
            current = await client.get_agent_version(name, version)
            promoted = await client.promote_agent_version(name, version, promoted_by)
        else:
            current = await client.get_syndicate_version(name, version)
            promoted = await client.promote_syndicate_version(name, version, promoted_by)
        return current, promoted

    console.print(f"[bold]Promoting {resource_type} '{name}' v{version}[/bold]")

    try:
        current, promoted = asyncio.run(do_promote())
        console.print(f"[green]✓ Promoted: {current.status} -> {promoted.status}[/green]")
        console.print(f"  Promoted by: {promoted_by}")
        if promoted.promoted_at:
            console.print(f"  Promoted at: {promoted.promoted_at}")
    except Exception as e:
        console.print(f"[red]✗ Failed to promote: {e}[/red]")
        raise typer.Exit(1)


@app.command("list")
def list_resources(
    resource_type: Annotated[str, typer.Argument(help="Resource type: skill, agent, or syndicate")],
    status: Annotated[str, typer.Option("--status", "-s", help="Filter by status")] = None,
    registry_url: Annotated[
        str, typer.Option("--registry-url", envvar="REGISTRY_URL", help="Registry API URL")
    ] = "https://metadata.almckay.io",
):
    """List resources in the registry."""
    from kubani.cli.registry_client import RegistryClient

    if resource_type not in ("skill", "agent", "syndicate"):
        console.print(f"[red]Invalid resource type: {resource_type}[/red]")
        console.print("Valid types: skill, agent, syndicate")
        raise typer.Exit(1)

    async def fetch_resources():
        client = RegistryClient(registry_url=registry_url)
        if resource_type == "skill":
            return await client.list_skills(status=status)
        elif resource_type == "agent":
            return await client.list_agents(status=status)
        else:
            return await client.list_syndicates(status=status)

    try:
        resources = asyncio.run(fetch_resources())
    except Exception as e:
        console.print(f"[red]✗ Failed to list resources: {e}[/red]")
        raise typer.Exit(1)

    if not resources:
        console.print(f"No {resource_type}s found")
        return

    table = Table(title=f"{resource_type.capitalize()}s")
    table.add_column("Name", style="cyan")
    table.add_column("Version", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("OCI Repository")

    for r in resources:
        table.add_row(
            r.name,
            r.current_version or "-",
            r.status or "-",
            r.oci_repository or "-",
        )

    console.print(table)


@app.command()
def versions(
    resource_type: Annotated[str, typer.Argument(help="Resource type: skill, agent, or syndicate")],
    name: Annotated[str, typer.Argument(help="Resource name")],
    registry_url: Annotated[
        str, typer.Option("--registry-url", envvar="REGISTRY_URL", help="Registry API URL")
    ] = "https://metadata.almckay.io",
):
    """List versions of a resource."""
    from kubani.cli.registry_client import RegistryClient

    if resource_type not in ("skill", "agent", "syndicate"):
        console.print(f"[red]Invalid resource type: {resource_type}[/red]")
        console.print("Valid types: skill, agent, syndicate")
        raise typer.Exit(1)

    async def fetch_versions():
        client = RegistryClient(registry_url=registry_url)
        if resource_type == "skill":
            return await client.list_skill_versions(name)
        elif resource_type == "agent":
            return await client.list_agent_versions(name)
        else:
            return await client.list_syndicate_versions(name)

    try:
        version_list = asyncio.run(fetch_versions())
    except Exception as e:
        console.print(f"[red]✗ Failed to list versions: {e}[/red]")
        raise typer.Exit(1)

    if not version_list:
        console.print(f"No versions found for {resource_type} '{name}'")
        return

    table = Table(title=f"Versions of {resource_type} '{name}'")
    table.add_column("Version", style="cyan")
    table.add_column("Status", style="yellow")
    table.add_column("OCI Tag", style="green")
    table.add_column("Created At")
    table.add_column("Created By")

    for v in version_list:
        table.add_row(
            v.version,
            v.status,
            v.oci_tag or "-",
            str(v.created_at)[:19] if v.created_at else "-",
            v.created_by or "-",
        )

    console.print(table)
