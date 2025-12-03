"""Main CLI entry point for cluster management."""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from cluster_manager.exceptions import TailscaleError
from cluster_manager.logging_config import get_logger, setup_logging

app = typer.Typer(
    name="cluster-mgr",
    help="Kubernetes cluster management CLI for Tailscale networks",
    add_completion=False,
)

console = Console()
logger = get_logger(__name__)


# Global callback to set up logging
@app.callback()
def main_callback(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    log_file: str | None = typer.Option(None, "--log-file", help="Path to log file"),
):
    """Global options for all commands."""
    log_path = Path(log_file) if log_file else None
    setup_logging(verbose=verbose, log_file=log_path)
    logger.debug("Logging initialized")


@app.command()
def version() -> None:
    """Show version information."""
    from cluster_manager import __version__

    typer.echo(f"Kubani version {__version__}")


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
    """
    Discover Tailscale nodes available for cluster membership.

    This command queries the Tailscale network for available nodes and displays
    their hostname, IP address, online status, and cluster membership status.
    """
    from cluster_manager.inventory import InventoryManager
    from cluster_manager.tailscale import TailscaleDiscovery

    logger.info("Starting Tailscale node discovery")

    try:
        # Discover nodes on Tailscale network
        nodes = TailscaleDiscovery.discover_nodes()
        logger.info(f"Discovered {len(nodes)} nodes on Tailscale network")

        # Apply filters
        nodes = TailscaleDiscovery.filter_nodes(
            nodes, online_only=online_only, hostname_pattern=filter_hostname
        )
        logger.debug(f"After filtering: {len(nodes)} nodes")

        if not nodes:
            console.print("[yellow]No nodes found matching the criteria[/yellow]")
            if online_only:
                console.print("Tip: Remove --online-only to see offline nodes")
            if filter_hostname:
                console.print(f"Tip: Check the hostname filter: {filter_hostname}")
            return

        # Get cluster membership status if requested
        cluster_nodes = set()
        if show_cluster_status:
            try:
                # Try to find inventory file in standard location
                inventory_path = "ansible/inventory/hosts.yml"
                logger.debug(f"Checking inventory at: {inventory_path}")
                inventory_mgr = InventoryManager(inventory_path)
                nodes_in_cluster = inventory_mgr.get_nodes()
                cluster_nodes = {n.hostname for n in nodes_in_cluster}
                logger.debug(f"Found {len(cluster_nodes)} nodes in cluster inventory")
            except Exception as e:
                # If we can't read inventory, just skip cluster status
                logger.debug(f"Could not read inventory for cluster status: {e}")
                show_cluster_status = False

        # Create table for display
        table = Table(title="Discovered Tailscale Nodes")
        table.add_column("Hostname", style="cyan")
        table.add_column("Tailscale IP", style="magenta")
        table.add_column("Status", style="green")

        if show_cluster_status:
            table.add_column("In Cluster", style="yellow")

        # Add rows
        for node in sorted(nodes, key=lambda n: n.hostname):
            status = "✓ Online" if node.online else "✗ Offline"
            row = [node.hostname, str(node.tailscale_ip), status]

            if show_cluster_status:
                in_cluster = "Yes" if node.hostname in cluster_nodes else "No"
                row.append(in_cluster)

            table.add_row(*row)

        console.print(table)
        console.print(f"\n[bold]Total nodes found:[/bold] {len(nodes)}")

        if show_cluster_status:
            in_cluster_count = sum(1 for n in nodes if n.hostname in cluster_nodes)
            console.print(f"[bold]In cluster:[/bold] {in_cluster_count}")
            console.print(f"[bold]Not in cluster:[/bold] {len(nodes) - in_cluster_count}")

        logger.info("Discovery completed successfully")

    except TailscaleError as e:
        logger.error(f"Tailscale error: {e.message}")
        console.print(f"[red]Tailscale Error:[/red] {e.message}")
        if e.details:
            console.print(f"\n{e.details}")
        raise typer.Exit(code=1)
    except Exception as e:
        logger.error(f"Unexpected error during discovery: {e}", exc_info=True)
        console.print(f"[red]Unexpected error:[/red] {e}")
        console.print("\nRun with --verbose --log-file debug.log for more details")
        raise typer.Exit(code=1)


@app.command()
def add_node(
    hostname: str = typer.Argument(..., help="Hostname of the node to add"),
    tailscale_ip: str = typer.Argument(..., help="Tailscale IP address of the node"),
    role: str = typer.Option("worker", "--role", "-r", help="Node role: control-plane or worker"),
    reserved_cpu: str | None = typer.Option(
        None, "--reserved-cpu", help="CPU cores to reserve for local processes (e.g., '2')"
    ),
    reserved_memory: str | None = typer.Option(
        None, "--reserved-memory", help="Memory to reserve for local processes (e.g., '4Gi')"
    ),
    gpu: bool = typer.Option(False, "--gpu", help="Node has GPU capabilities"),
    labels: str | None = typer.Option(
        None,
        "--labels",
        "-l",
        help="Node labels as comma-separated key=value pairs (e.g., 'env=prod,tier=frontend')",
    ),
    taints: str | None = typer.Option(
        None,
        "--taints",
        "-t",
        help="Node taints as comma-separated key=value:effect (e.g., 'gpu=true:NoSchedule')",
    ),
    inventory_path: str = typer.Option(
        "ansible/inventory/hosts.yml", "--inventory", "-i", help="Path to Ansible inventory file"
    ),
) -> None:
    """
    Add a node to the Ansible inventory.

    This command validates the node configuration and adds it to the inventory
    file in the correct format and group (control_plane or workers).
    """
    from pydantic import ValidationError

    from cluster_manager.inventory import InventoryError, InventoryManager
    from cluster_manager.models.node import Node, NodeTaint

    try:
        # Parse labels
        node_labels = {}
        if labels:
            for label_pair in labels.split(","):
                label_pair = label_pair.strip()
                if "=" not in label_pair:
                    console.print(
                        f"[red]Error:[/red] Invalid label format: '{label_pair}'. Expected 'key=value'"
                    )
                    raise typer.Exit(code=1)
                key, value = label_pair.split("=", 1)
                node_labels[key.strip()] = value.strip()

        # Parse taints
        node_taints = []
        if taints:
            for taint_str in taints.split(","):
                taint_str = taint_str.strip()
                if "=" not in taint_str or ":" not in taint_str:
                    console.print(
                        f"[red]Error:[/red] Invalid taint format: '{taint_str}'. "
                        "Expected 'key=value:effect'"
                    )
                    raise typer.Exit(code=1)
                key_value, effect = taint_str.rsplit(":", 1)
                key, value = key_value.split("=", 1)
                try:
                    taint = NodeTaint(key=key.strip(), value=value.strip(), effect=effect.strip())
                    node_taints.append(taint)
                except ValidationError as e:
                    console.print(f"[red]Error:[/red] Invalid taint: {e}")
                    raise typer.Exit(code=1)

        # Create node object with validation
        try:
            node = Node(
                hostname=hostname,
                ansible_host=tailscale_ip,  # Use Tailscale IP as ansible_host
                tailscale_ip=tailscale_ip,
                role=role,
                reserved_cpu=reserved_cpu,
                reserved_memory=reserved_memory,
                gpu=gpu,
                node_labels=node_labels,
                node_taints=node_taints,
            )
        except ValidationError as e:
            console.print("[red]Validation Error:[/red]")
            for error in e.errors():
                field = ".".join(str(x) for x in error["loc"])
                console.print(f"  - {field}: {error['msg']}")
            raise typer.Exit(code=1)

        # Add node to inventory
        manager = InventoryManager(inventory_path)
        manager.add_node(node)

        console.print(f"[green]✓[/green] Successfully added node '{hostname}' to inventory")
        console.print(f"  Role: {role}")
        console.print(f"  Tailscale IP: {tailscale_ip}")
        if reserved_cpu:
            console.print(f"  Reserved CPU: {reserved_cpu}")
        if reserved_memory:
            console.print(f"  Reserved Memory: {reserved_memory}")
        if gpu:
            console.print("  GPU: Enabled")
        if node_labels:
            console.print(f"  Labels: {', '.join(f'{k}={v}' for k, v in node_labels.items())}")
        if node_taints:
            console.print(
                f"  Taints: {', '.join(f'{t.key}={t.value}:{t.effect}' for t in node_taints)}"
            )

    except InventoryError as e:
        console.print(f"[red]Inventory Error:[/red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        raise typer.Exit(code=1)


@app.command()
def remove_node(
    hostname: str = typer.Argument(..., help="Hostname of the node to remove"),
    drain: bool = typer.Option(
        True, "--drain/--no-drain", help="Drain node before removal (requires kubectl access)"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    inventory_path: str = typer.Option(
        "ansible/inventory/hosts.yml", "--inventory", "-i", help="Path to Ansible inventory file"
    ),
) -> None:
    """
    Remove a node from the Ansible inventory.

    This command removes a node from the inventory file. If --drain is enabled,
    it will attempt to drain the node using kubectl before removing it.
    """
    import subprocess

    from cluster_manager.inventory import InventoryError, InventoryManager

    try:
        manager = InventoryManager(inventory_path)

        # Check if node exists
        nodes = manager.get_nodes()
        node = next((n for n in nodes if n.hostname == hostname), None)

        if node is None:
            console.print(f"[red]Error:[/red] Node '{hostname}' not found in inventory")
            raise typer.Exit(code=1)

        # Confirm removal
        if not force:
            console.print(
                f"[yellow]Warning:[/yellow] About to remove node '{hostname}' from inventory"
            )
            console.print(f"  Role: {node.role}")
            console.print(f"  Tailscale IP: {node.tailscale_ip}")
            confirm = typer.confirm("Are you sure you want to continue?")
            if not confirm:
                console.print("Operation cancelled")
                raise typer.Exit(code=0)

        # Drain node if requested
        if drain:
            console.print(f"[yellow]Draining node '{hostname}'...[/yellow]")
            try:
                # Try to drain the node
                result = subprocess.run(
                    ["kubectl", "drain", hostname, "--ignore-daemonsets", "--delete-emptydir-data"],
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                )

                if result.returncode == 0:
                    console.print("[green]✓[/green] Node drained successfully")
                else:
                    console.print(
                        f"[yellow]Warning:[/yellow] Failed to drain node: {result.stderr}"
                    )
                    console.print("Continuing with removal from inventory...")

            except subprocess.TimeoutExpired:
                console.print("[yellow]Warning:[/yellow] Drain operation timed out")
                console.print("Continuing with removal from inventory...")
            except FileNotFoundError:
                console.print("[yellow]Warning:[/yellow] kubectl not found, skipping drain")
            except Exception as e:
                console.print(f"[yellow]Warning:[/yellow] Failed to drain node: {e}")
                console.print("Continuing with removal from inventory...")

        # Remove from inventory
        manager.remove_node(hostname)

        console.print(f"[green]✓[/green] Successfully removed node '{hostname}' from inventory")

        if drain:
            console.print("\n[yellow]Note:[/yellow] To complete removal, you may need to:")
            console.print("  1. Delete the node from Kubernetes: kubectl delete node " + hostname)
            console.print("  2. Stop K3s service on the node: systemctl stop k3s or k3s-agent")

    except InventoryError as e:
        console.print(f"[red]Inventory Error:[/red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        raise typer.Exit(code=1)


@app.command()
def config_get(
    key: str = typer.Argument(
        ..., help="Configuration key to retrieve (supports nested keys with dot notation)"
    ),
    scope: str = typer.Option(
        "all", "--scope", "-s", help="Configuration scope: all, control_plane, or workers"
    ),
    inventory_path: str = typer.Option(
        "ansible/inventory/hosts.yml", "--inventory", "-i", help="Path to Ansible inventory file"
    ),
) -> None:
    """
    Retrieve a configuration value from the Ansible inventory.

    This command retrieves configuration variables from the inventory file.
    Supports nested keys using dot notation (e.g., 'k3s.version').
    """
    from cluster_manager.inventory import InventoryError, InventoryManager

    try:
        manager = InventoryManager(inventory_path)

        # Validate scope
        valid_scopes = ["all", "control_plane", "workers"]
        if scope not in valid_scopes:
            console.print(
                f"[red]Error:[/red] Invalid scope '{scope}'. Must be one of: {', '.join(valid_scopes)}"
            )
            raise typer.Exit(code=1)

        # Get variables for the scope
        vars_dict = manager.get_vars(scope)

        # Handle nested keys (e.g., 'parent.child')
        keys = key.split(".")
        value = vars_dict

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                console.print(f"[red]Error:[/red] Key '{key}' not found in scope '{scope}'")
                raise typer.Exit(code=1)

        # Display the value
        console.print(f"[cyan]{key}[/cyan] (scope: {scope}):")

        # Format output based on value type
        if isinstance(value, dict):
            from rich.json import JSON

            console.print(JSON.from_data(value))
        elif isinstance(value, list):
            for item in value:
                console.print(f"  - {item}")
        else:
            console.print(f"  {value}")

    except InventoryError as e:
        console.print(f"[red]Inventory Error:[/red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        raise typer.Exit(code=1)


@app.command()
def config_set(
    key: str = typer.Argument(
        ..., help="Configuration key to set (supports nested keys with dot notation)"
    ),
    value: str = typer.Argument(..., help="Configuration value to set"),
    scope: str = typer.Option(
        "all", "--scope", "-s", help="Configuration scope: all, control_plane, or workers"
    ),
    value_type: str = typer.Option(
        "string", "--type", "-t", help="Value type: string, int, bool, or json"
    ),
    inventory_path: str = typer.Option(
        "ansible/inventory/hosts.yml", "--inventory", "-i", help="Path to Ansible inventory file"
    ),
) -> None:
    """
    Set a configuration value in the Ansible inventory.

    This command updates configuration variables in the inventory file.
    Supports nested keys using dot notation (e.g., 'k3s.version').

    Examples:
        config-set k3s_version v1.28.5+k3s1
        config-set cluster_name my-cluster --scope all
        config-set reserved_cpu 4 --scope workers --type int
        config-set gpu_enabled true --scope workers --type bool
    """
    import json

    from cluster_manager.inventory import InventoryError, InventoryManager

    try:
        manager = InventoryManager(inventory_path)

        # Validate scope
        valid_scopes = ["all", "control_plane", "workers"]
        if scope not in valid_scopes:
            console.print(
                f"[red]Error:[/red] Invalid scope '{scope}'. Must be one of: {', '.join(valid_scopes)}"
            )
            raise typer.Exit(code=1)

        # Parse value based on type
        parsed_value = value
        try:
            if value_type == "int":
                parsed_value = int(value)
            elif value_type == "bool":
                if value.lower() in ["true", "1", "yes", "on"]:
                    parsed_value = True
                elif value.lower() in ["false", "0", "no", "off"]:
                    parsed_value = False
                else:
                    console.print(f"[red]Error:[/red] Invalid boolean value: '{value}'")
                    raise typer.Exit(code=1)
            elif value_type == "json":
                parsed_value = json.loads(value)
            elif value_type != "string":
                console.print(
                    f"[red]Error:[/red] Invalid type '{value_type}'. Must be one of: string, int, bool, json"
                )
                raise typer.Exit(code=1)
        except (ValueError, json.JSONDecodeError) as e:
            console.print(f"[red]Error:[/red] Failed to parse value as {value_type}: {e}")
            raise typer.Exit(code=1)

        # Handle nested keys
        keys = key.split(".")

        if len(keys) == 1:
            # Simple key
            manager.set_var(key, parsed_value, scope)
        else:
            # Nested key - need to get existing vars, update nested structure, then set
            vars_dict = manager.get_vars(scope)

            # Navigate to parent and create nested structure if needed
            current = vars_dict
            for k in keys[:-1]:
                if k not in current:
                    current[k] = {}
                elif not isinstance(current[k], dict):
                    console.print(
                        f"[red]Error:[/red] Cannot set nested key: '{k}' is not a dictionary"
                    )
                    raise typer.Exit(code=1)
                current = current[k]

            # Set the final value
            current[keys[-1]] = parsed_value

            # Write back the entire top-level key
            manager.set_var(keys[0], vars_dict[keys[0]], scope)

        console.print(
            f"[green]✓[/green] Successfully set '{key}' = {parsed_value} (scope: {scope})"
        )

        # Show the updated value
        console.print("\nUpdated configuration:")
        console.print(f"  [cyan]{key}[/cyan]: {parsed_value}")

    except InventoryError as e:
        console.print(f"[red]Inventory Error:[/red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        raise typer.Exit(code=1)


@app.command()
def provision(
    playbook: str = typer.Option(
        "provision_cluster.yml",
        "--playbook",
        "-p",
        help="Playbook to execute (provision_cluster.yml, add_node.yml, or site.yml)",
    ),
    inventory_path: str = typer.Option(
        "ansible/inventory/hosts.yml", "--inventory", "-i", help="Path to Ansible inventory file"
    ),
    check: bool = typer.Option(
        False, "--check", "-c", help="Run in check mode (dry-run, no changes made)"
    ),
    tags: str | None = typer.Option(
        None,
        "--tags",
        "-t",
        help="Only run plays and tasks tagged with these values (comma-separated)",
    ),
    skip_tags: str | None = typer.Option(
        None, "--skip-tags", help="Skip plays and tasks tagged with these values (comma-separated)"
    ),
    limit: str | None = typer.Option(
        None, "--limit", "-l", help="Limit execution to specific hosts or groups"
    ),
    verbose: int = typer.Option(
        0,
        "--verbose",
        "-v",
        count=True,
        help="Increase verbosity (can be used multiple times: -v, -vv, -vvv)",
    ),
    extra_vars: str | None = typer.Option(
        None, "--extra-vars", "-e", help="Extra variables as JSON string or key=value pairs"
    ),
) -> None:
    """
    Execute Ansible playbook to provision or update the cluster.

    This command runs the specified Ansible playbook using ansible-runner,
    displaying progress and results in real-time.

    Examples:
        # Provision the entire cluster
        cluster-mgr provision

        # Run in check mode (dry-run)
        cluster-mgr provision --check

        # Only run tasks with specific tags
        cluster-mgr provision --tags "k3s,networking"

        # Add a new node
        cluster-mgr provision --playbook add_node.yml --limit new-node

        # Run with extra variables
        cluster-mgr provision --extra-vars '{"k3s_version": "v1.28.5+k3s1"}'
    """
    from pathlib import Path

    import ansible_runner

    try:
        # Validate playbook path
        playbook_dir = Path("ansible/playbooks")
        playbook_path = playbook_dir / playbook

        if not playbook_path.exists():
            console.print(f"[red]Error:[/red] Playbook not found: {playbook_path}")
            console.print(f"\nAvailable playbooks in {playbook_dir}:")
            for pb in playbook_dir.glob("*.yml"):
                console.print(f"  - {pb.name}")
            raise typer.Exit(code=1)

        # Validate inventory
        inventory_file = Path(inventory_path)
        if not inventory_file.exists():
            console.print(f"[red]Error:[/red] Inventory file not found: {inventory_path}")
            raise typer.Exit(code=1)

        # Build ansible-runner parameters
        runner_params = {
            "private_data_dir": "ansible",
            "playbook": f"playbooks/{playbook}",
            "inventory": f"../{inventory_path}",  # Relative to private_data_dir
            "quiet": False,
            "verbosity": verbose,
        }

        # Add optional parameters
        extravars = {}
        if check:
            runner_params["cmdline"] = "--check"

        if tags:
            runner_params["tags"] = tags

        if skip_tags:
            runner_params["skip_tags"] = skip_tags

        if limit:
            runner_params["limit"] = limit

        if extra_vars:
            # Parse extra vars (support both JSON and key=value format)
            import json

            try:
                extravars = json.loads(extra_vars)
            except json.JSONDecodeError:
                # Try parsing as key=value pairs
                for pair in extra_vars.split():
                    if "=" in pair:
                        key, value = pair.split("=", 1)
                        extravars[key] = value

        if extravars:
            runner_params["extravars"] = extravars

        # Display execution info
        console.print("\n[bold cyan]Ansible Playbook Execution[/bold cyan]")
        console.print(f"Playbook: {playbook}")
        console.print(f"Inventory: {inventory_path}")
        if check:
            console.print("[yellow]Mode: Check (dry-run)[/yellow]")
        if tags:
            console.print(f"Tags: {tags}")
        if skip_tags:
            console.print(f"Skip Tags: {skip_tags}")
        if limit:
            console.print(f"Limit: {limit}")
        if extravars:
            console.print(f"Extra Vars: {extravars}")
        console.print()

        # Run the playbook
        console.print("[bold]Starting playbook execution...[/bold]\n")

        runner = ansible_runner.run(**runner_params)

        # Display results
        console.print("\n[bold cyan]Execution Summary[/bold cyan]")
        console.print(f"Status: {runner.status}")
        console.print(f"Return Code: {runner.rc}")

        if runner.stats:
            console.print("\n[bold]Host Statistics:[/bold]")
            stats_table = Table()
            stats_table.add_column("Host", style="cyan")
            stats_table.add_column("OK", style="green")
            stats_table.add_column("Changed", style="yellow")
            stats_table.add_column("Unreachable", style="red")
            stats_table.add_column("Failed", style="red")
            stats_table.add_column("Skipped", style="blue")

            for host, stats in runner.stats.items():
                if host != "localhost":  # Skip localhost stats
                    stats_table.add_row(
                        host,
                        str(stats.get("ok", 0)),
                        str(stats.get("changed", 0)),
                        str(stats.get("unreachable", 0)),
                        str(stats.get("failures", 0)),
                        str(stats.get("skipped", 0)),
                    )

            console.print(stats_table)

        # Check for failures
        if runner.rc != 0:
            console.print("\n[red]✗ Playbook execution failed[/red]")
            console.print("Check the output above for error details")
            raise typer.Exit(code=runner.rc)
        else:
            console.print("\n[green]✓ Playbook execution completed successfully[/green]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Playbook execution interrupted by user[/yellow]")
        raise typer.Exit(code=130)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        raise typer.Exit(code=1)


@app.command()
def status(
    inventory_path: str = typer.Option(
        "ansible/inventory/hosts.yml", "--inventory", "-i", help="Path to Ansible inventory file"
    ),
    show_pods: bool = typer.Option(
        False, "--pods", "-p", help="Show pod information for each node"
    ),
    namespace: str | None = typer.Option(
        None, "--namespace", "-n", help="Filter pods by namespace (requires --pods)"
    ),
) -> None:
    """
    Show cluster status and node health.

    This command queries the Kubernetes cluster to display the current status
    of all nodes, including their roles, readiness, resource usage, and
    optionally running pods.

    Examples:
        # Show basic cluster status
        cluster-mgr status

        # Show status with pod information
        cluster-mgr status --pods

        # Show pods in specific namespace
        cluster-mgr status --pods --namespace kube-system
    """
    from datetime import datetime

    from kubernetes import client, config
    from kubernetes.client.rest import ApiException

    try:
        # Load kubeconfig
        try:
            config.load_kube_config()
        except Exception as e:
            console.print(f"[red]Error:[/red] Failed to load kubeconfig: {e}")
            console.print("\nMake sure:")
            console.print("  1. The cluster has been provisioned")
            console.print("  2. Kubeconfig is available at ~/.kube/config")
            console.print("  3. You have access to the cluster")
            raise typer.Exit(code=1)

        # Create API clients
        v1 = client.CoreV1Api()

        # Get cluster info
        try:
            version_api = client.VersionApi()
            version_info = version_api.get_code()
            console.print(f"[bold cyan]Cluster Version:[/bold cyan] {version_info.git_version}")
        except ApiException:
            console.print("[yellow]Warning:[/yellow] Could not retrieve cluster version")

        # Get nodes
        try:
            nodes = v1.list_node()
        except ApiException as e:
            console.print(f"[red]Error:[/red] Failed to list nodes: {e}")
            raise typer.Exit(code=1)

        if not nodes.items:
            console.print("[yellow]No nodes found in the cluster[/yellow]")
            raise typer.Exit(code=0)

        # Display node information
        console.print(f"\n[bold cyan]Cluster Nodes ({len(nodes.items)}):[/bold cyan]")

        nodes_table = Table()
        nodes_table.add_column("Name", style="cyan")
        nodes_table.add_column("Role", style="magenta")
        nodes_table.add_column("Status", style="green")
        nodes_table.add_column("Version", style="blue")
        nodes_table.add_column("Internal IP", style="yellow")
        nodes_table.add_column("Age")

        for node in sorted(nodes.items, key=lambda n: n.metadata.name):
            # Get node role
            labels = node.metadata.labels or {}
            if (
                "node-role.kubernetes.io/control-plane" in labels
                or "node-role.kubernetes.io/master" in labels
            ):
                role = "Control Plane"
            else:
                role = "Worker"

            # Get node status
            conditions = node.status.conditions or []
            ready_condition = next((c for c in conditions if c.type == "Ready"), None)
            if ready_condition and ready_condition.status == "True":
                status = "[green]✓ Ready[/green]"
            else:
                status = "[red]✗ NotReady[/red]"

            # Get internal IP
            addresses = node.status.addresses or []
            internal_ip = next((a.address for a in addresses if a.type == "InternalIP"), "N/A")

            # Calculate age
            creation_time = node.metadata.creation_timestamp
            age = datetime.now(creation_time.tzinfo) - creation_time
            age_str = f"{age.days}d" if age.days > 0 else f"{age.seconds // 3600}h"

            # Get version
            version = node.status.node_info.kubelet_version

            nodes_table.add_row(node.metadata.name, role, status, version, internal_ip, age_str)

        console.print(nodes_table)

        # Show pod information if requested
        if show_pods:
            console.print("\n[bold cyan]Pod Information:[/bold cyan]")

            try:
                if namespace:
                    pods = v1.list_namespaced_pod(namespace)
                else:
                    pods = v1.list_pod_for_all_namespaces()
            except ApiException as e:
                console.print(f"[red]Error:[/red] Failed to list pods: {e}")
                raise typer.Exit(code=1)

            if not pods.items:
                console.print("[yellow]No pods found[/yellow]")
            else:
                pods_table = Table()
                pods_table.add_column("Namespace", style="cyan")
                pods_table.add_column("Name", style="magenta")
                pods_table.add_column("Node", style="yellow")
                pods_table.add_column("Status", style="green")
                pods_table.add_column("Restarts")

                for pod in sorted(
                    pods.items, key=lambda p: (p.metadata.namespace, p.metadata.name)
                ):
                    # Get pod status
                    phase = pod.status.phase
                    if phase == "Running":
                        status_str = "[green]Running[/green]"
                    elif phase == "Pending":
                        status_str = "[yellow]Pending[/yellow]"
                    elif phase == "Failed":
                        status_str = "[red]Failed[/red]"
                    elif phase == "Succeeded":
                        status_str = "[blue]Succeeded[/blue]"
                    else:
                        status_str = phase

                    # Count restarts
                    container_statuses = pod.status.container_statuses or []
                    total_restarts = sum(cs.restart_count for cs in container_statuses)

                    pods_table.add_row(
                        pod.metadata.namespace,
                        pod.metadata.name,
                        pod.spec.node_name or "N/A",
                        status_str,
                        str(total_restarts),
                    )

                console.print(pods_table)
                console.print(f"\n[bold]Total pods:[/bold] {len(pods.items)}")

        # Show summary
        ready_nodes = sum(
            1
            for node in nodes.items
            if any(c.type == "Ready" and c.status == "True" for c in (node.status.conditions or []))
        )

        console.print("\n[bold]Summary:[/bold]")
        console.print(f"  Total Nodes: {len(nodes.items)}")
        console.print(f"  Ready Nodes: {ready_nodes}")
        console.print(f"  Not Ready: {len(nodes.items) - ready_nodes}")

        if ready_nodes == len(nodes.items):
            console.print("\n[green]✓ All nodes are ready[/green]")
        else:
            console.print("\n[yellow]⚠ Some nodes are not ready[/yellow]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Status check interrupted by user[/yellow]")
        raise typer.Exit(code=130)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        import traceback

        console.print(traceback.format_exc())
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
