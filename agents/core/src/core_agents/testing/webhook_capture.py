"""
Discord webhook capture utilities for testing.

Provides mock webhook functionality to test Discord notifications
without making actual HTTP requests.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DiscordWebhookCapture:
    """
    Captures Discord webhook calls for testing.

    Use to verify:
    - Number of notifications sent
    - Notification content and structure
    - Error handling for webhook failures
    - Rate limiting behavior

    Example usage:
        capture = DiscordWebhookCapture()

        # In your mock:
        async def mock_post(url, json, **kwargs):
            return capture.capture(json)

        # After test:
        assert capture.call_count == 1
        assert "error" in capture.calls[0]["content"]
    """

    calls: list[dict[str, Any]] = field(default_factory=list)
    should_fail: bool = False
    fail_with: Exception | None = None
    fail_on_call: int | None = None

    def capture(self, payload: dict[str, Any]) -> str:
        """
        Record a webhook call and return a fake message ID.

        Args:
            payload: The webhook payload (embeds, content, etc.)

        Returns:
            A fake Discord message ID

        Raises:
            The configured exception if should_fail is True
        """
        self.calls.append(payload)

        # Check if we should fail on this specific call (takes precedence)
        if self.fail_on_call is not None:
            if len(self.calls) == self.fail_on_call:
                raise self.fail_with or Exception(f"Simulated failure on call {self.fail_on_call}")
            # If fail_on_call is set but not this call, don't check should_fail
        elif self.should_fail and self.fail_with:
            # Only fail on all calls if fail_on_call is not set
            raise self.fail_with

        return f"discord-msg-{len(self.calls)}"

    def set_failure(self, error: Exception, on_call: int | None = None) -> None:
        """
        Configure the webhook to fail with an error.

        Args:
            error: The exception to raise
            on_call: Optional specific call number to fail on (1-indexed).
                    If None, all calls will fail.
        """
        self.should_fail = True
        self.fail_with = error
        self.fail_on_call = on_call

    def clear(self) -> None:
        """Clear captured calls and reset failure state."""
        self.calls.clear()
        self.should_fail = False
        self.fail_with = None
        self.fail_on_call = None

    @property
    def call_count(self) -> int:
        """Number of webhook calls made."""
        return len(self.calls)

    @property
    def last_call(self) -> dict[str, Any] | None:
        """Get the most recent webhook call, or None if no calls."""
        return self.calls[-1] if self.calls else None

    def get_embeds(self, call_index: int = -1) -> list[dict[str, Any]]:
        """
        Get embeds from a specific call.

        Args:
            call_index: Index of the call (-1 for last)

        Returns:
            List of embed dictionaries, or empty list if no embeds
        """
        if not self.calls:
            return []
        try:
            call = self.calls[call_index]
            return call.get("embeds", [])
        except IndexError:
            return []

    def assert_called_once(self) -> None:
        """Assert that the webhook was called exactly once."""
        assert self.call_count == 1, f"Expected 1 call, got {self.call_count}"

    def assert_called_n_times(self, n: int) -> None:
        """Assert that the webhook was called exactly n times."""
        assert self.call_count == n, f"Expected {n} calls, got {self.call_count}"

    def assert_not_called(self) -> None:
        """Assert that the webhook was not called."""
        assert self.call_count == 0, f"Expected 0 calls, got {self.call_count}"
