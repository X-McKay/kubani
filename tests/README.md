# Kubani Nexus Testing Guide

This directory contains comprehensive tests for the Kubani Nexus system. The test suite validates all components from unit tests to full end-to-end integration with cluster services.

## Table of Contents

- [Overview](#overview)
- [Test Structure](#test-structure)
- [Quick Start](#quick-start)
- [Test Setup](#test-setup)
- [Running Tests](#running-tests)
- [Test Categories](#test-categories)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## Overview

The Nexus test suite follows a pyramid structure:

```
                    ┌─────────────────────┐
                    │   E2E Tests (5%)    │
                    │  Cluster Services   │
                    └─────────────────────┘
                  ┌───────────────────────────┐
                  │  Integration Tests (20%)  │
                  │  Gateway, Workflow, DB    │
                  └───────────────────────────┘
              ┌─────────────────────────────────────┐
              │      Unit Tests (75%)                │
              │  Models, Activities, Sandbox, DB     │
              └─────────────────────────────────────┘
```

### Coverage Targets

- Overall: ≥ 75%
- Unit tests: ≥ 80%
- Integration tests: ≥ 60%
- E2E tests: ≥ 40%

## Test Structure

```
tests/
├── README.md                    # This file
├── fixtures/                    # Test fixtures and mocks
│   └── mocks.py                # Mock objects for testing
├── utils/                       # Test utilities
│   ├── helpers.py              # Helper functions
│   └── cluster_config.py       # Cluster configuration
├── unit/                        # Unit tests (75% of tests)
│   ├── models/                 # Pydantic model tests
│   ├── db/                     # Database operation tests
│   ├── sandbox/                # Sandbox executor tests
│   ├── activities/             # Temporal activity tests
│   └── config/                 # Configuration tests
├── integration/                 # Integration tests (20% of tests)
│   ├── gateway/                # Gateway API tests
│   ├── workflow/               # Workflow orchestration tests
│   └── database/               # Database schema tests
├── e2e/                        # End-to-end tests (5% of tests)
│   ├── test_conversation_flow.py
│   ├── test_approval_workflow.py
│   ├── test_memory_system.py
│   └── test_error_handling.py
├── performance/                 # Performance tests
├── security/                    # Security tests
├── error_handling/             # Error handling tests
├── cluster/                    # Cluster integration tests
├── build/                      # Build artifact tests
└── quality/                    # Code quality tests
```

## Quick Start

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- `uv` package manager
- Access to Kubernetes cluster (for E2E tests)

### Install Dependencies

```bash
# Install all dependencies including test extras
uv sync --all-extras
```

### Run All Tests

```bash
# Run the complete test suite
uv run pytest

# Run with coverage report
uv run pytest --cov=kubani.nexus --cov-report=html
```

### Run Specific Test Categories

```bash
# Unit tests only (fast)
uv run pytest tests/unit/ -v

# Integration tests only (medium)
uv run pytest tests/integration/ -v

# E2E tests only (slow, requires cluster)
uv run pytest tests/e2e/ -v
```

## Test Setup

### Local Development Setup

1. **Start Required Services**

```bash
# Start PostgreSQL, Redis, and Temporal
docker-compose -f docker-compose.test.yml up -d

# Verify services are running
docker-compose -f docker-compose.test.yml ps
```

2. **Configure Environment Variables**

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your configuration
# Required variables:
# - NEXUS_DATABASE_URL
# - REDIS_URL
# - TEMPORAL_HOST
# - OPENAI_API_KEY (for LLM tests)
```

3. **Initialize Test Database**

```bash
# Run database initialization script
docker-compose -f docker-compose.test.yml exec postgres \
  psql -U postgres -d nexus_test -f /docker-entrypoint-initdb.d/nexus-init.sql
```

### Cluster Testing Setup

For E2E tests that require cluster services:

1. **Configure Cluster Access**

```bash
# Ensure kubeconfig is in standard location
mkdir -p ~/.kube

# If needed, fetch from control plane
ssh al@100.71.65.62 "sudo cat /etc/rancher/k3s/k3s.yaml" | \
  sed 's/127.0.0.1/100.71.65.62/g' > ~/.kube/config
chmod 600 ~/.kube/config

# Verify cluster access
kubectl get pods -n kubani
```

2. **Set Cluster Environment Variables**

```bash
# Add to .env or export
export CLUSTER_VLLM_ENDPOINT="http://vllm.kubani.svc.cluster.local:8000"
export CLUSTER_TEMPORAL_ENDPOINT="temporal.kubani.svc.cluster.local:7233"
export CLUSTER_REDIS_ENDPOINT="redis.kubani.svc.cluster.local:6379"
export CLUSTER_POSTGRES_ENDPOINT="postgresql.kubani.svc.cluster.local:5432"
export CLUSTER_QDRANT_ENDPOINT="http://qdrant.kubani.svc.cluster.local:6333"
export CLUSTER_NEO4J_ENDPOINT="bolt://neo4j.kubani.svc.cluster.local:7687"
```

3. **Verify Cluster Services**

```bash
# Check service health
kubectl get svc -n kubani
kubectl get pods -n kubani

# Test connectivity
kubectl port-forward -n kubani svc/vllm 8000:8000 &
curl http://localhost:8000/health
```

## Running Tests

### Basic Test Execution

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run with extra verbose output (show test names)
uv run pytest -vv

# Run specific test file
uv run pytest tests/unit/models/test_messages.py

# Run specific test function
uv run pytest tests/unit/models/test_messages.py::test_user_message_serialization
```

### Test Markers

Tests are organized with markers for selective execution:

```bash
# Run only unit tests
uv run pytest -m unit

# Run only integration tests
uv run pytest -m integration

# Run only E2E tests
uv run pytest -m e2e

# Run only cluster tests
uv run pytest -m cluster

# Run only property-based tests
uv run pytest -m property

# Run only security tests
uv run pytest -m security

# Run only performance tests
uv run pytest -m performance

# Combine markers (unit OR integration)
uv run pytest -m "unit or integration"

# Exclude markers (everything except e2e)
uv run pytest -m "not e2e"
```

### Coverage Reports

```bash
# Generate HTML coverage report
uv run pytest --cov=kubani.nexus --cov-report=html

# View report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux

# Generate terminal report with missing lines
uv run pytest --cov=kubani.nexus --cov-report=term-missing

# Fail if coverage below threshold
uv run pytest --cov=kubani.nexus --cov-fail-under=75
```

### Parallel Execution

```bash
# Install pytest-xdist
uv pip install pytest-xdist

# Run tests in parallel (auto-detect CPU count)
uv run pytest -n auto

# Run with specific number of workers
uv run pytest -n 4

# Note: Integration and E2E tests should run sequentially
uv run pytest tests/unit/ -n auto
uv run pytest tests/integration/
uv run pytest tests/e2e/
```

### Test Output Control

```bash
# Show print statements
uv run pytest -s

# Show local variables on failure
uv run pytest -l

# Stop on first failure
uv run pytest -x

# Stop after N failures
uv run pytest --maxfail=3

# Show slowest tests
uv run pytest --durations=10

# Show test setup/teardown
uv run pytest --setup-show
```

## Test Categories

### Unit Tests

**Location:** `tests/unit/`

**Purpose:** Test individual components in isolation with mocked dependencies

**Execution Time:** Fast (< 5 seconds per test)

**Examples:**
```bash
# Test Pydantic models
uv run pytest tests/unit/models/

# Test database operations (mocked)
uv run pytest tests/unit/db/

# Test sandbox executor
uv run pytest tests/unit/sandbox/

# Test Temporal activities
uv run pytest tests/unit/activities/
```

### Integration Tests

**Location:** `tests/integration/`

**Purpose:** Test component interactions with real services

**Execution Time:** Medium (5-30 seconds per test)

**Requirements:**
- Docker Compose services running
- PostgreSQL, Redis, Temporal

**Examples:**
```bash
# Start services first
docker-compose -f docker-compose.test.yml up -d

# Test Gateway API
uv run pytest tests/integration/gateway/

# Test workflow orchestration
uv run pytest tests/integration/workflow/

# Test database schema
uv run pytest tests/integration/database/
```

### End-to-End Tests

**Location:** `tests/e2e/`

**Purpose:** Test complete system with all components

**Execution Time:** Slow (30-300 seconds per test)

**Requirements:**
- All integration test requirements
- Cluster access (optional but recommended)
- LLM service available

**Examples:**
```bash
# Test full conversation flow
uv run pytest tests/e2e/test_conversation_flow.py

# Test approval workflow
uv run pytest tests/e2e/test_approval_workflow.py

# Test memory system
uv run pytest tests/e2e/test_memory_system.py

# Test with cluster services
uv run pytest tests/e2e/ -m cluster
```

### Property-Based Tests

**Framework:** Hypothesis

**Purpose:** Test universal properties across many generated inputs

**Configuration:** 100 examples per property

**Examples:**
```bash
# Run all property tests
uv run pytest -m property

# Run with more examples
uv run pytest -m property --hypothesis-seed=12345

# Show statistics
uv run pytest -m property --hypothesis-show-statistics
```

### Performance Tests

**Location:** `tests/performance/`

**Purpose:** Validate system performance under load

**Examples:**
```bash
# Test concurrent connections
uv run pytest tests/performance/test_concurrent_connections.py

# Test rapid message processing
uv run pytest tests/performance/test_rapid_message_processing.py

# Test database query performance
uv run pytest tests/performance/test_database_query_performance.py
```

### Security Tests

**Location:** `tests/security/`

**Purpose:** Validate security controls and isolation

**Examples:**
```bash
# Test sandbox security
uv run pytest tests/security/test_sandbox_security.py

# Run all security tests
uv run pytest -m security
```

## Troubleshooting

### Common Issues

#### 1. Tests Not Discovered

**Problem:** pytest doesn't find tests

**Solution:**
```bash
# Check test paths in pyproject.toml
cat pyproject.toml | grep testpaths

# Should include both:
# testpaths = ["tests", "kubani/tests"]

# Verify test file naming
# Files must start with test_*.py
# Functions must start with test_*
```

#### 2. Import Errors

**Problem:** `ModuleNotFoundError` or import failures

**Solution:**
```bash
# Ensure virtual environment is activated
source .venv/bin/activate

# Reinstall dependencies
uv sync --all-extras

# Check PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Verify __init__.py files exist
find kubani/nexus -name __init__.py
```

#### 3. Database Connection Errors

**Problem:** Cannot connect to PostgreSQL

**Solution:**
```bash
# Check if services are running
docker-compose -f docker-compose.test.yml ps

# Restart services
docker-compose -f docker-compose.test.yml restart postgres

# Check connection
docker-compose -f docker-compose.test.yml exec postgres \
  psql -U postgres -c "SELECT 1"

# Verify environment variables
echo $NEXUS_DATABASE_URL
```

#### 4. Temporal Connection Errors

**Problem:** Cannot connect to Temporal

**Solution:**
```bash
# Check Temporal service
docker-compose -f docker-compose.test.yml logs temporal

# Restart Temporal
docker-compose -f docker-compose.test.yml restart temporal

# Wait for Temporal to be ready
sleep 10

# Verify connection
curl http://localhost:7233/health
```

#### 5. Redis Connection Errors

**Problem:** Cannot connect to Redis

**Solution:**
```bash
# Check Redis service
docker-compose -f docker-compose.test.yml logs redis

# Test connection
docker-compose -f docker-compose.test.yml exec redis redis-cli ping

# Should return: PONG
```

#### 6. Cluster Access Issues

**Problem:** Cannot access cluster services

**Solution:**
```bash
# Verify kubeconfig
kubectl cluster-info

# Check namespace
kubectl get pods -n kubani

# Test service connectivity
kubectl port-forward -n kubani svc/vllm 8000:8000

# Verify in another terminal
curl http://localhost:8000/health
```

#### 7. LLM API Errors

**Problem:** LLM tests fail with API errors

**Solution:**
```bash
# Check API key
echo $OPENAI_API_KEY

# For cluster LLM, verify endpoint
echo $CLUSTER_VLLM_ENDPOINT

# Test endpoint directly
curl $CLUSTER_VLLM_ENDPOINT/health

# Skip LLM tests if unavailable
uv run pytest -m "not cluster"
```

#### 8. Slow Tests

**Problem:** Tests take too long

**Solution:**
```bash
# Run only fast unit tests
uv run pytest tests/unit/ -n auto

# Skip slow tests
uv run pytest -m "not e2e"

# Show slowest tests
uv run pytest --durations=10

# Increase timeout for slow tests
uv run pytest --timeout=600
```

#### 9. Flaky Tests

**Problem:** Tests pass/fail intermittently

**Solution:**
```bash
# Run test multiple times
uv run pytest tests/path/to/test.py --count=10

# Use pytest-rerunfailures
uv pip install pytest-rerunfailures
uv run pytest --reruns 3

# Mark test as flaky in code
@pytest.mark.flaky(reruns=3)
def test_flaky_behavior():
    ...
```

#### 10. Coverage Not Generated

**Problem:** Coverage report is empty or missing

**Solution:**
```bash
# Ensure pytest-cov is installed
uv pip install pytest-cov

# Run with explicit coverage
uv run pytest --cov=kubani.nexus --cov-report=html

# Check .coveragerc or pyproject.toml for exclusions
cat pyproject.toml | grep -A 10 "\[tool.coverage"

# Clear old coverage data
rm -rf .coverage htmlcov/
```

### Debug Mode

```bash
# Run with Python debugger
uv run pytest --pdb

# Drop into debugger on failure
uv run pytest --pdb --maxfail=1

# Use ipdb for better debugging
uv pip install ipdb
uv run pytest --pdbcls=IPython.terminal.debugger:TerminalPdb
```

### Logging

```bash
# Show all logs
uv run pytest --log-cli-level=DEBUG

# Show logs only on failure
uv run pytest --log-cli-level=INFO

# Capture logs to file
uv run pytest --log-file=test.log --log-file-level=DEBUG
```

## Contributing

### Writing New Tests

1. **Choose the Right Test Type**
   - Unit test: Testing a single function/class in isolation
   - Integration test: Testing component interactions
   - E2E test: Testing complete user workflows

2. **Follow Naming Conventions**
   - File: `test_<component>.py`
   - Function: `test_<behavior>`
   - Class: `Test<Component>`

3. **Use Appropriate Fixtures**
   - Import from `tests/fixtures/mocks.py`
   - Create new fixtures in `conftest.py`
   - Use `@pytest.fixture` decorator

4. **Add Test Markers**
   ```python
   @pytest.mark.unit
   @pytest.mark.asyncio
   async def test_my_function():
       ...
   ```

5. **Write Clear Assertions**
   ```python
   # Good
   assert result.status == "completed"
   assert len(messages) == 5
   
   # Better
   assert result.status == "completed", f"Expected completed, got {result.status}"
   assert len(messages) == 5, f"Expected 5 messages, got {len(messages)}"
   ```

6. **Document Test Purpose**
   ```python
   def test_user_message_validation():
       """Test that UserMessage validates source enum correctly.
       
       This test verifies that invalid MessageSource values raise
       ValidationError as specified in Requirement 1.2.
       """
       ...
   ```

### Running Tests Before Commit

```bash
# Run pre-commit checks
uv run ruff check kubani/
uv run mypy kubani/nexus/

# Run relevant tests
uv run pytest tests/unit/ -n auto

# Check coverage
uv run pytest --cov=kubani.nexus --cov-fail-under=75
```

### CI/CD Integration

Tests run automatically on:
- Push to any branch
- Pull request creation
- Pull request updates

See `.github/workflows/test-nexus.yml` for CI configuration.

## Additional Resources

- [Design Document](.kiro/specs/nexus-testing/design.md)
- [Requirements Document](.kiro/specs/nexus-testing/requirements.md)
- [Test Execution Guide](./TEST_EXECUTION.md)
- [CI/CD Documentation](./CI_CD.md)
- [Pytest Documentation](https://docs.pytest.org/)
- [Hypothesis Documentation](https://hypothesis.readthedocs.io/)

## Support

For issues or questions:
1. Check this README and troubleshooting section
2. Review test logs and error messages
3. Check existing tests for examples
4. Ask in team chat or create an issue

---

**Last Updated:** 2026-02-11
**Maintained By:** Kubani Development Team
