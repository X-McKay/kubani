# Phase 6: CLI & Config Consolidation - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

> **Note (2026-01-23)**: The kubani CLI has been moved from `tools/kubani` to `platform/cli`.
> Update installation command: `uv pip install -e platform/cli`

**Goal:** Consolidate cluster-mgr commands into kubani and create unified configuration management, resulting in a single CLI entry point for all Kubani operations.

**Architecture:** Add `cluster` and `config` command groups to kubani using Typer, migrate cluster-mgr functionality, and create a configuration management layer that bridges Ansible inventory and Pydantic config systems.

**Tech Stack:** Python 3.11+, Typer, Pydantic, PyYAML, Rich (for output formatting)

**Risk Level:** MEDIUM - Affects developer workflow. Mitigated by keeping cluster-mgr as deprecated alias initially.

---

## Pre-Flight Checklist

Before starting, verify:
```bash
# On feature/restructure branch
git branch --show-current

# Phase 5 complete
grep "version" agents/k8s-monitor/pyproject.toml
# Expected: version = "0.4.0"

# kubani installed
kubani --version

# cluster-mgr exists
ls cluster_manager/cli.py

# Config directory exists
ls config/
```

---

## Current State Analysis

### Two CLI Tools

| Tool | Purpose | Commands |
|------|---------|----------|
| `cluster-mgr` | Infrastructure/cluster lifecycle | 8 commands (discover, add-node, provision, status, etc.) |
| `kubani` | Agent development lifecycle | 22+ commands (run, test, eval, skill, agent, etc.) |

### Two Config Systems

| System | Purpose | Location |
|--------|---------|----------|
| Ansible inventory | Infrastructure variables | `inventory/group_vars/` |
| Pydantic config | Application settings | `config/*.yaml` |

### Target State

```
kubani
├── init, run, test, eval, ...     # Existing agent commands
├── skill [draft|eval|improve|...] # Existing skill commands
├── agent [run|list|info|eval]     # Existing agent commands
├── cluster                         # NEW: Infrastructure commands
│   ├── discover                   # From cluster-mgr
│   ├── add-node                   # From cluster-mgr
│   ├── remove-node                # From cluster-mgr
│   ├── provision                  # From cluster-mgr
│   └── status                     # From cluster-mgr
├── config                          # NEW: Configuration management
│   ├── get KEY                    # Get config value
│   ├── set KEY VALUE              # Set config value
│   ├── show                       # Show effective config
│   ├── validate                   # Validate config files
│   └── edit                       # Open config in editor
└── env                             # NEW: Environment management
    ├── list                       # List environments
    ├── use ENV                    # Switch environment
    └── show                       # Show current environment
```

---

## Batch 1: Cluster Command Group (Tasks 1-4)

### Task 1: Create Cluster Command Group Structure

**Files:**
- Create: `tools/kubani/src/kubani_dev/commands/cluster.py`
- Modify: `tools/kubani/src/kubani_dev/cli.py`

**Step 1: Create cluster command module**

```python
"""Cluster management commands - migrated from cluster-mgr."""

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="cluster",
    help="Kubernetes cluster infrastructure management",
    no_args_is_help=True,
)

console = Console()


@app.command()
def discover(
    show_offline: bool = typer.Option(False, "--offline", help="Include offline nodes"),
):
    """Discover Tailscale nodes available for cluster membership."""
    from kubani_dev.commands.cluster_impl import discover_nodes

    discover_nodes(show_offline=show_offline)


@app.command("add-node")
def add_node(
    hostname: str = typer.Argument(..., help="Node hostname"),
    role: str = typer.Option("worker", help="Node role (control_plane, worker)"),
    labels: list[str] = typer.Option([], "--label", "-l", help="Node labels"),
    taints: list[str] = typer.Option([], "--taint", "-t", help="Node taints"),
    gpu: bool = typer.Option(False, "--gpu", help="Node has GPU"),
):
    """Add a node to the Kubernetes cluster."""
    from kubani_dev.commands.cluster_impl import add_cluster_node

    add_cluster_node(
        hostname=hostname,
        role=role,
        labels=labels,
        taints=taints,
        gpu=gpu,
    )


@app.command("remove-node")
def remove_node(
    hostname: str = typer.Argument(..., help="Node hostname"),
    drain: bool = typer.Option(True, help="Drain node before removal"),
    force: bool = typer.Option(False, "--force", help="Force removal"),
):
    """Remove a node from the Kubernetes cluster."""
    from kubani_dev.commands.cluster_impl import remove_cluster_node

    remove_cluster_node(hostname=hostname, drain=drain, force=force)


@app.command()
def provision(
    tags: list[str] = typer.Option([], "--tag", "-t", help="Ansible tags"),
    limit: str = typer.Option(None, "--limit", "-l", help="Limit to hosts"),
    check: bool = typer.Option(False, "--check", help="Dry run mode"),
    playbook: str = typer.Option("site.yml", help="Playbook to run"),
):
    """Run Ansible provisioning playbooks."""
    from kubani_dev.commands.cluster_impl import run_provision

    run_provision(tags=tags, limit=limit, check=check, playbook=playbook)


@app.command()
def status(
    show_pods: bool = typer.Option(False, "--pods", "-p", help="Show pod status"),
    namespace: str = typer.Option(None, "--namespace", "-n", help="Filter by namespace"),
):
    """Show cluster status and health."""
    from kubani_dev.commands.cluster_impl import show_cluster_status

    show_cluster_status(show_pods=show_pods, namespace=namespace)
```

**Step 2: Register cluster app in main CLI**

Add to `cli.py`:
```python
from kubani_dev.commands.cluster import app as cluster_app

app.add_typer(cluster_app, name="cluster")
```

**Step 3: Commit**

```bash
git add tools/kubani/src/kubani_dev/commands/cluster.py
git add tools/kubani/src/kubani_dev/cli.py
git commit -m "feat(kubani): add cluster command group structure

Commands added:
- cluster discover: Find Tailscale nodes
- cluster add-node: Add node to cluster
- cluster remove-node: Remove node from cluster
- cluster provision: Run Ansible playbooks
- cluster status: Show cluster health

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 2: Implement Cluster Command Logic

**Files:**
- Create: `tools/kubani/src/kubani_dev/commands/cluster_impl.py`

**Step 1: Create implementation module**

```python
"""Implementation for cluster commands - adapted from cluster_manager."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

# Paths
REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent.parent
INVENTORY_PATH = REPO_ROOT / "inventory"
ANSIBLE_PATH = REPO_ROOT / "infrastructure" / "ansible"


def discover_nodes(show_offline: bool = False) -> None:
    """Discover Tailscale nodes available for cluster membership."""
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        console.print(f"[red]Error running tailscale: {e}[/red]")
        return
    except json.JSONDecodeError:
        console.print("[red]Failed to parse tailscale output[/red]")
        return

    peers = data.get("Peer", {})
    current = data.get("Self", {})

    table = Table(title="Tailscale Nodes")
    table.add_column("Hostname", style="cyan")
    table.add_column("IP", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("OS", style="blue")
    table.add_column("In Cluster", style="magenta")

    # Add self
    table.add_row(
        current.get("HostName", "unknown"),
        current.get("TailscaleIPs", ["?"])[0],
        "online (self)",
        current.get("OS", "?"),
        _check_in_cluster(current.get("HostName", "")),
    )

    # Add peers
    for peer_id, peer in peers.items():
        online = peer.get("Online", False)
        if not online and not show_offline:
            continue

        status = "online" if online else "offline"
        table.add_row(
            peer.get("HostName", "unknown"),
            peer.get("TailscaleIPs", ["?"])[0] if peer.get("TailscaleIPs") else "?",
            status,
            peer.get("OS", "?"),
            _check_in_cluster(peer.get("HostName", "")),
        )

    console.print(table)


def _check_in_cluster(hostname: str) -> str:
    """Check if hostname is in Ansible inventory."""
    hosts_file = INVENTORY_PATH / "hosts.yml"
    if not hosts_file.exists():
        return "?"

    try:
        import yaml
        with open(hosts_file) as f:
            inventory = yaml.safe_load(f)

        # Check all groups for the hostname
        all_hosts = set()
        for group in inventory.get("all", {}).get("children", {}).values():
            if isinstance(group, dict) and "hosts" in group:
                all_hosts.update(group["hosts"].keys())

        return "yes" if hostname in all_hosts else "no"
    except Exception:
        return "?"


def add_cluster_node(
    hostname: str,
    role: str,
    labels: list[str],
    taints: list[str],
    gpu: bool,
) -> None:
    """Add a node to the Ansible inventory."""
    import yaml

    hosts_file = INVENTORY_PATH / "hosts.yml"
    if not hosts_file.exists():
        console.print(f"[red]Inventory file not found: {hosts_file}[/red]")
        return

    with open(hosts_file) as f:
        inventory = yaml.safe_load(f)

    # Determine group based on role
    group = "control_plane" if role == "control_plane" else "workers"

    # Add to appropriate group
    children = inventory.setdefault("all", {}).setdefault("children", {})
    group_data = children.setdefault(group, {}).setdefault("hosts", {})

    if hostname in group_data:
        console.print(f"[yellow]Node {hostname} already exists in {group}[/yellow]")
        return

    # Build host vars
    host_vars: dict[str, Any] = {}
    if labels:
        host_vars["k8s_labels"] = dict(l.split("=") for l in labels if "=" in l)
    if taints:
        host_vars["k8s_taints"] = taints
    if gpu:
        host_vars["gpu_enabled"] = True

    group_data[hostname] = host_vars if host_vars else None

    with open(hosts_file, "w") as f:
        yaml.dump(inventory, f, default_flow_style=False, sort_keys=False)

    console.print(f"[green]Added {hostname} to {group}[/green]")

    if host_vars:
        console.print(f"  Labels: {host_vars.get('k8s_labels', {})}")
        console.print(f"  Taints: {host_vars.get('k8s_taints', [])}")
        console.print(f"  GPU: {host_vars.get('gpu_enabled', False)}")


def remove_cluster_node(hostname: str, drain: bool, force: bool) -> None:
    """Remove a node from the Ansible inventory."""
    import yaml

    hosts_file = INVENTORY_PATH / "hosts.yml"
    if not hosts_file.exists():
        console.print(f"[red]Inventory file not found: {hosts_file}[/red]")
        return

    with open(hosts_file) as f:
        inventory = yaml.safe_load(f)

    # Find and remove from all groups
    found = False
    for group_name, group_data in inventory.get("all", {}).get("children", {}).items():
        if isinstance(group_data, dict) and "hosts" in group_data:
            if hostname in group_data["hosts"]:
                if drain and not force:
                    console.print(f"[yellow]Draining node {hostname}...[/yellow]")
                    try:
                        subprocess.run(
                            ["kubectl", "drain", hostname, "--ignore-daemonsets", "--delete-emptydir-data"],
                            check=True,
                        )
                    except subprocess.CalledProcessError as e:
                        console.print(f"[red]Failed to drain: {e}[/red]")
                        if not force:
                            return

                del group_data["hosts"][hostname]
                found = True
                console.print(f"[green]Removed {hostname} from {group_name}[/green]")

    if not found:
        console.print(f"[yellow]Node {hostname} not found in inventory[/yellow]")
        return

    with open(hosts_file, "w") as f:
        yaml.dump(inventory, f, default_flow_style=False, sort_keys=False)


def run_provision(
    tags: list[str],
    limit: str | None,
    check: bool,
    playbook: str,
) -> None:
    """Run Ansible provisioning."""
    playbook_path = ANSIBLE_PATH / playbook
    if not playbook_path.exists():
        console.print(f"[red]Playbook not found: {playbook_path}[/red]")
        return

    cmd = [
        "ansible-playbook",
        str(playbook_path),
        "-i", str(INVENTORY_PATH / "hosts.yml"),
    ]

    if tags:
        cmd.extend(["--tags", ",".join(tags)])
    if limit:
        cmd.extend(["--limit", limit])
    if check:
        cmd.append("--check")

    console.print(f"[cyan]Running: {' '.join(cmd)}[/cyan]")

    try:
        subprocess.run(cmd, check=True)
        console.print("[green]Provisioning complete[/green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Provisioning failed: {e}[/red]")


def show_cluster_status(show_pods: bool, namespace: str | None) -> None:
    """Show cluster status."""
    # Get nodes
    try:
        result = subprocess.run(
            ["kubectl", "get", "nodes", "-o", "json"],
            capture_output=True,
            text=True,
            check=True,
        )
        nodes = json.loads(result.stdout).get("items", [])
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        console.print(f"[red]Failed to get nodes: {e}[/red]")
        return

    # Node table
    node_table = Table(title="Cluster Nodes")
    node_table.add_column("Name", style="cyan")
    node_table.add_column("Status", style="green")
    node_table.add_column("Roles", style="yellow")
    node_table.add_column("Version", style="blue")
    node_table.add_column("Age", style="magenta")

    for node in nodes:
        name = node["metadata"]["name"]
        conditions = {c["type"]: c["status"] for c in node["status"]["conditions"]}
        status = "Ready" if conditions.get("Ready") == "True" else "NotReady"

        labels = node["metadata"].get("labels", {})
        roles = []
        for label in labels:
            if label.startswith("node-role.kubernetes.io/"):
                roles.append(label.split("/")[1])

        version = node["status"]["nodeInfo"]["kubeletVersion"]

        node_table.add_row(
            name,
            f"[green]{status}[/green]" if status == "Ready" else f"[red]{status}[/red]",
            ", ".join(roles) or "worker",
            version,
            _get_age(node["metadata"]["creationTimestamp"]),
        )

    console.print(node_table)

    # Pod table (optional)
    if show_pods:
        console.print()
        cmd = ["kubectl", "get", "pods", "-A", "-o", "wide"]
        if namespace:
            cmd = ["kubectl", "get", "pods", "-n", namespace, "-o", "wide"]

        subprocess.run(cmd)


def _get_age(timestamp: str) -> str:
    """Convert ISO timestamp to human-readable age."""
    from datetime import datetime, timezone

    try:
        created = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - created

        days = delta.days
        if days > 0:
            return f"{days}d"

        hours = delta.seconds // 3600
        if hours > 0:
            return f"{hours}h"

        minutes = delta.seconds // 60
        return f"{minutes}m"
    except Exception:
        return "?"
```

**Step 2: Commit**

```bash
git add tools/kubani/src/kubani_dev/commands/cluster_impl.py
git commit -m "feat(kubani): implement cluster command logic

Migrated from cluster_manager:
- discover_nodes: Tailscale node discovery
- add_cluster_node: Add to Ansible inventory
- remove_cluster_node: Remove with optional drain
- run_provision: Ansible playbook execution
- show_cluster_status: Node and pod status

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 3: Add Config Command Group

**Files:**
- Create: `tools/kubani/src/kubani_dev/commands/config.py`
- Modify: `tools/kubani/src/kubani_dev/cli.py`

**Step 1: Create config command module**

```python
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
from rich.table import Table

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


@app.command()
def set(
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
    from core_agents.config_unified import KubaniConfig
    from pydantic import ValidationError

    errors = []

    for env in ["development", "production"]:
        try:
            # Set environment and load config
            os.environ["KUBANI_ENVIRONMENT"] = env
            config = _load_config(env)

            # Validate against Pydantic model
            KubaniConfig(**config)
            console.print(f"[green][OK] {env}: Valid[/green]")

        except ValidationError as e:
            console.print(f"[red][FAIL] {env}: Invalid[/red]")
            for error in e.errors():
                loc = ".".join(str(x) for x in error["loc"])
                errors.append(f"  {env}.{loc}: {error['msg']}")
        except Exception as e:
            console.print(f"[red][FAIL] {env}: Error - {e}[/red]")
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
```

**Step 2: Register config app in main CLI**

Add to `cli.py`:
```python
from kubani_dev.commands.config import app as config_app

app.add_typer(config_app, name="config")
```

**Step 3: Commit**

```bash
git add tools/kubani/src/kubani_dev/commands/config.py
git add tools/kubani/src/kubani_dev/cli.py
git commit -m "feat(kubani): add config command group

Commands:
- config get KEY: Get config value (dot notation)
- config set KEY VALUE: Set config value
- config show: Show effective configuration
- config validate: Validate against Pydantic schema
- config edit: Open config in editor
- config diff: Compare environments

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 4: Add Environment Command Group

**Files:**
- Create: `tools/kubani/src/kubani_dev/commands/env.py`
- Modify: `tools/kubani/src/kubani_dev/cli.py`

**Step 1: Create env command module**

```python
"""Environment management commands."""

import os
from pathlib import Path

import typer
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
    import yaml

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

    with open(target_file, "w") as f:
        f.write(f"# {env.title()} environment configuration\n")
        f.write(f"# Copied from {copy_from}.yaml\n\n")
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    console.print(f"[green]Created {target_file.name}[/green]")
```

**Step 2: Register env app in main CLI and add .kubani-env to .gitignore**

Add to `cli.py`:
```python
from kubani_dev.commands.env import app as env_app

app.add_typer(env_app, name="env")
```

Add to `.gitignore`:
```
.kubani-env
```

**Step 3: Commit**

```bash
git add tools/kubani/src/kubani_dev/commands/env.py
git add tools/kubani/src/kubani_dev/cli.py
git add .gitignore
git commit -m "feat(kubani): add env command group

Commands:
- env list: List available environments
- env use ENV: Switch to environment
- env show: Show current environment details
- env init ENV: Initialize new environment config

Environment stored in .kubani-env (gitignored)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Batch 2: Deprecation & Migration (Tasks 5-7)

### Task 5: Deprecate cluster-mgr with Wrapper

**Files:**
- Modify: `cluster_manager/cli.py`

**Step 1: Add deprecation warnings**

Update the cluster-mgr CLI to show deprecation warnings and delegate to kubani:

```python
"""
DEPRECATED: Use kubani cluster commands instead.

This CLI is maintained for backwards compatibility only.
All commands delegate to kubani cluster.
"""

import sys
import warnings

import typer

app = typer.Typer(
    help="[DEPRECATED] Cluster management - use 'kubani cluster' instead",
)


def _deprecation_warning(command: str) -> None:
    """Print deprecation warning."""
    typer.echo(
        typer.style(
            f"WARNING: cluster-mgr is deprecated. Use 'kubani cluster {command}' instead.",
            fg=typer.colors.YELLOW,
        ),
        err=True,
    )


@app.command()
def discover(show_offline: bool = typer.Option(False, "--offline")):
    """[DEPRECATED] Use: kubani cluster discover"""
    _deprecation_warning("discover")
    from kubani_dev.commands.cluster_impl import discover_nodes
    discover_nodes(show_offline=show_offline)


@app.command("add-node")
def add_node(
    hostname: str = typer.Argument(...),
    role: str = typer.Option("worker"),
    labels: list[str] = typer.Option([]),
    taints: list[str] = typer.Option([]),
    gpu: bool = typer.Option(False),
):
    """[DEPRECATED] Use: kubani cluster add-node"""
    _deprecation_warning("add-node")
    from kubani_dev.commands.cluster_impl import add_cluster_node
    add_cluster_node(hostname=hostname, role=role, labels=labels, taints=taints, gpu=gpu)


# ... similar wrappers for other commands ...


@app.command()
def status(show_pods: bool = typer.Option(False, "--pods", "-p")):
    """[DEPRECATED] Use: kubani cluster status"""
    _deprecation_warning("status")
    from kubani_dev.commands.cluster_impl import show_cluster_status
    show_cluster_status(show_pods=show_pods, namespace=None)


if __name__ == "__main__":
    app()
```

**Step 2: Update README with deprecation notice**

Add to `cluster_manager/README.md`:
```markdown
# cluster-mgr (DEPRECATED)

> **DEPRECATED:** This CLI has been consolidated into `kubani`.
> Use `kubani cluster` commands instead.

## Migration Guide

| Old Command | New Command |
|-------------|-------------|
| `cluster-mgr discover` | `kubani cluster discover` |
| `cluster-mgr add-node` | `kubani cluster add-node` |
| `cluster-mgr remove-node` | `kubani cluster remove-node` |
| `cluster-mgr provision` | `kubani cluster provision` |
| `cluster-mgr status` | `kubani cluster status` |
```

**Step 3: Commit**

```bash
git add cluster_manager/
git commit -m "deprecate(cluster-mgr): add deprecation warnings and delegate to kubani

All cluster-mgr commands now:
1. Print deprecation warning
2. Delegate to kubani cluster implementation

Migration path provided in README.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 6: Add Tests for New Commands

**Files:**
- Create: `tools/kubani/tests/test_cluster_commands.py`
- Create: `tools/kubani/tests/test_config_commands.py`
- Create: `tools/kubani/tests/test_env_commands.py`

**Step 1: Create cluster command tests**

```python
"""Tests for cluster commands."""

import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock

from kubani_dev.cli import app

runner = CliRunner()


class TestClusterDiscover:
    """Tests for cluster discover command."""

    @patch("kubani_dev.commands.cluster_impl.subprocess.run")
    def test_discover_shows_nodes(self, mock_run):
        """Test discover command shows tailscale nodes."""
        mock_run.return_value = MagicMock(
            stdout='{"Self": {"HostName": "test-node", "TailscaleIPs": ["100.64.0.1"], "OS": "linux"}, "Peer": {}}',
            returncode=0,
        )

        result = runner.invoke(app, ["cluster", "discover"])

        assert result.exit_code == 0
        assert "test-node" in result.output

    @patch("kubani_dev.commands.cluster_impl.subprocess.run")
    def test_discover_handles_tailscale_error(self, mock_run):
        """Test discover handles tailscale errors gracefully."""
        mock_run.side_effect = FileNotFoundError()

        result = runner.invoke(app, ["cluster", "discover"])

        assert "Error" in result.output


class TestClusterStatus:
    """Tests for cluster status command."""

    @patch("kubani_dev.commands.cluster_impl.subprocess.run")
    def test_status_shows_nodes(self, mock_run):
        """Test status command shows cluster nodes."""
        mock_run.return_value = MagicMock(
            stdout='{"items": [{"metadata": {"name": "node1", "creationTimestamp": "2024-01-01T00:00:00Z", "labels": {}}, "status": {"conditions": [{"type": "Ready", "status": "True"}], "nodeInfo": {"kubeletVersion": "v1.28.0"}}}]}',
            returncode=0,
        )

        result = runner.invoke(app, ["cluster", "status"])

        assert result.exit_code == 0
        assert "node1" in result.output
```

**Step 2: Create config command tests**

```python
"""Tests for config commands."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner
from unittest.mock import patch

from kubani_dev.cli import app

runner = CliRunner()


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create temporary config directory."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Create default config
    default_config = {
        "llm": {"api_url": "http://localhost:8000", "model": "test-model"},
        "temporal": {"host": "localhost:7233"},
    }
    with open(config_dir / "default.yaml", "w") as f:
        yaml.dump(default_config, f)

    return config_dir


class TestConfigGet:
    """Tests for config get command."""

    def test_get_simple_key(self, temp_config_dir):
        """Test getting a simple config key."""
        with patch("kubani_dev.commands.config.CONFIG_DIR", temp_config_dir):
            result = runner.invoke(app, ["config", "get", "llm.api_url"])

        assert result.exit_code == 0
        assert "http://localhost:8000" in result.output

    def test_get_missing_key(self, temp_config_dir):
        """Test getting a missing key returns error."""
        with patch("kubani_dev.commands.config.CONFIG_DIR", temp_config_dir):
            result = runner.invoke(app, ["config", "get", "nonexistent.key"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestConfigSet:
    """Tests for config set command."""

    def test_set_creates_local_yaml(self, temp_config_dir):
        """Test set creates local.yaml by default."""
        with patch("kubani_dev.commands.config.CONFIG_DIR", temp_config_dir):
            result = runner.invoke(app, ["config", "set", "custom.key", "value"])

        assert result.exit_code == 0

        local_file = temp_config_dir / "local.yaml"
        assert local_file.exists()

        with open(local_file) as f:
            config = yaml.safe_load(f)

        assert config["custom"]["key"] == "value"


class TestConfigShow:
    """Tests for config show command."""

    def test_show_displays_config(self, temp_config_dir):
        """Test show displays merged configuration."""
        with patch("kubani_dev.commands.config.CONFIG_DIR", temp_config_dir):
            result = runner.invoke(app, ["config", "show"])

        assert result.exit_code == 0
        assert "llm" in result.output
        assert "temporal" in result.output
```

**Step 3: Create env command tests**

```python
"""Tests for env commands."""

import pytest
from pathlib import Path
from typer.testing import CliRunner
from unittest.mock import patch

from kubani_dev.cli import app

runner = CliRunner()


@pytest.fixture
def temp_env_setup(tmp_path):
    """Create temporary environment setup."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Create default and production configs
    (config_dir / "default.yaml").write_text("llm:\n  model: default")
    (config_dir / "production.yaml").write_text("llm:\n  model: prod")

    env_file = tmp_path / ".kubani-env"

    return config_dir, env_file


class TestEnvList:
    """Tests for env list command."""

    def test_list_shows_environments(self, temp_env_setup):
        """Test list shows available environments."""
        config_dir, env_file = temp_env_setup

        with patch("kubani_dev.commands.env.CONFIG_DIR", config_dir):
            with patch("kubani_dev.commands.env.ENV_FILE", env_file):
                result = runner.invoke(app, ["env", "list"])

        assert result.exit_code == 0
        assert "development" in result.output
        assert "production" in result.output


class TestEnvUse:
    """Tests for env use command."""

    def test_use_switches_environment(self, temp_env_setup):
        """Test use switches to specified environment."""
        config_dir, env_file = temp_env_setup

        with patch("kubani_dev.commands.env.CONFIG_DIR", config_dir):
            with patch("kubani_dev.commands.env.ENV_FILE", env_file):
                result = runner.invoke(app, ["env", "use", "production"])

        assert result.exit_code == 0
        assert "production" in result.output
        assert env_file.read_text() == "production"
```

**Step 4: Commit**

```bash
git add tools/kubani/tests/
git commit -m "test(kubani): add tests for cluster, config, and env commands

Test coverage:
- cluster discover: Tailscale integration, error handling
- cluster status: Node listing, kubectl integration
- config get/set/show: Key access, file creation
- env list/use: Environment switching

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 7: Update Documentation

**Files:**
- Modify: `tools/kubani/README.md`
- Modify: `.claude/CLAUDE.md`

**Step 1: Update kubani README**

Add new sections to `tools/kubani/README.md`:

```markdown
## Cluster Management

Manage Kubernetes cluster infrastructure:

```bash
# Discover Tailscale nodes
kubani cluster discover

# Add a node to the cluster
kubani cluster add-node hostname --role worker --label env=prod

# Remove a node (with drain)
kubani cluster remove-node hostname

# Run provisioning
kubani cluster provision --tag k8s --limit workers

# Show cluster status
kubani cluster status --pods
```

## Configuration Management

Manage Kubani configuration:

```bash
# Get a config value
kubani config get llm.api_url

# Set a config value (writes to local.yaml)
kubani config set llm.model my-model

# Show effective configuration
kubani config show --env production

# Validate configuration
kubani config validate

# Compare environments
kubani config diff development production

# Edit config file
kubani config edit --env production
```

## Environment Management

Switch between environments:

```bash
# List available environments
kubani env list

# Switch to an environment
kubani env use production

# Show current environment
kubani env show

# Initialize a new environment
kubani env init staging --copy-from production
```
```

**Step 2: Update CLAUDE.md**

Update the Key Commands section in `.claude/CLAUDE.md`:

```markdown
## Key Commands

| Command | Purpose |
|---------|---------|
| `just setup` | Initial project setup |
| `just test` | Run all tests |
| `just lint` | Ruff linting |
| `just ci` | Pre-commit checks |
| `kubani init` | Initialize configuration |
| `kubani local-run` | Run agent locally |
| `kubani test` | Run agent tests |
| `kubani eval` | Run evaluations |
| `kubani deploy` | Deploy to cluster |
| `kubani sync` | Sync skills, agents, MCP to registry |
| `kubani cluster discover` | Discover Tailscale nodes |
| `kubani cluster status` | Show cluster health |
| `kubani cluster provision` | Run Ansible playbooks |
| `kubani config get KEY` | Get config value |
| `kubani config show` | Show effective config |
| `kubani env use ENV` | Switch environment |
```

**Step 3: Commit**

```bash
git add tools/kubani/README.md
git add .claude/CLAUDE.md
git commit -m "docs: update documentation for CLI consolidation

- kubani README: Add cluster, config, and env command docs
- CLAUDE.md: Add new commands to key commands table

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Batch 3: Finalization (Tasks 8-10)

### Task 8: Version Bump and Changelog

**Files:**
- Modify: `tools/kubani/pyproject.toml`
- Create: `CHANGELOG.md` (if not exists)

**Step 1: Bump kubani version**

Update `tools/kubani/pyproject.toml`:
```toml
version = "0.4.0"
```

**Step 2: Update/create CHANGELOG**

Add to `CHANGELOG.md`:
```markdown
## [0.4.0] - 2026-01-22

### Added
- `kubani cluster` command group (migrated from cluster-mgr)
  - `discover` - Tailscale node discovery
  - `add-node` - Add node to Ansible inventory
  - `remove-node` - Remove node with optional drain
  - `provision` - Run Ansible playbooks
  - `status` - Show cluster health
- `kubani config` command group
  - `get` - Get config value with dot notation
  - `set` - Set config value
  - `show` - Show effective configuration
  - `validate` - Validate against Pydantic schema
  - `edit` - Open config in editor
  - `diff` - Compare environments
- `kubani env` command group
  - `list` - List available environments
  - `use` - Switch environment
  - `show` - Show current environment
  - `init` - Initialize new environment

### Deprecated
- `cluster-mgr` CLI - Use `kubani cluster` instead
```

**Step 3: Commit**

```bash
git add tools/kubani/pyproject.toml CHANGELOG.md
git commit -m "chore(kubani): bump version to 0.4.0 for CLI consolidation

Phase 6 complete:
- cluster-mgr migrated to kubani cluster
- New config management commands
- New environment management commands

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 9: Run Full Test Suite

**Step 1: Run all kubani tests**

```bash
cd tools/kubani && python -m pytest tests/ -v
```

Expected: All tests pass

**Step 2: Run integration test**

```bash
# Test cluster commands work
kubani cluster --help
kubani cluster status

# Test config commands work
kubani config show
kubani config validate

# Test env commands work
kubani env list
kubani env show
```

**Step 3: Verify deprecation warnings**

```bash
# Should show deprecation warning
cluster-mgr status
```

Expected: Warning message pointing to kubani

---

### Task 10: Final Verification and Summary

**Step 1: Verify all commands are accessible**

```bash
kubani --help
```

Expected output should show:
- cluster (Kubernetes cluster infrastructure management)
- config (Configuration management for Kubani)
- env (Environment management for Kubani)
- Plus all existing commands (run, test, eval, skill, agent, etc.)

**Step 2: Create verification script**

```bash
#!/bin/bash
# verify-phase6.sh

echo "=== Phase 6 Verification ==="

echo -n "cluster commands: "
kubani cluster --help > /dev/null 2>&1 && echo "[OK]" || echo "[FAIL]"

echo -n "config commands: "
kubani config --help > /dev/null 2>&1 && echo "[OK]" || echo "[FAIL]"

echo -n "env commands: "
kubani env --help > /dev/null 2>&1 && echo "[OK]" || echo "[FAIL]"

echo -n "deprecation warning: "
cluster-mgr --help 2>&1 | grep -q "DEPRECATED" && echo "[OK]" || echo "[FAIL]"

echo -n "config validation: "
kubani config validate > /dev/null 2>&1 && echo "[OK]" || echo "[FAIL]"

echo "=== Done ==="
```

**Step 3: Commit verification script**

```bash
git add scripts/verify-phase6.sh
git commit -m "chore: add Phase 6 verification script

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

### Deliverables

| Item | Description |
|------|-------------|
| `kubani cluster` | 5 commands migrated from cluster-mgr |
| `kubani config` | 6 new configuration management commands |
| `kubani env` | 4 new environment management commands |
| cluster-mgr deprecation | Wrapper with warnings, migration guide |
| Tests | Coverage for all new commands |
| Documentation | Updated README and CLAUDE.md |

### Command Count

| Before | After |
|--------|-------|
| cluster-mgr: 8 commands | Deprecated (wrapper) |
| kubani: 22+ commands | kubani: 37+ commands |

### Migration Path

Users should update their workflows:
```bash
# Old
cluster-mgr discover
cluster-mgr status

# New
kubani cluster discover
kubani cluster status
```

### Risk Mitigation

1. **Backwards compatibility**: cluster-mgr still works (with warnings)
2. **Gradual migration**: Users can migrate at their own pace
3. **Clear documentation**: Migration guide in README
4. **No breaking changes**: Same functionality, new location
