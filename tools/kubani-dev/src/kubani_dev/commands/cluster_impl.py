"""Implementation for cluster commands - adapted from cluster_manager."""

import json
import subprocess
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()

# Paths - find repo root relative to this file
REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent.parent
INVENTORY_PATH = REPO_ROOT / "infrastructure" / "ansible" / "inventory"
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
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error running tailscale: {e}[/red]")
        return
    except FileNotFoundError:
        console.print("[red]Error: tailscale command not found[/red]")
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
        current.get("TailscaleIPs", ["?"])[0] if current.get("TailscaleIPs") else "?",
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
        host_vars["k8s_labels"] = dict(label.split("=") for label in labels if "=" in label)
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
                            [
                                "kubectl",
                                "drain",
                                hostname,
                                "--ignore-daemonsets",
                                "--delete-emptydir-data",
                            ],
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
    playbook_path = ANSIBLE_PATH / "playbooks" / playbook
    if not playbook_path.exists():
        console.print(f"[red]Playbook not found: {playbook_path}[/red]")
        console.print("\nAvailable playbooks:")
        for pb in (ANSIBLE_PATH / "playbooks").glob("*.yml"):
            console.print(f"  - {pb.name}")
        return

    cmd = [
        "ansible-playbook",
        str(playbook_path),
        "-i",
        str(INVENTORY_PATH / "hosts.yml"),
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
    except FileNotFoundError:
        console.print("[red]Error: ansible-playbook command not found[/red]")


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
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Failed to get nodes: {e}[/red]")
        return
    except FileNotFoundError:
        console.print("[red]Error: kubectl command not found[/red]")
        return
    except json.JSONDecodeError:
        console.print("[red]Failed to parse kubectl output[/red]")
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

    # Summary
    ready_count = sum(
        1
        for node in nodes
        if any(c["type"] == "Ready" and c["status"] == "True" for c in node["status"]["conditions"])
    )
    console.print(f"\n[bold]Total:[/bold] {len(nodes)} nodes, {ready_count} ready")

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
