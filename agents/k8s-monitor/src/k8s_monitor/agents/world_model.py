"""
WorldModelAgent - Maintains a real-time model of the cluster state.

The WorldModel provides a single source of truth for system state that
other agents can query. It maintains a graph of cluster resources and
their relationships, tracks modifications by agents, and enables
temporal queries about system history.

This agent:
- Subscribes to all events from the Event Bus
- Builds and maintains an in-memory graph of cluster resources
- Tracks agent activities and their effects on resources
- Answers queries about system state via A2A
- Detects anomalies by comparing current state to historical patterns
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ResourceKind(str, Enum):
    """Kubernetes resource kinds."""

    POD = "Pod"
    DEPLOYMENT = "Deployment"
    REPLICASET = "ReplicaSet"
    STATEFULSET = "StatefulSet"
    DAEMONSET = "DaemonSet"
    NODE = "Node"
    SERVICE = "Service"
    INGRESS = "Ingress"
    CONFIGMAP = "ConfigMap"
    SECRET = "Secret"  # pragma: allowlist secret
    PVC = "PersistentVolumeClaim"
    PV = "PersistentVolume"
    NAMESPACE = "Namespace"
    NETWORKPOLICY = "NetworkPolicy"
    JOB = "Job"
    CRONJOB = "CronJob"


class EventType(str, Enum):
    """Types of events the WorldModel handles."""

    # Kubernetes events
    RESOURCE_CREATED = "resource_created"
    RESOURCE_UPDATED = "resource_updated"
    RESOURCE_DELETED = "resource_deleted"
    RESOURCE_STATUS_CHANGED = "resource_status_changed"

    # Agent events
    AGENT_ACTION = "agent_action"
    AGENT_HANDOFF = "agent_handoff"
    SKILL_EXECUTED = "skill_executed"

    # System events
    HEALTH_CHECK = "health_check"
    ALERT_TRIGGERED = "alert_triggered"
    REMEDIATION_STARTED = "remediation_started"
    REMEDIATION_COMPLETED = "remediation_completed"


class QueryType(str, Enum):
    """Types of queries the WorldModel supports."""

    GET_RESOURCE = "get_resource"
    LIST_RESOURCES = "list_resources"
    GET_HISTORY = "get_history"
    GET_RELATED = "get_related"
    GET_LINEAGE = "get_lineage"
    GET_AFFECTED = "get_affected"
    GET_AGENT_ACTIONS = "get_agent_actions"
    GET_NAMESPACE_STATUS = "get_namespace_status"
    GET_CLUSTER_SUMMARY = "get_cluster_summary"


@dataclass
class ResourceNode:
    """A node in the world model graph representing a K8s resource."""

    uid: str
    kind: ResourceKind
    name: str
    namespace: str | None
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)
    status: str = "Unknown"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_modified_by: str | None = None
    last_modified_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def resource_id(self) -> str:
        """Generate a unique resource ID."""
        if self.namespace:
            return f"{self.kind.value}/{self.namespace}/{self.name}"
        return f"{self.kind.value}/{self.name}"


@dataclass
class ResourceEdge:
    """An edge representing a relationship between resources."""

    source_uid: str
    target_uid: str
    relationship: str  # e.g., "owns", "selects", "mounts", "references"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class StateEvent:
    """An event that modifies the world state."""

    event_id: str
    event_type: EventType
    resource_uid: str | None
    agent_id: str | None
    timestamp: datetime
    data: dict[str, Any]


class WorldModelQuery(BaseModel):
    """A query to the WorldModel."""

    query_type: QueryType
    resource_type: str | None = None
    namespace: str | None = None
    name: str | None = None
    resource_id: str | None = None
    time_range: str | None = None  # e.g., "last_24h", "last_1h"
    relationship: str | None = None
    agent_id: str | None = None
    limit: int = 100


class WorldModelResponse(BaseModel):
    """Response from the WorldModel."""

    success: bool
    query_type: QueryType
    data: Any = None
    error: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WorldModelAgent:
    """
    Maintains a real-time model of the cluster state.

    The WorldModel is the "single source of truth" for what exists in the
    cluster and how resources relate to each other. Other agents query the
    WorldModel rather than making direct API calls, which reduces load on
    the cluster and ensures consistency.

    Graph Structure:
    - Nodes: Kubernetes resources (pods, deployments, services, etc.)
    - Edges: Relationships (owns, selects, mounts, references)

    Features:
    - Real-time updates from Event Bus
    - Resource lineage tracking (what owns/creates what)
    - Impact analysis (what would be affected by a change)
    - Historical state queries
    - Agent activity tracking
    """

    NAME = "world_model_agent"
    DESCRIPTION = "Maintains real-time cluster state model"

    def __init__(
        self,
        history_max_events: int = 10000,
        history_max_age_hours: int = 24,
    ):
        """
        Initialize the WorldModelAgent.

        Args:
            history_max_events: Maximum events to keep in history
            history_max_age_hours: Maximum age of events to retain
        """
        # Resource graph: uid -> ResourceNode
        self._nodes: dict[str, ResourceNode] = {}

        # Relationship graph: source_uid -> list of ResourceEdge
        self._edges: dict[str, list[ResourceEdge]] = {}

        # Reverse edges for efficient "what points to me" queries
        self._reverse_edges: dict[str, list[ResourceEdge]] = {}

        # Event history for temporal queries
        self._history: deque[StateEvent] = deque(maxlen=history_max_events)
        self._history_max_age = timedelta(hours=history_max_age_hours)

        # Index for quick lookups
        self._by_kind: dict[ResourceKind, set[str]] = {}
        self._by_namespace: dict[str, set[str]] = {}
        self._by_name: dict[str, set[str]] = {}

        # Agent activity tracking
        self._agent_actions: dict[str, list[StateEvent]] = {}

        # Stats
        self._stats = {
            "events_processed": 0,
            "queries_answered": 0,
            "nodes_count": 0,
            "edges_count": 0,
        }

        self._lock = asyncio.Lock()

    async def handle_event(self, event: StateEvent) -> None:
        """
        Handle an incoming event and update the world state.

        Args:
            event: The state event to process
        """
        async with self._lock:
            self._history.append(event)
            self._stats["events_processed"] += 1

            # Track agent actions
            if event.agent_id:
                if event.agent_id not in self._agent_actions:
                    self._agent_actions[event.agent_id] = []
                self._agent_actions[event.agent_id].append(event)

            # Process by event type
            if event.event_type == EventType.RESOURCE_CREATED:
                await self._handle_resource_created(event)
            elif event.event_type == EventType.RESOURCE_UPDATED:
                await self._handle_resource_updated(event)
            elif event.event_type == EventType.RESOURCE_DELETED:
                await self._handle_resource_deleted(event)
            elif event.event_type == EventType.RESOURCE_STATUS_CHANGED:
                await self._handle_status_changed(event)
            elif event.event_type == EventType.AGENT_ACTION:
                await self._handle_agent_action(event)
            elif event.event_type == EventType.SKILL_EXECUTED:
                await self._handle_skill_executed(event)

            self._stats["nodes_count"] = len(self._nodes)
            self._stats["edges_count"] = sum(len(e) for e in self._edges.values())

    async def query(self, query: WorldModelQuery) -> WorldModelResponse:
        """
        Answer a query about the world state.

        Args:
            query: The query to process

        Returns:
            WorldModelResponse with results
        """
        self._stats["queries_answered"] += 1

        try:
            if query.query_type == QueryType.GET_RESOURCE:
                return await self._query_get_resource(query)
            elif query.query_type == QueryType.LIST_RESOURCES:
                return await self._query_list_resources(query)
            elif query.query_type == QueryType.GET_HISTORY:
                return await self._query_get_history(query)
            elif query.query_type == QueryType.GET_RELATED:
                return await self._query_get_related(query)
            elif query.query_type == QueryType.GET_LINEAGE:
                return await self._query_get_lineage(query)
            elif query.query_type == QueryType.GET_AFFECTED:
                return await self._query_get_affected(query)
            elif query.query_type == QueryType.GET_AGENT_ACTIONS:
                return await self._query_agent_actions(query)
            elif query.query_type == QueryType.GET_NAMESPACE_STATUS:
                return await self._query_namespace_status(query)
            elif query.query_type == QueryType.GET_CLUSTER_SUMMARY:
                return await self._query_cluster_summary(query)
            else:
                return WorldModelResponse(
                    success=False,
                    query_type=query.query_type,
                    error=f"Unknown query type: {query.query_type}",
                )
        except Exception as e:
            logger.exception(f"Query failed: {query}")
            return WorldModelResponse(
                success=False,
                query_type=query.query_type,
                error=str(e),
            )

    # --- Event handlers ---

    async def _handle_resource_created(self, event: StateEvent) -> None:
        """Handle resource creation event."""
        data = event.data
        node = ResourceNode(
            uid=data.get("uid", event.resource_uid or ""),
            kind=ResourceKind(data.get("kind", "Pod")),
            name=data.get("name", ""),
            namespace=data.get("namespace"),
            labels=data.get("labels", {}),
            annotations=data.get("annotations", {}),
            status=data.get("status", "Unknown"),
            metadata=data.get("metadata", {}),
        )

        self._add_node(node)

        # Add relationship edges if owner references exist
        owner_refs = data.get("owner_references", [])
        for owner in owner_refs:
            edge = ResourceEdge(
                source_uid=owner.get("uid", ""),
                target_uid=node.uid,
                relationship="owns",
            )
            self._add_edge(edge)

    async def _handle_resource_updated(self, event: StateEvent) -> None:
        """Handle resource update event."""
        uid = event.resource_uid
        if uid and uid in self._nodes:
            node = self._nodes[uid]
            node.updated_at = event.timestamp
            if event.agent_id:
                node.last_modified_by = event.agent_id
                node.last_modified_at = event.timestamp

            # Update status if provided
            if "status" in event.data:
                node.status = event.data["status"]

            # Update labels if provided
            if "labels" in event.data:
                node.labels.update(event.data["labels"])

    async def _handle_resource_deleted(self, event: StateEvent) -> None:
        """Handle resource deletion event."""
        uid = event.resource_uid
        if uid:
            self._remove_node(uid)

    async def _handle_status_changed(self, event: StateEvent) -> None:
        """Handle resource status change event."""
        uid = event.resource_uid
        if uid and uid in self._nodes:
            node = self._nodes[uid]
            node.status = event.data.get("new_status", node.status)
            node.updated_at = event.timestamp

    async def _handle_agent_action(self, event: StateEvent) -> None:
        """Handle agent action event."""
        uid = event.resource_uid
        if uid and uid in self._nodes:
            node = self._nodes[uid]
            node.last_modified_by = event.agent_id
            node.last_modified_at = event.timestamp

    async def _handle_skill_executed(self, event: StateEvent) -> None:
        """Handle skill execution event."""
        # Track skill execution in metadata
        uid = event.resource_uid
        if uid and uid in self._nodes:
            node = self._nodes[uid]
            skills = node.metadata.setdefault("skills_applied", [])
            skills.append(
                {
                    "skill_id": event.data.get("skill_id"),
                    "agent_id": event.agent_id,
                    "timestamp": event.timestamp.isoformat(),
                    "success": event.data.get("success", False),
                }
            )

    # --- Graph operations ---

    def _add_node(self, node: ResourceNode) -> None:
        """Add a node to the graph."""
        self._nodes[node.uid] = node

        # Update indexes
        if node.kind not in self._by_kind:
            self._by_kind[node.kind] = set()
        self._by_kind[node.kind].add(node.uid)

        if node.namespace:
            if node.namespace not in self._by_namespace:
                self._by_namespace[node.namespace] = set()
            self._by_namespace[node.namespace].add(node.uid)

        if node.name not in self._by_name:
            self._by_name[node.name] = set()
        self._by_name[node.name].add(node.uid)

    def _remove_node(self, uid: str) -> None:
        """Remove a node from the graph."""
        if uid not in self._nodes:
            return

        node = self._nodes[uid]

        # Remove from indexes
        if node.kind in self._by_kind:
            self._by_kind[node.kind].discard(uid)
        if node.namespace and node.namespace in self._by_namespace:
            self._by_namespace[node.namespace].discard(uid)
        if node.name in self._by_name:
            self._by_name[node.name].discard(uid)

        # Remove edges
        if uid in self._edges:
            del self._edges[uid]
        if uid in self._reverse_edges:
            del self._reverse_edges[uid]

        # Remove from other edge lists
        for edges in self._edges.values():
            edges[:] = [e for e in edges if e.target_uid != uid]
        for edges in self._reverse_edges.values():
            edges[:] = [e for e in edges if e.source_uid != uid]

        del self._nodes[uid]

    def _add_edge(self, edge: ResourceEdge) -> None:
        """Add an edge to the graph."""
        if edge.source_uid not in self._edges:
            self._edges[edge.source_uid] = []
        self._edges[edge.source_uid].append(edge)

        if edge.target_uid not in self._reverse_edges:
            self._reverse_edges[edge.target_uid] = []
        self._reverse_edges[edge.target_uid].append(edge)

    # --- Query handlers ---

    async def _query_get_resource(self, query: WorldModelQuery) -> WorldModelResponse:
        """Get a single resource by name/namespace."""
        for _uid, node in self._nodes.items():
            if query.resource_type and node.kind.value != query.resource_type:
                continue
            if query.namespace and node.namespace != query.namespace:
                continue
            if query.name and node.name != query.name:
                continue

            return WorldModelResponse(
                success=True,
                query_type=query.query_type,
                data=self._node_to_dict(node),
            )

        return WorldModelResponse(
            success=False,
            query_type=query.query_type,
            error="Resource not found",
        )

    async def _query_list_resources(self, query: WorldModelQuery) -> WorldModelResponse:
        """List resources matching filters."""
        results = []

        for _uid, node in self._nodes.items():
            if query.resource_type and node.kind.value != query.resource_type:
                continue
            if query.namespace and node.namespace != query.namespace:
                continue

            results.append(self._node_to_dict(node))
            if len(results) >= query.limit:
                break

        return WorldModelResponse(
            success=True,
            query_type=query.query_type,
            data=results,
        )

    async def _query_get_history(self, query: WorldModelQuery) -> WorldModelResponse:
        """Get modification history for a resource."""
        cutoff = self._parse_time_range(query.time_range)
        results = []

        for event in self._history:
            if query.resource_id and event.resource_uid != query.resource_id:
                continue
            if event.timestamp < cutoff:
                continue

            results.append(
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type.value,
                    "timestamp": event.timestamp.isoformat(),
                    "agent_id": event.agent_id,
                    "data": event.data,
                }
            )

            if len(results) >= query.limit:
                break

        return WorldModelResponse(
            success=True,
            query_type=query.query_type,
            data=results,
        )

    async def _query_get_related(self, query: WorldModelQuery) -> WorldModelResponse:
        """Get resources related to a given resource."""
        uid = query.resource_id
        if not uid:
            return WorldModelResponse(
                success=False,
                query_type=query.query_type,
                error="resource_id is required",
            )

        related = []

        # Outgoing edges (resources this one owns/references)
        if uid in self._edges:
            for edge in self._edges[uid]:
                if edge.target_uid in self._nodes:
                    node = self._nodes[edge.target_uid]
                    related.append(
                        {
                            "relationship": edge.relationship,
                            "direction": "outgoing",
                            "resource": self._node_to_dict(node),
                        }
                    )

        # Incoming edges (resources that own/reference this one)
        if uid in self._reverse_edges:
            for edge in self._reverse_edges[uid]:
                if edge.source_uid in self._nodes:
                    node = self._nodes[edge.source_uid]
                    related.append(
                        {
                            "relationship": edge.relationship,
                            "direction": "incoming",
                            "resource": self._node_to_dict(node),
                        }
                    )

        return WorldModelResponse(
            success=True,
            query_type=query.query_type,
            data=related,
        )

    async def _query_get_lineage(self, query: WorldModelQuery) -> WorldModelResponse:
        """Get all ancestors of a resource (what owns it, recursively)."""
        uid = query.resource_id
        if not uid:
            return WorldModelResponse(
                success=False,
                query_type=query.query_type,
                error="resource_id is required",
            )

        ancestors = []
        visited = set()

        def find_ancestors(current_uid: str) -> None:
            if current_uid in visited:
                return
            visited.add(current_uid)

            if current_uid in self._reverse_edges:
                for edge in self._reverse_edges[current_uid]:
                    if edge.relationship == "owns" and edge.source_uid in self._nodes:
                        ancestors.append(self._node_to_dict(self._nodes[edge.source_uid]))
                        find_ancestors(edge.source_uid)

        find_ancestors(uid)

        return WorldModelResponse(
            success=True,
            query_type=query.query_type,
            data=ancestors,
        )

    async def _query_get_affected(self, query: WorldModelQuery) -> WorldModelResponse:
        """Get all descendants that would be affected by changes to a resource."""
        uid = query.resource_id
        if not uid:
            return WorldModelResponse(
                success=False,
                query_type=query.query_type,
                error="resource_id is required",
            )

        affected = []
        visited = set()

        def find_affected(current_uid: str) -> None:
            if current_uid in visited:
                return
            visited.add(current_uid)

            if current_uid in self._edges:
                for edge in self._edges[current_uid]:
                    if edge.target_uid in self._nodes:
                        affected.append(self._node_to_dict(self._nodes[edge.target_uid]))
                        find_affected(edge.target_uid)

        find_affected(uid)

        return WorldModelResponse(
            success=True,
            query_type=query.query_type,
            data=affected,
        )

    async def _query_agent_actions(self, query: WorldModelQuery) -> WorldModelResponse:
        """Get actions performed by a specific agent."""
        agent_id = query.agent_id
        if not agent_id:
            # Return all agent action counts
            summary = {agent: len(actions) for agent, actions in self._agent_actions.items()}
            return WorldModelResponse(
                success=True,
                query_type=query.query_type,
                data=summary,
            )

        if agent_id not in self._agent_actions:
            return WorldModelResponse(
                success=True,
                query_type=query.query_type,
                data=[],
            )

        cutoff = self._parse_time_range(query.time_range)
        results = []

        for event in self._agent_actions[agent_id]:
            if event.timestamp < cutoff:
                continue
            results.append(
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type.value,
                    "resource_uid": event.resource_uid,
                    "timestamp": event.timestamp.isoformat(),
                    "data": event.data,
                }
            )

            if len(results) >= query.limit:
                break

        return WorldModelResponse(
            success=True,
            query_type=query.query_type,
            data=results,
        )

    async def _query_namespace_status(self, query: WorldModelQuery) -> WorldModelResponse:
        """Get status summary for a namespace."""
        namespace = query.namespace
        if not namespace:
            return WorldModelResponse(
                success=False,
                query_type=query.query_type,
                error="namespace is required",
            )

        if namespace not in self._by_namespace:
            return WorldModelResponse(
                success=True,
                query_type=query.query_type,
                data={"namespace": namespace, "resources": []},
            )

        # Count resources by kind and status
        by_kind: dict[str, dict[str, int]] = {}
        for uid in self._by_namespace[namespace]:
            if uid not in self._nodes:
                continue
            node = self._nodes[uid]
            kind = node.kind.value

            if kind not in by_kind:
                by_kind[kind] = {}
            if node.status not in by_kind[kind]:
                by_kind[kind][node.status] = 0
            by_kind[kind][node.status] += 1

        return WorldModelResponse(
            success=True,
            query_type=query.query_type,
            data={
                "namespace": namespace,
                "resource_counts": by_kind,
                "total_resources": len(self._by_namespace[namespace]),
            },
        )

    async def _query_cluster_summary(self, query: WorldModelQuery) -> WorldModelResponse:
        """Get a summary of the entire cluster state."""
        summary = {
            "total_resources": len(self._nodes),
            "total_relationships": sum(len(e) for e in self._edges.values()),
            "resources_by_kind": {kind.value: len(uids) for kind, uids in self._by_kind.items()},
            "resources_by_namespace": {ns: len(uids) for ns, uids in self._by_namespace.items()},
            "events_in_history": len(self._history),
            "active_agents": len(self._agent_actions),
            "stats": self._stats,
        }

        return WorldModelResponse(
            success=True,
            query_type=query.query_type,
            data=summary,
        )

    # --- Helpers ---

    def _node_to_dict(self, node: ResourceNode) -> dict[str, Any]:
        """Convert a ResourceNode to a dictionary."""
        return {
            "uid": node.uid,
            "kind": node.kind.value,
            "name": node.name,
            "namespace": node.namespace,
            "status": node.status,
            "labels": node.labels,
            "created_at": node.created_at.isoformat(),
            "updated_at": node.updated_at.isoformat(),
            "last_modified_by": node.last_modified_by,
            "last_modified_at": (
                node.last_modified_at.isoformat() if node.last_modified_at else None
            ),
            "resource_id": node.resource_id,
        }

    def _parse_time_range(self, time_range: str | None) -> datetime:
        """Parse a time range string into a cutoff datetime."""
        if not time_range:
            return datetime.min.replace(tzinfo=UTC)

        now = datetime.now(UTC)

        if time_range == "last_1h":
            return now - timedelta(hours=1)
        elif time_range == "last_6h":
            return now - timedelta(hours=6)
        elif time_range == "last_24h":
            return now - timedelta(hours=24)
        elif time_range == "last_7d":
            return now - timedelta(days=7)
        else:
            return datetime.min.replace(tzinfo=UTC)

    def get_stats(self) -> dict[str, Any]:
        """Get current statistics."""
        return {
            **self._stats,
            "history_size": len(self._history),
            "agents_tracked": len(self._agent_actions),
        }
