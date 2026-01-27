"""End-to-end tests for Skill Auto workflow with real services.

These tests require:
- Temporal cluster running
- LLM endpoint accessible
- File system access

Run with:
    pytest kubani/workflows/skill_auto/tests/test_e2e.py -v -s --timeout=300
"""

import asyncio
import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

from kubani.workflows.skill_auto.models import SkillAutoInput

# Configure logging for visibility during tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Skip these tests if not running with --run-e2e flag
pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_E2E_TESTS"),
    reason="E2E tests require RUN_E2E_TESTS=1 environment variable",
)


@pytest.fixture
def temp_skills_dir():
    """Create a temporary skills directory for testing."""
    temp_dir = tempfile.mkdtemp(prefix="skill_auto_test_")
    dev_dir = Path(temp_dir) / "_development"
    dev_dir.mkdir()
    yield temp_dir
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temporal_host():
    """Get Temporal host from environment or default."""
    return os.environ.get("TEMPORAL_HOST", "temporal.almckay.io:7233")


class TestSkillAutoE2E:
    """End-to-end tests for the Skill Auto workflow."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(300)
    async def test_workflow_creates_skill_files(self, temp_skills_dir, temporal_host):
        """Test that the workflow creates skill files on disk."""
        from temporalio.client import Client
        from temporalio.worker import Worker
        from temporalio.worker.workflow_sandbox import (
            SandboxedWorkflowRunner,
            SandboxRestrictions,
        )

        from kubani.workflows.skill_auto import SkillAutoWorkflow
        from kubani.workflows.skill_auto.temporal.activities import (
            detect_skill_overlap_activity,
            generate_test_cases_activity,
            infer_skill_structure_activity,
            load_existing_skills_activity,
            read_file_content_activity,
            run_evaluation_activity,
            run_improvement_activity,
            send_notification_activity,
            write_file_content_activity,
            write_skill_files_activity,
        )

        # Connect to Temporal
        client = await Client.connect(temporal_host)

        # Configure workflow input - simple skill, 1 iteration only
        workflow_input = SkillAutoInput(
            description="A skill that calculates the sum of two numbers",
            mode="create",
            max_iterations=1,
            target_accuracy=0.5,  # Low target so it stops after 1 iteration
            notify=False,
            allow_overlap=True,  # Skip overlap check for test speed
        )

        # Start worker with real activities
        task_queue = f"skill-auto-e2e-test-{uuid.uuid4().hex[:8]}"

        async with Worker(
            client,
            task_queue=task_queue,
            workflows=[SkillAutoWorkflow],
            workflow_runner=SandboxedWorkflowRunner(
                restrictions=SandboxRestrictions.default.with_passthrough_modules("httpx")
            ),
            activities=[
                detect_skill_overlap_activity,
                generate_test_cases_activity,
                infer_skill_structure_activity,
                load_existing_skills_activity,
                run_evaluation_activity,
                run_improvement_activity,
                send_notification_activity,
                write_skill_files_activity,
                read_file_content_activity,
                write_file_content_activity,
            ],
        ):
            # Execute workflow
            workflow_id = f"e2e-test-{uuid.uuid4().hex[:8]}"
            logger.info(f"Starting workflow {workflow_id}")

            result = await client.execute_workflow(
                SkillAutoWorkflow.run,
                workflow_input,
                id=workflow_id,
                task_queue=task_queue,
            )

            logger.info(f"Workflow completed: {result}")

            # Verify result
            assert result.skill_path is not None, "Expected skill_path in result"
            assert result.iterations_completed >= 1, "Expected at least 1 iteration"

            # Verify files were created
            skill_path = Path(result.skill_path)
            assert skill_path.exists(), f"Skill directory not created: {skill_path}"
            assert (skill_path / "SKILL.md").exists(), "SKILL.md not created"
            assert (skill_path / "test_cases.yaml").exists(), "test_cases.yaml not created"
            assert (skill_path / "metadata.json").exists(), "metadata.json not created"

            # Verify SKILL.md has content
            skill_content = (skill_path / "SKILL.md").read_text()
            assert len(skill_content) > 100, "SKILL.md content too short"
            assert "sum" in skill_content.lower() or "add" in skill_content.lower(), (
                "SKILL.md should mention the skill purpose"
            )

            # Log final metrics if available
            if result.final_metrics:
                logger.info(
                    f"Final metrics: accuracy={result.final_metrics.accuracy:.2%}, "
                    f"tests={result.final_metrics.tests_passed}/{result.final_metrics.tests_total}"
                )


if __name__ == "__main__":
    # Allow running directly for quick testing

    os.environ["RUN_E2E_TESTS"] = "1"

    with tempfile.TemporaryDirectory(prefix="skill_auto_test_") as temp_dir:
        asyncio.run(
            TestSkillAutoE2E().test_workflow_creates_skill_files(
                temp_dir,
                os.environ.get("TEMPORAL_HOST", "temporal.almckay.io:7233"),
            )
        )
