# Testing Guide

This document describes the testing strategy and tools used in the Kubani project.

## Testing Framework

The project uses **pytest** as the primary testing framework with the following extensions:

- **Hypothesis**: Property-based testing library for generating test cases
- **pytest-cov**: Coverage reporting plugin
- **pytest-mock**: Mocking utilities (if needed)

## Test Organization

Tests are organized into two main categories:

### Unit Tests (`tests/unit/`)

Unit tests verify specific functionality of individual components:

- Test specific examples and edge cases
- Test error conditions and validation
- Test integration between components
- Fast execution, isolated from external dependencies

### Property-Based Tests (`tests/properties/`)

Property-based tests verify universal properties that should hold across all inputs:

- Use Hypothesis to generate random test data
- Test invariants and correctness properties
- Each test references a specific property from the design document
- Configured to run 100 iterations per test

## Running Tests

### Using Make (Recommended)

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

### Using pytest directly

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/unit/test_cli.py

# Run specific test function
uv run pytest tests/unit/test_cli.py::test_discover_command

# Run with verbose output
uv run pytest -v

# Run with coverage
uv run pytest --cov=cluster_manager --cov-report=html
```

### Using mise tasks

```bash
# Run all tests
mise run test

# Run unit tests
mise run test-unit

# Run property tests
mise run test-properties
```

## Writing Tests

### Unit Test Example

```python
import pytest
from cluster_manager.models.node import Node

def test_node_creation():
    """Test basic node creation with required fields."""
    node = Node(
        hostname="test-node",
        ansible_host="100.64.0.1",
        tailscale_ip="100.64.0.1",
        role="worker"
    )
    assert node.hostname == "test-node"
    assert node.role == "worker"

def test_node_validation_fails_with_invalid_ip():
    """Test that node creation fails with invalid IP."""
    with pytest.raises(ValueError):
        Node(
            hostname="test-node",
            ansible_host="invalid-ip",
            tailscale_ip="invalid-ip",
            role="worker"
        )
```

### Property-Based Test Example

```python
from hypothesis import given, strategies as st
from cluster_manager.models.node import Node

@given(
    hostname=st.text(min_size=1, max_size=63, alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-')),
    role=st.sampled_from(['control-plane', 'worker'])
)
def test_property_8_minimal_node_requirements(hostname, role):
    """
    Feature: tailscale-k8s-cluster, Property 8: Minimal node definition requirements

    For any node definition, only hostname, Tailscale IP, and role should be
    required fields, with all other fields being optional.
    """
    # Generate a valid Tailscale IP
    ip = f"100.64.{st.integers(0, 255).example()}.{st.integers(1, 254).example()}"

    # Should be able to create node with only required fields
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
    assert node.node_labels == {}
    assert node.node_taints == []
```

## Test Configuration

### pytest Configuration

Configuration is in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "--verbose",
    "--cov=cluster_manager",
    "--cov-report=term-missing",
    "--cov-report=html",
    "--hypothesis-show-statistics",
]
```

### Hypothesis Configuration

Hypothesis settings are configured in `pyproject.toml`:

```toml
[tool.hypothesis]
max_examples = 100
deadline = 5000
derandomize = false
```

- **max_examples**: Number of test cases to generate per property test
- **deadline**: Maximum time (ms) per test case
- **derandomize**: Set to false to use random data (true for reproducible tests)

### Coverage Configuration

Coverage settings are in `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["cluster_manager"]
omit = ["tests/*", ".venv/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]
```

## Coverage Reports

After running tests with coverage, reports are generated in:

- **Terminal**: Summary displayed in console
- **HTML**: Detailed report in `htmlcov/index.html`

To view the HTML report:

```bash
make coverage
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Code Quality Tools

### Linting with Ruff

```bash
# Check for issues
make lint

# Auto-fix issues
uv run ruff check --fix .

# Format code
make format
```

### Type Checking with mypy

```bash
# Run type checking with mypy
make type-check

# Check specific file
uv run mypy cluster_manager/cli.py
```

### Type Checking with ty (Experimental)

`ty` is an experimental type checker from Astral (creators of Ruff and uv):

```bash
# Run type checking with ty
make type-check-ty

# Or directly
uv run ty check cluster_manager
```

### Run All Checks

```bash
# Run all quality checks
make check-all
```

## Pre-commit Hooks

Pre-commit hooks automatically run checks before each commit.

### Install hooks

```bash
make pre-commit-install
# or
uv run pre-commit install
```

### Run hooks manually

```bash
uv run pre-commit run --all-files
```

### Configured hooks

- **trailing-whitespace**: Remove trailing whitespace
- **end-of-file-fixer**: Ensure files end with newline
- **check-yaml**: Validate YAML syntax
- **check-toml**: Validate TOML syntax
- **ruff**: Lint and format Python code
- **mypy**: Type checking

## Continuous Integration

Tests should be run in CI/CD pipeline:

```yaml
# Example GitHub Actions workflow
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install uv
          uv sync --extra dev
      - name: Run tests
        run: make test
      - name: Run checks
        run: make check-all
```

## Best Practices

1. **Write tests first**: Consider TDD for new features
2. **Test behavior, not implementation**: Focus on what the code does, not how
3. **Use descriptive names**: Test names should explain what they verify
4. **Keep tests isolated**: Each test should be independent
5. **Use fixtures**: Share setup code with pytest fixtures
6. **Mock external dependencies**: Don't rely on external services in unit tests
7. **Property tests for invariants**: Use Hypothesis for testing universal properties
8. **Unit tests for examples**: Use regular tests for specific scenarios
9. **Maintain coverage**: Aim for >80% coverage on critical paths
10. **Run tests frequently**: Use pre-commit hooks and CI/CD

## Troubleshooting

### Tests fail with import errors

Ensure dependencies are installed:
```bash
make install-dev
```

### Hypothesis tests are slow

Reduce `max_examples` in `pyproject.toml` for faster feedback during development.

### Coverage report missing files

Check that `source` in `[tool.coverage.run]` includes your package.

### Pre-commit hooks fail

Update hooks to latest versions:
```bash
uv run pre-commit autoupdate
```

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [Hypothesis documentation](https://hypothesis.readthedocs.io/)
- [pytest-cov documentation](https://pytest-cov.readthedocs.io/)
- [Ruff documentation](https://docs.astral.sh/ruff/)
- [mypy documentation](https://mypy.readthedocs.io/)
- [pre-commit documentation](https://pre-commit.com/)
