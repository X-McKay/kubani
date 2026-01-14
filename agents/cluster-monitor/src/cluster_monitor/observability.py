"""
Observability utilities for cluster-monitor.

Provides structured logging, metrics, and error tracking.
"""

import logging
import time
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Metrics (simple in-memory counters for now)
# =============================================================================

_metrics = {
    "investigations_started": 0,
    "investigations_completed": 0,
    "investigations_failed": 0,
    "worker_tasks_total": 0,
    "worker_tasks_success": 0,
    "worker_tasks_failed": 0,
    "stage_durations": {},
}


def increment_metric(name: str, value: int = 1) -> None:
    """Increment a metric counter."""
    if name in _metrics:
        _metrics[name] += value
    else:
        _metrics[name] = value


def record_duration(name: str, duration: float) -> None:
    """Record a duration metric."""
    if name not in _metrics["stage_durations"]:
        _metrics["stage_durations"][name] = []
    _metrics["stage_durations"][name].append(duration)


def get_metrics() -> dict[str, Any]:
    """Get all metrics."""
    return _metrics.copy()


# =============================================================================
# Structured Logging
# =============================================================================


def log_investigation_start(investigation_id: str, correlation_id: str, event_count: int) -> None:
    """Log investigation start."""
    logger.info(
        "Investigation started",
        extra={
            "investigation_id": investigation_id,
            "correlation_id": correlation_id,
            "event_count": event_count,
            "event_type": "investigation_start",
        },
    )
    increment_metric("investigations_started")


def log_investigation_complete(
    investigation_id: str, duration: float, success: bool
) -> None:
    """Log investigation completion."""
    logger.info(
        f"Investigation {'completed' if success else 'failed'}",
        extra={
            "investigation_id": investigation_id,
            "duration_seconds": duration,
            "success": success,
            "event_type": "investigation_complete",
        },
    )
    if success:
        increment_metric("investigations_completed")
    else:
        increment_metric("investigations_failed")
    record_duration("investigation_total", duration)


def log_stage_transition(
    investigation_id: str, from_stage: str, to_stage: str, duration: float
) -> None:
    """Log stage transition."""
    logger.info(
        f"Stage transition: {from_stage} -> {to_stage}",
        extra={
            "investigation_id": investigation_id,
            "from_stage": from_stage,
            "to_stage": to_stage,
            "duration_seconds": duration,
            "event_type": "stage_transition",
        },
    )
    record_duration(f"stage_{from_stage}", duration)


def log_worker_task(
    investigation_id: str, task_type: str, task_id: str, success: bool, duration: float
) -> None:
    """Log worker task completion."""
    logger.info(
        f"Worker task {task_type} {'succeeded' if success else 'failed'}",
        extra={
            "investigation_id": investigation_id,
            "task_type": task_type,
            "task_id": task_id,
            "success": success,
            "duration_seconds": duration,
            "event_type": "worker_task",
        },
    )
    increment_metric("worker_tasks_total")
    if success:
        increment_metric("worker_tasks_success")
    else:
        increment_metric("worker_tasks_failed")


def log_error(
    investigation_id: str, error: Exception, context: dict[str, Any] | None = None
) -> None:
    """Log an error with context."""
    logger.error(
        f"Error in investigation: {type(error).__name__}: {error}",
        extra={
            "investigation_id": investigation_id,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context or {},
            "event_type": "error",
        },
        exc_info=True,
    )


# =============================================================================
# Context Managers
# =============================================================================


@contextmanager
def timed_operation(operation_name: str, investigation_id: str | None = None):
    """
    Context manager for timing operations.
    
    Usage:
        with timed_operation("worker_task", investigation_id):
            # do work
            pass
    """
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        logger.debug(
            f"Operation {operation_name} took {duration:.2f}s",
            extra={
                "operation": operation_name,
                "investigation_id": investigation_id,
                "duration_seconds": duration,
            },
        )
        record_duration(operation_name, duration)


@contextmanager
def error_context(investigation_id: str, operation: str):
    """
    Context manager for error handling with logging.
    
    Usage:
        with error_context(investigation_id, "worker_delegation"):
            # do work that might fail
            pass
    """
    try:
        yield
    except Exception as e:
        log_error(investigation_id, e, {"operation": operation})
        raise
