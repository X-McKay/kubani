"""Mission scheduling utilities.

Provides cron-based scheduling for NexusMissions. Uses the ``croniter``
library to compute the next execution time from a cron expression.

Predefined schedule constants mirror the framework's ScheduleConfig
patterns for consistency across the Kubani platform.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# =========================================================================
# Predefined schedule constants (cron expressions)
# =========================================================================

SCHEDULE_EVERY_5_MIN = "*/5 * * * *"
SCHEDULE_EVERY_15_MIN = "*/15 * * * *"
SCHEDULE_EVERY_30_MIN = "*/30 * * * *"
SCHEDULE_EVERY_HOUR = "0 * * * *"
SCHEDULE_EVERY_6_HOURS = "0 */6 * * *"
SCHEDULE_TWICE_DAILY = "0 9,21 * * *"
SCHEDULE_DAILY_MORNING = "0 9 * * *"
SCHEDULE_DAILY_EVENING = "0 21 * * *"
SCHEDULE_WEEKLY_MONDAY = "0 9 * * 1"

# Human-readable labels for the UI
SCHEDULE_LABELS: dict[str, str] = {
    SCHEDULE_EVERY_5_MIN: "Every 5 minutes",
    SCHEDULE_EVERY_15_MIN: "Every 15 minutes",
    SCHEDULE_EVERY_30_MIN: "Every 30 minutes",
    SCHEDULE_EVERY_HOUR: "Every hour",
    SCHEDULE_EVERY_6_HOURS: "Every 6 hours",
    SCHEDULE_TWICE_DAILY: "Twice daily (9am & 9pm)",
    SCHEDULE_DAILY_MORNING: "Daily at 9am",
    SCHEDULE_DAILY_EVENING: "Daily at 9pm",
    SCHEDULE_WEEKLY_MONDAY: "Weekly on Monday at 9am",
}


# =========================================================================
# Scheduling functions
# =========================================================================


def compute_next_run(cron_expr: str, after: datetime | None = None) -> datetime:
    """Compute the next execution time for a cron expression.

    Args:
        cron_expr: A standard 5-field cron expression (e.g., ``"0 * * * *"``).
        after: Compute the next run after this time. Defaults to now (UTC).

    Returns:
        The next execution time as a timezone-aware UTC datetime.

    Raises:
        ValueError: If the cron expression is invalid.
    """
    try:
        from croniter import croniter
    except ImportError as e:
        raise ImportError(
            "croniter is required for mission scheduling. "
            "Install with: pip install croniter"
        ) from e

    base = after or datetime.now(timezone.utc)
    # croniter works with naive datetimes; we convert and re-attach UTC
    base_naive = base.replace(tzinfo=None)
    cron = croniter(cron_expr, base_naive)
    next_naive = cron.get_next(datetime)
    return next_naive.replace(tzinfo=timezone.utc)


def is_valid_cron(cron_expr: str) -> bool:
    """Check whether a cron expression is syntactically valid.

    Args:
        cron_expr: The cron expression to validate.

    Returns:
        True if valid, False otherwise.
    """
    try:
        from croniter import croniter

        return croniter.is_valid(cron_expr)
    except ImportError:
        logger.warning("croniter not installed; skipping cron validation")
        return True


def describe_schedule(cron_expr: str) -> str:
    """Return a human-readable description of a cron expression.

    Uses the predefined label map first; falls back to the raw expression.

    Args:
        cron_expr: The cron expression.

    Returns:
        Human-readable schedule description.
    """
    return SCHEDULE_LABELS.get(cron_expr, f"Custom schedule: {cron_expr}")
