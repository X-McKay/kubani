#!/bin/bash
# Verification script for development tooling setup

set -e

echo "==================================="
echo "Development Tooling Verification"
echo "==================================="
echo ""

# Check Python version
echo "✓ Checking Python version..."
python --version

# Check UV
echo "✓ Checking UV package manager..."
uv --version

# Check pytest
echo "✓ Checking pytest..."
uv run pytest --version

# Check Hypothesis
echo "✓ Checking Hypothesis..."
uv run python -c "import hypothesis; print(f'Hypothesis {hypothesis.__version__}')"

# Check pytest-cov
echo "✓ Checking pytest-cov..."
uv run python -c "import pytest_cov; print('pytest-cov installed')"

# Check ruff
echo "✓ Checking ruff..."
uv run ruff --version

# Check ty
echo "✓ Checking ty..."
uv run ty --version

# Check pre-commit
echo "✓ Checking pre-commit..."
uv run pre-commit --version

# Check if pre-commit hooks are installed
echo "✓ Checking pre-commit hooks installation..."
if [ -f .git/hooks/pre-commit ]; then
    echo "  Pre-commit hooks are installed"
else
    echo "  WARNING: Pre-commit hooks not installed. Run: make pre-commit-install"
fi

echo ""
echo "==================================="
echo "Running Quick Tests"
echo "==================================="
echo ""

# Run a quick unit test
echo "✓ Running unit tests..."
uv run pytest tests/unit/test_basic.py -v --tb=short

# Run a quick property test
echo ""
echo "✓ Running property-based tests..."
uv run pytest tests/properties/test_node_model.py::test_property_8_minimal_node_definition_requirements -v --tb=short

# Run linting check
echo ""
echo "✓ Running linting check..."
uv run ruff check cluster_manager --select E,F --quiet && echo "  No critical errors found"

# Run type checking
echo ""
echo "✓ Running type checking with ty..."
uv run ty check cluster_manager/models/node.py

echo ""
echo "==================================="
echo "All tooling verified successfully!"
echo "==================================="
echo ""
echo "Available commands:"
echo "  make test          - Run all tests"
echo "  make test-unit     - Run unit tests only"
echo "  make test-props    - Run property-based tests only"
echo "  make coverage      - Run tests with coverage report"
echo "  make lint          - Run linting checks"
echo "  make format        - Format code"
echo "  make type-check    - Run type checking with mypy"
echo "  make type-check-ty - Run type checking with ty"
echo "  make check-all     - Run all checks"
echo ""
