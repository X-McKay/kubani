"""Domain layer for skill_auto workflow.

This layer contains pure business logic and data structures
with no dependencies on Temporal, external services, or I/O.
"""

from .decisions import should_continue_iteration
from .models import IterationContext

__all__ = [
    "IterationContext",
    "should_continue_iteration",
]
