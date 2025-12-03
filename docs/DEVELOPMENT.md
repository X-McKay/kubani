# Development Guide

This guide covers the development workflow, tooling, and best practices for contributing to Kubani.

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) - Fast Python package manager
- [mise](https://mise.jdx.dev/) - Runtime version manager (optional but recommended)

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd kubani
```

2. Install dependencies:
```bash
make install-dev
```

3. Install pre-commit hooks:
```bash
make pre-commit-install
```

4. Verify setup:
```bash
make test
```

## Development Workflow

### Running Tests

```bash
# Run all tests
make test

# Run only unit tests
make test-unit

# Run only property-based tests
make test-props

# Run tests with coverage report
make coverage
```

### Code Quality

```bash
# Run linting
make lint

# Auto-format code
make format

# Run type checking (mypy)
make type-check

# Run type checking (ty - experimental)
make type-check-ty

# Run all checks
make check-all
```

### Using Mise Tasks

If you have mise installed, you can use the configured tasks:

```bash
# List available tasks
mise tasks

# Run tests
mise run test

# Run linting
mise run lint

# Run type checking
mise run type-check
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

### mypy

Static type checker for Python.

**Configuration**: `pyproject.toml` under `[tool.mypy]`

**Usage**:
```bash
# Check entire package
uv run mypy cluster_manager

# Check specific file
uv run mypy cluster_manager/cli.py

# Install missing type stubs
uv run mypy --install-types
```

### ty

Experimental type checker from Astral (creators of Ruff and uv).

**Usage**:
```bash
# Check entire package
uv run ty check cluster_manager

# Check specific file
uv run ty check cluster_manager/cli.py
```

### pre-commit

Git hook framework for running checks before commits.

**Configuration**: `.pre-commit-config.yaml`

**Hooks**:
- Trailing whitespace removal
- End-of-file fixer
- YAML/TOML validation
- Ruff linting and formatting
- mypy type checking

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
- Type checking (mypy)
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
# Install missing type stubs
uv run mypy --install-types

# Ignore specific error
# type: ignore[error-code]
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
- [mypy documentation](https://mypy.readthedocs.io/)
- [Typer documentation](https://typer.tiangolo.com/)
- [Textual documentation](https://textual.textualize.io/)
- [Pydantic documentation](https://docs.pydantic.dev/)

## Getting Help

- Check existing documentation in `docs/`
- Review test examples in `tests/`
- Ask questions in project discussions
- Report bugs in issue tracker
