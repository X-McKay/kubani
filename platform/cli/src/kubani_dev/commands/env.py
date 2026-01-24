"""Environment management commands."""

import os
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="env",
    help="Environment management for Kubani",
    no_args_is_help=True,
)

console = Console()

REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent.parent
CONFIG_DIR = REPO_ROOT / "config"
ENV_FILE = REPO_ROOT / ".kubani-env"


def _get_current_env() -> str:
    """Get current environment from file or env var."""
    if ENV_FILE.exists():
        return ENV_FILE.read_text().strip()
    return os.getenv("KUBANI_ENVIRONMENT", "development")


def _set_current_env(env: str) -> None:
    """Set current environment in file."""
    ENV_FILE.write_text(env)


@app.command("list")
def list_envs():
    """List available environments."""
    current = _get_current_env()

    table = Table(title="Available Environments")
    table.add_column("Environment", style="cyan")
    table.add_column("Config File", style="green")
    table.add_column("Status", style="yellow")

    # Find all environment configs
    envs = set()
    if CONFIG_DIR.exists():
        for config_file in CONFIG_DIR.glob("*.yaml"):
            name = config_file.stem
            if name not in ("default", "local"):
                envs.add(name)

    # Always include development and production
    envs.add("development")
    envs.add("production")

    for env in sorted(envs):
        config_file = CONFIG_DIR / f"{env}.yaml"
        exists = config_file.exists()
        status = "[green]active[/green]" if env == current else ""

        table.add_row(
            env,
            f"{env}.yaml" if exists else "[dim]uses default.yaml[/dim]",
            status,
        )

    console.print(table)


@app.command()
def use(
    env: str = typer.Argument(..., help="Environment to switch to"),
):
    """Switch to a different environment."""
    # Validate environment exists or can be created
    config_file = CONFIG_DIR / f"{env}.yaml"
    default_file = CONFIG_DIR / "default.yaml"

    if not config_file.exists() and not default_file.exists():
        console.print(f"[red]No config found for environment: {env}[/red]")
        raise typer.Exit(1)

    _set_current_env(env)
    console.print(f"[green]Switched to environment: {env}[/green]")

    if not config_file.exists():
        console.print(f"[dim]Note: Using default.yaml (no {env}.yaml found)[/dim]")


@app.command()
def show():
    """Show current environment details."""
    current = _get_current_env()

    config_file = CONFIG_DIR / f"{current}.yaml"
    local_file = CONFIG_DIR / "local.yaml"

    info = [
        f"[cyan]Environment:[/cyan] {current}",
        f"[cyan]Config file:[/cyan] {config_file if config_file.exists() else 'default.yaml'}",
        f"[cyan]Local overrides:[/cyan] {'yes' if local_file.exists() else 'no'}",
        f"[cyan]Env var override:[/cyan] {os.getenv('KUBANI_ENVIRONMENT', 'not set')}",
    ]

    console.print(Panel("\n".join(info), title="Current Environment"))


@app.command()
def init(
    env: str = typer.Argument(..., help="Environment name to initialize"),
    copy_from: str = typer.Option("default", help="Copy settings from this config"),
):
    """Initialize a new environment configuration."""
    target_file = CONFIG_DIR / f"{env}.yaml"

    if target_file.exists():
        console.print(f"[yellow]Environment {env} already exists[/yellow]")
        raise typer.Exit(1)

    source_file = CONFIG_DIR / f"{copy_from}.yaml"
    if not source_file.exists():
        console.print(f"[red]Source config not found: {copy_from}.yaml[/red]")
        raise typer.Exit(1)

    with open(source_file) as f:
        config = yaml.safe_load(f) or {}

    # Ensure config directory exists
    target_file.parent.mkdir(parents=True, exist_ok=True)

    with open(target_file, "w") as f:
        f.write(f"# {env.title()} environment configuration\n")
        f.write(f"# Copied from {copy_from}.yaml\n\n")
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    console.print(f"[green]Created {target_file.name}[/green]")
