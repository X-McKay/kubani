---
inclusion: always
---

## Development Environment

- Use bash shell for all command execution
- Runtime versions are managed via Mise (`.mise.toml`) - check and respect configured versions
- Python virtual environment is located at `.venv` - ensure it's activated before running Python commands

## Python Tooling

- Use `uv` as the package manager and script runner for all Python operations:
  - Run scripts: `uv run python script.py`
  - Execute modules: `uv run -m module_name`
  - Install dependencies: `uv pip install package`
- Use `ruff` for linting and code formatting
- Use `typos` (ty) for spell checking and typo detection
- Run tests with `pytest` via `uv run pytest`

## Testing

- Property-based tests use Hypothesis and are located in `tests/properties/`
- Unit tests are in `tests/unit/`
- Coverage reports are generated in `htmlcov/` directory
- Use `make test` or `uv run pytest` to run the test suite

## Ansible Conventions

- Roles follow standard Ansible structure: `tasks/`, `defaults/`, `handlers/`, `templates/`
- Playbooks are in `ansible/playbooks/`
- Inventory examples use `.example` suffix - never commit actual inventory files
- All roles should have a README.md documenting purpose, variables, and dependencies

## Code Quality

- Follow Python type hints conventions
- Maintain test coverage for new functionality
- Use Pydantic models for data validation (see `cluster_manager/models/`)
- Keep CLI commands idempotent where possible

## Kubernetes Cluster Access

- The cluster kubeconfig should be stored at `~/.kube/config` (standard location)
- Never export KUBECONFIG to non-standard locations - kubectl uses `~/.kube/config` by default
- If the kubeconfig needs to be fetched from the control plane node (sparky), copy it to the standard location:
  ```bash
  mkdir -p ~/.kube
  ssh al@100.71.65.62 "sudo cat /etc/rancher/k3s/k3s.yaml" | sed 's/127.0.0.1/100.71.65.62/g' > ~/.kube/config
  chmod 600 ~/.kube/config
  ```
- Control plane node: sparky (100.71.65.62)
- Worker nodes: rig0 (100.77.107.81), asio (100.92.107.71)
- All nodes are accessible via Tailscale IPs
- Do not import the KUBECONFIG from /tmp, ever, always import from ~/.kube/config or somewhere outside of /tmp
