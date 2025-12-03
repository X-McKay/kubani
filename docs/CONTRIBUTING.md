# Contributing to Kubani

Thank you for your interest in contributing to Kubani!

## Development Setup

1. Install [Mise](https://mise.jdx.dev/):
   ```bash
   curl https://mise.run | sh
   ```

2. Clone the repository and run setup:
   ```bash
   git clone <repository-url>
   cd kubani
   chmod +x setup.sh
   ./setup.sh
   ```

3. Activate the mise environment:
   ```bash
   mise shell
   ```

## Development Workflow

### Running Tests

```bash
# All tests
mise run test

# Unit tests only
mise run test-unit

# Property-based tests only
mise run test-properties

# With coverage
pytest --cov=cluster_manager --cov-report=html
```

### Code Quality

```bash
# Lint code
mise run lint

# Format code
mise run format

# Type checking
mise run type-check
```

### Testing Changes

1. Make your changes
2. Run tests: `mise run test`
3. Run linting: `mise run lint`
4. Run type checking: `mise run type-check`
5. Commit your changes

## Project Structure

```
.
├── ansible/              # Ansible automation
│   ├── inventory/       # Inventory and variables
│   ├── playbooks/       # Provisioning playbooks
│   └── roles/           # Ansible roles
├── cluster_manager/     # Python management tools
│   ├── cli/            # CLI commands
│   ├── tui/            # Terminal UI
│   └── models/         # Data models
├── gitops/             # GitOps manifests
└── tests/              # Test suite
    ├── unit/          # Unit tests
    ├── properties/    # Property-based tests
    └── integration/   # Integration tests
```

## Coding Standards

- Follow PEP 8 style guide
- Use type hints for all functions
- Write docstrings for public APIs
- Keep functions focused and small
- Write tests for new functionality

## Testing Guidelines

### Unit Tests
- Test specific functionality with concrete examples
- Use descriptive test names
- Keep tests isolated and independent

### Property-Based Tests
- Use Hypothesis for property-based testing
- Test universal properties that should hold for all inputs
- Run at least 100 iterations per property test
- Tag tests with the property they validate

### Integration Tests
- Test complete workflows
- Use test fixtures for setup/teardown
- Clean up resources after tests

## Commit Messages

Use clear, descriptive commit messages:
- Start with a verb (Add, Fix, Update, Remove, etc.)
- Keep the first line under 72 characters
- Add details in the body if needed

Examples:
```
Add node discovery command to CLI

Implement Tailscale node discovery functionality that queries
the Tailscale network and displays available nodes.
```

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes
3. Ensure all tests pass
4. Update documentation if needed
5. Submit a pull request with a clear description

## Questions?

Feel free to open an issue for questions or discussions!
