#!/bin/bash
# Setup script for Kubani development environment

set -e

echo "=== Kubani Setup ==="
echo ""

# Check for mise
if ! command -v mise &> /dev/null; then
    echo "❌ Mise is not installed."
    echo "Install it with: curl https://mise.run | sh"
    echo "Then add it to your PATH and run this script again."
    exit 1
fi
echo "✓ Mise is installed"

# Install mise tools (including UV, Python, kubectl)
echo ""
echo "Installing mise tools (Python, UV, kubectl)..."
mise install

# Install Python dependencies using UV (now managed by mise)
echo ""
echo "Installing Python dependencies..."
mise exec -- uv sync

# Install pre-commit hooks
echo ""
echo "Installing pre-commit hooks..."
mise exec -- uv run pre-commit install

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "Next steps:"
echo "  1. Copy ansible/inventory/hosts.yml.example to ansible/inventory/hosts.yml"
echo "  2. Edit hosts.yml with your node information"
echo "  3. Run 'cluster-mgr provision' to provision your cluster"
echo ""
echo "Available commands:"
echo "  cluster-mgr --help    - CLI help"
echo "  cluster-tui           - Launch TUI"
echo "  mise run test         - Run tests"
echo "  mise run lint         - Run linting"
echo ""
