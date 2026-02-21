# Test Execution Guide

This guide provides detailed instructions for running different types of tests in the Kubani Nexus test suite.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Environment Setup](#environment-setup)
- [Running Unit Tests](#running-unit-tests)
- [Running Integration Tests](#running-integration-tests)
- [Running E2E Tests with Cluster](#running-e2e-tests-with-cluster)
- [Running Specific Test Suites](#running-specific-test-suites)
- [Advanced Test Execution](#advanced-test-execution)
- [Continuous Integration](#continuous-integration)

## Prerequisites

### Required Software

- **Python 3.12+**: Check with `python --version`
- **uv**: Package manager - Install from https://docs.astral.sh/uv/
- **Docker**: For running test services - Check with `docker --version`
- **Docker Compose**: For orchestrating services - Check with `docker-compose --version`
- **kubectl**: For cluster access (E2E tests only) - Check with `kubectl version`

### Installation

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone repository
git clone <repository-url>
cd kubani

# Install dependencies
uv sync --all-extras

# Verify installation
uv run pytest --version
```

## Environment Setup

### Local Development Environment

1. **Create Environment File**

```bash
# Copy example file
cp .env.example .env

# Edit with your settings
nano .env
```

Required variables for local testing:
```bash
# Database
NEXUS_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/nexus_test

# Redis
REDIS_URL=redis://localhost:6379/0

# Temporal
TEMPORAL_HOST=localhost:7233
TEMPORAL_NAMESPACE=default

# LLM (optional for unit tests)
OPENAI_API_KEY=your-api-key-here
```

2. **Start Test Services**

```bash
# Start all required services
docker-compose -f docker-compose.test.yml up -d

# Verify services are running
docker-compose -f docker-compose.test.yml ps

# Expected output:
# NAME                COMMAND                  SERVICE    STATUS
# postgres            "docker-entrypoint..."   postgres   Up
# redis               "docker-entrypoint..."   redis      Up
# temporal            "temporal server..."     temporal   Up
```

3. **Initialize Database**

```bash
# Wait for PostgreSQL to be ready
sleep 5

# Run initialization script
docker-compose -f docker-compose.test.yml exec postgres \
  psql -U postgres -d nexus_test -f /docker-entrypoint-initdb.d/nexus-init.sql

# Verify tables were created
docker-compose -f docker-compose.test.yml exec postgres \
  psql -U postgres -d nexus_test -c "\dt"
```

### Cluster Environment (for E2E Tests)

1. **Configure Kubernetes Access**

```bash
# Ensure kubeconfig is in standard location
mkdir -p ~/.kube

# If needed, fetch from control plane (sparky)
ssh al@100.71.65.62 "sudo cat /etc/rancher/k3s/k3s.yaml" | \
  sed 's/127.0.0.1/100.71.65.62/g' > ~/.kube/config
chmod 600 ~/.kube/config

# Verify cluster access
kubectl cluster-info
kubectl get nodes
kubectl get pods -n kubani
```

2. **Set Cluster Environment Variables**

Add to `.env` or export:
```bash
# Cluster service endpoints
export CLUSTER_VLLM_ENDPOINT="http://vllm.kubani.svc.cluster.local:8000"
export CLUSTER_TEMPORAL_ENDPOINT="temporal.kubani.svc.cluster.local:7233"
export CLUSTER_REDIS_ENDPOINT="redis.kubani.svc.cluster.local:6379"
export CLUSTER_POSTGRES_ENDPOINT="postgresql.kubani.svc.cluster.local:5432"
export CLUSTER_QDRANT_ENDPOINT="http://qdrant.kubani.svc.cluster.local:6333"
export CLUSTER_NEO4J_ENDPOINT="bolt://neo4j.kubani.svc.cluster.local:7687"

# Kubernetes configuration
export KUBECONFIG=~/.kube/config
export KUBE_NAMESPACE=kubani
```

3. **Verify Cluster Services**

```bash
# Check service status
kubectl get svc -n kubani
kubectl get pods -n kubani

# Test vLLM endpoint
kubectl port-forward -n kubani svc/vllm 8000:8000 &
curl http://localhost:8000/health
kill %1  # Stop port-forward

# Test Temporal endpoint
kubectl port-forward -n kubani svc/temporal 7233:7233 &
curl http://localhost:7233/health
kill %1
```

## Running Unit Tests

Unit tests are fast, isolated tests that mock external dependencies. They should run in < 5 seconds per test.

### Run All Unit Tests

```bash
# Basic execution
uv run pytest tests/unit/

# With verbose output
uv run pytest tests/unit/ -v

# With coverage
uv run pytest tests/unit/ --cov=kubani.nexus --cov-report=term-missing

# Parallel execution (faster)
uv run pytest tests/unit/ -n auto
```

### Run Specific Unit Test Suites

```bash
# Test models only
uv run pytest tests/unit/models/ -v

# Test database operations
uv run pytest tests/unit/db/ -v

# Test sandbox executor
uv run pytest tests/unit/sandbox/ -v

# Test Temporal activities
uv run pytest tests/unit/activities/ -v

# Test configuration
uv run pytest tests/unit/config/ -v
```

### Run Individual Unit Tests

```bash
# Run specific test file
uv run pytest tests/unit/models/test_messages.py -v

# Run specific test function
uv run pytest tests/unit/models/test_messages.py::test_user_message_serialization -v

# Run specific test class
uv run pytest tests/unit/models/test_messages.py::TestUserMessage -v

# Run specific test method in class
uv run pytest tests/unit/models/test_messages.py::TestUserMessage::test_validation -v
```

### Unit Test Examples

```bash
# Test message serialization (Property-based test)
uv run pytest tests/unit/models/test_messages.py::test_user_message_serialization_roundtrip -v

# Test workflow state message window (Property-based test)
uv run pytest tests/unit/models/test_state.py::test_workflow_state_message_window -v

# Test sandbox security (Static analysis)
uv run pytest tests/unit/sandbox/test_executor.py::test_dangerous_import_detection -v

# Test database operations (Mocked)
uv run pytest tests/unit/db/test_conversations.py::test_save_message -v
```

### Expected Output

```
tests/unit/models/test_messages.py::test_user_message_serialization_roundtrip PASSED [100%]

========================= 1 passed in 0.23s =========================
```

## Running Integration Tests

Integration tests validate component interactions with real services. They require Docker Compose services to be running.

### Prerequisites

```bash
# Ensure services are running
docker-compose -f docker-compose.test.yml up -d

# Wait for services to be ready
sleep 10

# Verify services
docker-compose -f docker-compose.test.yml ps
```

### Run All Integration Tests

```bash
# Basic execution (sequential)
uv run pytest tests/integration/ -v

# With coverage
uv run pytest tests/integration/ --cov=kubani.nexus --cov-report=html

# With detailed output
uv run pytest tests/integration/ -vv -s
```

### Run Specific Integration Test Suites

```bash
# Test Gateway REST API
uv run pytest tests/integration/gateway/test_rest_api.py -v

# Test Gateway WebSocket
uv run pytest tests/integration/gateway/test_websocket.py -v

# Test Workflow orchestration
uv run pytest tests/integration/workflow/test_orchestrator.py -v

# Test Database schema
uv run pytest tests/integration/database/test_schema.py -v
```

### Integration Test Examples

```bash
# Test POST /api/nexus/chat endpoint
uv run pytest tests/integration/gateway/test_rest_api.py::test_post_chat -v

# Test WebSocket connection
uv run pytest tests/integration/gateway/test_websocket.py::test_websocket_connection -v

# Test workflow initialization
uv run pytest tests/integration/workflow/test_orchestrator.py::test_workflow_initialization -v

# Test database schema creation
uv run pytest tests/integration/database/test_schema.py::test_schema_creation -v
```

### Expected Output

```
tests/integration/gateway/test_rest_api.py::test_post_chat PASSED [100%]

========================= 1 passed in 2.45s =========================
```

### Troubleshooting Integration Tests

```bash
# Check service logs if tests fail
docker-compose -f docker-compose.test.yml logs postgres
docker-compose -f docker-compose.test.yml logs redis
docker-compose -f docker-compose.test.yml logs temporal

# Restart services
docker-compose -f docker-compose.test.yml restart

# Clean restart (removes volumes)
docker-compose -f docker-compose.test.yml down -v
docker-compose -f docker-compose.test.yml up -d
```

## Running E2E Tests with Cluster

E2E tests validate the complete system with all components, including cluster-deployed services.

### Prerequisites

```bash
# Verify cluster access
kubectl cluster-info
kubectl get pods -n kubani

# Verify cluster services are running
kubectl get svc -n kubani | grep -E "(vllm|temporal|redis|postgresql)"

# Verify environment variables
echo $CLUSTER_VLLM_ENDPOINT
echo $CLUSTER_TEMPORAL_ENDPOINT
```

### Run All E2E Tests

```bash
# Basic execution (sequential, slow)
uv run pytest tests/e2e/ -v

# With cluster marker
uv run pytest tests/e2e/ -m cluster -v

# With detailed logging
uv run pytest tests/e2e/ -v -s --log-cli-level=INFO

# With timeout (5 minutes per test)
uv run pytest tests/e2e/ -v --timeout=300
```

### Run Specific E2E Test Suites

```bash
# Test full conversation flow
uv run pytest tests/e2e/test_conversation_flow.py -v

# Test approval workflow
uv run pytest tests/e2e/test_approval_workflow.py -v

# Test memory system
uv run pytest tests/e2e/test_memory_system.py -v

# Test error handling
uv run pytest tests/e2e/test_error_handling.py -v
```

### E2E Test Examples

```bash
# Test complete message processing pipeline
uv run pytest tests/e2e/test_conversation_flow.py::test_complete_message_processing -v

# Test task execution with skills
uv run pytest tests/e2e/test_conversation_flow.py::test_task_execution_with_skills -v

# Test approval granted flow
uv run pytest tests/e2e/test_approval_workflow.py::test_approval_granted -v

# Test memory storage and recall
uv run pytest tests/e2e/test_memory_system.py::test_memory_storage -v
```

### Expected Output

```
tests/e2e/test_conversation_flow.py::test_complete_message_processing PASSED [100%]

========================= 1 passed in 45.23s =========================
```

### Cluster-Specific Tests

```bash
# Test cluster LLM integration
uv run pytest tests/cluster/test_llm_integration.py -v

# Test cluster services integration
uv run pytest tests/cluster/test_services_integration.py -v

# Run all cluster tests
uv run pytest tests/cluster/ -v
```

### Troubleshooting E2E Tests

```bash
# Check cluster pod status
kubectl get pods -n kubani

# Check pod logs
kubectl logs -n kubani <pod-name>

# Check service endpoints
kubectl get svc -n kubani

# Port-forward for debugging
kubectl port-forward -n kubani svc/vllm 8000:8000

# Test endpoint directly
curl http://localhost:8000/health

# Check Temporal workflows
kubectl port-forward -n kubani svc/temporal 8080:8080
# Open http://localhost:8080 in browser
```

## Running Specific Test Suites

### Performance Tests

```bash
# Run all performance tests
uv run pytest tests/performance/ -v

# Test concurrent connections
uv run pytest tests/performance/test_concurrent_connections.py -v

# Test rapid message processing
uv run pytest tests/performance/test_rapid_message_processing.py -v

# Test database query performance
uv run pytest tests/performance/test_database_query_performance.py -v
```

### Security Tests

```bash
# Run all security tests
uv run pytest tests/security/ -v

# Test sandbox security
uv run pytest tests/security/test_sandbox_security.py -v

# Run with security marker
uv run pytest -m security -v
```

### Error Handling Tests

```bash
# Run all error handling tests
uv run pytest tests/error_handling/ -v

# Test LLM unavailability
uv run pytest tests/error_handling/test_llm_unavailability.py -v

# Test database connection loss
uv run pytest tests/error_handling/test_database_connection_loss.py -v
```

### Build Tests

```bash
# Run all build tests
uv run pytest tests/build/ -v

# Test Dockerfiles
uv run pytest tests/build/test_dockerfiles.py -v

# Test Docker Compose
uv run pytest tests/build/test_docker_compose.py -v
```

### Code Quality Tests

```bash
# Run all quality tests
uv run pytest tests/quality/ -v

# Test code quality
uv run pytest tests/quality/test_code_quality.py -v

# Run linting
uv run ruff check kubani/

# Run type checking
uv run mypy kubani/nexus/
```

## Advanced Test Execution

### Using Test Markers

```bash
# Run only unit tests
uv run pytest -m unit -v

# Run only integration tests
uv run pytest -m integration -v

# Run only E2E tests
uv run pytest -m e2e -v

# Run only property-based tests
uv run pytest -m property -v

# Combine markers (unit OR integration)
uv run pytest -m "unit or integration" -v

# Exclude markers (everything except E2E)
uv run pytest -m "not e2e" -v

# Multiple exclusions
uv run pytest -m "not e2e and not cluster" -v
```

### Filtering by Test Name

```bash
# Run tests matching pattern
uv run pytest -k "message" -v

# Run tests NOT matching pattern
uv run pytest -k "not websocket" -v

# Multiple patterns (OR)
uv run pytest -k "message or workflow" -v

# Multiple patterns (AND)
uv run pytest -k "message and serialization" -v
```

### Controlling Test Output

```bash
# Show print statements
uv run pytest -s

# Show local variables on failure
uv run pytest -l

# Show full diff on assertion failure
uv run pytest -vv

# Capture logs
uv run pytest --log-cli-level=DEBUG

# Show test durations
uv run pytest --durations=10

# Show slowest 20 tests
uv run pytest --durations=20
```

### Stopping on Failures

```bash
# Stop on first failure
uv run pytest -x

# Stop after 3 failures
uv run pytest --maxfail=3

# Run last failed tests only
uv run pytest --lf

# Run failed tests first, then others
uv run pytest --ff
```

### Parallel Execution

```bash
# Auto-detect CPU count
uv run pytest tests/unit/ -n auto

# Use 4 workers
uv run pytest tests/unit/ -n 4

# Distribute by file
uv run pytest tests/unit/ -n auto --dist=loadfile

# Distribute by test
uv run pytest tests/unit/ -n auto --dist=loadscope
```

### Coverage Options

```bash
# Basic coverage
uv run pytest --cov=kubani.nexus

# HTML report
uv run pytest --cov=kubani.nexus --cov-report=html

# Terminal report with missing lines
uv run pytest --cov=kubani.nexus --cov-report=term-missing

# XML report (for CI)
uv run pytest --cov=kubani.nexus --cov-report=xml

# Multiple reports
uv run pytest --cov=kubani.nexus --cov-report=html --cov-report=term

# Fail if coverage below threshold
uv run pytest --cov=kubani.nexus --cov-fail-under=75

# Show coverage for specific module
uv run pytest --cov=kubani.nexus.models --cov-report=term-missing
```

### Debugging Tests

```bash
# Drop into debugger on failure
uv run pytest --pdb

# Drop into debugger at start of test
uv run pytest --trace

# Use ipdb for better debugging
uv pip install ipdb
uv run pytest --pdbcls=IPython.terminal.debugger:TerminalPdb

# Show setup/teardown
uv run pytest --setup-show

# Verbose fixture output
uv run pytest --fixtures
```

### Property-Based Testing Options

```bash
# Run with specific seed (reproducible)
uv run pytest -m property --hypothesis-seed=12345

# Show statistics
uv run pytest -m property --hypothesis-show-statistics

# Run more examples
uv run pytest -m property --hypothesis-profile=thorough

# Debug mode (verbose output)
uv run pytest -m property --hypothesis-verbosity=verbose
```

## Continuous Integration

### Local CI Simulation

Run the same checks that CI runs:

```bash
# 1. Linting
uv run ruff check kubani/

# 2. Type checking
uv run mypy kubani/nexus/

# 3. Unit tests with coverage
uv run pytest tests/unit/ -n auto --cov=kubani.nexus --cov-fail-under=75

# 4. Integration tests
uv run pytest tests/integration/ -v

# 5. E2E tests (if cluster available)
uv run pytest tests/e2e/ -v

# 6. Security tests
uv run pytest -m security -v

# 7. Code quality
uv run pytest tests/quality/ -v
```

### Full Test Suite

```bash
# Run everything (takes 10-30 minutes)
uv run pytest --cov=kubani.nexus --cov-report=html --cov-fail-under=75

# Run everything except cluster tests
uv run pytest -m "not cluster" --cov=kubani.nexus --cov-report=html

# Run with all checks
uv run ruff check kubani/ && \
uv run mypy kubani/nexus/ && \
uv run pytest --cov=kubani.nexus --cov-fail-under=75
```

### CI Pipeline Stages

The CI pipeline runs tests in stages:

1. **Lint and Type Check** (1-2 minutes)
   ```bash
   uv run ruff check kubani/
   uv run mypy kubani/nexus/
   ```

2. **Unit Tests** (2-5 minutes)
   ```bash
   uv run pytest tests/unit/ -n auto --cov=kubani.nexus
   ```

3. **Integration Tests** (5-10 minutes)
   ```bash
   uv run pytest tests/integration/ -v
   ```

4. **E2E Tests** (10-20 minutes, cluster required)
   ```bash
   uv run pytest tests/e2e/ -v --cluster
   ```

5. **Coverage Report** (1 minute)
   ```bash
   uv run pytest --cov=kubani.nexus --cov-report=xml --cov-fail-under=75
   ```

### Pre-Commit Checks

Run before committing:

```bash
# Quick check (< 1 minute)
uv run ruff check kubani/
uv run pytest tests/unit/models/ -n auto

# Standard check (2-5 minutes)
uv run ruff check kubani/
uv run mypy kubani/nexus/
uv run pytest tests/unit/ -n auto

# Full check (10-15 minutes)
uv run ruff check kubani/
uv run mypy kubani/nexus/
uv run pytest tests/unit/ tests/integration/ -n auto --cov=kubani.nexus
```

## Test Execution Checklist

### Before Running Tests

- [ ] Virtual environment activated
- [ ] Dependencies installed (`uv sync --all-extras`)
- [ ] Environment variables configured (`.env` file)
- [ ] Docker services running (for integration/E2E tests)
- [ ] Cluster access configured (for cluster tests)

### After Running Tests

- [ ] All tests passed
- [ ] Coverage meets threshold (≥ 75%)
- [ ] No linting errors
- [ ] No type errors
- [ ] Test logs reviewed
- [ ] Coverage report reviewed

### Troubleshooting Checklist

- [ ] Check service status (`docker-compose ps`)
- [ ] Check service logs (`docker-compose logs`)
- [ ] Verify environment variables (`echo $VAR_NAME`)
- [ ] Check cluster access (`kubectl cluster-info`)
- [ ] Review test output and error messages
- [ ] Check for resource leaks (orphaned containers/processes)
- [ ] Verify test isolation (no shared state)

## Additional Resources

- [Test README](./README.md) - Overview and setup
- [CI/CD Documentation](./CI_CD.md) - Continuous integration details
- [Design Document](../.kiro/specs/nexus-testing/design.md) - Testing strategy
- [Requirements Document](../.kiro/specs/nexus-testing/requirements.md) - Test requirements

---

**Last Updated:** 2026-02-11
**Maintained By:** Kubani Development Team
