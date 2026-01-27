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


async def run_skill_workflow(
    temporal_host: str,
    description: str,
    max_iterations: int = 1,
    target_accuracy: float = 0.5,
) -> tuple:
    """Helper to run skill auto workflow."""
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
        save_iteration_result_activity,
        send_notification_activity,
        write_file_content_activity,
        write_skill_files_activity,
    )

    # Connect to Temporal
    client = await Client.connect(temporal_host)

    # Configure workflow input
    workflow_input = SkillAutoInput(
        description=description,
        mode="create",
        max_iterations=max_iterations,
        target_accuracy=target_accuracy,
        notify=False,
        allow_overlap=True,  # Skip overlap check for test speed
    )

    # Start worker with real activities
    task_queue = f"skill-auto-e2e-test-{uuid.uuid4().hex[:8]}"
    workflow_id = f"e2e-test-{uuid.uuid4().hex[:8]}"

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
            read_file_content_activity,
            run_evaluation_activity,
            run_improvement_activity,
            save_iteration_result_activity,
            send_notification_activity,
            write_file_content_activity,
            write_skill_files_activity,
        ],
    ):
        logger.info(f"Starting workflow {workflow_id}")

        result = await client.execute_workflow(
            SkillAutoWorkflow.run,
            workflow_input,
            id=workflow_id,
            task_queue=task_queue,
        )

        return result, workflow_id


class TestSkillAutoE2E:
    """End-to-end tests for the Skill Auto workflow."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(300)
    async def test_simple_skill_creation(self, temp_skills_dir, temporal_host):
        """Test basic skill creation with a simple math skill."""
        result, workflow_id = await run_skill_workflow(
            temporal_host,
            description="A skill that calculates the sum of two numbers",
            max_iterations=1,
            target_accuracy=0.5,
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

        # Log final metrics
        if result.final_metrics:
            logger.info(
                f"Final metrics: accuracy={result.final_metrics.accuracy:.2%}, "
                f"tests={result.final_metrics.tests_passed}/{result.final_metrics.tests_total}"
            )

    @pytest.mark.asyncio
    @pytest.mark.timeout(600)
    async def test_complex_skill_with_iterations(self, temp_skills_dir, temporal_host):
        """Test complex skill creation that may require iterative improvement.

        This test creates a more complex skill that processes structured data,
        which typically requires multiple iterations to achieve high accuracy.
        """
        # Complex skill description that requires careful handling
        description = """A skill that parses and validates email addresses.

The skill should:
1. Accept an email string as input
2. Validate the email format (contains @ symbol, has domain part)
3. Extract the username (part before @) and domain (part after @)
4. Return structured JSON with: valid (boolean), username (string), domain (string)
5. Handle error cases: empty input, missing @ symbol, invalid format

Example:
- Input: "user@example.com"
- Output: {"valid": true, "username": "user", "domain": "example.com"}

- Input: "invalid-email"
- Output: {"valid": false, "error": "missing @ symbol"}
"""

        result, workflow_id = await run_skill_workflow(
            temporal_host,
            description=description,
            max_iterations=3,  # Allow up to 3 improvement iterations
            target_accuracy=0.9,  # High target to potentially trigger iterations
        )

        logger.info(f"Complex skill workflow completed: {result}")
        logger.info(f"Iterations completed: {result.iterations_completed}")
        logger.info(f"Stop reason: {result.stop_reason}")

        # Verify basic result
        assert result.skill_path is not None, "Expected skill_path in result"
        # Note: success=False is expected if target accuracy wasn't reached
        # We still consider this a successful test if iterations ran without errors
        assert result.error is None, f"Workflow should not have errors, got: {result.error}"

        # Verify files were created
        skill_path = Path(result.skill_path)
        assert skill_path.exists(), f"Skill directory not created: {skill_path}"
        assert (skill_path / "SKILL.md").exists(), "SKILL.md not created"

        # Verify SKILL.md has relevant content
        skill_content = (skill_path / "SKILL.md").read_text()
        assert "email" in skill_content.lower(), "SKILL.md should mention email"
        assert "@" in skill_content, "SKILL.md should mention @ symbol"

        # Log iteration details
        if result.final_metrics:
            logger.info(
                f"Final metrics after {result.iterations_completed} iterations: "
                f"accuracy={result.final_metrics.accuracy:.2%}, "
                f"tests={result.final_metrics.tests_passed}/{result.final_metrics.tests_total}"
            )

        # If multiple iterations occurred, log that improvement happened
        if result.iterations_completed > 1:
            logger.info(f"Skill improved over {result.iterations_completed} iterations!")

    @pytest.mark.asyncio
    @pytest.mark.timeout(480)
    async def test_iterative_improvement_json_processor(self, temp_skills_dir, temporal_host):
        """Test iterative improvement with a JSON processing skill.

        This skill requires handling multiple edge cases which typically
        needs improvement iterations to get right.
        """
        description = """A skill that processes JSON data and extracts values.

The skill should:
1. Accept a JSON string and a field path (dot notation like "user.name")
2. Parse the JSON and extract the value at the specified path
3. Handle nested objects (e.g., "user.address.city")
4. Handle arrays with index notation (e.g., "items.0.name")
5. Return the extracted value or an error if path not found

Inputs:
- json_data: The JSON string to process
- field_path: The dot-notation path to extract (e.g., "user.name")

Outputs:
- found: boolean indicating if the path exists
- value: the extracted value (as string) or null
- error: error message if any

Examples:
- json_data: '{"user": {"name": "Alice"}}', field_path: "user.name"
  Output: {"found": true, "value": "Alice"}

- json_data: '{"items": [{"id": 1}, {"id": 2}]}', field_path: "items.1.id"
  Output: {"found": true, "value": "2"}

- json_data: '{"a": 1}', field_path: "b.c"
  Output: {"found": false, "error": "path not found"}
"""

        result, workflow_id = await run_skill_workflow(
            temporal_host,
            description=description,
            max_iterations=3,
            target_accuracy=0.85,
        )

        logger.info(f"JSON processor skill workflow completed: {result}")
        logger.info(f"Iterations completed: {result.iterations_completed}")

        # Verify success
        assert result.skill_path is not None, "Expected skill_path in result"

        # Verify content
        skill_path = Path(result.skill_path)
        skill_content = (skill_path / "SKILL.md").read_text()
        assert "json" in skill_content.lower(), "SKILL.md should mention JSON"

        # Log metrics
        if result.final_metrics:
            logger.info(
                f"Final accuracy: {result.final_metrics.accuracy:.2%} "
                f"after {result.iterations_completed} iteration(s)"
            )


if __name__ == "__main__":
    # Allow running directly for quick testing
    import sys

    os.environ["RUN_E2E_TESTS"] = "1"

    # Parse command line args for which test to run
    test_name = sys.argv[1] if len(sys.argv) > 1 else "simple"

    with tempfile.TemporaryDirectory(prefix="skill_auto_test_") as temp_dir:
        tests = TestSkillAutoE2E()
        temporal_host = os.environ.get("TEMPORAL_HOST", "temporal.almckay.io:7233")

        if test_name == "simple":
            logger.info("Running simple skill creation test...")
            asyncio.run(tests.test_simple_skill_creation(temp_dir, temporal_host))
        elif test_name == "complex":
            logger.info("Running complex skill with iterations test...")
            asyncio.run(tests.test_complex_skill_with_iterations(temp_dir, temporal_host))
        elif test_name == "json":
            logger.info("Running JSON processor iterative improvement test...")
            asyncio.run(tests.test_iterative_improvement_json_processor(temp_dir, temporal_host))
        else:
            logger.info(f"Unknown test: {test_name}")
            logger.info("Available tests: simple, complex, json")
