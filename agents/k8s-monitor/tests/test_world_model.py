"""Tests for the WorldModelAgent."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from k8s_monitor.agents.world_model import (
    EventType,
    QueryType,
    ResourceEdge,
    ResourceKind,
    ResourceNode,
    StateEvent,
    WorldModelAgent,
    WorldModelQuery,
)


class TestResourceNode:
    """Tests for ResourceNode dataclass."""

    def test_create_node(self):
        """Test creating a resource node."""
        node = ResourceNode(
            uid="pod-123",
            kind=ResourceKind.POD,
            name="my-pod",
            namespace="default",
            status="Running",
        )

        assert node.uid == "pod-123"
        assert node.kind == ResourceKind.POD
        assert node.name == "my-pod"
        assert node.namespace == "default"
        assert node.status == "Running"

    def test_resource_id_with_namespace(self):
        """Test resource_id generation for namespaced resources."""
        node = ResourceNode(
            uid="pod-123",
            kind=ResourceKind.POD,
            name="my-pod",
            namespace="production",
        )

        assert node.resource_id == "Pod/production/my-pod"

    def test_resource_id_without_namespace(self):
        """Test resource_id generation for cluster-scoped resources."""
        node = ResourceNode(
            uid="node-123",
            kind=ResourceKind.NODE,
            name="worker-1",
            namespace=None,
        )

        assert node.resource_id == "Node/worker-1"

    def test_node_with_labels(self):
        """Test node with labels and annotations."""
        node = ResourceNode(
            uid="pod-123",
            kind=ResourceKind.POD,
            name="my-pod",
            namespace="default",
            labels={"app": "web", "env": "prod"},
            annotations={"deployment.kubernetes.io/revision": "1"},
        )

        assert node.labels["app"] == "web"
        assert "deployment.kubernetes.io/revision" in node.annotations


class TestResourceEdge:
    """Tests for ResourceEdge dataclass."""

    def test_create_edge(self):
        """Test creating a resource edge."""
        edge = ResourceEdge(
            source_uid="deployment-123",
            target_uid="pod-456",
            relationship="owns",
        )

        assert edge.source_uid == "deployment-123"
        assert edge.target_uid == "pod-456"
        assert edge.relationship == "owns"


class TestStateEvent:
    """Tests for StateEvent dataclass."""

    def test_create_event(self):
        """Test creating a state event."""
        event = StateEvent(
            event_id="event-123",
            event_type=EventType.RESOURCE_CREATED,
            resource_uid="pod-456",
            agent_id="sentinel_agent",
            timestamp=datetime.now(UTC),
            data={"kind": "Pod", "name": "my-pod", "namespace": "default"},
        )

        assert event.event_type == EventType.RESOURCE_CREATED
        assert event.resource_uid == "pod-456"
        assert event.agent_id == "sentinel_agent"


class TestWorldModelQuery:
    """Tests for WorldModelQuery model."""

    def test_create_query(self):
        """Test creating a query."""
        query = WorldModelQuery(
            query_type=QueryType.GET_RESOURCE,
            resource_type="Pod",
            namespace="default",
            name="my-pod",
        )

        assert query.query_type == QueryType.GET_RESOURCE
        assert query.resource_type == "Pod"

    def test_query_defaults(self):
        """Test query default values."""
        query = WorldModelQuery(query_type=QueryType.GET_CLUSTER_SUMMARY)

        assert query.limit == 100
        assert query.namespace is None


class TestWorldModelAgent:
    """Tests for WorldModelAgent."""

    @pytest.fixture
    def world_model(self):
        """Create a WorldModelAgent instance."""
        return WorldModelAgent()

    @pytest.mark.asyncio
    async def test_handle_resource_created(self, world_model):
        """Test handling resource creation event."""
        event = StateEvent(
            event_id="event-1",
            event_type=EventType.RESOURCE_CREATED,
            resource_uid="pod-123",
            agent_id=None,
            timestamp=datetime.now(UTC),
            data={
                "uid": "pod-123",
                "kind": "Pod",
                "name": "my-pod",
                "namespace": "default",
                "status": "Running",
            },
        )

        await world_model.handle_event(event)

        assert "pod-123" in world_model._nodes
        assert world_model._nodes["pod-123"].name == "my-pod"
        assert world_model._stats["nodes_count"] == 1

    @pytest.mark.asyncio
    async def test_handle_resource_deleted(self, world_model):
        """Test handling resource deletion event."""
        # First create a resource
        create_event = StateEvent(
            event_id="event-1",
            event_type=EventType.RESOURCE_CREATED,
            resource_uid="pod-123",
            agent_id=None,
            timestamp=datetime.now(UTC),
            data={
                "uid": "pod-123",
                "kind": "Pod",
                "name": "my-pod",
                "namespace": "default",
            },
        )
        await world_model.handle_event(create_event)

        # Then delete it
        delete_event = StateEvent(
            event_id="event-2",
            event_type=EventType.RESOURCE_DELETED,
            resource_uid="pod-123",
            agent_id=None,
            timestamp=datetime.now(UTC),
            data={},
        )
        await world_model.handle_event(delete_event)

        assert "pod-123" not in world_model._nodes

    @pytest.mark.asyncio
    async def test_handle_status_changed(self, world_model):
        """Test handling status change event."""
        # Create resource
        create_event = StateEvent(
            event_id="event-1",
            event_type=EventType.RESOURCE_CREATED,
            resource_uid="pod-123",
            agent_id=None,
            timestamp=datetime.now(UTC),
            data={
                "uid": "pod-123",
                "kind": "Pod",
                "name": "my-pod",
                "namespace": "default",
                "status": "Pending",
            },
        )
        await world_model.handle_event(create_event)

        # Update status
        status_event = StateEvent(
            event_id="event-2",
            event_type=EventType.RESOURCE_STATUS_CHANGED,
            resource_uid="pod-123",
            agent_id=None,
            timestamp=datetime.now(UTC),
            data={"new_status": "Running"},
        )
        await world_model.handle_event(status_event)

        assert world_model._nodes["pod-123"].status == "Running"

    @pytest.mark.asyncio
    async def test_handle_agent_action(self, world_model):
        """Test tracking agent actions."""
        # Create resource
        create_event = StateEvent(
            event_id="event-1",
            event_type=EventType.RESOURCE_CREATED,
            resource_uid="pod-123",
            agent_id=None,
            timestamp=datetime.now(UTC),
            data={
                "uid": "pod-123",
                "kind": "Pod",
                "name": "my-pod",
                "namespace": "default",
            },
        )
        await world_model.handle_event(create_event)

        # Agent modifies resource
        action_event = StateEvent(
            event_id="event-2",
            event_type=EventType.AGENT_ACTION,
            resource_uid="pod-123",
            agent_id="healer_agent",
            timestamp=datetime.now(UTC),
            data={"action": "restart"},
        )
        await world_model.handle_event(action_event)

        node = world_model._nodes["pod-123"]
        assert node.last_modified_by == "healer_agent"
        assert "healer_agent" in world_model._agent_actions

    @pytest.mark.asyncio
    async def test_query_get_resource(self, world_model):
        """Test querying for a specific resource."""
        # Create resource
        event = StateEvent(
            event_id="event-1",
            event_type=EventType.RESOURCE_CREATED,
            resource_uid="pod-123",
            agent_id=None,
            timestamp=datetime.now(UTC),
            data={
                "uid": "pod-123",
                "kind": "Pod",
                "name": "api-server",
                "namespace": "production",
                "status": "Running",
            },
        )
        await world_model.handle_event(event)

        # Query
        query = WorldModelQuery(
            query_type=QueryType.GET_RESOURCE,
            resource_type="Pod",
            namespace="production",
            name="api-server",
        )
        response = await world_model.query(query)

        assert response.success
        assert response.data["name"] == "api-server"
        assert response.data["status"] == "Running"

    @pytest.mark.asyncio
    async def test_query_list_resources(self, world_model):
        """Test listing resources with filters."""
        # Create multiple resources
        for i in range(5):
            event = StateEvent(
                event_id=f"event-{i}",
                event_type=EventType.RESOURCE_CREATED,
                resource_uid=f"pod-{i}",
                agent_id=None,
                timestamp=datetime.now(UTC),
                data={
                    "uid": f"pod-{i}",
                    "kind": "Pod",
                    "name": f"pod-{i}",
                    "namespace": "default",
                },
            )
            await world_model.handle_event(event)

        # Query all pods in default namespace
        query = WorldModelQuery(
            query_type=QueryType.LIST_RESOURCES,
            resource_type="Pod",
            namespace="default",
        )
        response = await world_model.query(query)

        assert response.success
        assert len(response.data) == 5

    @pytest.mark.asyncio
    async def test_query_with_limit(self, world_model):
        """Test query respects limit."""
        # Create multiple resources
        for i in range(10):
            event = StateEvent(
                event_id=f"event-{i}",
                event_type=EventType.RESOURCE_CREATED,
                resource_uid=f"pod-{i}",
                agent_id=None,
                timestamp=datetime.now(UTC),
                data={
                    "uid": f"pod-{i}",
                    "kind": "Pod",
                    "name": f"pod-{i}",
                    "namespace": "default",
                },
            )
            await world_model.handle_event(event)

        # Query with limit
        query = WorldModelQuery(
            query_type=QueryType.LIST_RESOURCES,
            namespace="default",
            limit=3,
        )
        response = await world_model.query(query)

        assert response.success
        assert len(response.data) == 3

    @pytest.mark.asyncio
    async def test_query_cluster_summary(self, world_model):
        """Test getting cluster summary."""
        # Create some resources
        for kind, count in [("Pod", 3), ("Deployment", 2), ("Service", 1)]:
            for i in range(count):
                event = StateEvent(
                    event_id=str(uuid.uuid4()),
                    event_type=EventType.RESOURCE_CREATED,
                    resource_uid=f"{kind.lower()}-{i}",
                    agent_id=None,
                    timestamp=datetime.now(UTC),
                    data={
                        "uid": f"{kind.lower()}-{i}",
                        "kind": kind,
                        "name": f"{kind.lower()}-{i}",
                        "namespace": "default",
                    },
                )
                await world_model.handle_event(event)

        query = WorldModelQuery(query_type=QueryType.GET_CLUSTER_SUMMARY)
        response = await world_model.query(query)

        assert response.success
        assert response.data["total_resources"] == 6
        assert response.data["resources_by_kind"]["Pod"] == 3
        assert response.data["resources_by_kind"]["Deployment"] == 2

    @pytest.mark.asyncio
    async def test_query_namespace_status(self, world_model):
        """Test getting namespace status summary."""
        # Create resources with different statuses
        statuses = ["Running", "Running", "Pending", "Failed"]
        for i, status in enumerate(statuses):
            event = StateEvent(
                event_id=f"event-{i}",
                event_type=EventType.RESOURCE_CREATED,
                resource_uid=f"pod-{i}",
                agent_id=None,
                timestamp=datetime.now(UTC),
                data={
                    "uid": f"pod-{i}",
                    "kind": "Pod",
                    "name": f"pod-{i}",
                    "namespace": "production",
                    "status": status,
                },
            )
            await world_model.handle_event(event)

        query = WorldModelQuery(
            query_type=QueryType.GET_NAMESPACE_STATUS,
            namespace="production",
        )
        response = await world_model.query(query)

        assert response.success
        assert response.data["total_resources"] == 4
        assert response.data["resource_counts"]["Pod"]["Running"] == 2
        assert response.data["resource_counts"]["Pod"]["Pending"] == 1
        assert response.data["resource_counts"]["Pod"]["Failed"] == 1

    @pytest.mark.asyncio
    async def test_query_get_history(self, world_model):
        """Test getting event history."""
        # Create some events
        for i in range(5):
            event = StateEvent(
                event_id=f"event-{i}",
                event_type=EventType.RESOURCE_CREATED,
                resource_uid="pod-123",
                agent_id=f"agent-{i}",
                timestamp=datetime.now(UTC),
                data={"iteration": i},
            )
            await world_model.handle_event(event)

        query = WorldModelQuery(
            query_type=QueryType.GET_HISTORY,
            resource_id="pod-123",
        )
        response = await world_model.query(query)

        assert response.success
        assert len(response.data) == 5

    @pytest.mark.asyncio
    async def test_query_agent_actions(self, world_model):
        """Test getting agent action history."""
        # Create events from specific agent
        for i in range(3):
            event = StateEvent(
                event_id=f"event-{i}",
                event_type=EventType.AGENT_ACTION,
                resource_uid=f"pod-{i}",
                agent_id="healer_agent",
                timestamp=datetime.now(UTC),
                data={"action": f"action-{i}"},
            )
            await world_model.handle_event(event)

        query = WorldModelQuery(
            query_type=QueryType.GET_AGENT_ACTIONS,
            agent_id="healer_agent",
        )
        response = await world_model.query(query)

        assert response.success
        assert len(response.data) == 3

    @pytest.mark.asyncio
    async def test_relationships_owns(self, world_model):
        """Test owner relationship edges."""
        # Create deployment
        deploy_event = StateEvent(
            event_id="event-1",
            event_type=EventType.RESOURCE_CREATED,
            resource_uid="deploy-123",
            agent_id=None,
            timestamp=datetime.now(UTC),
            data={
                "uid": "deploy-123",
                "kind": "Deployment",
                "name": "api-server",
                "namespace": "default",
            },
        )
        await world_model.handle_event(deploy_event)

        # Create pod owned by deployment
        pod_event = StateEvent(
            event_id="event-2",
            event_type=EventType.RESOURCE_CREATED,
            resource_uid="pod-456",
            agent_id=None,
            timestamp=datetime.now(UTC),
            data={
                "uid": "pod-456",
                "kind": "Pod",
                "name": "api-server-abc123",
                "namespace": "default",
                "owner_references": [{"uid": "deploy-123"}],
            },
        )
        await world_model.handle_event(pod_event)

        # Query related resources
        query = WorldModelQuery(
            query_type=QueryType.GET_RELATED,
            resource_id="deploy-123",
        )
        response = await world_model.query(query)

        assert response.success
        assert len(response.data) == 1
        assert response.data[0]["relationship"] == "owns"
        assert response.data[0]["resource"]["name"] == "api-server-abc123"

    @pytest.mark.asyncio
    async def test_query_get_lineage(self, world_model):
        """Test getting resource lineage (ancestors)."""
        # Create hierarchy: Deployment -> ReplicaSet -> Pod
        await world_model.handle_event(
            StateEvent(
                event_id="event-1",
                event_type=EventType.RESOURCE_CREATED,
                resource_uid="deploy-1",
                agent_id=None,
                timestamp=datetime.now(UTC),
                data={
                    "uid": "deploy-1",
                    "kind": "Deployment",
                    "name": "api",
                    "namespace": "default",
                },
            )
        )

        await world_model.handle_event(
            StateEvent(
                event_id="event-2",
                event_type=EventType.RESOURCE_CREATED,
                resource_uid="rs-1",
                agent_id=None,
                timestamp=datetime.now(UTC),
                data={
                    "uid": "rs-1",
                    "kind": "ReplicaSet",
                    "name": "api-abc",
                    "namespace": "default",
                    "owner_references": [{"uid": "deploy-1"}],
                },
            )
        )

        await world_model.handle_event(
            StateEvent(
                event_id="event-3",
                event_type=EventType.RESOURCE_CREATED,
                resource_uid="pod-1",
                agent_id=None,
                timestamp=datetime.now(UTC),
                data={
                    "uid": "pod-1",
                    "kind": "Pod",
                    "name": "api-abc-xyz",
                    "namespace": "default",
                    "owner_references": [{"uid": "rs-1"}],
                },
            )
        )

        # Query lineage for the pod
        query = WorldModelQuery(
            query_type=QueryType.GET_LINEAGE,
            resource_id="pod-1",
        )
        response = await world_model.query(query)

        assert response.success
        # Should have both ReplicaSet and Deployment in lineage
        assert len(response.data) == 2
        names = [r["name"] for r in response.data]
        assert "api-abc" in names
        assert "api" in names

    @pytest.mark.asyncio
    async def test_query_get_affected(self, world_model):
        """Test getting affected resources (descendants)."""
        # Create hierarchy
        await world_model.handle_event(
            StateEvent(
                event_id="event-1",
                event_type=EventType.RESOURCE_CREATED,
                resource_uid="deploy-1",
                agent_id=None,
                timestamp=datetime.now(UTC),
                data={
                    "uid": "deploy-1",
                    "kind": "Deployment",
                    "name": "api",
                    "namespace": "default",
                },
            )
        )

        for i in range(3):
            await world_model.handle_event(
                StateEvent(
                    event_id=f"event-pod-{i}",
                    event_type=EventType.RESOURCE_CREATED,
                    resource_uid=f"pod-{i}",
                    agent_id=None,
                    timestamp=datetime.now(UTC),
                    data={
                        "uid": f"pod-{i}",
                        "kind": "Pod",
                        "name": f"api-{i}",
                        "namespace": "default",
                        "owner_references": [{"uid": "deploy-1"}],
                    },
                )
            )

        # Query what would be affected by deployment changes
        query = WorldModelQuery(
            query_type=QueryType.GET_AFFECTED,
            resource_id="deploy-1",
        )
        response = await world_model.query(query)

        assert response.success
        assert len(response.data) == 3

    @pytest.mark.asyncio
    async def test_get_stats(self, world_model):
        """Test getting agent statistics."""
        # Process some events
        for i in range(3):
            await world_model.handle_event(
                StateEvent(
                    event_id=f"event-{i}",
                    event_type=EventType.RESOURCE_CREATED,
                    resource_uid=f"pod-{i}",
                    agent_id=None,
                    timestamp=datetime.now(UTC),
                    data={
                        "uid": f"pod-{i}",
                        "kind": "Pod",
                        "name": f"pod-{i}",
                        "namespace": "default",
                    },
                )
            )

        # Query to increment query count
        await world_model.query(WorldModelQuery(query_type=QueryType.GET_CLUSTER_SUMMARY))

        stats = world_model.get_stats()

        assert stats["events_processed"] == 3
        assert stats["queries_answered"] == 1
        assert stats["nodes_count"] == 3

    @pytest.mark.asyncio
    async def test_time_range_parsing(self, world_model):
        """Test time range parsing for history queries."""
        # Test different time ranges
        assert world_model._parse_time_range("last_1h") > datetime.now(UTC) - timedelta(hours=2)
        assert world_model._parse_time_range("last_24h") > datetime.now(UTC) - timedelta(hours=25)
        assert world_model._parse_time_range("last_7d") > datetime.now(UTC) - timedelta(days=8)
        assert world_model._parse_time_range(None).year == 1  # datetime.min

    @pytest.mark.asyncio
    async def test_query_missing_resource_id(self, world_model):
        """Test handling query with missing required resource_id."""
        # GET_LINEAGE requires resource_id
        query = WorldModelQuery(
            query_type=QueryType.GET_LINEAGE,
            resource_id=None,  # Missing required field
        )

        response = await world_model.query(query)

        assert not response.success
        assert "resource_id is required" in response.error


class TestResourceKind:
    """Tests for ResourceKind enum."""

    def test_all_kinds_exist(self):
        """Test all expected resource kinds exist."""
        assert ResourceKind.POD.value == "Pod"
        assert ResourceKind.DEPLOYMENT.value == "Deployment"
        assert ResourceKind.NODE.value == "Node"
        assert ResourceKind.SERVICE.value == "Service"
        assert ResourceKind.PVC.value == "PersistentVolumeClaim"


class TestEventType:
    """Tests for EventType enum."""

    def test_kubernetes_events(self):
        """Test Kubernetes event types."""
        assert EventType.RESOURCE_CREATED.value == "resource_created"
        assert EventType.RESOURCE_UPDATED.value == "resource_updated"
        assert EventType.RESOURCE_DELETED.value == "resource_deleted"

    def test_agent_events(self):
        """Test agent event types."""
        assert EventType.AGENT_ACTION.value == "agent_action"
        assert EventType.SKILL_EXECUTED.value == "skill_executed"


class TestQueryType:
    """Tests for QueryType enum."""

    def test_query_types(self):
        """Test all query types."""
        assert QueryType.GET_RESOURCE.value == "get_resource"
        assert QueryType.LIST_RESOURCES.value == "list_resources"
        assert QueryType.GET_HISTORY.value == "get_history"
        assert QueryType.GET_LINEAGE.value == "get_lineage"
        assert QueryType.GET_AFFECTED.value == "get_affected"
        assert QueryType.GET_CLUSTER_SUMMARY.value == "get_cluster_summary"
