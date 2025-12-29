"""
Intelligence and pattern detection for AI agents.

Provides pattern recognition, recurrence detection, and analysis
capabilities for agent workflows.

Modules:
    recurrence: Issue pattern detection and prevention suggestions
"""

from core_agents.intelligence.recurrence import (
    IssueRecord,
    PatternMatcher,
    PatternType,
    RecurrencePattern,
    Severity,
    get_pattern_matcher,
    get_patterns,
    record_issue,
    suggest_prevention,
)

__all__ = [
    "PatternMatcher",
    "PatternType",
    "RecurrencePattern",
    "IssueRecord",
    "Severity",
    "get_pattern_matcher",
    "get_patterns",
    "record_issue",
    "suggest_prevention",
]
