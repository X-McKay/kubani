"""Pytest configuration and fixtures."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_skills_dir():
    """Create a temporary skills directory with test skills."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_path = Path(tmpdir)

        # Create k8s/diagnostic/check-pod-health skill
        skill_dir = skills_path / "k8s" / "diagnostic" / "check-pod-health"
        skill_dir.mkdir(parents=True)

        (skill_dir / "SKILL.md").write_text("""---
name: check-pod-health
version: "1.0.0"
description: Check the health status of a Kubernetes pod
metadata:
  domain: k8s
  category: diagnostic
  requires-approval: false
  confidence: 0.9
  mcp-servers:
    - kubernetes-mcp-server
---

# Check Pod Health

## Preconditions
- Pod name and namespace are provided

## Actions
1. Get pod status
2. Check container states
3. Report health status
""")

        # Create scripts directory with a simple script
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "main.py").write_text("""#!/usr/bin/env python3
import json
import os

context = json.loads(os.environ.get('SKILL_CONTEXT', '{}'))
pod_name = context.get('pod_name', 'unknown')
namespace = context.get('namespace', 'default')

print(f"Checking health for pod {pod_name} in namespace {namespace}")
print("Status: Healthy")
""")

        # Create k8s/remediation/restart-pod skill (no scripts - declarative)
        remediation_dir = skills_path / "k8s" / "remediation" / "restart-pod"
        remediation_dir.mkdir(parents=True)

        (remediation_dir / "SKILL.md").write_text("""---
name: restart-pod
version: "1.0.0"
description: Restart a pod by deleting it
metadata:
  domain: k8s
  category: remediation
  requires-approval: true
---

# Restart Pod

This is a declarative skill with no scripts.
""")

        # Create a skill in _development (should be filtered out)
        dev_dir = skills_path / "_development" / "test-skill"
        dev_dir.mkdir(parents=True)
        (dev_dir / "SKILL.md").write_text("""---
name: test-skill
version: "0.1.0"
description: A test skill in development
---

# Test Skill

Work in progress.
""")

        yield skills_path


@pytest.fixture
def mock_microsandbox(mocker):
    """Mock microsandbox to avoid needing a running server."""
    # Create mock execution result
    mock_execution = mocker.MagicMock()
    mock_execution.output = mocker.AsyncMock(return_value="Mock output")
    mock_execution.error = mocker.AsyncMock(return_value="")
    mock_execution.exit_code = 0
    mock_execution.success = True

    # Create mock sandbox
    mock_sandbox = mocker.MagicMock()
    mock_sandbox.run = mocker.AsyncMock(return_value=mock_execution)
    mock_sandbox.id = "test-sandbox-123"

    # Mock the context manager
    mock_create = mocker.MagicMock()
    mock_create.__aenter__ = mocker.AsyncMock(return_value=mock_sandbox)
    mock_create.__aexit__ = mocker.AsyncMock(return_value=None)

    # Patch PythonSandbox.create
    mocker.patch(
        "skills_mcp.executor.MicrosandboxExecutor.is_available",
        mocker.AsyncMock(return_value=False),
    )

    return mock_sandbox
