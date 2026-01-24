"""Tests for skill execution."""

import pytest

from skills_mcp.discovery import SkillDiscovery
from skills_mcp.executor import (
    ExecutionStatus,
    SkillExecutorManager,
    SubprocessExecutor,
)


class TestSubprocessExecutor:
    """Tests for SubprocessExecutor."""

    @pytest.mark.asyncio
    async def test_execute_python_script(self, temp_skills_dir):
        """Test executing a Python skill script."""
        discovery = SkillDiscovery(temp_skills_dir)
        skill = discovery.get_skill("k8s/diagnostic/check-pod-health")
        assert skill is not None

        executor = SubprocessExecutor()
        result = await executor.execute(
            skill=skill,
            context={"pod_name": "nginx-123", "namespace": "default"},
            timeout=30.0,
        )

        assert result.status == ExecutionStatus.SUCCESS
        assert result.exit_code == 0
        assert "nginx-123" in result.output
        assert "Healthy" in result.output

    @pytest.mark.asyncio
    async def test_execute_with_no_scripts(self, temp_skills_dir):
        """Test executing a skill with no scripts."""
        discovery = SkillDiscovery(temp_skills_dir)
        skill = discovery.get_skill("k8s/remediation/restart-pod")
        assert skill is not None

        executor = SubprocessExecutor()
        result = await executor.execute(
            skill=skill,
            context={},
            timeout=30.0,
        )

        assert result.status == ExecutionStatus.FAILED
        assert "No executable script found" in result.error

    @pytest.mark.asyncio
    async def test_execute_timeout(self, temp_skills_dir):
        """Test that execution respects timeout."""
        discovery = SkillDiscovery(temp_skills_dir)
        skill = discovery.get_skill("k8s/diagnostic/check-pod-health")
        assert skill is not None

        # Modify the script to sleep
        script_path = (
            temp_skills_dir / "k8s" / "diagnostic" / "check-pod-health" / "scripts" / "main.py"
        )
        script_path.write_text("""
import time
time.sleep(10)
print("Done")
""")

        executor = SubprocessExecutor()
        result = await executor.execute(
            skill=skill,
            context={},
            timeout=0.5,  # Very short timeout
        )

        assert result.status == ExecutionStatus.TIMEOUT
        assert "timed out" in result.error

    @pytest.mark.asyncio
    async def test_context_passed_to_script(self, temp_skills_dir):
        """Test that context is passed to the script via environment."""
        discovery = SkillDiscovery(temp_skills_dir)
        skill = discovery.get_skill("k8s/diagnostic/check-pod-health")
        assert skill is not None

        # Update script to echo context
        script_path = (
            temp_skills_dir / "k8s" / "diagnostic" / "check-pod-health" / "scripts" / "main.py"
        )
        script_path.write_text("""
import json
import os
context = json.loads(os.environ['SKILL_CONTEXT'])
print(f"pod={context.get('pod_name')}")
print(f"ns={context.get('namespace')}")
""")

        executor = SubprocessExecutor()
        result = await executor.execute(
            skill=skill,
            context={"pod_name": "test-pod", "namespace": "test-ns"},
            timeout=30.0,
        )

        assert result.status == ExecutionStatus.SUCCESS
        assert "pod=test-pod" in result.output
        assert "ns=test-ns" in result.output


class TestSkillExecutorManager:
    """Tests for SkillExecutorManager."""

    @pytest.mark.asyncio
    async def test_falls_back_to_subprocess(self, temp_skills_dir, mock_microsandbox):
        """Test that manager falls back to subprocess when microsandbox unavailable."""
        manager = SkillExecutorManager(microsandbox_enabled=True)
        executor = await manager.get_executor()

        # Should fall back to subprocess since microsandbox is mocked as unavailable
        assert executor.name == "subprocess"

    @pytest.mark.asyncio
    async def test_records_outcomes(self, temp_skills_dir, mock_microsandbox):
        """Test that execution outcomes are recorded."""
        discovery = SkillDiscovery(temp_skills_dir)
        skill = discovery.get_skill("k8s/diagnostic/check-pod-health")
        assert skill is not None

        manager = SkillExecutorManager(microsandbox_enabled=False)
        await manager.execute(
            skill=skill,
            context={"pod_name": "test"},
            agent_id="test-agent",
        )

        outcomes = manager.get_outcomes()
        assert len(outcomes) == 1
        assert outcomes[0].skill_path == "k8s/diagnostic/check-pod-health"
        assert outcomes[0].agent_id == "test-agent"

    @pytest.mark.asyncio
    async def test_outcome_limit(self, temp_skills_dir, mock_microsandbox):
        """Test that outcomes are limited to prevent memory issues."""
        discovery = SkillDiscovery(temp_skills_dir)
        skill = discovery.get_skill("k8s/diagnostic/check-pod-health")
        assert skill is not None

        manager = SkillExecutorManager(microsandbox_enabled=False)

        # Execute many times
        for i in range(5):
            await manager.execute(skill=skill, context={"i": i})

        # Should only return up to limit
        outcomes = manager.get_outcomes(limit=3)
        assert len(outcomes) == 3

    @pytest.mark.asyncio
    async def test_disabled_microsandbox(self, temp_skills_dir):
        """Test with microsandbox explicitly disabled."""
        manager = SkillExecutorManager(microsandbox_enabled=False)
        executor = await manager.get_executor()

        assert executor.name == "subprocess"
        assert manager.get_executor_name() == "subprocess"
