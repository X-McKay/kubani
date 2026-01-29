"""Cluster management commands - migrated from cluster-mgr."""

import typer
from rich.console import Console

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
    from kubani.cli.commands.cluster_impl import discover_nodes

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
    from kubani.cli.commands.cluster_impl import add_cluster_node

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
    from kubani.cli.commands.cluster_impl import remove_cluster_node

    remove_cluster_node(hostname=hostname, drain=drain, force=force)


@app.command()
def provision(
    tags: list[str] = typer.Option([], "--tag", "-t", help="Ansible tags"),
    limit: str = typer.Option(None, "--limit", "-l", help="Limit to hosts"),
    check: bool = typer.Option(False, "--check", help="Dry run mode"),
    playbook: str = typer.Option("site.yml", help="Playbook to run"),
):
    """Run Ansible provisioning playbooks."""
    from kubani.cli.commands.cluster_impl import run_provision

    run_provision(tags=tags, limit=limit, check=check, playbook=playbook)


@app.command()
def status(
    show_pods: bool = typer.Option(False, "--pods", "-p", help="Show pod status"),
    namespace: str = typer.Option(None, "--namespace", "-n", help="Filter by namespace"),
):
    """Show cluster status and health."""
    from kubani.cli.commands.cluster_impl import show_cluster_status

    show_cluster_status(show_pods=show_pods, namespace=namespace)
