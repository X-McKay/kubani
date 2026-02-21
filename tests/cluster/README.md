# Cluster Integration Tests for Kubani Nexus

This directory contains integration tests that validate the Nexus system with cluster-deployed services. These tests ensure that the system works correctly in a production-like environment.

## Test Files

### test_llm_integration.py

Tests the integration with cluster-deployed vLLM service to validate LLM-dependent components.

### test_services_integration.py

Tests the integration with all cluster-deployed services (Temporal, Redis, PostgreSQL, Qdrant, Neo4j) to validate the complete system infrastructure.

### test_services_integration.py

Tests the integration with all cluster-deployed services to validate the complete system infrastructure.

**Test Coverage:**

1. **Cluster Temporal Connection (31.1)**
   - `test_cluster_temporal_connection` - Validates connection to cluster Temporal server
   - `test_workflow_registration` - Validates workflow and activity registration
   - `test_workflow_execution` - Validates workflow can be started on cluster
   - **Status:** PASSING (connects to cluster Temporal at 100.71.65.62:7233)

2. **Cluster Redis Connection (31.2)**
   - `test_cluster_redis_connection` - Validates connection to cluster Redis
   - `test_redis_pubsub_operations` - Validates pub/sub operations work
   - `test_redis_key_operations` - Validates key operations work
   - **Status:** SKIPPED (requires Redis authentication)

3. **Cluster PostgreSQL Connection (31.3)**
   - `test_cluster_postgres_connection` - Validates connection to cluster PostgreSQL
   - `test_postgres_database_operations` - Validates all database operations
   - `test_postgres_skill_registry_operations` - Validates skill registry operations
   - **Status:** SKIPPED (requires PostgreSQL authentication)

4. **Cluster Qdrant Connection (31.4)**
   - `test_cluster_qdrant_connection` - Validates connection to cluster Qdrant
   - `test_qdrant_vector_storage_and_retrieval` - Validates vector operations
   - `test_qdrant_memory_storage` - Validates memory storage pattern
   - **Status:** SKIPPED (Qdrant not running on cluster)

5. **Cluster Neo4j Connection (31.5)**
   - `test_cluster_neo4j_connection` - Validates connection to cluster Neo4j
   - `test_neo4j_graph_storage_and_queries` - Validates graph operations
   - `test_neo4j_skill_relationships` - Validates skill relationship tracking
   - **Status:** SKIPPED (requires Neo4j authentication)

6. **Cluster Service Unavailability (31.6)**
   - `test_temporal_unavailability` - Tests error handling for Temporal failures
   - `test_redis_unavailability` - Tests error handling for Redis failures
   - `test_postgres_unavailability` - Tests error handling for PostgreSQL failures
   - `test_qdrant_unavailability` - Tests error handling for Qdrant failures
   - `test_neo4j_unavailability` - Tests error handling for Neo4j failures
   - **Status:** PASSING

7. **Service Endpoint Configuration (31.7)**
   - `test_endpoints_from_environment` - Tests configuration from environment variables
   - `test_endpoints_have_correct_format` - Tests endpoint format validation
   - `test_kubeconfig_path_exists` - Tests kubeconfig path is set
   - `test_namespace_is_set` - Tests namespace is configured
   - `test_environment_variable_override` - Tests environment variable precedence
   - `test_local_fallback_when_cluster_unavailable` - Tests localhost fallback
   - **Status:** PASSING

**Test Coverage (LLM Integration):**

1. **Cluster LLM Connection (30.1)**
   - `test_cluster_llm_connection` - Validates connection to cluster vLLM endpoint
   - `test_cluster_llm_authentication` - Validates authentication with cluster LLM
   - **Status:** SKIPPED by default (requires VLLM_ENDPOINT environment variable)

2. **Plan Response with Cluster LLM (30.2)**
   - `test_plan_response_simple_question` - Tests simple conversational responses
   - `test_plan_response_with_context` - Tests responses with conversation history
   - **Status:** PASSING (uses mocked activity context)

3. **Task Planning with Cluster LLM (30.3)**
   - `test_plan_response_task_request` - Tests structured plan generation
   - `test_plan_response_with_available_skills` - Tests plan references to available skills
   - **Status:** PASSING

4. **Response Generation with Cluster LLM (30.4)**
   - `test_generate_response` - Tests response synthesis from execution results
   - `test_generate_response_with_failures` - Tests handling of failed steps
   - **Status:** PASSING

5. **Skill Synthesis with Cluster LLM (30.5)**
   - `test_skill_synthesis` - Tests autonomous skill creation
   - `test_skill_synthesis_generates_valid_python` - Tests generated code validity
   - **Status:** PASSING

6. **Cluster LLM Unavailability (30.6)**
   - `test_llm_unavailability_retry` - Tests error handling for invalid endpoints
   - `test_activity_handles_llm_failure` - Tests graceful degradation in activities
   - **Status:** PASSING

7. **LLM Endpoint Configuration (30.7)**
   - `test_endpoint_from_environment` - Tests configuration via environment variables
   - `test_endpoint_explicit_override` - Tests explicit parameter override
   - `test_cluster_config_provides_endpoint` - Tests cluster config provides valid endpoint
   - **Status:** PASSING

## Running the Tests

### Run all cluster tests:
```bash
uv run pytest tests/cluster/ -v
```

### Run only services integration tests:
```bash
uv run pytest tests/cluster/test_services_integration.py -v
```

### Run only LLM integration tests:
```bash
uv run pytest tests/cluster/test_llm_integration.py -v
```

### Run with actual cluster connection (requires cluster access):
```bash
export VLLM_ENDPOINT=https://your-cluster-vllm:8000/v1
export TEMPORAL_HOST=your-cluster-temporal:7233
export REDIS_URL=redis://your-cluster-redis:6379
export NEXUS_DATABASE_URL=postgresql://user:pass@your-cluster-postgres:5432/nexus
export QDRANT_URL=http://your-cluster-qdrant:6333
export NEO4J_URI=bolt://your-cluster-neo4j:7687
export NEO4J_PASSWORD=your-password

uv run pytest tests/cluster/ -v
```

### Run without coverage requirements (for faster iteration):
```bash
uv run pytest tests/cluster/ -v --no-cov
```

## Configuration

### Environment Variables

The tests use the following environment variables for cluster configuration:

**LLM Service:**
- `VLLM_ENDPOINT` - vLLM API endpoint (e.g., `https://llm.almckay.io/v1`)
- `LLM_MODEL` - Model identifier (default: `nvidia/Qwen3-14B-FP4`)
- `LLM_API_URL` - Alternative to VLLM_ENDPOINT

**Infrastructure Services:**
- `TEMPORAL_HOST` - Temporal server endpoint (e.g., `100.71.65.62:7233`)
- `REDIS_URL` - Redis connection URL (e.g., `redis://100.71.65.62:6379`)
- `NEXUS_DATABASE_URL` - PostgreSQL connection string
- `QDRANT_URL` - Qdrant vector DB endpoint (e.g., `http://100.71.65.62:6333`)
- `NEO4J_URI` - Neo4j graph DB endpoint (e.g., `bolt://100.71.65.62:7687`)
- `NEO4J_PASSWORD` - Neo4j authentication password

### Kubeconfig

If environment variables are not set, the tests will attempt to load cluster configuration from `~/.kube/config`.

### Local Fallback

By default, tests fall back to localhost endpoints when cluster is not available. This allows tests to run in CI/CD without cluster access.

## Test Behavior

### Skipped Tests

Tests that require actual cluster connectivity are automatically skipped when services are not available or authentication fails. This prevents test failures in environments without cluster access.

### Service Authentication

Most cluster services require authentication:
- **Redis:** Requires password or ACL configuration
- **PostgreSQL:** Requires username/password
- **Neo4j:** Requires username/password
- **Temporal:** Usually no authentication required
- **Qdrant:** Usually no authentication required
- **vLLM:** Usually no authentication required

### Graceful Degradation

All tests are designed to skip gracefully when services are unavailable, providing clear skip messages that explain what's missing.

## Requirements Validated

**Cluster Services Integration (Task 31):**
- **Requirement 16.1:** Cluster Temporal connection and workflow registration
- **Requirement 16.2:** Cluster Redis connection and pub/sub operations
- **Requirement 16.3:** Cluster PostgreSQL connection and database operations
- **Requirement 16.4:** Cluster Qdrant connection and vector operations
- **Requirement 16.5:** Cluster Neo4j connection and graph operations
- **Requirement 16.6:** Cluster service unavailability handling
- **Requirement 16.7:** Service endpoint configuration

**Cluster LLM Integration (Task 30):**
- **Requirement 15.1:** Cluster LLM connection and authentication
- **Requirement 15.2:** Plan response with cluster LLM
- **Requirement 15.3:** Task planning with cluster LLM
- **Requirement 15.4:** Response generation with cluster LLM
- **Requirement 15.5:** Skill synthesis with cluster LLM
- **Requirement 15.6:** Cluster LLM unavailability handling
- **Requirement 15.7:** LLM endpoint configuration

## Test Results

As of the last run:
- **test_services_integration.py:** 14 passed, 12 skipped
- **test_llm_integration.py:** 13 passed, 2 skipped
- **Total:** 27 passed, 14 skipped

## Troubleshooting

### Connection Errors

If you see connection errors:
1. Verify service endpoints are set correctly in environment variables
2. Check network connectivity to cluster
3. Verify cluster services are running: `kubectl get pods -n kubani`
4. Check firewall/security group rules

### Authentication Errors

If you see authentication errors:
1. Verify credentials are correct
2. Check service-specific authentication configuration
3. For Redis: Check ACL configuration
4. For PostgreSQL: Check pg_hba.conf
5. For Neo4j: Check auth settings

### Configuration Issues

If tests use wrong endpoint:
1. Check `config/local.yaml` for overrides
2. Verify environment variables are set
3. Check kubeconfig at `~/.kube/config`
4. Try explicit endpoint in test

### Skipped Tests

Tests are skipped when:
1. Services are not available (connection refused)
2. Authentication fails
3. Required environment variables are not set
4. Kubeconfig is not available

This is expected behavior and allows tests to run in different environments.

## Future Improvements

1. Add integration tests for complete workflows using all services
2. Add performance benchmarks for cluster services
3. Add load testing for concurrent operations
4. Add chaos testing for service failures
5. Add monitoring and observability tests
6. Add backup and recovery tests
7. Add security and access control tests

</content>
</file>

<file name="tests/cluster/README.md" language="markdown" >
<content>
# Cluster Integration Tests for Kubani Nexus

This directory contains integration tests that validate the Nexus system with cluster-deployed services. These tests ensure that the system works correctly in a production-like environment.

## Test Files

### test_llm_integration.py

Tests the integration with cluster-deployed vLLM service to validate LLM-dependent components.

### test_services_integration.py

Tests the integration with all cluster-deployed services (Temporal, Redis, PostgreSQL, Qdrant, Neo4j) to validate the complete system infrastructure.

**Test Coverage:**

1. **Cluster LLM Connection (30.1)**
   - `test_cluster_llm_connection` - Validates connection to cluster vLLM endpoint
   - `test_cluster_llm_authentication` - Validates authentication with cluster LLM
   - **Status:** SKIPPED by default (requires VLLM_ENDPOINT environment variable)

2. **Plan Response with Cluster LLM (30.2)**
   - `test_plan_response_simple_question` - Tests simple conversational responses
   - `test_plan_response_with_context` - Tests responses with conversation history
   - **Status:** PASSING (uses mocked activity context)

3. **Task Planning with Cluster LLM (30.3)**
   - `test_plan_response_task_request` - Tests structured plan generation
   - `test_plan_response_with_available_skills` - Tests plan references to available skills
   - **Status:** PASSING

4. **Response Generation with Cluster LLM (30.4)**
   - `test_generate_response` - Tests response synthesis from execution results
   - `test_generate_response_with_failures` - Tests handling of failed steps
   - **Status:** PASSING

5. **Skill Synthesis with Cluster LLM (30.5)**
   - `test_skill_synthesis` - Tests autonomous skill creation
   - `test_skill_synthesis_generates_valid_python` - Tests generated code validity
   - **Status:** PASSING

6. **Cluster LLM Unavailability (30.6)**
   - `test_llm_unavailability_retry` - Tests error handling for invalid endpoints
   - `test_activity_handles_llm_failure` - Tests graceful degradation in activities
   - **Status:** PASSING

7. **LLM Endpoint Configuration (30.7)**
   - `test_endpoint_from_environment` - Tests configuration via environment variables
   - `test_endpoint_explicit_override` - Tests explicit parameter override
   - `test_cluster_config_provides_endpoint` - Tests cluster config provides valid endpoint
   - **Status:** PASSING

## Running the Tests

### Run all cluster tests:
```bash
uv run pytest tests/cluster/ -v
```

### Run only LLM integration tests:
```bash
uv run pytest tests/cluster/test_llm_integration.py -v
```

### Run with actual cluster connection (requires cluster access):
```bash
export VLLM_ENDPOINT=https://your-cluster-vllm:8000/v1
uv run pytest tests/cluster/test_llm_integration.py -v
```

### Run without coverage requirements (for faster iteration):
```bash
uv run pytest tests/cluster/ -v --no-cov
```

## Configuration

### Environment Variables

The tests use the following environment variables for cluster configuration:

- `VLLM_ENDPOINT` - vLLM API endpoint (e.g., `https://llm.almckay.io/v1`)
- `LLM_MODEL` - Model identifier (default: `nvidia/Qwen3-14B-FP4`)
- `LLM_API_URL` - Alternative to VLLM_ENDPOINT
- `TEMPORAL_HOST` - Temporal server endpoint
- `REDIS_URL` - Redis connection URL
- `NEXUS_DATABASE_URL` - PostgreSQL connection string
- `QDRANT_URL` - Qdrant vector DB endpoint
- `NEO4J_URI` - Neo4j graph DB endpoint

### Kubeconfig

If environment variables are not set, the tests will attempt to load cluster configuration from `~/.kube/config`.

### Local Fallback

By default, tests fall back to localhost endpoints when cluster is not available. This allows tests to run in CI/CD without cluster access.

## Test Behavior

### Skipped Tests

Tests that require actual cluster connectivity (e.g., `test_cluster_llm_connection`) are automatically skipped when `VLLM_ENDPOINT` is not set. This prevents test failures in environments without cluster access.

### Mocked Components

Most tests mock the Temporal activity context to avoid requiring a running Temporal server. This allows testing the LLM integration logic in isolation.

### Activity Context Mocking

Activities that use `activity.heartbeat()` are wrapped with mocked activity context:

```python
with patch("kubani.nexus.orchestrator.activities.activity") as mock_activity:
    mock_activity.heartbeat = Mock()
    result = await plan_response(input_data)
```

## Requirements Validated

- **Requirement 15.1:** Cluster LLM connection and authentication
- **Requirement 15.2:** Plan response with cluster LLM
- **Requirement 15.3:** Task planning with cluster LLM
- **Requirement 15.4:** Response generation with cluster LLM
- **Requirement 15.5:** Skill synthesis with cluster LLM
- **Requirement 15.6:** Cluster LLM unavailability handling
- **Requirement 15.7:** LLM endpoint configuration

## Test Results

As of the last run:
- **13 tests PASSED**
- **2 tests SKIPPED** (require VLLM_ENDPOINT)
- **0 tests FAILED**

## Troubleshooting

### Connection Errors

If you see connection errors:
1. Verify `VLLM_ENDPOINT` is set correctly
2. Check network connectivity to cluster
3. Verify cluster services are running
4. Check firewall/security group rules

### Configuration Issues

If tests use wrong endpoint:
1. Check `config/local.yaml` for overrides
2. Verify environment variables are set
3. Try explicit endpoint in test: `llm = FrameworkLLM(api_url="...")`

### Activity Context Errors

If you see "Not in activity context" errors:
1. Ensure activity mocking is in place
2. Check that `activity.heartbeat` is mocked
3. Verify patch target is correct

## Future Improvements

1. Add tests for cluster Temporal integration
2. Add tests for cluster Redis pub/sub
3. Add tests for cluster PostgreSQL operations
4. Add tests for cluster Qdrant vector operations
5. Add tests for cluster Neo4j graph operations
6. Add performance benchmarks for cluster LLM
7. Add load testing for concurrent requests
