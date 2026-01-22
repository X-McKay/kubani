"""
DEPRECATED: Use kubani-dev cluster commands instead.

This CLI is maintained for backwards compatibility only.
All commands delegate to kubani-dev cluster.
"""


import typer
from rich.console import Console

app = typer.Typer(
    name="cluster-mgr",
    help="[DEPRECATED] Cluster management - use 'kubani-dev cluster' instead",
    add_completion=False,
)

console = Console()


def _deprecation_warning(command: str) -> None:
    """Print deprecation warning."""
    typer.echo(
        typer.style(
            f"WARNING: cluster-mgr is deprecated. Use 'kubani-dev cluster {command}' instead.",
            fg=typer.colors.YELLOW,
        ),
        err=True,
    )


@app.callback()
def main_callback(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    log_file: str | None = typer.Option(None, "--log-file", help="Path to log file"),
):
    """[DEPRECATED] Use 'kubani-dev cluster' instead."""
    pass


@app.command()
def version() -> None:
    """Show version information."""
    from cluster_manager import __version__

    typer.echo(f"Kubani version {__version__} (DEPRECATED - use kubani-dev)")


@app.command()
def discover(
    online_only: bool = typer.Option(False, "--online-only", "-o", help="Show only online nodes"),
    filter_hostname: str | None = typer.Option(
        None, "--filter", "-f", help="Filter nodes by hostname pattern"
    ),
    show_cluster_status: bool = typer.Option(
        True,
        "--show-cluster-status/--no-cluster-status",
        help="Show whether nodes are in the cluster",
    ),
) -> None:
    """[DEPRECATED] Use: kubani-dev cluster discover"""
    _deprecation_warning("discover")
    from kubani_dev.commands.cluster_impl import discover_nodes

    discover_nodes(show_offline=not online_only)


@app.command()
def add_node(
    hostname: str = typer.Argument(..., help="Hostname of the node to add"),
    tailscale_ip: str = typer.Argument(..., help="Tailscale IP address of the node"),
    role: str = typer.Option("worker", "--role", "-r", help="Node role: control-plane or worker"),
    reserved_cpu: str | None = typer.Option(
        None, "--reserved-cpu", help="CPU cores to reserve for local processes"
    ),
    reserved_memory: str | None = typer.Option(
        None, "--reserved-memory", help="Memory to reserve for local processes"
    ),
    gpu: bool = typer.Option(False, "--gpu", help="Node has GPU capabilities"),
    labels: str | None = typer.Option(
        None,
        "--labels",
        "-l",
        help="Node labels as comma-separated key=value pairs",
    ),
    taints: str | None = typer.Option(
        None,
        "--taints",
        "-t",
        help="Node taints as comma-separated key=value:effect",
    ),
    inventory_path: str = typer.Option(
        "ansible/inventory/hosts.yml", "--inventory", "-i", help="Path to Ansible inventory file"
    ),
) -> None:
    """[DEPRECATED] Use: kubani-dev cluster add-node"""
    _deprecation_warning("add-node")
    from kubani_dev.commands.cluster_impl import add_cluster_node

    # Parse labels into list format
    label_list = []
    if labels:
        label_list = [l.strip() for l in labels.split(",")]

    # Parse taints into list format
    taint_list = []
    if taints:
        taint_list = [t.strip() for t in taints.split(",")]

    add_cluster_node(
        hostname=hostname,
        role="control_plane" if role == "control-plane" else role,
        labels=label_list,
        taints=taint_list,
        gpu=gpu,
    )


@app.command()
def remove_node(
    hostname: str = typer.Argument(..., help="Hostname of the node to remove"),
    drain: bool = typer.Option(True, "--drain/--no-drain", help="Drain node before removal"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    inventory_path: str = typer.Option(
        "ansible/inventory/hosts.yml", "--inventory", "-i", help="Path to Ansible inventory file"
    ),
) -> None:
    """[DEPRECATED] Use: kubani-dev cluster remove-node"""
    _deprecation_warning("remove-node")
    from kubani_dev.commands.cluster_impl import remove_cluster_node

    remove_cluster_node(hostname=hostname, drain=drain, force=force)


@app.command()
def config_get(
    key: str = typer.Argument(..., help="Configuration key to retrieve"),
    scope: str = typer.Option(
        "all", "--scope", "-s", help="Configuration scope: all, control_plane, or workers"
    ),
    inventory_path: str = typer.Option(
        "ansible/inventory/hosts.yml", "--inventory", "-i", help="Path to Ansible inventory file"
    ),
) -> None:
    """[DEPRECATED] Use: kubani-dev config get"""
    _deprecation_warning("N/A - use 'kubani-dev config get'")
    console.print("[yellow]This command has been replaced by 'kubani-dev config get'[/yellow]")
    console.print("Example: kubani-dev config get llm.api_url")


@app.command()
def config_set(
    key: str = typer.Argument(..., help="Configuration key to set"),
    value: str = typer.Argument(..., help="Configuration value to set"),
    scope: str = typer.Option("all", "--scope", "-s", help="Configuration scope"),
    value_type: str = typer.Option(
        "string", "--type", "-t", help="Value type: string, int, bool, or json"
    ),
    inventory_path: str = typer.Option(
        "ansible/inventory/hosts.yml", "--inventory", "-i", help="Path to Ansible inventory file"
    ),
) -> None:
    """[DEPRECATED] Use: kubani-dev config set"""
    _deprecation_warning("N/A - use 'kubani-dev config set'")
    console.print("[yellow]This command has been replaced by 'kubani-dev config set'[/yellow]")
    console.print(f"Example: kubani-dev config set {key} {value}")


@app.command()
def provision(
    playbook: str = typer.Option(
        "provision_cluster.yml",
        "--playbook",
        "-p",
        help="Playbook to execute",
    ),
    inventory_path: str = typer.Option(
        "ansible/inventory/hosts.yml", "--inventory", "-i", help="Path to Ansible inventory file"
    ),
    check: bool = typer.Option(False, "--check", "-c", help="Run in check mode (dry-run)"),
    tags: str | None = typer.Option(
        None,
        "--tags",
        "-t",
        help="Only run plays and tasks tagged with these values",
    ),
    skip_tags: str | None = typer.Option(
        None, "--skip-tags", help="Skip plays and tasks tagged with these values"
    ),
    limit: str | None = typer.Option(
        None, "--limit", "-l", help="Limit execution to specific hosts or groups"
    ),
    verbose: int = typer.Option(
        0,
        "--verbose",
        "-v",
        count=True,
        help="Increase verbosity",
    ),
    extra_vars: str | None = typer.Option(
        None, "--extra-vars", "-e", help="Extra variables as JSON string"
    ),
) -> None:
    """[DEPRECATED] Use: kubani-dev cluster provision"""
    _deprecation_warning("provision")
    from kubani_dev.commands.cluster_impl import run_provision

    # Parse tags into list
    tag_list = []
    if tags:
        tag_list = [t.strip() for t in tags.split(",")]

    run_provision(
        tags=tag_list,
        limit=limit,
        check=check,
        playbook=playbook,
    )


@app.command()
def status(
    inventory_path: str = typer.Option(
        "ansible/inventory/hosts.yml", "--inventory", "-i", help="Path to Ansible inventory file"
    ),
    show_pods: bool = typer.Option(
        False, "--pods", "-p", help="Show pod information for each node"
    ),
    namespace: str | None = typer.Option(
        None, "--namespace", "-n", help="Filter pods by namespace"
    ),
) -> None:
    """[DEPRECATED] Use: kubani-dev cluster status"""
    _deprecation_warning("status")
    from kubani_dev.commands.cluster_impl import show_cluster_status

    show_cluster_status(show_pods=show_pods, namespace=namespace)


if __name__ == "__main__":
    app()
