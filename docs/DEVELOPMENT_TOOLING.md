# Development Tooling Guide

This document describes the development tooling setup for the Kubani project.

## Overview

The project uses modern Python development tools to ensure code quality, maintainability, and correctness:

- **UV**: Fast Python package manager and script runner
- **pytest**: Unit testing framework
- **Hypothesis**: Property-based testing library
- **pytest-cov**: Code coverage reporting
- **ruff**: Fast Python linter and formatter
- **ty**: Experimental type checker (faster than mypy)
- **mypy**: Static type checker
- **pre-commit**: Git hooks for automated checks

## Quick Start

### Initial Setup

1. Install dependencies:
   ```bash
   make install
   ```

2. Install development dependencies:
   ```bash
   make install-dev
   ```

3. Install pre-commit hooks:
   ```bash
   make pre-commit-install
   ```

### Verify Installation

Run the verification script to ensure all tools are properly configured:

```bash
./scripts/verify_tooling.sh
```

## Testing

### Running Tests

```bash
# Run all tests
make test

# Run unit tests only
make test-unit

# Run property-based tests only
make test-props

# Run with coverage report
make coverage
```

### Test Organization

- **Unit tests**: `tests/unit/` - Test specific functions and classes
- **Property tests**: `tests/properties/` - Test universal properties across many inputs
- **Integration tests**: `tests/integration/` - Test complete workflows

### Property-Based Testing

Property-based tests use Hypothesis to generate test cases automatically. Each property test:

- Runs 100 examples by default (configured in `pyproject.toml`)
- References a specific correctness property from the design document
- Uses the format: `Feature: {feature_name}, Property {number}: {property_text}`

Example:
```python
from hypothesis import given, strategies as st

@given(hostname=st.text(min_size=1, max_size=63))
def test_property_8_minimal_node_definition_requirements(hostname):
    """
    Feature: tailscale-k8s-cluster, Property 8: Minimal node definition requirements

    For any node definition, only hostname, Tailscale IP, and role should be required.
    """
    # Test implementation
    pass
```

### Coverage Reports

Coverage reports are generated in two formats:

- **Terminal**: Shows coverage summary with missing lines
- **HTML**: Detailed report in `htmlcov/index.html`

Open the HTML report:
```bash
open htmlcov/index.html
```

## Code Quality

### Linting

```bash
# Check for linting issues
make lint

# Auto-fix issues where possible
uv run ruff check --fix .
```

### Formatting

```bash
# Format code
make format

# Check formatting without changes
uv run ruff format --check .
```

### Type Checking

```bash
# Type check with mypy
make type-check

# Type check with ty (faster)
make type-check-ty

# Check specific file
uv run ty check cluster_manager/models/node.py
```

### Run All Checks

```bash
make check-all
```

## Pre-commit Hooks

Pre-commit hooks run automatically before each commit to ensure code quality.

### Installed Hooks

1. **trailing-whitespace**: Remove trailing whitespace
2. **end-of-file-fixer**: Ensure files end with newline
3. **check-yaml**: Validate YAML syntax
4. **check-toml**: Validate TOML syntax
5. **check-merge-conflict**: Detect merge conflict markers
6. **ruff**: Lint and format Python code
7. **mypy**: Type check Python code

### Manual Execution

Run hooks on all files:
```bash
uv run pre-commit run --all-files
```

Run specific hook:
```bash
uv run pre-commit run ruff --all-files
```

### Bypassing Hooks

In rare cases where you need to bypass hooks:
```bash
git commit --no-verify -m "message"
```

**Note**: Only bypass hooks when absolutely necessary and ensure issues are fixed in a follow-up commit.

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

### Makefile

Provides convenient commands for common development tasks.

## Tool Details

### UV Package Manager

UV is a fast Python package manager written in Rust. It replaces pip and provides:

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

Experimental type checker that provides faster feedback than mypy.

Usage:
```bash
# Check specific file
uv run ty check cluster_manager/models/node.py

# Check entire package
uv run ty check cluster_manager
```

### Mypy

Static type checker for Python.

Configuration in `pyproject.toml`:
```toml
[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

## Continuous Integration

The project is configured to run all checks in CI:

1. Linting with ruff
2. Type checking with mypy
3. Unit tests
4. Property-based tests
5. Coverage reporting

## Best Practices

### Before Committing

1. Run tests: `make test`
2. Check linting: `make lint`
3. Format code: `make format`
4. Type check: `make type-check`

Or run all at once:
```bash
make check-all && make test
```

### Writing Tests

1. **Unit tests**: Test specific functionality with concrete examples
2. **Property tests**: Test universal properties across many inputs
3. **Both are important**: Unit tests catch specific bugs, property tests verify general correctness

### Type Hints

- Add type hints to all function signatures
- Use `from typing import` for complex types
- Run type checker regularly: `make type-check-ty`

### Code Style

- Follow PEP 8 guidelines
- Use ruff for automatic formatting
- Keep line length to 100 characters
- Use descriptive variable names

## Troubleshooting

### Pre-commit Hook Failures

If pre-commit hooks fail:

1. Review the error messages
2. Fix the issues manually or run `make format`
3. Stage the changes: `git add .`
4. Commit again

### Type Checking Errors

If type checking fails:

1. Review the error messages
2. Add missing type hints
3. Fix type mismatches
4. Run `make type-check` to verify

### Test Failures

If tests fail:

1. Review the test output
2. Fix the code or update the test
3. Run tests again: `make test`
4. Check coverage: `make coverage`

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
