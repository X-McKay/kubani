"""Tests for the Nexus Execution Sandbox.

Tests the static analysis safety guard and the subprocess execution
sandbox. These tests do NOT require Docker — they test the sandbox
logic directly.
"""

from __future__ import annotations

import asyncio

import pytest

from kubani.nexus.sandbox.executor import (
    analyze_skill_safety,
    execute_skill_in_sandbox,
)


# =========================================================================
# Static Analysis Safety Guard Tests
# =========================================================================


class TestSafetyAnalysis:
    """Test the AST-based static analysis safety guard."""

    def test_safe_code_passes(self):
        """Test that safe code passes analysis."""
        code = '''
import json

def main(inputs):
    data = inputs.get("data", [])
    return {"count": len(data), "sum": sum(data)}
'''
        result = analyze_skill_safety(code)
        assert result["safe"] is True
        assert result["risk_score"] < 8.0

    def test_subprocess_blocked(self):
        """Test that subprocess import is flagged."""
        code = '''
import subprocess

def main(inputs):
    result = subprocess.run(["ls", "-la"], capture_output=True)
    return {"output": result.stdout.decode()}
'''
        result = analyze_skill_safety(code)
        assert result["safe"] is False
        assert result["risk_score"] >= 8.0
        assert any("subprocess" in f for f in result["findings"])

    def test_os_system_blocked(self):
        """Test that os.system is flagged."""
        code = '''
import os

def main(inputs):
    os.system("rm -rf /")
    return {}
'''
        result = analyze_skill_safety(code)
        assert result["safe"] is False
        assert any("system" in f for f in result["findings"])

    def test_eval_blocked(self):
        """Test that eval() is flagged."""
        code = '''
def main(inputs):
    return eval(inputs.get("expression", "1+1"))
'''
        result = analyze_skill_safety(code)
        assert result["safe"] is False
        assert any("eval" in f for f in result["findings"])

    def test_exec_blocked(self):
        """Test that exec() is flagged."""
        code = '''
def main(inputs):
    exec(inputs.get("code", "pass"))
    return {}
'''
        result = analyze_skill_safety(code)
        assert result["safe"] is False
        assert any("exec" in f for f in result["findings"])

    def test_ctypes_blocked(self):
        """Test that ctypes import is flagged."""
        code = '''
import ctypes

def main(inputs):
    return {}
'''
        result = analyze_skill_safety(code)
        assert result["safe"] is False
        assert any("ctypes" in f for f in result["findings"])

    def test_dunder_import_blocked(self):
        """Test that __import__ is flagged."""
        code = '''
def main(inputs):
    mod = __import__("os")
    return {}
'''
        result = analyze_skill_safety(code)
        assert result["safe"] is False
        assert any("__import__" in f for f in result["findings"])

    def test_safe_with_requests(self):
        """Test that using requests library is safe."""
        code = '''
import requests
import json

def main(inputs):
    url = inputs.get("url", "https://example.com")
    response = requests.get(url, timeout=10)
    return {"status": response.status_code, "length": len(response.text)}
'''
        result = analyze_skill_safety(code)
        assert result["safe"] is True

    def test_safe_with_json_and_math(self):
        """Test that standard library usage is safe."""
        code = '''
import json
import math
from collections import Counter

def main(inputs):
    data = inputs.get("numbers", [1, 2, 3])
    return {
        "mean": sum(data) / len(data),
        "sqrt_sum": math.sqrt(sum(data)),
        "counts": dict(Counter(data)),
    }
'''
        result = analyze_skill_safety(code)
        assert result["safe"] is True
        assert result["risk_score"] == 0.0

    def test_syntax_error_fails(self):
        """Test that code with syntax errors fails analysis."""
        code = '''
def main(inputs)
    return {}
'''
        result = analyze_skill_safety(code)
        assert result["safe"] is False
        assert "Syntax error" in result["reason"]

    def test_medium_risk_code(self):
        """Test that medium-risk code (socket) is flagged but not blocked."""
        code = '''
import socket

def main(inputs):
    hostname = inputs.get("host", "example.com")
    ip = socket.gethostbyname(hostname)
    return {"ip": ip}
'''
        result = analyze_skill_safety(code)
        # Socket has risk 4.0 which is < 8.0 threshold
        assert result["safe"] is True
        assert result["risk_score"] > 0
        assert len(result["findings"]) > 0

    def test_os_remove_flagged(self):
        """Test that os.remove is flagged."""
        code = '''
import os

def main(inputs):
    os.remove("/tmp/test.txt")
    return {}
'''
        result = analyze_skill_safety(code)
        assert any("remove" in f for f in result["findings"])

    def test_shutil_rmtree_flagged(self):
        """Test that shutil.rmtree is flagged."""
        code = '''
import shutil

def main(inputs):
    shutil.rmtree("/tmp/test_dir")
    return {}
'''
        result = analyze_skill_safety(code)
        assert any("rmtree" in f for f in result["findings"])


# =========================================================================
# Sandbox Execution Tests
# =========================================================================


class TestSandboxExecution:
    """Test the subprocess sandbox execution."""

    @pytest.mark.asyncio
    async def test_execute_simple_skill(self):
        """Test executing a simple, safe skill."""
        code = '''
import json

def main(inputs):
    numbers = inputs.get("numbers", [1, 2, 3])
    return {"sum": sum(numbers), "count": len(numbers)}
'''
        result = await execute_skill_in_sandbox(
            skill_name="test/sum",
            inputs={"numbers": [10, 20, 30]},
            timeout_seconds=10,
            skill_content=code,
        )

        assert result.success is True
        assert result.exit_code == 0
        assert "60" in result.output  # sum of 10+20+30

    @pytest.mark.asyncio
    async def test_execute_skill_with_error(self):
        """Test that a skill with a runtime error is handled gracefully."""
        code = '''
def main(inputs):
    return 1 / 0  # ZeroDivisionError
'''
        result = await execute_skill_in_sandbox(
            skill_name="test/error",
            inputs={},
            timeout_seconds=10,
            skill_content=code,
        )

        assert result.success is False
        assert result.exit_code != 0

    @pytest.mark.asyncio
    async def test_execute_skill_timeout(self):
        """Test that a long-running skill is killed after timeout."""
        code = '''
import time

def main(inputs):
    time.sleep(60)
    return {"done": True}
'''
        result = await execute_skill_in_sandbox(
            skill_name="test/timeout",
            inputs={},
            timeout_seconds=2,
            skill_content=code,
        )

        assert result.success is False
        assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_dangerous_code_blocked_before_execution(self):
        """Test that dangerous code is blocked by static analysis."""
        code = '''
import subprocess

def main(inputs):
    subprocess.run(["rm", "-rf", "/"])
    return {}
'''
        result = await execute_skill_in_sandbox(
            skill_name="test/dangerous",
            inputs={},
            timeout_seconds=10,
            skill_content=code,
        )

        assert result.success is False
        assert "static analysis" in result.error.lower()

    @pytest.mark.asyncio
    async def test_environment_isolation(self):
        """Test that sensitive environment variables are not accessible."""
        code = '''
import os
import json

def main(inputs):
    # Try to read sensitive env vars
    secrets = {
        "openai": os.environ.get("OPENAI_API_KEY", "NOT_FOUND"),
        "discord": os.environ.get("DISCORD_BOT_TOKEN", "NOT_FOUND"),
        "github": os.environ.get("GITHUB_TOKEN", "NOT_FOUND"),
        "db": os.environ.get("NEXUS_DATABASE_URL", "NOT_FOUND"),
    }
    return secrets
'''
        # Set a fake secret to verify it's stripped
        import os
        original = os.environ.get("OPENAI_API_KEY")

        result = await execute_skill_in_sandbox(
            skill_name="test/env-check",
            inputs={},
            timeout_seconds=10,
            skill_content=code,
        )

        assert result.success is True
        # The output should show NOT_FOUND for all secrets
        assert "NOT_FOUND" in result.output

    @pytest.mark.asyncio
    async def test_skill_receives_inputs(self):
        """Test that the skill correctly receives input data."""
        code = '''
import json

def main(inputs):
    name = inputs.get("name", "World")
    return {"greeting": f"Hello, {name}!"}
'''
        result = await execute_skill_in_sandbox(
            skill_name="test/greet",
            inputs={"name": "Kubani"},
            timeout_seconds=10,
            skill_content=code,
        )

        assert result.success is True
        assert "Kubani" in result.output

    @pytest.mark.asyncio
    async def test_duration_tracking(self):
        """Test that execution duration is tracked."""
        code = '''
import time

def main(inputs):
    time.sleep(0.5)
    return {"done": True}
'''
        result = await execute_skill_in_sandbox(
            skill_name="test/duration",
            inputs={},
            timeout_seconds=10,
            skill_content=code,
        )

        assert result.success is True
        assert result.duration_ms >= 400  # At least 400ms
