"""
Anomaly Detection for predictive monitoring.

Provides statistical anomaly detection for metrics, enabling
proactive alerting before failures occur.

Key concepts:
- MetricBaseline: Statistical baseline for a metric (mean, std, percentiles)
- AnomalyDetector: Detects deviations from baseline
- AnomalyAlert: Alert when anomaly is detected

Usage:
    from core_agents.intelligence.anomaly import (
        AnomalyDetector,
        MetricBaseline,
        AnomalyType,
    )

    # Create detector
    detector = AnomalyDetector()

    # Add historical data points to build baseline
    for value in historical_cpu_values:
        detector.add_data_point("cpu_usage", value)

    # Check for anomalies in new data
    alert = detector.check("cpu_usage", current_cpu_value)
    if alert:
        print(f"Anomaly detected: {alert.description}")
        print(f"Severity: {alert.severity}")
"""

import logging
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AnomalyType(Enum):
    """Types of anomalies that can be detected."""

    SPIKE = "spike"  # Sudden increase
    DROP = "drop"  # Sudden decrease
    DRIFT = "drift"  # Gradual change over time
    VOLATILITY = "volatility"  # Unusual variance
    THRESHOLD = "threshold"  # Crossed absolute threshold
    TREND = "trend"  # Sustained directional change


class AlertSeverity(Enum):
    """Severity levels for anomaly alerts."""

    INFO = "info"  # Informational, no action needed
    WARNING = "warning"  # Worth monitoring
    CRITICAL = "critical"  # Requires attention


@dataclass
class MetricBaseline:
    """
    Statistical baseline for a metric.

    Attributes:
        name: Metric name
        mean: Average value
        std_dev: Standard deviation
        min_value: Minimum observed value
        max_value: Maximum observed value
        p50: 50th percentile (median)
        p90: 90th percentile
        p99: 99th percentile
        sample_count: Number of samples used
        last_updated: When the baseline was last updated
    """

    name: str
    mean: float
    std_dev: float
    min_value: float
    max_value: float
    p50: float
    p90: float
    p99: float
    sample_count: int
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))

    def z_score(self, value: float) -> float:
        """Calculate z-score (standard deviations from mean)."""
        if self.std_dev == 0:
            return 0.0 if value == self.mean else float("inf")
        return (value - self.mean) / self.std_dev

    def is_outlier(self, value: float, threshold: float = 3.0) -> bool:
        """Check if value is an outlier (beyond threshold std devs)."""
        return abs(self.z_score(value)) > threshold

    def percentile_rank(self, value: float) -> float:
        """Estimate percentile rank of a value (0-100)."""
        if value <= self.min_value:
            return 0.0
        if value >= self.max_value:
            return 100.0
        # Simple linear interpolation between known percentiles
        if value <= self.p50:
            return 50.0 * (value - self.min_value) / (self.p50 - self.min_value + 0.0001)
        elif value <= self.p90:
            return 50.0 + 40.0 * (value - self.p50) / (self.p90 - self.p50 + 0.0001)
        else:
            return 90.0 + 10.0 * (value - self.p90) / (self.max_value - self.p90 + 0.0001)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "mean": self.mean,
            "std_dev": self.std_dev,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "p50": self.p50,
            "p90": self.p90,
            "p99": self.p99,
            "sample_count": self.sample_count,
            "last_updated": self.last_updated.isoformat(),
        }


@dataclass
class AnomalyAlert:
    """
    Alert generated when an anomaly is detected.

    Attributes:
        metric_name: Name of the metric with anomaly
        anomaly_type: Type of anomaly detected
        severity: Alert severity
        value: Current value that triggered the alert
        expected_range: Expected range based on baseline
        z_score: How many std devs from mean
        description: Human-readable description
        timestamp: When the anomaly was detected
        metadata: Additional context
    """

    metric_name: str
    anomaly_type: AnomalyType
    severity: AlertSeverity
    value: float
    expected_range: tuple[float, float]
    z_score: float
    description: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "metric_name": self.metric_name,
            "anomaly_type": self.anomaly_type.value,
            "severity": self.severity.value,
            "value": self.value,
            "expected_range": self.expected_range,
            "z_score": self.z_score,
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class MetricThreshold:
    """
    Absolute thresholds for a metric.

    Attributes:
        warning_high: Warning if value exceeds this
        critical_high: Critical if value exceeds this
        warning_low: Warning if value falls below this
        critical_low: Critical if value falls below this
    """

    warning_high: float | None = None
    critical_high: float | None = None
    warning_low: float | None = None
    critical_low: float | None = None


class AnomalyDetector:
    """
    Detects anomalies in metric time series.

    Uses statistical methods to establish baselines and detect
    deviations that may indicate problems.

    Example:
        detector = AnomalyDetector()

        # Build baseline from historical data
        for value in historical_values:
            detector.add_data_point("cpu_usage", value)

        # Check new values for anomalies
        alert = detector.check("cpu_usage", 95.5)
        if alert:
            print(f"Anomaly: {alert.description}")

        # Set absolute thresholds
        detector.set_threshold("memory_percent", MetricThreshold(
            warning_high=80.0,
            critical_high=95.0,
        ))
    """

    # Default thresholds for common Kubernetes metrics
    DEFAULT_THRESHOLDS: dict[str, MetricThreshold] = {
        "cpu_percent": MetricThreshold(warning_high=80.0, critical_high=95.0),
        "memory_percent": MetricThreshold(warning_high=85.0, critical_high=95.0),
        "disk_percent": MetricThreshold(warning_high=80.0, critical_high=90.0),
        "pod_restart_count": MetricThreshold(warning_high=3.0, critical_high=10.0),
        "error_rate": MetricThreshold(warning_high=0.01, critical_high=0.05),
        "latency_p99_ms": MetricThreshold(warning_high=1000.0, critical_high=5000.0),
    }

    def __init__(
        self,
        window_size: int = 1000,
        min_samples: int = 30,
        z_score_warning: float = 2.0,
        z_score_critical: float = 3.0,
    ) -> None:
        """
        Initialize the anomaly detector.

        Args:
            window_size: Number of recent data points to keep for baseline
            min_samples: Minimum samples needed before anomaly detection
            z_score_warning: Z-score threshold for warning alerts
            z_score_critical: Z-score threshold for critical alerts
        """
        self.window_size = window_size
        self.min_samples = min_samples
        self.z_score_warning = z_score_warning
        self.z_score_critical = z_score_critical

        # Data storage
        self._data: dict[str, deque[float]] = {}
        self._baselines: dict[str, MetricBaseline] = {}
        self._thresholds: dict[str, MetricThreshold] = dict(self.DEFAULT_THRESHOLDS)
        self._last_values: dict[str, list[tuple[datetime, float]]] = {}

    def add_data_point(
        self,
        metric_name: str,
        value: float,
        timestamp: datetime | None = None,
    ) -> None:
        """
        Add a data point for a metric.

        Args:
            metric_name: Name of the metric
            value: Metric value
            timestamp: When the value was recorded (default: now)
        """
        if metric_name not in self._data:
            self._data[metric_name] = deque(maxlen=self.window_size)
            self._last_values[metric_name] = []

        self._data[metric_name].append(value)

        # Keep recent values for trend detection
        ts = timestamp or datetime.now(UTC)
        self._last_values[metric_name].append((ts, value))
        # Keep only last 10 for trend analysis
        self._last_values[metric_name] = self._last_values[metric_name][-10:]

        # Update baseline if we have enough samples
        if len(self._data[metric_name]) >= self.min_samples:
            self._update_baseline(metric_name)

    def _update_baseline(self, metric_name: str) -> None:
        """Update the baseline statistics for a metric."""
        data = list(self._data[metric_name])
        n = len(data)

        if n == 0:
            return

        # Calculate statistics
        sorted_data = sorted(data)
        mean = sum(data) / n
        variance = sum((x - mean) ** 2 for x in data) / n
        std_dev = math.sqrt(variance)

        self._baselines[metric_name] = MetricBaseline(
            name=metric_name,
            mean=mean,
            std_dev=std_dev,
            min_value=sorted_data[0],
            max_value=sorted_data[-1],
            p50=sorted_data[n // 2],
            p90=sorted_data[int(n * 0.9)],
            p99=sorted_data[int(n * 0.99)] if n >= 100 else sorted_data[-1],
            sample_count=n,
        )

    def set_threshold(self, metric_name: str, threshold: MetricThreshold) -> None:
        """Set absolute thresholds for a metric."""
        self._thresholds[metric_name] = threshold

    def get_baseline(self, metric_name: str) -> MetricBaseline | None:
        """Get the current baseline for a metric."""
        return self._baselines.get(metric_name)

    def check(
        self,
        metric_name: str,
        value: float,
        timestamp: datetime | None = None,
    ) -> AnomalyAlert | None:
        """
        Check a value for anomalies.

        Args:
            metric_name: Name of the metric
            value: Current value to check
            timestamp: When the value was recorded

        Returns:
            AnomalyAlert if anomaly detected, None otherwise
        """
        alerts: list[AnomalyAlert] = []
        ts = timestamp or datetime.now(UTC)

        # Check absolute thresholds first
        threshold_alert = self._check_threshold(metric_name, value, ts)
        if threshold_alert:
            alerts.append(threshold_alert)

        # Check statistical anomalies if we have a baseline
        baseline = self._baselines.get(metric_name)
        if baseline and baseline.sample_count >= self.min_samples:
            stat_alert = self._check_statistical(metric_name, value, baseline, ts)
            if stat_alert:
                alerts.append(stat_alert)

            # Check for trend anomalies
            trend_alert = self._check_trend(metric_name, value, baseline, ts)
            if trend_alert:
                alerts.append(trend_alert)

        # Return the most severe alert
        if alerts:
            alerts.sort(
                key=lambda a: (
                    a.severity == AlertSeverity.CRITICAL,
                    a.severity == AlertSeverity.WARNING,
                ),
                reverse=True,
            )
            return alerts[0]

        return None

    def _check_threshold(
        self,
        metric_name: str,
        value: float,
        timestamp: datetime,
    ) -> AnomalyAlert | None:
        """Check value against absolute thresholds."""
        threshold = self._thresholds.get(metric_name)
        if not threshold:
            return None

        # Check critical thresholds
        if threshold.critical_high is not None and value >= threshold.critical_high:
            return AnomalyAlert(
                metric_name=metric_name,
                anomaly_type=AnomalyType.THRESHOLD,
                severity=AlertSeverity.CRITICAL,
                value=value,
                expected_range=(0, threshold.critical_high),
                z_score=0.0,
                description=f"{metric_name} ({value:.2f}) exceeds critical threshold ({threshold.critical_high})",
                timestamp=timestamp,
                metadata={"threshold_type": "critical_high"},
            )

        if threshold.critical_low is not None and value <= threshold.critical_low:
            return AnomalyAlert(
                metric_name=metric_name,
                anomaly_type=AnomalyType.THRESHOLD,
                severity=AlertSeverity.CRITICAL,
                value=value,
                expected_range=(threshold.critical_low, float("inf")),
                z_score=0.0,
                description=f"{metric_name} ({value:.2f}) below critical threshold ({threshold.critical_low})",
                timestamp=timestamp,
                metadata={"threshold_type": "critical_low"},
            )

        # Check warning thresholds
        if threshold.warning_high is not None and value >= threshold.warning_high:
            return AnomalyAlert(
                metric_name=metric_name,
                anomaly_type=AnomalyType.THRESHOLD,
                severity=AlertSeverity.WARNING,
                value=value,
                expected_range=(0, threshold.warning_high),
                z_score=0.0,
                description=f"{metric_name} ({value:.2f}) exceeds warning threshold ({threshold.warning_high})",
                timestamp=timestamp,
                metadata={"threshold_type": "warning_high"},
            )

        if threshold.warning_low is not None and value <= threshold.warning_low:
            return AnomalyAlert(
                metric_name=metric_name,
                anomaly_type=AnomalyType.THRESHOLD,
                severity=AlertSeverity.WARNING,
                value=value,
                expected_range=(threshold.warning_low, float("inf")),
                z_score=0.0,
                description=f"{metric_name} ({value:.2f}) below warning threshold ({threshold.warning_low})",
                timestamp=timestamp,
                metadata={"threshold_type": "warning_low"},
            )

        return None

    def _check_statistical(
        self,
        metric_name: str,
        value: float,
        baseline: MetricBaseline,
        timestamp: datetime,
    ) -> AnomalyAlert | None:
        """Check for statistical anomalies using z-score."""
        z = baseline.z_score(value)
        abs_z = abs(z)

        if abs_z < self.z_score_warning:
            return None

        # Determine type and severity
        anomaly_type = AnomalyType.SPIKE if z > 0 else AnomalyType.DROP
        severity = (
            AlertSeverity.CRITICAL if abs_z >= self.z_score_critical else AlertSeverity.WARNING
        )

        expected_low = baseline.mean - (self.z_score_warning * baseline.std_dev)
        expected_high = baseline.mean + (self.z_score_warning * baseline.std_dev)

        return AnomalyAlert(
            metric_name=metric_name,
            anomaly_type=anomaly_type,
            severity=severity,
            value=value,
            expected_range=(expected_low, expected_high),
            z_score=z,
            description=(
                f"{metric_name} {anomaly_type.value}: {value:.2f} "
                f"(z-score: {z:.2f}, expected: {expected_low:.2f}-{expected_high:.2f})"
            ),
            timestamp=timestamp,
            metadata={
                "baseline_mean": baseline.mean,
                "baseline_std": baseline.std_dev,
                "percentile_rank": baseline.percentile_rank(value),
            },
        )

    def _check_trend(
        self,
        metric_name: str,
        value: float,
        baseline: MetricBaseline,
        timestamp: datetime,
    ) -> AnomalyAlert | None:
        """Check for sustained trend anomalies."""
        recent = self._last_values.get(metric_name, [])
        if len(recent) < 5:
            return None

        # Check if all recent values are above/below mean
        values = [v for _, v in recent]
        above_mean = sum(1 for v in values if v > baseline.mean)
        below_mean = len(values) - above_mean

        # If 80%+ of recent values are on one side, it's a trend
        if above_mean >= len(values) * 0.8:
            trend_direction = "increasing"
            avg_deviation = sum(v - baseline.mean for v in values) / len(values)
        elif below_mean >= len(values) * 0.8:
            trend_direction = "decreasing"
            avg_deviation = sum(baseline.mean - v for v in values) / len(values)
        else:
            return None

        # Only alert if the deviation is significant
        if baseline.std_dev > 0 and abs(avg_deviation) / baseline.std_dev < 1.0:
            return None

        return AnomalyAlert(
            metric_name=metric_name,
            anomaly_type=AnomalyType.TREND,
            severity=AlertSeverity.WARNING,
            value=value,
            expected_range=(baseline.mean - baseline.std_dev, baseline.mean + baseline.std_dev),
            z_score=avg_deviation / baseline.std_dev if baseline.std_dev > 0 else 0,
            description=(
                f"{metric_name} showing {trend_direction} trend: "
                f"recent average {avg_deviation:.2f} from baseline mean"
            ),
            timestamp=timestamp,
            metadata={
                "trend_direction": trend_direction,
                "recent_values": values,
                "avg_deviation": avg_deviation,
            },
        )

    def get_all_baselines(self) -> dict[str, MetricBaseline]:
        """Get all current baselines."""
        return dict(self._baselines)

    def get_statistics(self) -> dict[str, Any]:
        """Get summary statistics about the detector."""
        return {
            "metrics_tracked": len(self._data),
            "metrics_with_baseline": len(self._baselines),
            "total_data_points": sum(len(d) for d in self._data.values()),
            "thresholds_configured": len(self._thresholds),
            "window_size": self.window_size,
            "min_samples": self.min_samples,
        }


# Singleton detector
_anomaly_detector: AnomalyDetector | None = None


def get_anomaly_detector() -> AnomalyDetector:
    """Get the global anomaly detector."""
    global _anomaly_detector
    if _anomaly_detector is None:
        _anomaly_detector = AnomalyDetector()
    return _anomaly_detector


def check_metric(metric_name: str, value: float) -> AnomalyAlert | None:
    """
    Check a metric value for anomalies using the global detector.

    Convenience function for simple usage.

    Args:
        metric_name: Name of the metric
        value: Current value to check

    Returns:
        AnomalyAlert if anomaly detected, None otherwise
    """
    detector = get_anomaly_detector()
    detector.add_data_point(metric_name, value)
    return detector.check(metric_name, value)
