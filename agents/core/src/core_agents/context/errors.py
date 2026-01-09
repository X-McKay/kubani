"""
Error context management for AI agents.

Preserves error information in context to prevent agents from repeating
the same mistakes. This is a key context engineering technique that
improves agent reliability and reduces wasted iterations.

Usage:
    from core_agents.context.errors import ErrorContext

    errors = ErrorContext()
    errors.record_error(
        action="kubectl get pods",
        error_message="connection refused",
        context={"namespace": "prod"}
    )

    # Check before retrying
    if errors.has_similar_error("connection refused"):
        # Try different approach
        pass

    # Get error summary for LLM context
    summary = errors.get_context_summary()
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from difflib import SequenceMatcher
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ErrorRecord:
    """Record of an error that occurred during agent execution."""

    action: str
    error_message: str
    error_type: str = "unknown"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    context: dict[str, Any] = field(default_factory=dict)
    recovery_attempted: bool = False
    recovery_action: str = ""
    recovery_successful: bool = False

    def similarity_to(self, other: "ErrorRecord") -> float:
        """Calculate similarity to another error record."""
        # Compare error messages
        msg_similarity = SequenceMatcher(
            None, self.error_message.lower(), other.error_message.lower()
        ).ratio()

        # Compare actions
        action_similarity = SequenceMatcher(
            None, self.action.lower(), other.action.lower()
        ).ratio()

        # Weighted average
        return 0.7 * msg_similarity + 0.3 * action_similarity

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action": self.action,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context,
            "recovery_attempted": self.recovery_attempted,
            "recovery_action": self.recovery_action,
            "recovery_successful": self.recovery_successful,
        }


@dataclass
class ErrorContextConfig:
    """Configuration for ErrorContext."""

    max_errors: int = 50
    similarity_threshold: float = 0.8
    include_context_in_summary: bool = True
    max_summary_errors: int = 5


class ErrorContext:
    """
    Manages error context for agent execution.

    Key features:
    1. Records errors with full context
    2. Detects similar/repeated errors
    3. Tracks recovery attempts
    4. Provides summarized context for LLM prompts
    """

    def __init__(self, config: ErrorContextConfig | None = None):
        """
        Initialize ErrorContext.

        Args:
            config: Optional configuration
        """
        self.config = config or ErrorContextConfig()
        self._errors: list[ErrorRecord] = []
        self._error_counts: dict[str, int] = {}

        logger.debug("ErrorContext initialized")

    def record_error(
        self,
        action: str,
        error_message: str,
        error_type: str = "unknown",
        context: dict[str, Any] | None = None,
    ) -> ErrorRecord:
        """
        Record an error that occurred.

        Args:
            action: The action that caused the error
            error_message: The error message
            error_type: Type/category of error
            context: Additional context

        Returns:
            The created ErrorRecord
        """
        record = ErrorRecord(
            action=action,
            error_message=error_message,
            error_type=error_type,
            context=context or {},
        )

        self._errors.append(record)

        # Track error type counts
        self._error_counts[error_type] = self._error_counts.get(error_type, 0) + 1

        # Trim if over limit
        if len(self._errors) > self.config.max_errors:
            self._errors = self._errors[-self.config.max_errors :]

        logger.warning(f"Error recorded: {action} - {error_message}")
        return record

    def record_recovery(
        self,
        error: ErrorRecord,
        recovery_action: str,
        successful: bool,
    ) -> None:
        """
        Record a recovery attempt for an error.

        Args:
            error: The error that was recovered from
            recovery_action: What was done to recover
            successful: Whether recovery succeeded
        """
        error.recovery_attempted = True
        error.recovery_action = recovery_action
        error.recovery_successful = successful

        status = "successful" if successful else "failed"
        logger.info(f"Recovery {status}: {recovery_action}")

    def has_similar_error(
        self,
        error_message: str,
        action: str = "",
        threshold: float | None = None,
    ) -> bool:
        """
        Check if a similar error has occurred recently.

        Args:
            error_message: Error message to check
            action: Optional action to match
            threshold: Similarity threshold (default from config)

        Returns:
            True if similar error found
        """
        threshold = threshold or self.config.similarity_threshold

        test_record = ErrorRecord(action=action, error_message=error_message)

        for error in self._errors:
            if test_record.similarity_to(error) >= threshold:
                return True

        return False

    def get_similar_errors(
        self,
        error_message: str,
        action: str = "",
        threshold: float | None = None,
    ) -> list[ErrorRecord]:
        """
        Get all similar errors.

        Args:
            error_message: Error message to match
            action: Optional action to match
            threshold: Similarity threshold

        Returns:
            List of similar error records
        """
        threshold = threshold or self.config.similarity_threshold
        test_record = ErrorRecord(action=action, error_message=error_message)

        similar = []
        for error in self._errors:
            if test_record.similarity_to(error) >= threshold:
                similar.append(error)

        return similar

    def get_successful_recoveries(self, error_type: str = "") -> list[ErrorRecord]:
        """
        Get errors that were successfully recovered from.

        Args:
            error_type: Optional filter by error type

        Returns:
            List of successfully recovered errors
        """
        recovered = []
        for error in self._errors:
            if error.recovery_successful:
                if not error_type or error.error_type == error_type:
                    recovered.append(error)
        return recovered

    def get_error_count(self, error_type: str = "") -> int:
        """Get count of errors, optionally by type."""
        if error_type:
            return self._error_counts.get(error_type, 0)
        return len(self._errors)

    def get_recent_errors(self, count: int = 5) -> list[ErrorRecord]:
        """Get the most recent errors."""
        return self._errors[-count:]

    def get_context_summary(self, max_errors: int | None = None) -> str:
        """
        Get a summary suitable for LLM context.

        This summary helps the agent avoid repeating mistakes.

        Args:
            max_errors: Maximum errors to include

        Returns:
            Formatted summary string
        """
        max_errors = max_errors or self.config.max_summary_errors

        if not self._errors:
            return ""

        lines = ["## Recent Errors (Avoid Repeating)"]
        lines.append("")

        recent = self._errors[-max_errors:]
        for error in recent:
            lines.append(f"**Action**: {error.action}")
            lines.append(f"**Error**: {error.error_message}")

            if error.recovery_attempted:
                status = "✓" if error.recovery_successful else "✗"
                lines.append(f"**Recovery** {status}: {error.recovery_action}")

            if self.config.include_context_in_summary and error.context:
                ctx_str = ", ".join(f"{k}={v}" for k, v in error.context.items())
                lines.append(f"**Context**: {ctx_str}")

            lines.append("")

        # Add guidance
        if len(self._errors) >= 3:
            lines.append("**Guidance**: Multiple errors have occurred. Consider:")
            lines.append("- Using a different approach")
            lines.append("- Checking prerequisites")
            lines.append("- Requesting human assistance if stuck")

        return "\n".join(lines)

    def get_error_patterns(self) -> dict[str, int]:
        """
        Analyze error patterns.

        Returns:
            Dict mapping error types to counts
        """
        return dict(self._error_counts)

    def clear(self) -> None:
        """Clear all error records."""
        self._errors = []
        self._error_counts = {}
        logger.debug("Error context cleared")

    def to_dict(self) -> dict[str, Any]:
        """Export error context as dictionary."""
        return {
            "errors": [e.to_dict() for e in self._errors],
            "error_counts": self._error_counts,
            "total_errors": len(self._errors),
        }
