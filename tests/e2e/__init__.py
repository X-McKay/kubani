"""
End-to-End Integration Tests for Kubani Multi-Agent System.

These tests validate complete workflows in a real Kubernetes environment
using kind (Kubernetes in Docker).

Prerequisites:
- Docker installed and running
- kind CLI installed
- kubectl configured
- pytest with pytest-asyncio

Run with:
    just test-e2e          # Full E2E test suite
    just test-e2e-quick    # Quick smoke tests only
"""
