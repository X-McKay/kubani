"""
Capacity Planning for Kubernetes clusters.

Provides resource analysis, growth projection, and capacity
recommendations based on historical usage patterns.

Key concepts:
- ResourceUsage: Point-in-time resource consumption snapshot
- CapacityForecast: Projected resource needs over time
- CapacityPlanner: Analyzes usage and generates recommendations

Usage:
    from core_agents.intelligence.capacity import (
        CapacityPlanner,
        ResourceUsage,
        CapacityRecommendation,
    )

    # Create planner
    planner = CapacityPlanner()

    # Record usage snapshots over time
    planner.record_usage(ResourceUsage(
        node_name="node-1",
        cpu_cores_used=4.5,
        cpu_cores_total=8,
        memory_gb_used=12.0,
        memory_gb_total=16,
        storage_gb_used=100,
        storage_gb_total=500,
    ))

    # Get capacity recommendations
    recommendations = planner.get_recommendations()
    for rec in recommendations:
        print(f"{rec.resource_type}: {rec.message}")
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ResourceType(Enum):
    """Types of resources to track."""

    CPU = "cpu"
    MEMORY = "memory"
    STORAGE = "storage"
    GPU = "gpu"
    PODS = "pods"


class RecommendationType(Enum):
    """Types of capacity recommendations."""

    SCALE_UP = "scale_up"  # Need more resources
    SCALE_DOWN = "scale_down"  # Over-provisioned
    REBALANCE = "rebalance"  # Uneven distribution
    OPTIMIZE = "optimize"  # Improve utilization
    ALERT = "alert"  # Approaching limits


class Urgency(Enum):
    """Urgency level for recommendations."""

    LOW = "low"  # Nice to have
    MEDIUM = "medium"  # Should address soon
    HIGH = "high"  # Needs attention
    CRITICAL = "critical"  # Immediate action needed


@dataclass
class ResourceUsage:
    """
    Point-in-time resource usage snapshot.

    Attributes:
        node_name: Name of the node (or "cluster" for aggregates)
        cpu_cores_used: CPU cores currently in use
        cpu_cores_total: Total CPU cores available
        memory_gb_used: Memory in GB currently in use
        memory_gb_total: Total memory in GB available
        storage_gb_used: Storage in GB currently in use
        storage_gb_total: Total storage in GB available
        gpu_used: GPUs currently in use (optional)
        gpu_total: Total GPUs available (optional)
        pod_count: Current pod count (optional)
        pod_limit: Maximum pods allowed (optional)
        timestamp: When this snapshot was taken
    """

    node_name: str
    cpu_cores_used: float
    cpu_cores_total: float
    memory_gb_used: float
    memory_gb_total: float
    storage_gb_used: float = 0.0
    storage_gb_total: float = 0.0
    gpu_used: int = 0
    gpu_total: int = 0
    pod_count: int = 0
    pod_limit: int = 110  # Default K8s limit
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def cpu_percent(self) -> float:
        """CPU utilization percentage."""
        if self.cpu_cores_total == 0:
            return 0.0
        return (self.cpu_cores_used / self.cpu_cores_total) * 100

    @property
    def memory_percent(self) -> float:
        """Memory utilization percentage."""
        if self.memory_gb_total == 0:
            return 0.0
        return (self.memory_gb_used / self.memory_gb_total) * 100

    @property
    def storage_percent(self) -> float:
        """Storage utilization percentage."""
        if self.storage_gb_total == 0:
            return 0.0
        return (self.storage_gb_used / self.storage_gb_total) * 100

    @property
    def pod_percent(self) -> float:
        """Pod utilization percentage."""
        if self.pod_limit == 0:
            return 0.0
        return (self.pod_count / self.pod_limit) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "node_name": self.node_name,
            "cpu_cores_used": self.cpu_cores_used,
            "cpu_cores_total": self.cpu_cores_total,
            "cpu_percent": self.cpu_percent,
            "memory_gb_used": self.memory_gb_used,
            "memory_gb_total": self.memory_gb_total,
            "memory_percent": self.memory_percent,
            "storage_gb_used": self.storage_gb_used,
            "storage_gb_total": self.storage_gb_total,
            "storage_percent": self.storage_percent,
            "gpu_used": self.gpu_used,
            "gpu_total": self.gpu_total,
            "pod_count": self.pod_count,
            "pod_limit": self.pod_limit,
            "pod_percent": self.pod_percent,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class CapacityForecast:
    """
    Projected capacity over time.

    Attributes:
        resource_type: Type of resource forecasted
        current_usage: Current utilization percentage
        projected_usage: Projected utilization at forecast_horizon
        growth_rate: Daily growth rate (percentage points)
        days_until_warning: Days until warning threshold (80%)
        days_until_critical: Days until critical threshold (90%)
        forecast_horizon_days: How far ahead the projection extends
        confidence: Confidence level (0-1) based on data quality
    """

    resource_type: ResourceType
    current_usage: float
    projected_usage: float
    growth_rate: float
    days_until_warning: int | None
    days_until_critical: int | None
    forecast_horizon_days: int
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "resource_type": self.resource_type.value,
            "current_usage": self.current_usage,
            "projected_usage": self.projected_usage,
            "growth_rate": self.growth_rate,
            "days_until_warning": self.days_until_warning,
            "days_until_critical": self.days_until_critical,
            "forecast_horizon_days": self.forecast_horizon_days,
            "confidence": self.confidence,
        }


@dataclass
class CapacityRecommendation:
    """
    Capacity planning recommendation.

    Attributes:
        resource_type: Type of resource
        recommendation_type: Type of recommendation
        urgency: How urgent the recommendation is
        message: Human-readable recommendation
        details: Additional context and data
        estimated_headroom_days: Days of headroom if no action taken
    """

    resource_type: ResourceType
    recommendation_type: RecommendationType
    urgency: Urgency
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    estimated_headroom_days: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "resource_type": self.resource_type.value,
            "recommendation_type": self.recommendation_type.value,
            "urgency": self.urgency.value,
            "message": self.message,
            "details": self.details,
            "estimated_headroom_days": self.estimated_headroom_days,
        }


class CapacityPlanner:
    """
    Analyzes resource usage and provides capacity recommendations.

    Tracks historical usage to project future needs and identify
    potential capacity issues before they become critical.

    Example:
        planner = CapacityPlanner()

        # Record node usage over time
        for usage in usage_snapshots:
            planner.record_usage(usage)

        # Get forecasts
        forecasts = planner.forecast_capacity(horizon_days=30)
        for forecast in forecasts:
            print(f"{forecast.resource_type}: {forecast.days_until_critical} days")

        # Get recommendations
        recs = planner.get_recommendations()
        for rec in recs:
            print(f"[{rec.urgency.value}] {rec.message}")
    """

    # Utilization thresholds
    WARNING_THRESHOLD = 80.0  # Percent
    CRITICAL_THRESHOLD = 90.0  # Percent
    UNDERUTILIZED_THRESHOLD = 30.0  # Percent
    IMBALANCE_THRESHOLD = 20.0  # Percent difference between nodes

    def __init__(
        self,
        history_days: int = 30,
        min_data_points: int = 5,
    ) -> None:
        """
        Initialize the capacity planner.

        Args:
            history_days: Days of history to keep for analysis
            min_data_points: Minimum data points needed for forecasting
        """
        self.history_days = history_days
        self.min_data_points = min_data_points

        # Usage history by node
        self._usage_history: dict[str, list[ResourceUsage]] = {}
        # Cluster-wide aggregates
        self._cluster_history: list[ResourceUsage] = []

    def record_usage(self, usage: ResourceUsage) -> None:
        """
        Record a resource usage snapshot.

        Args:
            usage: Resource usage snapshot to record
        """
        node = usage.node_name

        if node not in self._usage_history:
            self._usage_history[node] = []

        self._usage_history[node].append(usage)

        # Prune old data
        cutoff = datetime.now(UTC) - timedelta(days=self.history_days)
        self._usage_history[node] = [u for u in self._usage_history[node] if u.timestamp > cutoff]

        # Update cluster aggregate
        self._update_cluster_aggregate()

    def _update_cluster_aggregate(self) -> None:
        """Update cluster-wide aggregate from latest node data."""
        if not self._usage_history:
            return

        # Get the most recent usage from each node
        latest_by_node: dict[str, ResourceUsage] = {}
        for node, history in self._usage_history.items():
            if history:
                latest_by_node[node] = max(history, key=lambda u: u.timestamp)

        if not latest_by_node:
            return

        # Aggregate
        total_cpu_used = sum(u.cpu_cores_used for u in latest_by_node.values())
        total_cpu_total = sum(u.cpu_cores_total for u in latest_by_node.values())
        total_memory_used = sum(u.memory_gb_used for u in latest_by_node.values())
        total_memory_total = sum(u.memory_gb_total for u in latest_by_node.values())
        total_storage_used = sum(u.storage_gb_used for u in latest_by_node.values())
        total_storage_total = sum(u.storage_gb_total for u in latest_by_node.values())
        total_gpu_used = sum(u.gpu_used for u in latest_by_node.values())
        total_gpu_total = sum(u.gpu_total for u in latest_by_node.values())
        total_pods = sum(u.pod_count for u in latest_by_node.values())
        total_pod_limit = sum(u.pod_limit for u in latest_by_node.values())

        cluster_usage = ResourceUsage(
            node_name="cluster",
            cpu_cores_used=total_cpu_used,
            cpu_cores_total=total_cpu_total,
            memory_gb_used=total_memory_used,
            memory_gb_total=total_memory_total,
            storage_gb_used=total_storage_used,
            storage_gb_total=total_storage_total,
            gpu_used=total_gpu_used,
            gpu_total=total_gpu_total,
            pod_count=total_pods,
            pod_limit=total_pod_limit,
        )

        self._cluster_history.append(cluster_usage)

        # Prune old cluster data
        cutoff = datetime.now(UTC) - timedelta(days=self.history_days)
        self._cluster_history = [u for u in self._cluster_history if u.timestamp > cutoff]

    def get_current_usage(self, node: str | None = None) -> ResourceUsage | None:
        """
        Get the most recent usage snapshot.

        Args:
            node: Node name, or None for cluster aggregate

        Returns:
            Most recent ResourceUsage or None if no data
        """
        if node is None:
            return self._cluster_history[-1] if self._cluster_history else None

        history = self._usage_history.get(node, [])
        return history[-1] if history else None

    def forecast_capacity(
        self,
        horizon_days: int = 30,
        node: str | None = None,
    ) -> list[CapacityForecast]:
        """
        Forecast capacity for each resource type.

        Args:
            horizon_days: How many days ahead to forecast
            node: Node name, or None for cluster aggregate

        Returns:
            List of CapacityForecast for each resource type
        """
        history = self._cluster_history if node is None else self._usage_history.get(node, [])

        if len(history) < self.min_data_points:
            return []

        forecasts = []

        # Forecast each resource type
        for resource_type, get_usage in [
            (ResourceType.CPU, lambda u: u.cpu_percent),
            (ResourceType.MEMORY, lambda u: u.memory_percent),
            (ResourceType.STORAGE, lambda u: u.storage_percent),
            (ResourceType.PODS, lambda u: u.pod_percent),
        ]:
            forecast = self._forecast_resource(history, resource_type, get_usage, horizon_days)
            if forecast:
                forecasts.append(forecast)

        return forecasts

    def _forecast_resource(
        self,
        history: list[ResourceUsage],
        resource_type: ResourceType,
        get_usage: Any,
        horizon_days: int,
    ) -> CapacityForecast | None:
        """Forecast a single resource type."""
        if len(history) < 2:
            return None

        # Extract usage percentages with timestamps
        data_points = [(u.timestamp, get_usage(u)) for u in history]
        data_points.sort(key=lambda x: x[0])

        # Calculate growth rate (percentage points per day)
        first_ts, first_val = data_points[0]
        last_ts, last_val = data_points[-1]

        days_elapsed = max((last_ts - first_ts).total_seconds() / 86400, 1)
        growth_rate = (last_val - first_val) / days_elapsed

        # Project forward
        projected_usage = last_val + (growth_rate * horizon_days)
        projected_usage = max(0, min(100, projected_usage))  # Clamp to 0-100

        # Calculate days until thresholds
        days_until_warning = None
        days_until_critical = None

        if growth_rate > 0:
            if last_val < self.WARNING_THRESHOLD:
                days_until_warning = int((self.WARNING_THRESHOLD - last_val) / growth_rate)
            if last_val < self.CRITICAL_THRESHOLD:
                days_until_critical = int((self.CRITICAL_THRESHOLD - last_val) / growth_rate)

        # Calculate confidence based on data quality
        data_span_days = days_elapsed
        confidence = min(1.0, data_span_days / 7)  # Full confidence after a week
        confidence *= min(1.0, len(data_points) / 20)  # More points = more confidence

        return CapacityForecast(
            resource_type=resource_type,
            current_usage=last_val,
            projected_usage=projected_usage,
            growth_rate=growth_rate,
            days_until_warning=days_until_warning,
            days_until_critical=days_until_critical,
            forecast_horizon_days=horizon_days,
            confidence=confidence,
        )

    def get_recommendations(self) -> list[CapacityRecommendation]:
        """
        Generate capacity recommendations based on current state and forecasts.

        Returns:
            List of CapacityRecommendation sorted by urgency
        """
        recommendations: list[CapacityRecommendation] = []

        # Get current cluster state
        current = self.get_current_usage()
        if not current:
            return recommendations

        # Check current utilization levels
        recommendations.extend(self._check_utilization(current))

        # Check forecasts
        forecasts = self.forecast_capacity()
        recommendations.extend(self._check_forecasts(forecasts))

        # Check node balance
        recommendations.extend(self._check_balance())

        # Sort by urgency
        urgency_order = {
            Urgency.CRITICAL: 0,
            Urgency.HIGH: 1,
            Urgency.MEDIUM: 2,
            Urgency.LOW: 3,
        }
        recommendations.sort(key=lambda r: urgency_order[r.urgency])

        return recommendations

    def _check_utilization(self, usage: ResourceUsage) -> list[CapacityRecommendation]:
        """Check current utilization levels."""
        recommendations = []

        for resource_type, percent, name in [
            (ResourceType.CPU, usage.cpu_percent, "CPU"),
            (ResourceType.MEMORY, usage.memory_percent, "Memory"),
            (ResourceType.STORAGE, usage.storage_percent, "Storage"),
            (ResourceType.PODS, usage.pod_percent, "Pod capacity"),
        ]:
            if percent >= self.CRITICAL_THRESHOLD:
                recommendations.append(
                    CapacityRecommendation(
                        resource_type=resource_type,
                        recommendation_type=RecommendationType.SCALE_UP,
                        urgency=Urgency.CRITICAL,
                        message=f"{name} at {percent:.1f}% - immediate capacity increase needed",
                        details={"current_percent": percent, "threshold": self.CRITICAL_THRESHOLD},
                    )
                )
            elif percent >= self.WARNING_THRESHOLD:
                recommendations.append(
                    CapacityRecommendation(
                        resource_type=resource_type,
                        recommendation_type=RecommendationType.ALERT,
                        urgency=Urgency.HIGH,
                        message=f"{name} at {percent:.1f}% - approaching capacity limits",
                        details={"current_percent": percent, "threshold": self.WARNING_THRESHOLD},
                    )
                )
            elif percent <= self.UNDERUTILIZED_THRESHOLD and percent > 0:
                recommendations.append(
                    CapacityRecommendation(
                        resource_type=resource_type,
                        recommendation_type=RecommendationType.SCALE_DOWN,
                        urgency=Urgency.LOW,
                        message=f"{name} at {percent:.1f}% - potentially over-provisioned",
                        details={
                            "current_percent": percent,
                            "threshold": self.UNDERUTILIZED_THRESHOLD,
                        },
                    )
                )

        return recommendations

    def _check_forecasts(self, forecasts: list[CapacityForecast]) -> list[CapacityRecommendation]:
        """Check forecasts for upcoming capacity issues."""
        recommendations = []

        for forecast in forecasts:
            resource_name = forecast.resource_type.value.upper()

            # Check if critical threshold will be reached soon
            if forecast.days_until_critical is not None:
                if forecast.days_until_critical <= 7:
                    recommendations.append(
                        CapacityRecommendation(
                            resource_type=forecast.resource_type,
                            recommendation_type=RecommendationType.SCALE_UP,
                            urgency=Urgency.HIGH,
                            message=(
                                f"{resource_name} projected to reach critical level in "
                                f"{forecast.days_until_critical} days"
                            ),
                            details={
                                "current_usage": forecast.current_usage,
                                "projected_usage": forecast.projected_usage,
                                "growth_rate": forecast.growth_rate,
                            },
                            estimated_headroom_days=forecast.days_until_critical,
                        )
                    )
                elif forecast.days_until_critical <= 30:
                    recommendations.append(
                        CapacityRecommendation(
                            resource_type=forecast.resource_type,
                            recommendation_type=RecommendationType.ALERT,
                            urgency=Urgency.MEDIUM,
                            message=(
                                f"{resource_name} growth trend indicates capacity needed in "
                                f"{forecast.days_until_critical} days"
                            ),
                            details={
                                "current_usage": forecast.current_usage,
                                "growth_rate": forecast.growth_rate,
                            },
                            estimated_headroom_days=forecast.days_until_critical,
                        )
                    )

        return recommendations

    def _check_balance(self) -> list[CapacityRecommendation]:
        """Check for imbalanced resource distribution across nodes."""
        recommendations = []

        if len(self._usage_history) < 2:
            return recommendations

        # Get latest usage from each node
        node_usages = []
        for node, history in self._usage_history.items():
            if history:
                node_usages.append((node, history[-1]))

        if len(node_usages) < 2:
            return recommendations

        # Check CPU balance
        cpu_percents = [u.cpu_percent for _, u in node_usages]
        cpu_range = max(cpu_percents) - min(cpu_percents)

        if cpu_range > self.IMBALANCE_THRESHOLD:
            max_node = max(node_usages, key=lambda x: x[1].cpu_percent)[0]
            min_node = min(node_usages, key=lambda x: x[1].cpu_percent)[0]
            recommendations.append(
                CapacityRecommendation(
                    resource_type=ResourceType.CPU,
                    recommendation_type=RecommendationType.REBALANCE,
                    urgency=Urgency.MEDIUM,
                    message=(
                        f"CPU load imbalanced: {cpu_range:.1f}% difference "
                        f"between {max_node} and {min_node}"
                    ),
                    details={
                        "max_node": max_node,
                        "max_percent": max(cpu_percents),
                        "min_node": min_node,
                        "min_percent": min(cpu_percents),
                    },
                )
            )

        # Check memory balance
        mem_percents = [u.memory_percent for _, u in node_usages]
        mem_range = max(mem_percents) - min(mem_percents)

        if mem_range > self.IMBALANCE_THRESHOLD:
            max_node = max(node_usages, key=lambda x: x[1].memory_percent)[0]
            min_node = min(node_usages, key=lambda x: x[1].memory_percent)[0]
            recommendations.append(
                CapacityRecommendation(
                    resource_type=ResourceType.MEMORY,
                    recommendation_type=RecommendationType.REBALANCE,
                    urgency=Urgency.MEDIUM,
                    message=(
                        f"Memory load imbalanced: {mem_range:.1f}% difference "
                        f"between {max_node} and {min_node}"
                    ),
                    details={
                        "max_node": max_node,
                        "max_percent": max(mem_percents),
                        "min_node": min_node,
                        "min_percent": min(mem_percents),
                    },
                )
            )

        return recommendations

    def get_statistics(self) -> dict[str, Any]:
        """Get summary statistics about the planner state."""
        return {
            "nodes_tracked": len(self._usage_history),
            "cluster_data_points": len(self._cluster_history),
            "history_days": self.history_days,
            "nodes": list(self._usage_history.keys()),
            "data_points_per_node": {
                node: len(history) for node, history in self._usage_history.items()
            },
        }


# Singleton planner
_capacity_planner: CapacityPlanner | None = None


def get_capacity_planner() -> CapacityPlanner:
    """Get the global capacity planner."""
    global _capacity_planner
    if _capacity_planner is None:
        _capacity_planner = CapacityPlanner()
    return _capacity_planner


def record_node_usage(
    node_name: str,
    cpu_cores_used: float,
    cpu_cores_total: float,
    memory_gb_used: float,
    memory_gb_total: float,
    **kwargs: Any,
) -> None:
    """
    Record node resource usage using the global planner.

    Convenience function for simple usage.

    Args:
        node_name: Name of the node
        cpu_cores_used: CPU cores currently in use
        cpu_cores_total: Total CPU cores available
        memory_gb_used: Memory in GB currently in use
        memory_gb_total: Total memory in GB available
        **kwargs: Additional ResourceUsage fields
    """
    planner = get_capacity_planner()
    usage = ResourceUsage(
        node_name=node_name,
        cpu_cores_used=cpu_cores_used,
        cpu_cores_total=cpu_cores_total,
        memory_gb_used=memory_gb_used,
        memory_gb_total=memory_gb_total,
        **kwargs,
    )
    planner.record_usage(usage)
