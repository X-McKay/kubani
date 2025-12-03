.PHONY: help install install-dev test test-unit test-props coverage lint format type-check type-check-ty check-all pre-commit-install clean

help:
	@echo "Kubani - Kubernetes Cluster Automation"
	@echo ""
	@echo "Available targets:"
	@echo "  install           - Install dependencies using UV"
	@echo "  install-dev       - Install dev dependencies"
	@echo "  test              - Run all tests"
	@echo "  test-unit         - Run unit tests only"
	@echo "  test-props        - Run property-based tests only"
	@echo "  coverage          - Run tests with coverage report"
	@echo "  lint              - Run linting checks"
	@echo "  format            - Format code"
	@echo "  type-check        - Run type checking with mypy"
	@echo "  type-check-ty     - Run type checking with ty (experimental)"
	@echo "  check-all         - Run all checks (lint, format, type)"
	@echo "  pre-commit-install - Install pre-commit hooks"
	@echo "  clean             - Remove build artifacts"

install:
	uv sync

install-dev:
	uv sync --extra dev

test:
	uv run pytest

test-unit:
	uv run pytest tests/unit

test-props:
	uv run pytest tests/properties

coverage:
	uv run pytest --cov=cluster_manager --cov-report=html --cov-report=term

lint:
	uv run ruff check .

format:
	uv run ruff format .

type-check:
	uv run mypy cluster_manager

type-check-ty:
	uv run ty check cluster_manager

check-all: lint type-check
	@echo "All checks passed!"

pre-commit-install:
	uv run pre-commit install

clean:
	rm -rf build/ dist/ *.egg-info
	rm -rf .pytest_cache .mypy_cache .ruff_cache .hypothesis
	rm -rf htmlcov/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
