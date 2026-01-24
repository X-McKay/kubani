# Changelog

All notable changes to kubani-dev will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-01-22

### Added
- `kubani-dev cluster` command group (migrated from cluster-mgr)
  - `discover` - Tailscale node discovery
  - `add-node` - Add node to Ansible inventory
  - `remove-node` - Remove node with optional drain
  - `provision` - Run Ansible playbooks
  - `status` - Show cluster health
- `kubani-dev config` command group
  - `get` - Get config value with dot notation
  - `set` - Set config value
  - `show` - Show effective configuration
  - `validate` - Validate against Pydantic schema
  - `edit` - Open config in editor
  - `diff` - Compare environments
- `kubani-dev env` command group
  - `list` - List available environments
  - `use` - Switch environment
  - `show` - Show current environment
  - `init` - Initialize new environment

### Deprecated
- `cluster-mgr` CLI - Use `kubani-dev cluster` instead

## [0.1.0] - 2025-12-01

### Added
- Initial release
- `kubani-dev run` - Run agent locally with hot-reload
- `kubani-dev test` - Run tests for agents
- `kubani-dev eval` - Run evaluation suites
- `kubani-dev dashboard` - Observability dashboard
- `kubani-dev new` - Create new agent from template
- `kubani-dev sync` - Sync to registry
- `kubani-dev skill` - Skill management commands
- `kubani-dev agent` - Agent management commands
