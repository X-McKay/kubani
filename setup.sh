#!/bin/bash
# Setup script for Kubani development environment
#
# This is a minimal bootstrap script that installs mise,
# then delegates to 'just setup' for full project setup.

set -e

echo "=== Kubani Bootstrap ==="
echo ""

# Check for mise
if ! command -v mise &> /dev/null; then
    echo "Mise is not installed."
    echo ""
    echo "Install it with:"
    echo "  curl https://mise.run | sh"
    echo ""
    echo "Then add mise to your shell and run this script again."
    echo "See: https://mise.jdx.dev/getting-started.html"
    exit 1
fi
echo "✓ Mise is installed"

# Install mise tools (including just, uv, Python, kubectl)
echo ""
echo "Installing mise tools..."
mise install

# Check if just is now available
if ! command -v just &> /dev/null; then
    echo ""
    echo "Just was installed but not in PATH."
    echo "Run: mise reshim"
    echo "Then run: just setup"
    exit 0
fi

# Run full setup via just
echo ""
echo "Running full setup via just..."
echo ""
just setup
