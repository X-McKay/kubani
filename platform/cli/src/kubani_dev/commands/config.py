"""Configuration management commands."""

import os
import subprocess
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

app = typer.Typer(
    name="config",
    help="Configuration management for Kubani",
    no_args_is_help=True,
)

console = Console()

# Config directory
REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent.parent
CONFIG_DIR = REPO_ROOT / "config"


def _get_environment() -> str:
    """Get current environment."""
    return os.getenv("KUBANI_ENVIRONMENT", "development")


def _load_config(env: str | None = None) -> dict[str, Any]:
    """Load merged configuration for environment."""
    env = env or _get_environment()

    config: dict[str, Any] = {}

    # Load default
    default_path = CONFIG_DIR / "default.yaml"
    if default_path.exists():
        with open(default_path) as f:
            config = yaml.safe_load(f) or {}

    # Load environment-specific
    env_path = CONFIG_DIR / f"{env}.yaml"
    if env_path.exists():
        with open(env_path) as f:
            env_config = yaml.safe_load(f) or {}
            config = _deep_merge(config, env_config)

    # Load local overrides
    local_path = CONFIG_DIR / "local.yaml"
    if local_path.exists():
        with open(local_path) as f:
            local_config = yaml.safe_load(f) or {}
            config = _deep_merge(config, local_config)

    return config


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _get_nested(config: dict, key: str) -> Any:
    """Get nested value using dot notation."""
    parts = key.split(".")
    value = config
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def _set_nested(config: dict, key: str, value: Any) -> None:
    """Set nested value using dot notation."""
    parts = key.split(".")
    target = config
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


@app.command()
def get(
    key: str = typer.Argument(..., help="Config key (dot notation, e.g., 'llm.api_url')"),
    env: str = typer.Option(None, "--env", "-e", help="Environment to read from"),
):
    """Get a configuration value."""
    config = _load_config(env)
    value = _get_nested(config, key)

    if value is None:
        console.print(f"[yellow]Key not found: {key}[/yellow]")
        raise typer.Exit(1)

    if isinstance(value, (dict, list)):
        console.print(yaml.dump(value, default_flow_style=False))
    else:
        console.print(str(value))


@app.command("set")
def set_config(
    key: str = typer.Argument(..., help="Config key (dot notation)"),
    value: str = typer.Argument(..., help="Value to set"),
    env: str = typer.Option(None, "--env", "-e", help="Environment config to modify"),
    local: bool = typer.Option(False, "--local", "-l", help="Write to local.yaml"),
):
    """Set a configuration value."""
    # Determine which file to modify
    if local:
        config_file = CONFIG_DIR / "local.yaml"
    elif env:
        config_file = CONFIG_DIR / f"{env}.yaml"
    else:
        config_file = CONFIG_DIR / "local.yaml"
        console.print("[dim]Writing to local.yaml (use --env to modify environment config)[/dim]")

    # Load existing config
    config: dict[str, Any] = {}
    if config_file.exists():
        with open(config_file) as f:
            config = yaml.safe_load(f) or {}

    # Parse value (try to infer type)
    parsed_value: Any = value
    if value.lower() == "true":
        parsed_value = True
    elif value.lower() == "false":
        parsed_value = False
    elif value.isdigit():
        parsed_value = int(value)
    else:
        try:
            parsed_value = float(value)
        except ValueError:
            pass

    # Set the value
    _set_nested(config, key, parsed_value)

    # Ensure config directory exists
    config_file.parent.mkdir(parents=True, exist_ok=True)

    # Write back
    with open(config_file, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    console.print(f"[green]Set {key} = {parsed_value} in {config_file.name}[/green]")


@app.command()
def show(
    env: str = typer.Option(None, "--env", "-e", help="Environment to show"),
    section: str = typer.Option(None, "--section", "-s", help="Show only this section"),
):
    """Show effective configuration."""
    env = env or _get_environment()
    config = _load_config(env)

    if section:
        config = _get_nested(config, section)
        if config is None:
            console.print(f"[yellow]Section not found: {section}[/yellow]")
            raise typer.Exit(1)

    yaml_str = yaml.dump(config, default_flow_style=False, sort_keys=False)
    syntax = Syntax(yaml_str, "yaml", theme="monokai", line_numbers=True)

    title = f"Configuration ({env})"
    if section:
        title += f" - {section}"

    console.print(Panel(syntax, title=title))


@app.command()
def validate():
    """Validate configuration files against schema."""
    errors = []

    for env in ["development", "production"]:
        try:
            config = _load_config(env)

            # Try to import and validate against Pydantic model
            try:
                from core_agents.config_unified import KubaniConfig

                KubaniConfig(**config)
                console.print(f"[green]✓ {env}: Valid[/green]")
            except ImportError:
                # core_agents not available, just check YAML is valid
                console.print(f"[green]✓ {env}: YAML valid (schema validation skipped)[/green]")

        except yaml.YAMLError as e:
            console.print(f"[red]✗ {env}: Invalid YAML[/red]")
            errors.append(f"  {env}: {str(e)}")
        except Exception as e:
            console.print(f"[red]✗ {env}: Error - {e}[/red]")
            errors.append(f"  {env}: {str(e)}")

    if errors:
        console.print("\n[red]Validation errors:[/red]")
        for error in errors:
            console.print(error)
        raise typer.Exit(1)

    console.print("\n[green]All configurations valid![/green]")


@app.command()
def edit(
    env: str = typer.Option(None, "--env", "-e", help="Environment config to edit"),
    local: bool = typer.Option(False, "--local", "-l", help="Edit local.yaml"),
):
    """Open configuration file in editor."""
    if local:
        config_file = CONFIG_DIR / "local.yaml"
    elif env:
        config_file = CONFIG_DIR / f"{env}.yaml"
    else:
        config_file = CONFIG_DIR / "default.yaml"

    if not config_file.exists():
        console.print(f"[yellow]Creating {config_file.name}...[/yellow]")
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.touch()

    editor = os.getenv("EDITOR", "vim")
    subprocess.run([editor, str(config_file)])


@app.command()
def diff(
    env1: str = typer.Argument("development", help="First environment"),
    env2: str = typer.Argument("production", help="Second environment"),
):
    """Compare configurations between environments."""
    config1 = _load_config(env1)
    config2 = _load_config(env2)

    yaml1 = yaml.dump(config1, default_flow_style=False, sort_keys=True)
    yaml2 = yaml.dump(config2, default_flow_style=False, sort_keys=True)

    # Write to temp files and diff
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=f"_{env1}.yaml", delete=False) as f1:
        f1.write(yaml1)
        path1 = f1.name

    with tempfile.NamedTemporaryFile(mode="w", suffix=f"_{env2}.yaml", delete=False) as f2:
        f2.write(yaml2)
        path2 = f2.name

    try:
        subprocess.run(["diff", "--color=always", "-u", path1, path2])
    finally:
        os.unlink(path1)
        os.unlink(path2)
