# Unit Testing Strategy for Kubani

**Date:** 2026-01-24
**Status:** Proposed
**Goal:** Achieve 75% unit test coverage across kubani/ with value-driven, maintainable tests

## Executive Summary

After a major refactor, kubani/ has ~81 Python files with only 8 test files, resulting in critical gaps in test coverage. This strategy establishes comprehensive unit testing with 75% minimum coverage, focusing on preventing regressions, enabling confident refactoring, and documenting behavior through tests.

## Current State Analysis

**Coverage Gaps:**
- Framework modules (~3,256 lines): 0% coverage
  - `config.py` (996 lines) - Critical, used everywhere
  - `events/bus.py` (~500 lines) - Core communication
  - `mcp/client.py` (608 lines) - All agents depend on this
  - `learning/`, `memory/`, `temporal/`, `observability/` - Untested or empty

**Existing Tests:**
- 8 test files total across agents, syndicates, MCP servers
- Agents/syndicates have partial coverage
- No framework-level tests

## Architecture Overview

### Test Structure

```
kubani/
├── tests/                          # Framework unit tests (NEW)
│   ├── unit/                       # Fast, isolated unit tests
│   │   ├── test_config.py
│   │   ├── test_events_bus.py
│   │   ├── test_events_types.py
│   │   ├── test_mcp_client.py
│   │   └── test_mcp_skills.py
│   ├── integration/                # Integration tests with real services
│   │   ├── test_redis_event_bus.py
│   │   ├── test_mcp_integration.py
│   │   └── test_config_loading.py
│   ├── fixtures/                   # Shared test fixtures
│   │   ├── config_fixtures.py
│   │   ├── mcp_mocks.py
│   │   └── event_fixtures.py
│   └── conftest.py                 # Pytest configuration
├── agents/{agent}/tests/           # ✓ Already exists
├── syndicates/{syndicate}/tests/   # ✓ Already exists
└── mcp/servers/{server}/tests/     # ✓ Partially exists
```

### Coverage Targets by Component

| Component | Target | Priority | Rationale |
|-----------|--------|----------|-----------|
| Framework core (config, events, mcp) | 85% | Critical | Used by all agents/syndicates |
| Agents | 75% | High | Integration-heavy, business logic |
| Syndicates | 70% | Medium | Orchestration, less pure logic |
| MCP servers | 80% | High | API contracts, multiple consumers |

## Testing Principles

### Value-Driven Testing

**For each test, ask: "What breaking change would this catch?"**

**High-Value Tests (Priority 1):**
- **Contract tests** - API boundaries other code depends on
  - Example: `Event.to_stream_data()` format changes break Redis consumers
  - Example: `MCPClient.call_tool()` signature changes break all agents

- **Integration points** - Where components connect
  - Example: Config loading: YAML → environment variables → code
  - Example: Event bus: publish → Redis → subscribe

- **Error handling paths** - Critical but often untested
  - Example: Redis connection failures in event bus
  - Example: MCP server timeout handling
  - Example: Invalid config value validation

**Medium-Value Tests (Priority 2):**
- Business logic with complex conditionals
- State management and lifecycle
- Data transformations and validation

**Low-Value Tests (avoid unless trivial):**
- Simple getters/setters
- Pass-through methods with no logic
- Code already covered by integration tests

### Dead Code Elimination

**No Coverage Exemptions - Only Delete or Test**

Before writing tests for any module:
1. **Usage analysis**: Is it imported anywhere?
2. **Git history**: Last modified >6 months ago?
3. **Decision**: Delete, deprecate, or test

If a module can't hit 75% coverage, it's a code smell:
- Too complex → needs refactoring
- Dead code → should be deleted
- Missing abstractions → needs redesign

## Component-Specific Testing Strategy

### 1. Config Module (`kubani/framework/config.py`)

**Priority:** Critical (used by all components)
**Target Coverage:** 85%
**Lines:** 996

**High-Value Test Cases:**
```python
# tests/unit/test_config.py

class TestConfigLoading:
    """Config hierarchy and loading"""
    def test_default_values_when_no_files_exist()
    def test_yaml_files_load_in_correct_order()  # default → env → local
    def test_environment_variables_override_yaml()
    def test_nested_env_vars_with_double_underscore()  # KUBANI__LLM__API_URL
    def test_deep_merge_combines_nested_dicts()
    def test_deep_merge_later_values_override()

class TestConfigValidation:
    """Pydantic validation and error cases"""
    def test_invalid_log_level_raises_validation_error()
    def test_invalid_environment_raises_validation_error()
    def test_negative_timeout_raises_validation_error()
    def test_required_fields_enforced()

class TestComputedFields:
    """@computed_field properties"""
    def test_temporal_grpc_url_from_host()
    def test_qdrant_url_with_https_when_use_https_true()
    def test_redis_url_includes_password_when_set()

class TestConfigSingleton:
    """get_config() and reload_config()"""
    def test_get_config_returns_same_instance()
    def test_reload_config_clears_cache()
    def test_configure_for_local_dev_sets_env_vars()

class TestMem0Integration:
    """mem0-compatible config generation"""
    def test_get_mem0_config_structure()
    def test_get_graph_mem0_config_includes_neo4j()
```

**Mocking Strategy:**
- Mock file system for YAML loading (use `tmp_path` fixture)
- Mock environment variables (use `monkeypatch` fixture)
- No external service dependencies

### 2. Event Bus (`kubani/framework/events/`)

**Priority:** Critical (core communication)
**Target Coverage:** 80% (unit), 90% (integration)
**Lines:** ~500

**High-Value Test Cases:**

```python
# tests/unit/test_events_types.py

class TestEventSerialization:
    """Event data format contracts"""
    def test_to_stream_data_returns_all_string_values()
    def test_to_stream_data_includes_required_fields()
    def test_from_stream_data_reconstructs_event()
    def test_from_stream_data_handles_missing_correlation_id()
    def test_from_stream_data_raises_on_missing_type()
    def test_from_stream_data_raises_on_missing_source()
    def test_timestamp_serialization_roundtrip()
    def test_payload_json_serialization()

# tests/unit/test_events_bus.py (with fakeredis)

class TestEventBusPublish:
    """Event publishing"""
    def test_publish_generates_unique_event_id()
    def test_publish_adds_to_redis_stream()
    def test_publish_trims_stream_at_max_length()
    def test_publish_handles_redis_connection_error()

class TestEventBusSubscribe:
    """Event subscription"""
    def test_subscribe_filters_by_event_type()
    def test_subscribe_receives_all_types_when_none_specified()
    def test_subscribe_with_consumer_group_creates_group()
    def test_subscribe_acknowledges_messages_in_group_mode()
    def test_subscribe_handles_cancellation()

class TestEventBusGetRecent:
    """Recent event retrieval"""
    def test_get_recent_returns_events_since_id()
    def test_get_recent_filters_by_event_type()
    def test_get_recent_limits_results()

# tests/integration/test_redis_event_bus.py (real Redis)

class TestRedisEventBusIntegration:
    """Full publish/subscribe flow with real Redis"""
    def test_publish_subscribe_roundtrip()
    def test_consumer_groups_load_balance_events()
    def test_stream_trimming_removes_old_events()
    def test_connection_failure_raises_error()
```

**Mocking Strategy:**
- **Unit tests:** Use `fakeredis` for Redis mock
- **Integration tests:** Use `testcontainers` for real Redis instance
- Mock `redis.asyncio` import for error testing

### 3. MCP Client (`kubani/framework/mcp/client.py`)

**Priority:** Critical (all agents use this)
**Target Coverage:** 85%
**Lines:** 608

**High-Value Test Cases:**

```python
# tests/unit/test_mcp_client.py

class TestMCPServerClient:
    """Base MCP client functionality"""
    def test_initialization_sets_url_and_timeout()
    def test_get_client_creates_httpx_client()
    def test_get_client_reuses_existing_client()
    def test_call_tool_formats_request_correctly()
    def test_call_tool_returns_success_response()
    def test_call_tool_handles_http_error()
    def test_call_tool_handles_timeout()
    def test_list_tools_returns_tool_list()
    def test_health_check_returns_true_on_200()
    def test_health_check_returns_false_on_error()
    def test_close_closes_http_client()

class TestTemporalMCPClient:
    """Temporal-specific client methods"""
    def test_list_workflows_calls_correct_tool()
    def test_get_workflow_includes_run_id()
    def test_start_workflow_formats_args()
    def test_signal_workflow_sends_signal()
    def test_cancel_workflow_calls_cancel()

class TestQdrantMCPClient:
    """Qdrant-specific client methods"""
    def test_list_collections()
    def test_create_collection_with_vector_size()
    def test_search_vectors_with_filter()
    def test_upsert_vectors()
    def test_delete_points()

class TestMemoryMCPClient:
    """Memory-specific client methods"""
    def test_store_learning()
    def test_query_learnings_with_filters()
    def test_store_knowledge()
    def test_get_knowledge_graph()
    def test_cache_get_and_set()

class TestDiscordMCPClient:
    """Discord-specific client methods"""
    def test_send_message()
    def test_send_embed()
    def test_add_reaction()
    def test_wait_for_reaction()

class TestRegistryMCPClient:
    """Registry-specific client methods"""
    def test_register_agent()
    def test_heartbeat()
    def test_list_agents()
    def test_list_skills()

class TestSkillsMCPClient:
    """Skills-specific client methods"""
    def test_list_skills_with_filters()
    def test_get_skill()
    def test_execute_skill()

class TestMCPClient:
    """Unified MCP client"""
    def test_property_accessors_create_clients()
    def test_health_check_all_returns_status_dict()
    def test_close_closes_all_clients()
    def test_get_mcp_client_returns_singleton()
```

**Mocking Strategy:**
- Use `respx` library for mocking `httpx.AsyncClient`
- Mock successful/failed API responses
- Mock timeout scenarios
- No real MCP servers needed for unit tests

## Shared Fixtures & Test Utilities

### Fixture Organization

**`tests/fixtures/config_fixtures.py`**
```python
@pytest.fixture
def isolated_config_dir(tmp_path, monkeypatch):
    """Provides clean config directory for testing"""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setenv("KUBANI_CONFIG_DIR", str(config_dir))
    return config_dir

@pytest.fixture
def sample_config_yaml():
    """Returns dict with common config structure"""
    return {
        "environment": "test",
        "llm": {"api_url": "http://test:8000/v1"},
        "memory": {"qdrant": {"host": "test-qdrant"}},
    }

@pytest.fixture
def mock_env_vars(monkeypatch):
    """Factory for setting env vars in tests"""
    def _set(**kwargs):
        for key, value in kwargs.items():
            monkeypatch.setenv(f"KUBANI_{key.upper()}", str(value))
    return _set
```

**`tests/fixtures/mcp_mocks.py`**
```python
@pytest.fixture
def mock_mcp_response():
    """Factory for creating mock MCP responses"""
    def _create(success=True, data=None, error=None):
        return MCPResponse(success=success, data=data, error=error)
    return _create

@pytest.fixture
async def mock_mcp_server(respx_mock):
    """Fully mocked MCP server with common endpoints"""
    respx_mock.get("http://test-mcp:8081/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )
    respx_mock.get("http://test-mcp:8081/tools/list").mock(
        return_value=httpx.Response(200, json={"tools": []})
    )
    return respx_mock
```

**`tests/fixtures/event_fixtures.py`**
```python
@pytest.fixture
def event_factory():
    """Factory for creating test events"""
    def _create(
        event_type=EventType.K8S_ISSUE_DETECTED,
        source="test-agent",
        payload=None,
        **kwargs
    ):
        return Event(
            id=str(uuid.uuid4()),
            type=event_type,
            source=source,
            payload=payload or {},
            **kwargs
        )
    return _create

@pytest.fixture
async def fake_redis_event_bus():
    """Event bus using fakeredis for unit tests"""
    import fakeredis.aioredis

    bus = RedisEventBus(host="fake", port=6379)
    bus._client = fakeredis.aioredis.FakeRedis(decode_responses=False)
    bus._initialized = True
    yield bus
    await bus.close()
```

**`tests/conftest.py`**
```python
# Auto-import all fixtures
pytest_plugins = [
    "tests.fixtures.config_fixtures",
    "tests.fixtures.mcp_mocks",
    "tests.fixtures.event_fixtures",
]

# Asyncio configuration for async tests
@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.get_event_loop_policy()

# Mark slow/integration tests
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires services)"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow"
    )
```

## CI/Pre-commit Integration

### Coverage Configuration

**`pyproject.toml` (root)**
```toml
[tool.pytest.ini_options]
testpaths = ["kubani/tests", "kubani/agents/*/tests", "kubani/syndicates/*/tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
asyncio_mode = "auto"
addopts = [
    "--verbose",
    "--cov=kubani",
    "--cov-report=term-missing",
    "--cov-report=html:htmlcov",
]

[tool.coverage.run]
source = ["kubani"]
omit = [
    "tests/*",
    ".venv/*",
    "**/__pycache__/*",
    "**/conftest.py",
]

[tool.coverage.report]
fail_under = 75  # Target: 75% overall
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
    "@abstractmethod",
]
```

### Justfile Commands

```makefile
# Run only fast unit tests (for rapid iteration)
test-unit-fast:
    uv run pytest kubani/tests/unit -v --tb=short --no-cov

# Run integration tests (require services)
test-integration:
    uv run pytest kubani/tests/integration -v --tb=short

# Run tests with full coverage report
test-coverage:
    uv run pytest \
        --cov=kubani \
        --cov-report=term-missing \
        --cov-report=html:htmlcov \
        --cov-report=xml:coverage.xml \
        --cov-fail-under=75

# Enhanced CI command (existing)
ci: lint test-coverage check
    @echo "✓ All CI checks passed with 75% coverage!"
```

### Pre-commit Hook (Optional)

**`.pre-commit-config.yaml`** (add to existing)
```yaml
- repo: local
  hooks:
    - id: pytest-coverage-check
      name: Check test coverage on changed modules
      entry: bash -c 'uv run pytest --cov=kubani --cov-report=term --cov-fail-under=75 kubani/tests/'
      language: system
      pass_filenames: false
      stages: [pre-push]  # Only on push, not every commit
```

## Implementation Roadmap

### Phase 1: Foundation (Week 1)
**Goal: Set up testing infrastructure + test critical framework modules**

**Tasks:**
1. **Setup test structure**
   - Create `kubani/tests/{unit,integration,fixtures}` directories
   - Set up `conftest.py` with pytest configuration
   - Add dependencies: `pytest-asyncio`, `fakeredis`, `respx`, `pytest-cov`, `testcontainers`

2. **Create shared fixtures**
   - `config_fixtures.py` - Config testing utilities
   - `mcp_mocks.py` - MCP client mocking
   - `event_fixtures.py` - Event bus testing

3. **Test highest-impact modules**
   - `test_config.py` - Config loading, merging, validation (target: 85%)
   - `test_events_types.py` - Event serialization/deserialization (target: 90%)
   - `test_events_bus.py` - Event bus with fakeredis (target: 80%)

4. **CI Integration**
   - Update `justfile` with `test-unit-fast`, `test-coverage` commands
   - Add coverage reporting to existing `just ci` command
   - Configure pytest.ini with coverage thresholds

**Success Criteria:**
- ✅ Framework core config module >85% coverage
- ✅ Event types and bus >80% coverage
- ✅ CI fails if coverage drops below 75%
- ✅ `just test-coverage` runs successfully

**Deliverables:**
- Test infrastructure fully functional
- ~15-20 high-value tests for config + events
- Coverage enforcement in CI

---

### Phase 2: MCP & Integration (Week 2)
**Goal: Test MCP client layer + add integration tests**

**Tasks:**
1. **MCP Client unit tests**
   - `test_mcp_client.py` - Client initialization, tool calls, error handling
   - Test all typed clients (Temporal, Qdrant, Memory, Discord, Registry, Skills)
   - Use respx for HTTP mocking (target: 85%)

2. **Integration test suite**
   - `test_redis_event_bus.py` - Real Redis using testcontainers
   - `test_config_loading.py` - Full YAML loading from disk
   - `test_mcp_integration.py` - Basic MCP server connectivity (optional)

3. **Dead code audit**
   - Review `kubani/framework/learning/`, `memory/`, `temporal/`, `observability/`
   - Delete unused modules or plan refactoring
   - Document any deprecation decisions

**Success Criteria:**
- ✅ MCP client layer >85% coverage
- ✅ Integration tests pass with real Redis (using testcontainers)
- ✅ Dead code removed or deprecation plan documented
- ✅ Overall framework coverage >80%

**Deliverables:**
- ~25-30 MCP client tests
- 3-5 integration tests
- Dead code cleanup report

---

### Phase 3: Agents & Syndicates (Week 3)
**Goal: Ensure agents/syndicates have adequate test coverage**

**Tasks:**
1. **Audit existing tests**
   - Review `kubani/agents/*/tests/`
   - Review `kubani/syndicates/*/tests/`
   - Identify coverage gaps using `pytest --cov`

2. **Enhance agent tests**
   - Add missing unit tests for agent logic
   - Mock Temporal, MCP dependencies using shared fixtures
   - Target: 75% per agent

3. **Enhance syndicate tests**
   - Test workflow orchestration logic
   - Mock Temporal workflows
   - Target: 70% per syndicate

**Success Criteria:**
- ✅ Each agent >75% coverage
- ✅ Each syndicate >70% coverage
- ✅ All tests using shared fixtures (no duplication)
- ✅ Overall kubani/ coverage >75%

**Deliverables:**
- Enhanced agent test suites
- Enhanced syndicate test suites
- Overall 75% coverage milestone achieved

---

### Phase 4: Continuous Enforcement (Ongoing)
**Goal: Maintain coverage as code evolves**

**Tasks:**
1. **Documentation**
   - Update README with testing guide
   - Document fixture usage patterns
   - Create testing examples in CONTRIBUTING.md

2. **Coverage monitoring**
   - Track coverage trends over time
   - Review coverage reports in PR reviews
   - Enforce "no coverage drops" policy

3. **Maintenance**
   - Update tests when APIs change
   - Add tests for new modules before merge
   - Refactor tests to reduce duplication

**Success Criteria:**
- ✅ Coverage never drops below 75%
- ✅ New code includes tests before merge
- ✅ Team understands fixture patterns
- ✅ Testing is part of development workflow

---

## Implementation Priority Queue

**Must Have (Phase 1):**
1. `kubani/framework/config.py` - Everyone depends on this
2. `kubani/framework/events/types.py` - Core event contracts
3. `kubani/framework/events/bus.py` - Event communication
4. Test infrastructure setup

**Should Have (Phase 2):**
5. `kubani/framework/mcp/client.py` - All agents use MCP
6. Integration tests for Redis event bus
7. Dead code cleanup

**Nice to Have (Phase 3):**
8. Individual agent test improvements
9. Syndicate orchestration tests
10. Pre-commit coverage hook

## Dependencies

**New Test Dependencies:**
```toml
# pyproject.toml
[dependency-groups]
test = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "fakeredis>=2.20.0",
    "respx>=0.20.0",
    "testcontainers>=4.0.0",
]
```

**Installation:**
```bash
uv sync --group test
```

## Success Metrics

**Quantitative:**
- ✅ Overall kubani/ coverage: 75%+
- ✅ Framework core coverage: 85%+
- ✅ MCP client coverage: 85%+
- ✅ Agent coverage: 75%+ each
- ✅ Syndicate coverage: 70%+ each
- ✅ CI passes with coverage enforcement

**Qualitative:**
- ✅ Tests catch regressions during refactoring
- ✅ Team confident making changes to framework
- ✅ New contributors understand testing patterns
- ✅ Tests serve as documentation for complex modules

## Open Questions

1. **Integration test infrastructure**: Use testcontainers vs docker-compose vs manual setup?
   - **Recommendation**: Start with testcontainers (easy, self-contained)

2. **Pre-commit hook**: Too heavy for every commit?
   - **Recommendation**: Use pre-push stage only, or make optional

3. **Dead code**: Specific modules to audit in Phase 2?
   - **Recommendation**: Start with `learning/`, `memory/`, `temporal/`, `observability/`

## References

- pytest documentation: https://docs.pytest.org/
- pytest-asyncio: https://pytest-asyncio.readthedocs.io/
- fakeredis: https://github.com/cunla/fakeredis-py
- respx: https://lundberg.github.io/respx/
- testcontainers: https://testcontainers-python.readthedocs.io/
