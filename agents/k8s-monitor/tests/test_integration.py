"""
Integration tests for the k8s-monitor agent system.

These tests validate end-to-end workflows including:
1. Hierarchical agent flows (Coordinator → Triage → Diagnostician)
2. Context passing between agents (HandoffContext)
3. WorldModel integration with event handling
4. Multi-agent coordination patterns

These tests use mocks for external services (K8s API, Discord, MCP)
but test real agent interactions and data flow.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from k8s_monitor.agents.context import (
    HandoffContext,
    RequestType,
    ResourceType,
    Severity,
    Urgency,
)
from k8s_monitor.agents.coordinator import K8sCoordinatorAgent
from k8s_monitor.agents.diagnosis import (
    NetworkDiagnostician,
    NodeDiagnostician,
    PodDiagnostician,
    StorageDiagnostician,
)
from k8s_monitor.agents.triage import TriageAgent
from k8s_monitor.agents.world_model import (
    EventType,
    QueryType,
    StateEvent,
    WorldModelAgent,
    WorldModelQuery,
)


class TestHierarchicalAgentFlow:
    """
    Tests for hierarchical agent coordination.

    Validates:
    - Coordinator routes to correct sub-agents
    - Context flows properly between agents
    - Diagnosticians selected based on resource type
    """

    @pytest.fixture
    def coordinator(self):
        """Create a coordinator with all sub-agents."""
        return K8sCoordinatorAgent()

    @pytest.fixture
    def triage(self):
        """Create a triage agent."""
        return TriageAgent()

    def test_coordinator_initializes_all_sub_agents(self, coordinator):
        """Test coordinator initializes all required sub-agents."""
        assert coordinator._triage is not None
        assert coordinator._scout is not None
        assert coordinator._discord is not None
        assert coordinator._remediator is not None
        assert coordinator._memory is not None
        assert coordinator._pod_diag is not None
        assert coordinator._node_diag is not None
        assert coordinator._network_diag is not None
        assert coordinator._storage_diag is not None

    def test_coordinator_routes_pod_to_pod_diagnostician(self, coordinator):
        """Test coordinator routes pod issues to PodDiagnostician."""
        diag = coordinator._select_diagnostician(ResourceType.POD)
        assert isinstance(diag, PodDiagnostician)

    def test_coordinator_routes_deployment_to_pod_diagnostician(self, coordinator):
        """Test coordinator routes deployment issues to PodDiagnostician."""
        diag = coordinator._select_diagnostician(ResourceType.DEPLOYMENT)
        assert isinstance(diag, PodDiagnostician)

    def test_coordinator_routes_node_to_node_diagnostician(self, coordinator):
        """Test coordinator routes node issues to NodeDiagnostician."""
        diag = coordinator._select_diagnostician(ResourceType.NODE)
        assert isinstance(diag, NodeDiagnostician)

    def test_coordinator_routes_service_to_network_diagnostician(self, coordinator):
        """Test coordinator routes service issues to NetworkDiagnostician."""
        diag = coordinator._select_diagnostician(ResourceType.SERVICE)
        assert isinstance(diag, NetworkDiagnostician)

    def test_coordinator_routes_ingress_to_network_diagnostician(self, coordinator):
        """Test coordinator routes ingress issues to NetworkDiagnostician."""
        diag = coordinator._select_diagnostician(ResourceType.INGRESS)
        assert isinstance(diag, NetworkDiagnostician)

    def test_coordinator_routes_pvc_to_storage_diagnostician(self, coordinator):
        """Test coordinator routes PVC issues to StorageDiagnostician."""
        diag = coordinator._select_diagnostician(ResourceType.PVC)
        assert isinstance(diag, StorageDiagnostician)

    def test_coordinator_returns_none_for_unknown_type(self, coordinator):
        """Test coordinator returns None when no diagnostician matches."""
        diag = coordinator._select_diagnostician(None)
        assert diag is None


class TestContextPassingFlow:
    """
    Tests for context passing between agents.

    Validates HandoffContext flows correctly through the agent hierarchy.
    """

    def test_context_flows_from_triage_with_findings(self):
        """Test context collects findings during triage."""
        triage = TriageAgent()

        # Create initial context
        context = HandoffContext.for_issue(
            prompt="Pod my-app is CrashLoopBackOff",
            resource_type=ResourceType.POD,
            resource_name="my-app",
            namespace="production",
        )

        # Simulate triage processing result
        triage_result = """
RESOURCE_TYPE: pod
SEVERITY: critical
URGENCY: immediate
SUMMARY: Pod my-app is in CrashLoopBackOff, has restarted 15 times
RECOMMENDATION: Route to pod diagnostician
"""
        triage._process_result(context, triage_result)

        # Verify context was enriched
        assert context.severity == Severity.CRITICAL
        assert context.urgency == Urgency.IMMEDIATE
        assert context.resource_type == ResourceType.POD
        assert len(context.findings) > 0
        assert "triage_agent_assessment" in context.evidence

    def test_context_accumulates_multiple_findings(self):
        """Test context accumulates findings from multiple agents."""
        context = HandoffContext.for_issue(
            prompt="Node not ready",
            resource_type=ResourceType.NODE,
        )

        # Add findings from different agents
        context.add_finding(
            agent="triage_agent",
            description="Initial assessment: node issue",
            severity=Severity.WARNING,
        )

        context.add_finding(
            agent="node_diagnostician",
            description="Memory pressure detected",
            evidence={"memory_used": "95%"},
            severity=Severity.CRITICAL,
        )

        context.add_finding(
            agent="node_diagnostician",
            description="Disk pressure detected",
            evidence={"disk_used": "92%"},
            severity=Severity.WARNING,
        )

        assert len(context.findings) == 3
        assert context.findings[0].agent == "triage_agent"
        assert context.findings[1].agent == "node_diagnostician"
        assert context.findings[2].agent == "node_diagnostician"

    def test_context_tracks_request_lineage(self):
        """Test context maintains request tracking info."""
        context = HandoffContext.for_issue("Test issue")

        # Verify request tracking
        assert context.request_id is not None
        assert len(context.request_id) > 0
        assert context.created_at is not None
        assert context.request_type == RequestType.ISSUE_INVESTIGATION

    def test_context_serialization_for_handoff(self):
        """Test context can be serialized for agent handoff."""
        context = HandoffContext.for_issue(
            prompt="Test serialization",
            resource_type=ResourceType.DEPLOYMENT,
            resource_name="api-server",
            namespace="production",
        )

        context.severity = Severity.WARNING
        context.add_finding(
            agent="test",
            description="Test finding",
            severity=Severity.WARNING,
        )
        context.add_evidence("test_key", "test_value")

        # Serialize
        data = context.to_dict()

        # Verify serialization preserves key fields
        assert data["request_id"] == context.request_id
        assert data["request_type"] == "issue_investigation"
        assert data["findings_count"] == 1
        assert data["severity"] == "warning"
        # Note: evidence is stored on context but not serialized in to_dict()
        # The raw context retains evidence for agent use
        assert context.evidence["test_key"] == "test_value"


class TestWorldModelIntegration:
    """
    Tests for WorldModel integration with the agent system.

    Validates WorldModel can:
    - Track resources created/deleted by agents
    - Answer queries about system state
    - Track agent activities
    """

    @pytest.fixture
    def world_model(self):
        """Create a WorldModel instance."""
        return WorldModelAgent()

    @pytest.mark.asyncio
    async def test_world_model_tracks_agent_modifications(self, world_model):
        """Test WorldModel tracks which agent modified a resource."""
        # Create a resource
        create_event = StateEvent(
            event_id="event-1",
            event_type=EventType.RESOURCE_CREATED,
            resource_uid="pod-123",
            agent_id=None,
            timestamp=datetime.now(UTC),
            data={
                "uid": "pod-123",
                "kind": "Pod",
                "name": "my-app",
                "namespace": "default",
            },
        )
        await world_model.handle_event(create_event)

        # Simulate agent action on the resource
        action_event = StateEvent(
            event_id="event-2",
            event_type=EventType.AGENT_ACTION,
            resource_uid="pod-123",
            agent_id="cluster_remediator",
            timestamp=datetime.now(UTC),
            data={"action": "restart"},
        )
        await world_model.handle_event(action_event)

        # Query the resource
        query = WorldModelQuery(
            query_type=QueryType.GET_RESOURCE,
            resource_type="Pod",
            namespace="default",
            name="my-app",
        )
        response = await world_model.query(query)

        assert response.success
        assert response.data["last_modified_by"] == "cluster_remediator"

    @pytest.mark.asyncio
    async def test_world_model_tracks_skill_executions(self, world_model):
        """Test WorldModel tracks skill executions on resources."""
        # Create resource
        await world_model.handle_event(
            StateEvent(
                event_id="event-1",
                event_type=EventType.RESOURCE_CREATED,
                resource_uid="pod-456",
                agent_id=None,
                timestamp=datetime.now(UTC),
                data={
                    "uid": "pod-456",
                    "kind": "Pod",
                    "name": "crashloop-pod",
                    "namespace": "default",
                },
            )
        )

        # Execute skill
        await world_model.handle_event(
            StateEvent(
                event_id="event-2",
                event_type=EventType.SKILL_EXECUTED,
                resource_uid="pod-456",
                agent_id="healer_agent",
                timestamp=datetime.now(UTC),
                data={
                    "skill_id": "k8s-restart-crashloop",
                    "success": True,
                },
            )
        )

        # Check skills were tracked
        node = world_model._nodes["pod-456"]
        assert "skills_applied" in node.metadata
        assert len(node.metadata["skills_applied"]) == 1
        assert node.metadata["skills_applied"][0]["skill_id"] == "k8s-restart-crashloop"

    @pytest.mark.asyncio
    async def test_world_model_answers_namespace_queries(self, world_model):
        """Test WorldModel can answer queries about namespace health."""
        # Create pods in different states
        states = [
            ("pod-1", "Running"),
            ("pod-2", "Running"),
            ("pod-3", "CrashLoopBackOff"),
            ("pod-4", "Pending"),
        ]

        for pod_name, status in states:
            await world_model.handle_event(
                StateEvent(
                    event_id=str(uuid.uuid4()),
                    event_type=EventType.RESOURCE_CREATED,
                    resource_uid=pod_name,
                    agent_id=None,
                    timestamp=datetime.now(UTC),
                    data={
                        "uid": pod_name,
                        "kind": "Pod",
                        "name": pod_name,
                        "namespace": "app-namespace",
                        "status": status,
                    },
                )
            )

        # Query namespace status
        response = await world_model.query(
            WorldModelQuery(
                query_type=QueryType.GET_NAMESPACE_STATUS,
                namespace="app-namespace",
            )
        )

        assert response.success
        assert response.data["total_resources"] == 4
        assert response.data["resource_counts"]["Pod"]["Running"] == 2
        assert response.data["resource_counts"]["Pod"]["CrashLoopBackOff"] == 1

    @pytest.mark.asyncio
    async def test_world_model_provides_cluster_overview(self, world_model):
        """Test WorldModel provides cluster-wide overview."""
        # Create various resources
        resources = [
            ("deploy-1", "Deployment", "default"),
            ("deploy-2", "Deployment", "production"),
            ("pod-1", "Pod", "default"),
            ("pod-2", "Pod", "default"),
            ("svc-1", "Service", "production"),
            ("node-1", "Node", None),
        ]

        for uid, kind, namespace in resources:
            await world_model.handle_event(
                StateEvent(
                    event_id=str(uuid.uuid4()),
                    event_type=EventType.RESOURCE_CREATED,
                    resource_uid=uid,
                    agent_id=None,
                    timestamp=datetime.now(UTC),
                    data={
                        "uid": uid,
                        "kind": kind,
                        "name": uid,
                        "namespace": namespace,
                    },
                )
            )

        # Query cluster summary
        response = await world_model.query(
            WorldModelQuery(
                query_type=QueryType.GET_CLUSTER_SUMMARY,
            )
        )

        assert response.success
        assert response.data["total_resources"] == 6
        assert response.data["resources_by_kind"]["Deployment"] == 2
        assert response.data["resources_by_kind"]["Pod"] == 2
        assert response.data["resources_by_kind"]["Service"] == 1
        assert response.data["resources_by_kind"]["Node"] == 1


class TestDiagnosticianCapabilities:
    """
    Tests for diagnostician agent capabilities.

    Validates each diagnostician:
    - Handles the correct resource types
    - Provides diagnostic steps
    """

    def test_pod_diagnostician_handles_correct_types(self):
        """Test PodDiagnostician handles pod and deployment types."""
        diag = PodDiagnostician()

        assert diag.can_handle(ResourceType.POD)
        assert diag.can_handle(ResourceType.DEPLOYMENT)
        assert not diag.can_handle(ResourceType.NODE)
        assert not diag.can_handle(ResourceType.SERVICE)

    def test_node_diagnostician_handles_correct_types(self):
        """Test NodeDiagnostician handles node type only."""
        diag = NodeDiagnostician()

        assert diag.can_handle(ResourceType.NODE)
        assert not diag.can_handle(ResourceType.POD)
        assert not diag.can_handle(ResourceType.SERVICE)

    def test_network_diagnostician_handles_correct_types(self):
        """Test NetworkDiagnostician handles network resource types."""
        diag = NetworkDiagnostician()

        assert diag.can_handle(ResourceType.SERVICE)
        assert diag.can_handle(ResourceType.INGRESS)
        assert diag.can_handle(ResourceType.NETWORK_POLICY)
        assert not diag.can_handle(ResourceType.POD)
        assert not diag.can_handle(ResourceType.NODE)

    def test_storage_diagnostician_handles_correct_types(self):
        """Test StorageDiagnostician handles storage type."""
        diag = StorageDiagnostician()

        assert diag.can_handle(ResourceType.PVC)
        assert not diag.can_handle(ResourceType.POD)
        assert not diag.can_handle(ResourceType.NODE)

    def test_diagnosticians_provide_diagnostic_steps(self):
        """Test all diagnosticians provide diagnostic steps."""
        diagnosticians = [
            PodDiagnostician(),
            NodeDiagnostician(),
            NetworkDiagnostician(),
            StorageDiagnostician(),
        ]

        for diag in diagnosticians:
            steps = diag.get_diagnostic_steps()
            assert isinstance(steps, list)
            assert len(steps) > 0
            assert all(isinstance(s, str) for s in steps)


class TestTriageExtraction:
    """
    Tests for triage agent field extraction.

    Validates triage correctly parses LLM responses.
    """

    @pytest.fixture
    def triage(self):
        return TriageAgent()

    def test_extract_all_fields(self, triage):
        """Test extraction of all fields from structured response."""
        result = """
RESOURCE_TYPE: pod
SEVERITY: critical
URGENCY: immediate
SUMMARY: Pod is crashing repeatedly with OOM errors
RECOMMENDATION: Route to pod diagnostician
"""

        assert triage._extract_resource_type(result) == ResourceType.POD
        assert triage._extract_severity(result) == Severity.CRITICAL
        assert triage._extract_urgency(result) == Urgency.IMMEDIATE

    def test_extract_network_type(self, triage):
        """Test extraction maps 'network' to NETWORK_POLICY."""
        result = "RESOURCE_TYPE: network\nSEVERITY: warning"
        assert triage._extract_resource_type(result) == ResourceType.NETWORK_POLICY

    def test_extract_storage_type(self, triage):
        """Test extraction maps 'storage' to PVC."""
        result = "RESOURCE_TYPE: storage\nSEVERITY: warning"
        assert triage._extract_resource_type(result) == ResourceType.PVC

    def test_extract_urgency_aliases(self, triage):
        """Test extraction handles urgency aliases."""
        assert triage._extract_urgency("URGENCY: high") == Urgency.IMMEDIATE
        assert triage._extract_urgency("URGENCY: normal") == Urgency.SOON
        assert triage._extract_urgency("URGENCY: low") == Urgency.SCHEDULED

    def test_handle_malformed_response(self, triage):
        """Test extraction handles malformed responses gracefully."""
        result = "This is just some random text without structure"

        assert triage._extract_resource_type(result) is None
        assert triage._extract_severity(result) is None
        assert triage._extract_urgency(result) is None


class TestMultiAgentCoordination:
    """
    Tests for multi-agent coordination patterns.

    Validates agents can work together through swarm patterns.
    """

    @pytest.fixture
    def coordinator(self):
        # Coordinator uses lazy initialization so no external calls happen here
        return K8sCoordinatorAgent()

    def test_coordinator_has_all_agents(self, coordinator):
        """Test coordinator initializes with all necessary sub-agents."""
        # Verify coordinator has the necessary components (lazy-initialized)
        assert coordinator._triage is not None
        assert coordinator._pod_diag is not None
        assert coordinator._node_diag is not None
        assert coordinator._network_diag is not None
        assert coordinator._storage_diag is not None
        assert coordinator._remediator is not None
        assert coordinator._scout is not None
        assert coordinator._discord is not None
        assert coordinator._memory is not None

    def test_coordinator_diagnose_routes_correctly(self, coordinator):
        """Test coordinator.diagnose routes to correct diagnostician."""
        # Test with pod resource type
        context = HandoffContext.for_issue(
            prompt="Pod is failing",
            resource_type=ResourceType.POD,
        )

        # Mock the diagnostician's diagnose method
        with patch.object(coordinator._pod_diag, "diagnose") as mock_diagnose:
            mock_diagnose.return_value = context
            result = coordinator.diagnose(context)

            mock_diagnose.assert_called_once_with(context)
            assert result == context

    def test_coordinator_handles_unknown_resource_type(self, coordinator):
        """Test coordinator handles unknown resource type gracefully."""
        context = HandoffContext.for_issue(
            prompt="Unknown issue",
            resource_type=None,
        )

        result = coordinator.diagnose(context)

        # Should add a finding about no diagnostician
        assert len(result.findings) == 1
        assert "No specific diagnostician" in result.findings[0].description


class TestEndToEndScenarios:
    """
    End-to-end scenario tests.

    Tests complete workflows without external dependencies.
    """

    @pytest.mark.asyncio
    async def test_pod_crashloop_full_flow(self):
        """Test full flow for pod crashloop detection and triage."""
        # 1. Create context for crashloop issue
        context = HandoffContext.for_issue(
            prompt="Pod my-app-xyz is in CrashLoopBackOff, 15 restarts",
            resource_type=ResourceType.POD,
            resource_name="my-app-xyz",
            namespace="production",
        )

        # 2. Simulate triage assessment
        triage = TriageAgent()
        triage_result = """
RESOURCE_TYPE: pod
SEVERITY: critical
URGENCY: immediate
SUMMARY: Pod my-app-xyz is CrashLoopBackOff with 15 restarts, likely OOM or application error
RECOMMENDATION: Route to pod diagnostician for detailed analysis
"""
        triage._process_result(context, triage_result)

        # 3. Verify triage enriched context correctly
        assert context.severity == Severity.CRITICAL
        assert context.urgency == Urgency.IMMEDIATE
        assert context.resource_type == ResourceType.POD
        assert len(context.findings) == 1

        # 4. Verify correct diagnostician would be selected
        coordinator = K8sCoordinatorAgent()
        diag = coordinator._select_diagnostician(context.resource_type)
        assert isinstance(diag, PodDiagnostician)

    @pytest.mark.asyncio
    async def test_node_notready_full_flow(self):
        """Test full flow for node not ready detection."""
        # 1. Create context for node issue
        context = HandoffContext.for_issue(
            prompt="Node worker-2 is NotReady with MemoryPressure",
            resource_type=ResourceType.NODE,
            resource_name="worker-2",
        )

        # 2. Simulate triage
        triage = TriageAgent()
        triage_result = """
RESOURCE_TYPE: node
SEVERITY: critical
URGENCY: immediate
SUMMARY: Node worker-2 is NotReady due to MemoryPressure condition
RECOMMENDATION: Route to node diagnostician
"""
        triage._process_result(context, triage_result)

        # 3. Verify triage results
        assert context.severity == Severity.CRITICAL
        assert context.resource_type == ResourceType.NODE

        # 4. Verify node diagnostician selected
        coordinator = K8sCoordinatorAgent()
        diag = coordinator._select_diagnostician(context.resource_type)
        assert isinstance(diag, NodeDiagnostician)

    @pytest.mark.asyncio
    async def test_context_summary_after_full_triage(self):
        """Test context summary is informative after triage."""
        context = HandoffContext.for_issue(
            prompt="Service api-gateway has no endpoints",
            resource_type=ResourceType.SERVICE,
            resource_name="api-gateway",
            namespace="production",
        )

        triage = TriageAgent()
        triage_result = """
RESOURCE_TYPE: network
SEVERITY: warning
URGENCY: soon
SUMMARY: Service api-gateway has 0 endpoints, possible selector mismatch
RECOMMENDATION: Route to network diagnostician
"""
        triage._process_result(context, triage_result)

        # Get summary
        summary = context.get_summary()

        # Verify summary contains key information
        assert "issue_investigation" in summary.lower()
        assert "service" in summary.lower() or "network" in summary.lower()
        assert "warning" in summary.lower()
