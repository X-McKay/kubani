# cluster-mgr (DEPRECATED)

> **DEPRECATED:** This CLI has been consolidated into `kubani-dev`.
> Use `kubani-dev cluster` commands instead.

## Migration Guide

| Old Command | New Command |
|-------------|-------------|
| `cluster-mgr discover` | `kubani-dev cluster discover` |
| `cluster-mgr add-node` | `kubani-dev cluster add-node` |
| `cluster-mgr remove-node` | `kubani-dev cluster remove-node` |
| `cluster-mgr provision` | `kubani-dev cluster provision` |
| `cluster-mgr status` | `kubani-dev cluster status` |
| `cluster-mgr config-get` | `kubani-dev config get` |
| `cluster-mgr config-set` | `kubani-dev config set` |

## Why Deprecate?

The Kubani project now has a single unified CLI (`kubani-dev`) that handles:
- Agent development and testing
- Cluster infrastructure management
- Configuration management
- Environment switching

This consolidation reduces cognitive overhead and provides a consistent experience.

## Backwards Compatibility

The `cluster-mgr` command still works but will show deprecation warnings.
All commands delegate to the new `kubani-dev cluster` implementation.

## Components (Legacy)

### CLI (`cli.py`)
Command-line interface built with Typer - now a wrapper around kubani-dev.

### TUI (`tui/`)
Terminal user interface built with Textual for real-time monitoring:
- Node status and resource usage
- Service health monitoring
- Event streaming
- Interactive navigation

**Note:** The TUI is not yet migrated and still works independently.

### Models (`models/`)
Pydantic data models for:
- Node configuration
- Cluster state
- Inventory management
- Configuration validation
