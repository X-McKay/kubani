"""Test helper utilities for Kubani Nexus tests.

This module provides utility functions for common test operations:
- Database setup and teardown
- Workflow state polling
- Timestamp validation
- Log capture
"""

import asyncio
import logging
import re
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import datetime
from typing import Any


async def create_test_database(
    db_pool: Any, schema_file: str = "infrastructure/docker/nexus-init.sql"
) -> None:
    """Create test database schema.

    Args:
        db_pool: asyncpg connection pool
        schema_file: Path to SQL schema file

    Raises:
        FileNotFoundError: If schema file doesn't exist
        Exception: If schema creation fails
    """
    from pathlib import Path

    schema_path = Path(schema_file)
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_file}")

    schema_sql = schema_path.read_text()

    # Execute schema creation
    async with db_pool.acquire() as conn:
        await conn.execute(schema_sql)


async def wait_for_workflow_state(
    workflow_handle: Any,
    expected_status: str,
    timeout: int = 30,
    poll_interval: float = 0.5,
) -> dict[str, Any]:
    """Poll workflow until it reaches expected state or timeout.

    Args:
        workflow_handle: Temporal workflow handle
        expected_status: Expected workflow status (e.g., "IDLE", "PROCESSING")
        timeout: Maximum time to wait in seconds
        poll_interval: Time between polls in seconds

    Returns:
        Final workflow state

    Raises:
        TimeoutError: If workflow doesn't reach expected state within timeout
    """
    start_time = asyncio.get_running_loop().time()

    while True:
        # Query workflow state
        try:
            state = await workflow_handle.query("get_state")

            if state.get("status") == expected_status:
                return state

        except Exception:
            # Workflow might not be ready yet, continue polling
            pass

        # Check timeout
        elapsed = asyncio.get_running_loop().time() - start_time
        if elapsed >= timeout:
            raise TimeoutError(
                f"Workflow did not reach status '{expected_status}' within {timeout}s"
            )

        # Wait before next poll
        await asyncio.sleep(poll_interval)


def assert_iso8601_timestamp(timestamp: str) -> None:
    """Validate that a string is a valid ISO 8601 timestamp.

    Args:
        timestamp: String to validate

    Raises:
        AssertionError: If timestamp is not valid ISO 8601 format
    """
    # ISO 8601 format: YYYY-MM-DDTHH:MM:SS.ffffff+HH:MM or Z
    iso8601_pattern = re.compile(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$"
    )

    assert iso8601_pattern.match(timestamp), f"Invalid ISO 8601 timestamp: {timestamp}"

    # Also verify it can be parsed
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as e:
        raise AssertionError(f"Timestamp cannot be parsed: {timestamp}") from e


@contextmanager
def capture_logs(
    logger_name: str = "kubani.nexus",
    level: int = logging.DEBUG,
) -> Generator[list[logging.LogRecord], None, None]:
    """Context manager to capture log messages during test execution.

    Args:
        logger_name: Name of logger to capture
        level: Minimum log level to capture

    Yields:
        List of captured log records

    Example:
        with capture_logs("kubani.nexus") as logs:
            # Run code that logs
            function_that_logs()

        # Check captured logs
        assert len(logs) > 0
        assert logs[0].levelname == "INFO"
    """
    # Create a custom handler that captures records
    captured_records: list[logging.LogRecord] = []

    class ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured_records.append(record)

    # Set up handler
    handler = ListHandler()
    handler.setLevel(level)

    # Get logger and add handler
    logger = logging.getLogger(logger_name)
    original_level = logger.level
    logger.setLevel(level)
    logger.addHandler(handler)

    try:
        yield captured_records
    finally:
        # Clean up
        logger.removeHandler(handler)
        logger.setLevel(original_level)


async def wait_for_condition(
    condition: Callable[[], bool],
    timeout: int = 10,
    poll_interval: float = 0.1,
    error_message: str = "Condition not met within timeout",
) -> None:
    """Wait for a condition to become true.

    Args:
        condition: Callable that returns True when condition is met
        timeout: Maximum time to wait in seconds
        poll_interval: Time between checks in seconds
        error_message: Error message if timeout occurs

    Raises:
        TimeoutError: If condition is not met within timeout
    """
    start_time = asyncio.get_running_loop().time()

    while not condition():
        elapsed = asyncio.get_running_loop().time() - start_time
        if elapsed >= timeout:
            raise TimeoutError(error_message)

        await asyncio.sleep(poll_interval)


def create_test_id(prefix: str = "test") -> str:
    """Generate a unique test ID.

    Args:
        prefix: Prefix for the test ID

    Returns:
        Unique test ID string
    """
    import uuid

    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def cleanup_test_data(db_pool: Any, test_id: str) -> None:
    """Clean up test data from database.

    Args:
        db_pool: asyncpg connection pool
        test_id: Test ID used to identify test data
    """
    async with db_pool.acquire() as conn:
        # Delete test conversations and related data
        await conn.execute(
            "DELETE FROM conversation_messages WHERE conversation_id LIKE $1", f"%{test_id}%"
        )
        await conn.execute(
            "DELETE FROM conversations WHERE conversation_id LIKE $1", f"%{test_id}%"
        )
        await conn.execute(
            "DELETE FROM agent_actions WHERE conversation_id LIKE $1", f"%{test_id}%"
        )
        await conn.execute("DELETE FROM skills WHERE name LIKE $1", f"%{test_id}%")
