# Code Quality Tests

This directory contains tests that validate code quality standards for the Kubani Nexus codebase.

## Test Files

### test_ruff_linting.py

Tests for code linting and formatting using ruff:
- `test_ruff_linting`: Validates zero linting errors
- `test_ruff_format_check`: Validates code formatting
- `test_mypy_type_checking`: Validates type annotations

**Requirements:** 19.1, 19.2

### test_code_quality.py

Tests for general code quality standards:
- `test_docstrings_present`: Validates docstrings on public functions/classes
- `test_code_coverage`: Validates >= 75% test coverage
- `test_readme_exists`: Validates README has setup/deployment instructions
- `test_init_exports`: Validates __init__.py files have __all__ exports
- `test_naming_conventions`: Validates PEP 8 naming conventions

**Requirements:** 19.3, 19.4, 19.5, 19.6, 19.7

## Running Tests

Run all quality tests:
```bash
uv run pytest tests/quality/ -v
```

Run specific test:
```bash
uv run pytest tests/quality/test_ruff_linting.py::test_ruff_linting -v
```

## Fixing Issues

### Linting Errors

Fix automatically:
```bash
uv run ruff check --fix kubani/nexus/
```

### Formatting Issues

Fix automatically:
```bash
uv run ruff format kubani/nexus/
```

### Type Errors

Run mypy to see type errors:
```bash
uv run mypy kubani/nexus/ --strict
```

### Coverage

Generate coverage report:
```bash
uv run pytest tests/ --cov=kubani.nexus --cov-report=html
open htmlcov/index.html
```

## Quality Standards

- **Linting**: Zero ruff errors
- **Formatting**: All code formatted with ruff
- **Type Checking**: Mypy passes in strict mode
- **Docstrings**: All public functions/classes documented
- **Coverage**: >= 75% test coverage
- **Naming**: PEP 8 conventions (snake_case functions, PascalCase classes)
- **Exports**: All __init__.py files with imports have __all__ defined
