# Kubani Development CLI (kubani-dev)

A unified development tool for the Kubani AI agent system that accelerates development iteration cycles by 17x+ compared to deploying to a cluster for every change.

## Features

- **Hot-Reloading**: Run agents locally with automatic code reloading on changes
- **Integrated Testing**: Run tests with coverage and watch mode
- **Multi-Layer Evaluation**: Automated, LLM-as-Judge, and simulation-based evaluation
- **Observability Dashboard**: Real-time visibility into agent execution
- **Agent Scaffolding**: Create new agents from templates

## Installation

```bash
cd tools/kubani-dev
pip install -e .
```

## Usage

### Run an Agent Locally

```bash
# Run with hot-reloading (default)
kubani-dev run k8s-monitor

# Run with mock infrastructure
kubani-dev run k8s-monitor --mock-mcp --mock-redis
```

### Run Tests

```bash
# Run all tests
kubani-dev test

# Run tests for a specific agent
kubani-dev test k8s-monitor

# Run with coverage
kubani-dev test k8s-monitor --coverage

# Watch mode
kubani-dev test k8s-monitor --watch
```

### Run Evaluations

```bash
# Run all evaluation layers
kubani-dev eval k8s-monitor

# Run specific evaluation suite
kubani-dev eval k8s-monitor --suite llm-judge

# Save results to custom directory
kubani-dev eval k8s-monitor --output ./my-results
```

### Start Observability Dashboard

```bash
kubani-dev dashboard
kubani-dev dashboard --port 8080
```

### Create a New Agent

```bash
# Basic agent
kubani-dev new my-agent

# Federated agent (Sentinel/Healer/Explorer pattern)
kubani-dev new my-agent --template federated

# Workflow-based agent
kubani-dev new my-agent --template workflow
```

### Manage Skills

```bash
# List all skills
kubani-dev skills

# Search skills
kubani-dev skills --search "OOM"

# Validate all skills
kubani-dev skills --validate

# Get skill details
kubani-dev skills k8s/pod-restart
```

## Evaluation Framework

The evaluation framework provides multi-layered quality assessment:

### Layer 1: Automated Checks
- Syntax validation
- Type checking (mypy)
- Linting (ruff)

### Layer 2: LLM-as-Judge
- Code quality assessment
- Best practices evaluation
- Security review

### Layer 3: Simulation Testing
- Scenario-based testing
- Mock infrastructure
- Expected outcome validation

### Layer 4: Human Review
- Integration with review workflows
- Approval tracking

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type check
mypy src/kubani_dev

# Lint
ruff check src/kubani_dev
```

## Architecture

```
kubani-dev/
├── src/kubani_dev/
│   ├── __init__.py      # Package initialization
│   ├── cli.py           # Main CLI entry point
│   ├── runner.py        # Agent runner with hot-reload
│   ├── testing.py       # Test runner
│   ├── evaluation.py    # Multi-layer evaluation framework
│   ├── dashboard.py     # Observability dashboard
│   ├── skills.py        # Skills management
│   └── scaffold.py      # Agent scaffolding
└── pyproject.toml       # Package configuration
```
