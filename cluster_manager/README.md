# Cluster Manager

Python-based management tools for the Kubernetes cluster.

## Components

### CLI (`cli/`)
Command-line interface built with Typer for cluster management:
- Node discovery via Tailscale
- Inventory management
- Configuration updates
- Cluster provisioning
- Status monitoring

### TUI (`tui/`)
Terminal user interface built with Textual for real-time monitoring:
- Node status and resource usage
- Service health monitoring
- Event streaming
- Interactive navigation

### Models (`models/`)
Pydantic data models for:
- Node configuration
- Cluster state
- Inventory management
- Configuration validation

## Usage

### CLI
```bash
# Discover Tailscale nodes
cluster-mgr discover

# Add a node
cluster-mgr add-node hostname --role worker

# Provision cluster
cluster-mgr provision

# Check status
cluster-mgr status
```

### TUI
```bash
# Launch the TUI
cluster-tui

# Or via mise
mise run tui
```

## Development

The cluster manager is implemented as a Python package with entry points defined in `pyproject.toml`:
- `cluster-mgr` - CLI tool
- `cluster-tui` - TUI application

All components use type hints and are validated with mypy.
