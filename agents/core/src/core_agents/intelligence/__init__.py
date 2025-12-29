"""
Intelligence and pattern detection for AI agents.

Provides pattern recognition, recurrence detection, anomaly detection,
capacity planning, and analysis capabilities for agent workflows.

Modules:
    recurrence: Issue pattern detection and prevention suggestions
    anomaly: Statistical anomaly detection for predictive monitoring
    capacity: Resource capacity planning and forecasting
"""

from core_agents.intelligence.anomaly import (
    AlertSeverity,
    AnomalyAlert,
    AnomalyDetector,
    AnomalyType,
    MetricBaseline,
    MetricThreshold,
    check_metric,
    get_anomaly_detector,
)
from core_agents.intelligence.capacity import (
    CapacityForecast,
    CapacityPlanner,
    CapacityRecommendation,
    RecommendationType,
    ResourceType,
    ResourceUsage,
    Urgency,
    get_capacity_planner,
    record_node_usage,
)
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
    # Recurrence/Pattern detection
    "PatternMatcher",
    "PatternType",
    "RecurrencePattern",
    "IssueRecord",
    "Severity",
    "get_pattern_matcher",
    "get_patterns",
    "record_issue",
    "suggest_prevention",
    # Anomaly detection
    "AnomalyDetector",
    "AnomalyAlert",
    "AnomalyType",
    "AlertSeverity",
    "MetricBaseline",
    "MetricThreshold",
    "get_anomaly_detector",
    "check_metric",
    # Capacity planning
    "CapacityPlanner",
    "CapacityForecast",
    "CapacityRecommendation",
    "ResourceUsage",
    "ResourceType",
    "RecommendationType",
    "Urgency",
    "get_capacity_planner",
    "record_node_usage",
]
