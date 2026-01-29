# kubani CLI Documentation

Documentation for the kubani development CLI.

## Quick Links

- [**Local Development**](guides/local-development.md) - Complete local development guide
- [**Commands Reference**](reference/commands.md) - All CLI commands
- [**Testing Guide**](guides/testing.md) - Testing workflows

## Guides

Step-by-step guides for common workflows:

- [**Local Development**](guides/local-development.md) - Run agents locally with hot-reload
- [**Development Workflow**](guides/development-workflow.md) - End-to-end development
- [**Testing**](guides/testing.md) - Unit, integration, and evaluation tests
- [**Setup**](guides/setup.md) - Initial setup and configuration

## Reference

Complete CLI command reference:

- [**Commands**](reference/commands.md) - All available commands
- [**Error Codes**](reference/error-codes.md) - Error handling and troubleshooting

## Development

Contributing to kubani:

- [**Contributing**](development/contributing.md) - How to contribute
- [**Architecture**](development/architecture.md) (coming soon)

## Common Tasks

### Local Development
```bash
# Run agent locally with cluster services
kubani local-run --agent k8s-monitor --temporal cluster

# Run with hot-reload
kubani local-run --agent k8s-monitor --hot-reload

# Run with mock services (no cluster needed)
kubani local-run --agent k8s-monitor --mock-services
```

### Testing
```bash
# Run all tests
kubani test k8s-monitor

# Run with coverage
kubani test k8s-monitor --coverage

# Run specific test file
kubani test k8s-monitor --file tests/test_classifier.py
```

### Evaluation
```bash
# Run evaluation suite
kubani eval run --suite kubani/evaluations/k8s/pod_remediation.yaml

# Run specific layer
kubani eval run --suite kubani/evaluations/k8s/pod_remediation.yaml --layer llm_judge
```

### Deployment
```bash
# Deploy agent
kubani deploy --agent k8s-monitor --wait

# Deploy all agents
kubani deploy --all --wait
```

### Skills
```bash
# Sync skills to registry
kubani sync --skills

# Validate skill definitions
kubani skill validate k8s/diagnostic/investigate-pod-failure
```

## Related Documentation

- [Getting Started](../../getting-started/) - Initial setup
- [Kubani Package](../../kubani/) - Core framework
- [Infrastructure](../../infrastructure/) - Cluster operations
