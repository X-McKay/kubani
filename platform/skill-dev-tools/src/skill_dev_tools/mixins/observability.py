"""Observability Mixin - Structured logging, metrics, tracing."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from skill_dev_tools.base import AgentBase

logger = logging.getLogger(__name__)


class ObservabilityMixin:
    """
    Mixin for observability (logging, metrics, tracing).

    Provides structured logging and trace context propagation.

    Usage:
        class MyAgent(AgentBase, ObservabilityMixin):
            async def initialize(self) -> None:
                await super().initialize()
                self.init_observability()

            async def run(self) -> None:
                self.log.info("Starting processing", event_count=10)
    """

    def init_observability(self: AgentBase) -> None:
        """Initialize observability (structured logging)."""
        # Configure structlog
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        # Create bound logger for this agent
        self._log = structlog.get_logger(self.name)
        self._log = self._log.bind(
            agent_name=self.name,
            agent_version=self.version,
        )

        logger.info(f"Observability initialized for {self.name}")

    @property
    def log(self: AgentBase) -> Any:
        """Get the structured logger."""
        if not hasattr(self, "_log") or self._log is None:
            # Fallback to standard logger
            return logging.getLogger(self.name)
        return self._log

    def log_event(
        self: AgentBase,
        event: str,
        level: str = "info",
        **kwargs: Any,
    ) -> None:
        """
        Log a structured event.

        Args:
            event: Event name
            level: Log level (debug, info, warning, error)
            **kwargs: Additional context
        """
        log_method = getattr(self.log, level, self.log.info)
        log_method(event, **kwargs)
