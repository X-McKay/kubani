# Development Guide

This guide covers the development workflow, tooling, and best practices for contributing to Kubani.

## Quick Start

### Prerequisites

- Python 3.11+
- [mise](https://mise.jdx.dev/) - Runtime version manager (installs all other tools)

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd kubani
```

2. Install dependencies:
```bash
# Using setup script (recommended)
chmod +x setup.sh
./setup.sh

# Or manually
mise install          # Installs Python, UV, kubectl, just
just setup            # Installs Python dependencies and pre-commit hooks
```

3. Verify setup:
```bash
# Show available commands
just

# Or run tests
just test
```

## Development Workflow

All development commands are managed via [Just](https://github.com/casey/just). Run `just` to see all available commands.

### Running Tests

```bash
# Run all tests (root + agents)
just test

# Run root project tests only
just test-root

# Run only unit tests
just test-unit

# Run only property-based tests
just test-props

# Run tests with coverage report
just coverage

# Run agent tests via Earthly
just test-agents
```

### Code Quality

```bash
# Run linting
just lint

# Auto-format code
just fmt

# Run type checking (ty - fast type checker from Astral)
just check

# Run all checks (lint, format, type)
just check-all

# Quick CI check before pushing
just ci
```

### Agent Development

```bash
# Create new agent from template
just new-agent my-agent

# Local dev mode for agent
just dev k8s-monitor

# Build agent Docker image
just build k8s-monitor

# Push to registry
just push k8s-monitor v1.0.0
```

## Project Structure

```
kubani/
├── cluster_manager/          # Main Python package
│   ├── models/              # Data models (Pydantic)
│   ├── tui/                 # Terminal UI (Textual)
│   ├── cli.py               # CLI commands (Typer)
│   ├── inventory.py         # Ansible inventory management
│   ├── tailscale.py         # Tailscale integration
│   └── exceptions.py        # Custom exceptions
├── ansible/                 # Ansible playbooks and roles
│   ├── playbooks/          # Main playbooks
│   ├── roles/              # Ansible roles
│   └── inventory/          # Inventory examples
├── gitops/                  # GitOps manifests
│   ├── apps/               # Application definitions
│   ├── infrastructure/     # Infrastructure components
│   └── flux-system/        # Flux CD configuration
├── tests/                   # Test suite
│   ├── unit/               # Unit tests
│   ├── properties/         # Property-based tests
│   └── integration/        # Integration tests
└── docs/                    # Documentation
```

## Development Tools

### pytest

Test framework with plugins for coverage and property-based testing.

**Configuration**: `pyproject.toml` under `[tool.pytest.ini_options]`

**Usage**:
```bash
# Run specific test file
uv run pytest tests/unit/test_cli.py

# Run with verbose output
uv run pytest -v

# Run with specific marker
uv run pytest -m "not slow"
```

### Hypothesis

Property-based testing library for generating test cases.

**Configuration**: `pyproject.toml` under `[tool.hypothesis]`

**Settings**:
- `max_examples = 100`: Number of test cases per property
- `deadline = 5000`: Maximum time (ms) per test case

**Usage**:
```python
from hypothesis import given, strategies as st

@given(st.integers())
def test_property(value):
    assert some_property(value)
```

### pytest-cov

Coverage reporting plugin for pytest.

**Configuration**: `pyproject.toml` under `[tool.coverage.*]`

**Usage**:
```bash
# Generate HTML report
uv run pytest --cov=cluster_manager --cov-report=html

# View report
open htmlcov/index.html
```

### Ruff

Fast Python linter and formatter (replaces flake8, black, isort).

**Configuration**: `pyproject.toml` under `[tool.ruff]`

**Usage**:
```bash
# Check for issues
uv run ruff check .

# Auto-fix issues
uv run ruff check --fix .

# Format code
uv run ruff format .
```

### ty

Fast type checker from Astral (creators of Ruff and uv). We use ty instead of mypy for faster type checking feedback.

**Usage**:
```bash
# Check entire package
uv run ty check cluster_manager

# Check specific file
uv run ty check cluster_manager/cli.py

# Via just command
just check
```

### pre-commit

Git hook framework for running checks before commits.

**Configuration**: `.pre-commit-config.yaml`

**Hooks**:
- Trailing whitespace removal
- End-of-file fixer
- YAML/TOML validation
- Ruff linting and formatting

Note: Type checking with ty is done via `just check` rather than pre-commit hooks.

**Usage**:
```bash
# Install hooks
uv run pre-commit install

# Run manually on all files
uv run pre-commit run --all-files

# Update hook versions
uv run pre-commit autoupdate
```

## Writing Tests

### Unit Tests

Unit tests verify specific functionality:

```python
# tests/unit/test_example.py
import pytest
from cluster_manager.models.node import Node

def test_node_creation():
    """Test basic node creation."""
    node = Node(
        hostname="test-node",
        ansible_host="100.64.0.1",
        tailscale_ip="100.64.0.1",
        role="worker"
    )
    assert node.hostname == "test-node"
    assert node.role == "worker"

def test_invalid_ip_raises_error():
    """Test that invalid IP raises ValidationError."""
    with pytest.raises(ValueError):
        Node(
            hostname="test",
            ansible_host="invalid",
            tailscale_ip="invalid",
            role="worker"
        )
```

### Property-Based Tests

Property tests verify universal properties:

```python
# tests/properties/test_example.py
from hypothesis import given, strategies as st
from cluster_manager.models.node import Node

@given(
    hostname=st.text(min_size=1, max_size=63),
    role=st.sampled_from(['control-plane', 'worker'])
)
def test_property_minimal_requirements(hostname, role):
    """
    Feature: tailscale-k8s-cluster, Property 8: Minimal node requirements

    For any node, only hostname, IP, and role should be required.
    """
    ip = "100.64.0.1"
    node = Node(
        hostname=hostname,
        ansible_host=ip,
        tailscale_ip=ip,
        role=role
    )

    # Optional fields should have defaults
    assert node.reserved_cpu is None
    assert node.reserved_memory is None
    assert node.gpu is False
```

## Code Style

### Python Style Guide

- Follow PEP 8 (enforced by Ruff)
- Use type hints for all functions
- Maximum line length: 100 characters
- Use descriptive variable names
- Add docstrings to public functions/classes

### Type Hints

```python
from typing import Optional, List, Dict

def process_nodes(
    nodes: List[Node],
    filter_role: Optional[str] = None
) -> Dict[str, Node]:
    """Process nodes and return a mapping."""
    ...
```

### Docstrings

Use Google-style docstrings:

```python
def add_node(hostname: str, role: str) -> Node:
    """Add a new node to the inventory.

    Args:
        hostname: The node's hostname
        role: The node's role (control-plane or worker)

    Returns:
        The created Node object

    Raises:
        ValidationError: If the node data is invalid
        InventoryError: If the node already exists
    """
    ...
```

## Debugging

### Running with Debug Logging

```bash
# Set log level
export LOG_LEVEL=DEBUG

# Run CLI with debug output
cluster-mgr --verbose discover
```

### Using Python Debugger

```python
# Add breakpoint in code
import pdb; pdb.set_trace()

# Or use built-in breakpoint() (Python 3.7+)
breakpoint()
```

### Debugging Tests

```bash
# Run with pdb on failure
uv run pytest --pdb

# Run with verbose output
uv run pytest -vv

# Run specific test with print statements
uv run pytest tests/unit/test_cli.py::test_discover -s
```

## Common Tasks

### Adding a New Dependency

```bash
# Add runtime dependency
uv add package-name

# Add dev dependency
uv add --dev package-name

# Update dependencies
uv sync
```

### Creating a New CLI Command

1. Add command function in `cluster_manager/cli.py`
2. Use `@app.command()` decorator
3. Add type hints and docstring
4. Write unit tests in `tests/unit/test_cli.py`
5. Update CLI documentation

### Adding a New Ansible Role

1. Create role directory: `ansible/roles/role_name/`
2. Add standard directories: `tasks/`, `defaults/`, `handlers/`, `templates/`
3. Create `README.md` documenting the role
4. Add role to playbook
5. Write property tests in `tests/properties/`

## Continuous Integration

Tests run automatically on:
- Every push to main branch
- Every pull request
- Scheduled daily runs

CI checks:
- Unit tests
- Property-based tests
- Linting (Ruff)
- Type checking (ty)
- Coverage reporting

## Troubleshooting

### Import Errors

```bash
# Reinstall dependencies
uv sync --reinstall

# Clear cache
rm -rf .venv
uv sync
```

### Test Failures

```bash
# Run with verbose output
uv run pytest -vv

# Run specific test
uv run pytest tests/unit/test_cli.py::test_discover -v

# Show print statements
uv run pytest -s
```

### Type Checking Issues

```bash
# Run type checker
uv run ty check cluster_manager

# Or via just
just check
```

### Pre-commit Hook Failures

```bash
# Run hooks manually
uv run pre-commit run --all-files

# Skip hooks for emergency commit
git commit --no-verify
```

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [Hypothesis documentation](https://hypothesis.readthedocs.io/)
- [Ruff documentation](https://docs.astral.sh/ruff/)
- [ty documentation](https://github.com/astral-sh/ty)
- [Typer documentation](https://typer.tiangolo.com/)
- [Textual documentation](https://textual.textualize.io/)
- [Pydantic documentation](https://docs.pydantic.dev/)

## Getting Help

- Check existing documentation in `docs/`
- Review test examples in `tests/`
- Ask questions in project discussions
- Report bugs in issue tracker


## Development Tools

### UV Package Manager

UV is a fast Python package manager written in Rust that replaces pip:

- Faster dependency resolution
- Better dependency locking
- Script running capabilities

Usage:
```bash
# Install dependencies
uv sync

# Run script
uv run python script.py

# Run module
uv run -m pytest

# Install package
uv pip install package-name
```

### pytest

Test framework with rich plugin ecosystem.

Configuration in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = [
    "--verbose",
    "--cov=cluster_manager",
    "--cov-report=term-missing",
    "--cov-report=html",
    "--hypothesis-show-statistics",
]
```

### Hypothesis

Property-based testing library that generates test cases.

Configuration in `pyproject.toml`:
```toml
[tool.hypothesis]
max_examples = 100
deadline = 5000
derandomize = false
```

### Ruff

Fast Python linter and formatter (10-100x faster than alternatives).

Configuration in `pyproject.toml`:
```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]
```

Selected rules:
- **E**: pycodestyle errors
- **F**: Pyflakes
- **I**: isort (import sorting)
- **N**: pep8-naming
- **W**: pycodestyle warnings
- **UP**: pyupgrade (modern Python syntax)

### Ty

Fast type checker from Astral (creators of Ruff and uv). Used for all type checking in this project.

Usage:
```bash
# Check specific file
uv run ty check cluster_manager/models/node.py

# Check entire package
uv run ty check cluster_manager

# Via just command
just check
```

### Pre-commit

Git hook framework for running checks before commits.

**Configuration**: `.pre-commit-config.yaml`

**Hooks**:
- Trailing whitespace removal
- End-of-file fixer
- YAML/TOML validation
- Ruff linting and formatting

Note: Type checking with ty is done via `just check` rather than pre-commit hooks.

**Usage**:
```bash
# Install hooks
uv run pre-commit install

# Run manually on all files
uv run pre-commit run --all-files

# Update hook versions
uv run pre-commit autoupdate
```

## Configuration Files

### pyproject.toml

Central configuration for:
- Project metadata and dependencies
- pytest configuration
- Coverage settings
- Hypothesis settings
- Ruff linting rules
- Mypy type checking
- Ty type checking

### .pre-commit-config.yaml

Defines pre-commit hooks and their versions.

### justfile

Provides convenient commands for common development tasks. Run `just` to see all available commands.

## Continuous Integration

Tests run automatically on:
- Every push to main branch
- Every pull request
- Scheduled daily runs

CI checks:
- Unit tests
- Property-based tests
- Linting (Ruff)
- Type checking (ty)
- Coverage reporting

## Best Practices

### Before Committing

1. Run tests: `just test`
2. Check linting: `just lint`
3. Format code: `just fmt`
4. Type check: `just check`

Or run all at once:
```bash
just ci
```

### Writing Tests

1. **Unit tests**: Test specific functionality with concrete examples
2. **Property tests**: Test universal properties across many inputs
3. **Both are important**: Unit tests catch specific bugs, property tests verify general correctness

### Type Hints

- Add type hints to all function signatures
- Use `from typing import` for complex types
- Run type checker regularly: `just check-ty`

### Code Style

- Follow PEP 8 guidelines
- Use ruff for automatic formatting
- Keep line length to 100 characters
- Use descriptive variable names

## Troubleshooting

### Pre-commit Hook Failures

If pre-commit hooks fail:

1. Review the error messages
2. Fix the issues manually or run `just fmt`
3. Stage the changes: `git add .`
4. Commit again

### Type Checking Errors

If type checking fails:

1. Review the error messages
2. Add missing type hints
3. Fix type mismatches
4. Run `just check` to verify

### Test Failures

If tests fail:

1. Review the test output
2. Fix the code or update the test
3. Run tests again: `just test`
4. Check coverage: `just coverage`

### Hypothesis Test Failures

If property tests fail:

1. Review the counterexample provided by Hypothesis
2. Determine if it's a bug in the code or test
3. Fix the issue
4. Hypothesis will remember the failure and test it first next time

## Additional Resources

- [pytest documentation](https://docs.pytest.org/)
- [Hypothesis documentation](https://hypothesis.readthedocs.io/)
- [Ruff documentation](https://docs.astral.sh/ruff/)
- [UV documentation](https://github.com/astral-sh/uv)
- [Ty documentation](https://github.com/google/pytype)
- [Pre-commit documentation](https://pre-commit.com/)
- [Typer documentation](https://typer.tiangolo.com/)
- [Textual documentation](https://textual.textualize.io/)
- [Pydantic documentation](https://docs.pydantic.dev/)
