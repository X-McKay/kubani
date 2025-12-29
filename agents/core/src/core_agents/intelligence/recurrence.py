"""
Recurrence Intelligence for pattern detection and optimization.

This module provides pattern recognition and recurrence detection
for agent workflows, enabling:
- Detection of recurring issues and their patterns
- Automatic optimization of remediation strategies
- Predictive issue identification
- Trend analysis and alerting

Key concepts:
- RecurrencePattern: A detected pattern of recurring events/issues
- PatternMatcher: Analyzes events to identify patterns
- RecurrenceOptimizer: Suggests optimizations based on patterns

Usage:
    from core_agents.recurrence import (
        PatternMatcher,
        RecurrencePattern,
        suggest_prevention,
    )

    # Detect patterns in issues
    matcher = PatternMatcher()
    matcher.record_issue(issue_type="CrashLoopBackOff", resource="pod/app-123", namespace="prod")
    matcher.record_issue(issue_type="CrashLoopBackOff", resource="pod/app-124", namespace="prod")

    # Get detected patterns
    patterns = matcher.get_patterns()
    for pattern in patterns:
        print(f"{pattern.pattern_type}: {pattern.description} (confidence: {pattern.confidence})")
        print(f"  Prevention: {suggest_prevention(pattern)}")
"""

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """Types of recurrence patterns."""

    TEMPORAL = "temporal"  # Time-based patterns (e.g., every hour)
    RESOURCE = "resource"  # Resource-based patterns (e.g., same deployment)
    CAUSAL = "causal"  # Cause-effect patterns (e.g., after deployment)
    CLUSTER = "cluster"  # Clustered patterns (e.g., multiple issues at once)
    CASCADING = "cascading"  # One issue triggers others
    PERIODIC = "periodic"  # Regular interval patterns


class Severity(Enum):
    """Severity levels for patterns and issues."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class IssueRecord:
    """Record of an issue occurrence."""

    issue_type: str
    resource: str
    namespace: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolution_time: timedelta | None = None

    @property
    def resource_kind(self) -> str:
        """Extract resource kind (e.g., 'pod' from 'pod/app-123')."""
        if "/" in self.resource:
            return self.resource.split("/")[0]
        return "unknown"

    @property
    def resource_name(self) -> str:
        """Extract resource name (e.g., 'app-123' from 'pod/app-123')."""
        if "/" in self.resource:
            return self.resource.split("/")[1]
        return self.resource

    @property
    def resource_base_name(self) -> str:
        """Extract base name without replica suffix (e.g., 'app' from 'app-123-abc')."""
        name = self.resource_name
        # Common Kubernetes naming patterns: name-replicaset-pod, name-12345
        # Remove trailing hash/number suffixes
        parts = name.rsplit("-", 2)
        # Check if we have parts and last part looks like a hash or number
        if len(parts) >= 2 and re.match(r"^[a-z0-9]{5,}$", parts[-1]):
            name = parts[0] if len(parts) == 2 else f"{parts[0]}-{parts[1]}"
        return name


@dataclass
class RecurrencePattern:
    """A detected pattern of recurring events."""

    pattern_type: PatternType
    description: str
    confidence: float  # 0.0 to 1.0
    occurrences: int
    first_seen: datetime
    last_seen: datetime
    affected_resources: list[str]
    issue_types: list[str]
    severity: Severity = Severity.MEDIUM
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> timedelta:
        """Duration from first to last occurrence."""
        return self.last_seen - self.first_seen

    @property
    def frequency_per_hour(self) -> float:
        """Average occurrences per hour."""
        hours = max(self.duration.total_seconds() / 3600, 1)
        return self.occurrences / hours

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "pattern_type": self.pattern_type.value,
            "description": self.description,
            "confidence": self.confidence,
            "occurrences": self.occurrences,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "affected_resources": self.affected_resources,
            "issue_types": self.issue_types,
            "severity": self.severity.value,
            "frequency_per_hour": self.frequency_per_hour,
            "metadata": self.metadata,
        }


class PatternMatcher:
    """
    Analyzes issues to identify recurring patterns.

    Detects various types of patterns:
    - Temporal: Issues that occur at regular intervals
    - Resource: Issues affecting the same resource types/deployments
    - Cluster: Multiple issues occurring together
    - Cascading: Issues that trigger other issues

    Example:
        matcher = PatternMatcher()

        # Record issues as they occur
        matcher.record_issue("OOMKilled", "pod/app-123", "prod")
        matcher.record_issue("OOMKilled", "pod/app-456", "prod")
        matcher.record_issue("CrashLoopBackOff", "pod/app-123", "prod")

        # Get detected patterns
        patterns = matcher.get_patterns()
    """

    def __init__(
        self,
        temporal_window: timedelta = timedelta(hours=24),
        min_occurrences: int = 3,
        min_confidence: float = 0.6,
    ) -> None:
        """
        Initialize the pattern matcher.

        Args:
            temporal_window: Time window for pattern analysis
            min_occurrences: Minimum occurrences to form a pattern
            min_confidence: Minimum confidence threshold for patterns
        """
        self.temporal_window = temporal_window
        self.min_occurrences = min_occurrences
        self.min_confidence = min_confidence
        self._issues: list[IssueRecord] = []
        self._patterns: list[RecurrencePattern] = []
        self._last_analysis: datetime | None = None

    def record_issue(
        self,
        issue_type: str,
        resource: str,
        namespace: str,
        timestamp: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> IssueRecord:
        """
        Record an issue occurrence.

        Args:
            issue_type: Type of issue (e.g., "CrashLoopBackOff", "OOMKilled")
            resource: Affected resource (e.g., "pod/app-123")
            namespace: Kubernetes namespace
            timestamp: When the issue occurred (default: now)
            metadata: Additional issue metadata

        Returns:
            The recorded issue
        """
        issue = IssueRecord(
            issue_type=issue_type,
            resource=resource,
            namespace=namespace,
            timestamp=timestamp or datetime.now(UTC),
            metadata=metadata or {},
        )
        self._issues.append(issue)
        logger.debug(f"Recorded issue: {issue_type} on {resource}")
        return issue

    def mark_resolved(
        self,
        issue_type: str,
        resource: str,
        namespace: str,
        resolution_time: timedelta | None = None,
    ) -> bool:
        """
        Mark an issue as resolved.

        Args:
            issue_type: Type of issue
            resource: Affected resource
            namespace: Kubernetes namespace
            resolution_time: How long it took to resolve

        Returns:
            True if an issue was found and marked resolved
        """
        # Find the most recent matching unresolved issue
        for issue in reversed(self._issues):
            if (
                issue.issue_type == issue_type
                and issue.resource == resource
                and issue.namespace == namespace
                and not issue.resolved
            ):
                issue.resolved = True
                issue.resolution_time = resolution_time
                return True
        return False

    def get_patterns(self, force_reanalyze: bool = False) -> list[RecurrencePattern]:
        """
        Get detected patterns, analyzing if needed.

        Args:
            force_reanalyze: Force re-analysis even if recently done

        Returns:
            List of detected patterns above confidence threshold
        """
        # Re-analyze if forced or if new issues since last analysis
        should_analyze = force_reanalyze or self._last_analysis is None
        if not should_analyze and self._issues:
            latest_issue = max(i.timestamp for i in self._issues)
            should_analyze = latest_issue > (self._last_analysis or datetime.min.replace(tzinfo=UTC))

        if should_analyze:
            self._analyze_patterns()

        return [p for p in self._patterns if p.confidence >= self.min_confidence]

    def _analyze_patterns(self) -> None:
        """Analyze issues to detect patterns."""
        self._patterns = []
        self._last_analysis = datetime.now(UTC)

        # Filter to recent issues
        cutoff = datetime.now(UTC) - self.temporal_window
        recent_issues = [i for i in self._issues if i.timestamp >= cutoff]

        if len(recent_issues) < self.min_occurrences:
            return

        # Detect different pattern types
        self._detect_resource_patterns(recent_issues)
        self._detect_issue_type_patterns(recent_issues)
        self._detect_temporal_patterns(recent_issues)
        self._detect_cluster_patterns(recent_issues)

        logger.info(f"Pattern analysis complete: {len(self._patterns)} patterns detected")

    def _detect_resource_patterns(self, issues: list[IssueRecord]) -> None:
        """Detect patterns based on affected resources."""
        # Group by base resource name
        by_base_name: dict[str, list[IssueRecord]] = defaultdict(list)
        for issue in issues:
            key = f"{issue.namespace}/{issue.resource_kind}/{issue.resource_base_name}"
            by_base_name[key].append(issue)

        for key, group in by_base_name.items():
            if len(group) >= self.min_occurrences:
                issue_types = list({i.issue_type for i in group})
                affected = list({i.resource for i in group})
                timestamps = [i.timestamp for i in group]

                pattern = RecurrencePattern(
                    pattern_type=PatternType.RESOURCE,
                    description=f"Recurring issues on {key}: {', '.join(issue_types)}",
                    confidence=min(1.0, len(group) / 10),  # Cap at 1.0
                    occurrences=len(group),
                    first_seen=min(timestamps),
                    last_seen=max(timestamps),
                    affected_resources=affected,
                    issue_types=issue_types,
                    severity=self._calculate_severity(group),
                    metadata={"resource_key": key},
                )
                self._patterns.append(pattern)

    def _detect_issue_type_patterns(self, issues: list[IssueRecord]) -> None:
        """Detect patterns based on issue types."""
        # Group by issue type + namespace
        by_type: dict[str, list[IssueRecord]] = defaultdict(list)
        for issue in issues:
            key = f"{issue.namespace}/{issue.issue_type}"
            by_type[key].append(issue)

        for key, group in by_type.items():
            if len(group) >= self.min_occurrences:
                affected = list({i.resource for i in group})
                timestamps = [i.timestamp for i in group]
                namespace, issue_type = key.split("/", 1)

                pattern = RecurrencePattern(
                    pattern_type=PatternType.RESOURCE,
                    description=f"Recurring {issue_type} in {namespace} ({len(affected)} resources)",
                    confidence=min(1.0, len(group) / 10),
                    occurrences=len(group),
                    first_seen=min(timestamps),
                    last_seen=max(timestamps),
                    affected_resources=affected,
                    issue_types=[issue_type],
                    severity=self._calculate_severity(group),
                    metadata={"namespace": namespace, "issue_type": issue_type},
                )
                self._patterns.append(pattern)

    def _detect_temporal_patterns(self, issues: list[IssueRecord]) -> None:
        """Detect time-based patterns (regular intervals)."""
        if len(issues) < 3:
            return

        # Sort by timestamp
        sorted_issues = sorted(issues, key=lambda i: i.timestamp)

        # Calculate intervals between consecutive issues
        intervals: list[timedelta] = []
        for i in range(1, len(sorted_issues)):
            interval = sorted_issues[i].timestamp - sorted_issues[i - 1].timestamp
            intervals.append(interval)

        if not intervals:
            return

        # Check for periodic patterns (hourly, daily, etc.)
        avg_interval = sum(
            (i.total_seconds() for i in intervals), 0.0
        ) / len(intervals)

        # Calculate standard deviation
        variance = sum(
            (i.total_seconds() - avg_interval) ** 2 for i in intervals
        ) / len(intervals)
        std_dev = variance**0.5

        # If variance is low relative to mean, we have a periodic pattern
        if avg_interval > 0 and (std_dev / avg_interval) < 0.3:
            # Determine period type
            period_hours = avg_interval / 3600
            if period_hours < 1:
                period_desc = f"every {int(avg_interval / 60)} minutes"
            elif period_hours < 24:
                period_desc = f"every {int(period_hours)} hours"
            else:
                period_desc = f"every {int(period_hours / 24)} days"

            issue_types = list({i.issue_type for i in sorted_issues})
            affected = list({i.resource for i in sorted_issues})
            timestamps = [i.timestamp for i in sorted_issues]

            pattern = RecurrencePattern(
                pattern_type=PatternType.PERIODIC,
                description=f"Issues occurring {period_desc}",
                confidence=1.0 - min(1.0, std_dev / avg_interval),
                occurrences=len(sorted_issues),
                first_seen=min(timestamps),
                last_seen=max(timestamps),
                affected_resources=affected,
                issue_types=issue_types,
                severity=Severity.MEDIUM,
                metadata={
                    "avg_interval_seconds": avg_interval,
                    "std_dev_seconds": std_dev,
                    "period_description": period_desc,
                },
            )
            self._patterns.append(pattern)

    def _detect_cluster_patterns(self, issues: list[IssueRecord]) -> None:
        """Detect clusters of issues occurring together."""
        if len(issues) < 3:
            return

        # Group issues by 5-minute windows
        window_seconds = 300
        windows: dict[int, list[IssueRecord]] = defaultdict(list)
        for issue in issues:
            window_key = int(issue.timestamp.timestamp() / window_seconds)
            windows[window_key].append(issue)

        # Find windows with multiple issues
        for _window_key, group in windows.items():
            if len(group) >= 3:  # Multiple issues in same 5-minute window
                issue_types = list({i.issue_type for i in group})
                affected = list({i.resource for i in group})
                timestamps = [i.timestamp for i in group]

                pattern = RecurrencePattern(
                    pattern_type=PatternType.CLUSTER,
                    description=f"Cluster of {len(group)} issues occurring together",
                    confidence=min(1.0, len(group) / 5),
                    occurrences=len(group),
                    first_seen=min(timestamps),
                    last_seen=max(timestamps),
                    affected_resources=affected,
                    issue_types=issue_types,
                    severity=Severity.HIGH if len(group) >= 5 else Severity.MEDIUM,
                    metadata={"window_size_seconds": window_seconds},
                )
                self._patterns.append(pattern)

    def _calculate_severity(self, issues: list[IssueRecord]) -> Severity:
        """Calculate severity based on issue characteristics."""
        critical_types = {"OOMKilled", "NodeNotReady", "FailedScheduling", "Evicted"}
        high_types = {"CrashLoopBackOff", "ImagePullBackOff", "CreateContainerError"}

        issue_types = {i.issue_type for i in issues}

        if issue_types & critical_types:
            return Severity.CRITICAL
        elif issue_types & high_types or len(issues) >= 10:
            return Severity.HIGH
        elif len(issues) >= 5:
            return Severity.MEDIUM
        return Severity.LOW

    def get_statistics(self) -> dict[str, Any]:
        """Get summary statistics about recorded issues and patterns."""
        if not self._issues:
            return {"total_issues": 0, "patterns": 0}

        cutoff = datetime.now(UTC) - self.temporal_window
        recent = [i for i in self._issues if i.timestamp >= cutoff]

        return {
            "total_issues": len(self._issues),
            "recent_issues": len(recent),
            "patterns": len(self.get_patterns()),
            "unique_issue_types": len({i.issue_type for i in self._issues}),
            "unique_resources": len({i.resource for i in self._issues}),
            "unique_namespaces": len({i.namespace for i in self._issues}),
            "resolved_issues": len([i for i in self._issues if i.resolved]),
            "temporal_window_hours": self.temporal_window.total_seconds() / 3600,
        }


def suggest_prevention(pattern: RecurrencePattern) -> str:
    """
    Suggest prevention strategies for a detected pattern.

    Args:
        pattern: The detected pattern

    Returns:
        Suggested prevention strategy
    """
    suggestions = []

    # Based on pattern type
    if pattern.pattern_type == PatternType.PERIODIC:
        period = pattern.metadata.get("period_description", "regular intervals")
        suggestions.append(
            f"Issue recurs {period}. Consider scheduling maintenance or "
            "investigating time-based triggers (cron jobs, scheduled tasks)."
        )

    elif pattern.pattern_type == PatternType.RESOURCE:
        resource_key = pattern.metadata.get("resource_key", "unknown")
        suggestions.append(
            f"Resource {resource_key} has recurring issues. Consider: "
            "resource limits adjustment, deployment configuration review, "
            "or replacing the underlying infrastructure."
        )

    elif pattern.pattern_type == PatternType.CLUSTER:
        suggestions.append(
            "Multiple issues occurring together suggests a systemic problem. "
            "Check for common dependencies, shared resources, or cascading failures."
        )

    # Based on issue types
    issue_types = set(pattern.issue_types)

    if "OOMKilled" in issue_types:
        suggestions.append(
            "Memory issues detected. Consider increasing memory limits or "
            "investigating memory leaks in the application."
        )

    if "CrashLoopBackOff" in issue_types:
        suggestions.append(
            "Container crash loop detected. Check application logs for startup "
            "errors, missing dependencies, or configuration issues."
        )

    if "ImagePullBackOff" in issue_types:
        suggestions.append(
            "Image pull failures. Verify image exists, registry credentials are "
            "correct, and network connectivity to registry."
        )

    if "FailedScheduling" in issue_types:
        suggestions.append(
            "Scheduling failures. Check cluster capacity, node selectors, "
            "taints/tolerations, and resource requests."
        )

    # Based on severity
    if pattern.severity == Severity.CRITICAL:
        suggestions.append(
            "CRITICAL: This pattern indicates a serious issue that requires "
            "immediate attention and potentially a permanent fix."
        )

    return " ".join(suggestions) if suggestions else "No specific prevention strategy available."


# Singleton pattern matcher
_pattern_matcher: PatternMatcher | None = None


def get_pattern_matcher() -> PatternMatcher:
    """Get the global pattern matcher."""
    global _pattern_matcher
    if _pattern_matcher is None:
        _pattern_matcher = PatternMatcher()
    return _pattern_matcher


def record_issue(
    issue_type: str,
    resource: str,
    namespace: str,
    **kwargs: Any,
) -> IssueRecord:
    """
    Record an issue using the global pattern matcher.

    Convenience function for simple usage.

    Args:
        issue_type: Type of issue
        resource: Affected resource
        namespace: Kubernetes namespace
        **kwargs: Additional arguments passed to PatternMatcher.record_issue

    Returns:
        The recorded issue
    """
    return get_pattern_matcher().record_issue(
        issue_type=issue_type,
        resource=resource,
        namespace=namespace,
        **kwargs,
    )


def get_patterns() -> list[RecurrencePattern]:
    """
    Get detected patterns from the global pattern matcher.

    Returns:
        List of detected patterns
    """
    return get_pattern_matcher().get_patterns()
