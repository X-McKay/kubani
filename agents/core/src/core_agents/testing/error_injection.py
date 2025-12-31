"""
Error injection utilities for testing error handling.

Provides a way to inject errors at specific points in code execution
to test error handling, retry logic, and recovery patterns.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ErrorInjector:
    """
    Inject errors at specific points in execution.

    Use to test error handling for:
    - External service failures (MCP, APIs, databases)
    - Network errors (timeouts, connection refused)
    - Rate limiting and retries
    - Partial failures in batch operations

    Example usage:
        injector = ErrorInjector()

        # Always fail at a point
        injector.fail_on("mcp_connect", ConnectionError("MCP unavailable"))

        # Fail on the 3rd call (test retry after 2 failures)
        injector.fail_on_nth_call("api_call", 3, TimeoutError())

        # In code under test:
        injector.check_and_raise("mcp_connect")  # Raises ConnectionError
    """

    error_points: dict[str, Exception] = field(default_factory=dict)
    call_counts: dict[str, int] = field(default_factory=dict)
    fail_on_nth: dict[str, tuple[int, Exception]] = field(default_factory=dict)
    call_results: dict[str, list[Any]] = field(default_factory=dict)

    def fail_on(self, point: str, error: Exception) -> None:
        """
        Always fail at this point.

        Args:
            point: Identifier for the injection point
            error: Exception to raise when point is reached
        """
        self.error_points[point] = error

    def fail_on_nth_call(self, point: str, n: int, error: Exception) -> None:
        """
        Fail on the nth call to this point.

        Useful for testing retry logic where first N-1 attempts fail.

        Args:
            point: Identifier for the injection point
            n: Call number that should fail (1-indexed)
            error: Exception to raise on the nth call
        """
        self.fail_on_nth[point] = (n, error)
        self.call_counts[point] = 0

    def clear(self) -> None:
        """Clear all error injections and reset state."""
        self.error_points.clear()
        self.call_counts.clear()
        self.fail_on_nth.clear()
        self.call_results.clear()

    def check_and_raise(self, point: str) -> None:
        """
        Check if an error should be raised at this point.

        Call this at injection points in your code under test.

        Args:
            point: Identifier for the injection point

        Raises:
            The configured exception if this point should fail
        """
        # Check always-fail points
        if point in self.error_points:
            raise self.error_points[point]

        # Check nth-call failures
        if point in self.fail_on_nth:
            self.call_counts[point] = self.call_counts.get(point, 0) + 1
            n, error = self.fail_on_nth[point]
            if self.call_counts[point] == n:
                raise error

    def record_result(self, point: str, result: Any) -> None:
        """
        Record a result at an injection point.

        Useful for tracking what values were passed through a point.

        Args:
            point: Identifier for the injection point
            result: The value to record
        """
        if point not in self.call_results:
            self.call_results[point] = []
        self.call_results[point].append(result)

    def get_results(self, point: str) -> list[Any]:
        """
        Get all recorded results for a point.

        Args:
            point: Identifier for the injection point

        Returns:
            List of recorded results (empty if none)
        """
        return self.call_results.get(point, [])

    def get_call_count(self, point: str) -> int:
        """
        Get the number of times a point was checked.

        Args:
            point: Identifier for the injection point

        Returns:
            Number of times check_and_raise was called for this point
        """
        return self.call_counts.get(point, 0)
