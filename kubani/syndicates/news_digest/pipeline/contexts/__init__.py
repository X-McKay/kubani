"""Concrete PipelineContext implementations.

- ``TemporalContext``: For production use inside Temporal workflows.
- ``LocalContext``: For standalone testing without Temporal.
"""

from .temporal_context import TemporalContext
from .local_context import LocalContext

__all__ = [
    "TemporalContext",
    "LocalContext",
]
