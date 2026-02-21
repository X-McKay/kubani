# Legacy Code Removal Tests

## Overview

These tests verify that the Nexus codebase maintains architectural isolation by ensuring it does not import from legacy modules that are being replaced.

## Purpose

The Kubani Nexus system is a new implementation that replaces several legacy components:
- `kubani.syndicates.k8s_monitor` - Legacy Kubernetes monitoring syndicate
- `kubani.syndicates.news_digest` - Legacy news digest syndicate
- `kubani.workflows.agent_auto` - Legacy agent automation workflow
- `kubani.workflows.skill_auto` - Legacy skill automation workflow
- `kubani.framework.temporal` - Legacy Temporal framework abstractions
- `kubani.framework.temporal.memory` - Legacy memory implementation
- `kubani.framework.events` - Legacy event bus implementation

These tests ensure that the new Nexus implementation does not accidentally depend on these legacy modules, which would create architectural conflicts and technical debt.

## Test Coverage

### Individual Module Tests

Each test verifies that no files in `kubani/nexus/` import from a specific legacy module:

1. **test_no_k8s_monitor_imports** - Validates Requirements 18.1
2. **test_no_news_digest_imports** - Validates Requirements 18.2
3. **test_no_agent_auto_imports** - Validates Requirements 18.3
4. **test_no_skill_auto_imports** - Validates Requirements 18.4
5. **test_no_framework_temporal_imports** - Validates Requirements 18.5
6. **test_no_framework_temporal_memory_imports** - Validates Requirements 18.6
7. **test_no_framework_events_imports** - Validates Requirements 18.7

### Comprehensive Tests

- **test_nexus_files_exist** - Verifies the Nexus directory structure exists
- **test_all_legacy_modules_absent** - Comprehensive check of all legacy modules at once

## How It Works

The tests use Python's `ast` module to parse all Python files in the `kubani/nexus/` directory and extract import statements. They then check if any imports reference the forbidden legacy modules.

### Import Detection

The test scans for both types of imports:
```python
import kubani.syndicates.k8s_monitor  # Direct import
from kubani.syndicates.k8s_monitor import something  # From import
```

### Violation Reporting

If violations are found, the test fails with a detailed report showing:
- The file containing the violation
- The specific import statement
- The legacy module being imported

## Running the Tests

```bash
# Run all legacy code removal tests
uv run pytest tests/unit/test_legacy_code_removal.py -v

# Run a specific test
uv run pytest tests/unit/test_legacy_code_removal.py::TestLegacyCodeRemoval::test_no_k8s_monitor_imports -v

# Run with detailed output
uv run pytest tests/unit/test_legacy_code_removal.py -vv
```

## Expected Results

All tests should pass, indicating that the Nexus codebase is properly isolated from legacy modules.

If a test fails, it means:
1. A Nexus file is importing from a legacy module
2. The architectural isolation has been compromised
3. The import should be removed or the code should be refactored

## Maintenance

These tests should be run:
- Before merging any changes to the Nexus codebase
- As part of the CI/CD pipeline
- When adding new files to the Nexus directory

## Related Documentation

- Requirements Document: `.kiro/specs/nexus-testing/requirements.md` (Requirements 18.1-18.7)
- Design Document: `.kiro/specs/nexus-testing/design.md`
- Task List: `.kiro/specs/nexus-testing/tasks.md` (Task 33)
