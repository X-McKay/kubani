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
cd platform/cli
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

### Cluster Management

Manage Kubernetes cluster infrastructure (migrated from cluster-mgr):

```bash
# Discover Tailscale nodes
kubani-dev cluster discover

# Add a node to the cluster
kubani-dev cluster add-node hostname --role worker --label env=prod

# Remove a node (with drain)
kubani-dev cluster remove-node hostname

# Run provisioning
kubani-dev cluster provision --tag k8s --limit workers

# Show cluster status
kubani-dev cluster status --pods
```

### Configuration Management

Manage Kubani configuration:

```bash
# Get a config value
kubani-dev config get llm.api_url

# Set a config value (writes to local.yaml)
kubani-dev config set llm.model my-model

# Show effective configuration
kubani-dev config show --env production

# Validate configuration
kubani-dev config validate

# Compare environments
kubani-dev config diff development production

# Edit config file
kubani-dev config edit --env production
```

### Environment Management

Switch between environments:

```bash
# List available environments
kubani-dev env list

# Switch to an environment
kubani-dev env use production

# Show current environment
kubani-dev env show

# Initialize a new environment
kubani-dev env init staging --copy-from production
```

### Skill Development

```bash
# Draft a new skill (interactive LLM conversation)
kubani-dev skill draft my-skill "Description of what it does"

# Evaluate a skill (quick mode - single model)
kubani-dev skill eval skills/development/my-skill

# Evaluate with full comparison (4 configurations)
kubani-dev skill eval skills/development/my-skill --mode full --parallel

# Improve a skill based on evaluation
kubani-dev skill improve skills/development/my-skill --goals accuracy

# Promote to production
kubani-dev skill promote skills/development/my-skill --category core
```

#### Evaluation Modes

- **Quick mode** (default): Single evaluation with large model + thinking enabled. Fast feedback during development.
- **Full mode**: Compare 4 LLM configurations (large/small models, with/without thinking). Generates comparison matrix with accuracy, latency, and token metrics plus LLM-generated analysis.

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
