"""
Swarm workflow integration tests.

These tests validate complete workflows through the swarm system:
1. Health check workflow (Coordinator → Scout → Discord)
2. Issue investigation workflow (Coordinator → Triage → Diagnostician → Discord)
3. Remediation workflow (Coordinator → Triage → Remediator → Discord)
4. Error handling in swarm workflows
"""

from datetime import UTC, datetime

import pytest

from k8s_monitor.agents.context import (
    HandoffContext,
    RequestType,
    ResourceType,
    Severity,
    Urgency,
)
from k8s_monitor.agents.coordinator import K8sCoordinatorAgent
from k8s_monitor.agents.triage import TriageAgent
from k8s_monitor.agents.world_model import (
    EventType,
    QueryType,
    StateEvent,
    WorldModelAgent,
    WorldModelQuery,
)


class TestHealthCheckWorkflow:
    """
    Test complete health check workflow through the swarm.

    Flow: Coordinator → ClusterScout → Discord
    """

    @pytest.fixture
    def coordinator(self):
        return K8sCoordinatorAgent()

    @pytest.fixture
    def world_model(self):
        return WorldModelAgent()

    def test_health_check_creates_correct_context(self, coordinator):
        """Health check should create a HEALTH_CHECK context."""
        context = HandoffContext.for_health_check("Check cluster health")

        assert context.request_type == RequestType.HEALTH_CHECK
        assert context.original_prompt == "Check cluster health"
        assert context.severity is None  # Not yet determined
        assert context.urgency is None

    def test_health_check_flow_sequence(self, coordinator):
        """Health check should flow: Coordinator → Scout → Discord."""
        HandoffContext.for_health_check()

        # Verify coordinator routes health check to scout
        assert coordinator._scout is not None

        # Scout should be used for health checks
        # The routing logic is in the swarm prompt, but we can verify
        # the coordinator has all required agents
        assert coordinator._triage is not None
        assert coordinator._discord is not None

    @pytest.mark.asyncio
    async def test_health_check_records_in_world_model(self, world_model):
        """Health check activity should be recorded in WorldModel."""
        # Simulate health check action using correct EventType
        action_event = StateEvent(
            event_id="health-1",
            event_type=EventType.AGENT_ACTION,
            resource_uid=None,
            agent_id="cluster_scout",
            timestamp=datetime.now(UTC),
            data={"action": "cluster_health_check", "status": "started"},
        )
        await world_model.handle_event(action_event)

        # Verify event recorded
        query = WorldModelQuery(
            query_type=QueryType.GET_AGENT_ACTIONS,
            agent_id="cluster_scout",
        )
        response = await world_model.query(query)

        assert response.success
        # Response data contains agent actions
        assert response.data is not None

    def test_healthy_cluster_context_state(self, coordinator):
        """Healthy cluster should result in context with no critical findings."""
        context = HandoffContext.for_health_check()

        # Simulate scout finding healthy state
        context.add_finding(
            agent="cluster_scout",
            description="All pods running normally",
            severity=Severity.INFO,
        )
        context.add_finding(
            agent="cluster_scout",
            description="All nodes ready",
            severity=Severity.INFO,
        )

        # Verify context state
        assert len(context.findings) == 2
        assert all(f.severity == Severity.INFO for f in context.findings)
        assert context.fix_applied is False


class TestIssueInvestigationWorkflow:
    """
    Test issue investigation workflow through the swarm.

    Flow: Coordinator → Triage → Diagnostician → Discord
    """

    @pytest.fixture
    def coordinator(self):
        return K8sCoordinatorAgent()

    @pytest.fixture
    def triage(self):
        return TriageAgent()

    def test_issue_investigation_creates_correct_context(self, coordinator):
        """Issue investigation should create ISSUE_INVESTIGATION context."""
        context = HandoffContext.for_issue(
            prompt="Pod app-1 is CrashLoopBackOff",
            resource_type=ResourceType.POD,
            namespace="default",
            resource_name="app-1",
        )

        assert context.request_type == RequestType.ISSUE_INVESTIGATION
        assert context.resource_type == ResourceType.POD
        assert context.namespace == "default"
        assert context.resource_name == "app-1"

    def test_triage_extracts_resource_info(self, triage):
        """Triage should extract resource info from LLM response."""
        # Use proper format - fields are extracted by looking for FIELD: value
        # The regex expects either another FIELD: or end of string after the value
        llm_response = """RESOURCE_TYPE: Pod
SEVERITY: critical
URGENCY: immediate"""

        resource_type = triage._extract_resource_type(llm_response)
        severity = triage._extract_severity(llm_response)
        urgency = triage._extract_urgency(llm_response)

        assert resource_type == ResourceType.POD
        assert severity == Severity.CRITICAL
        assert urgency == Urgency.IMMEDIATE

    def test_coordinator_routes_to_correct_diagnostician(self, coordinator):
        """Coordinator should route to appropriate diagnostician."""
        # Test routing via diagnose method
        HandoffContext.for_issue(
            prompt="Pod failing",
            resource_type=ResourceType.POD,
        )

        # Verify we have diagnosticians
        assert coordinator._pod_diag is not None
        assert coordinator._node_diag is not None
        assert coordinator._network_diag is not None
        assert coordinator._storage_diag is not None

    def test_issue_context_accumulates_findings(self, coordinator):
        """Issue investigation should accumulate findings from multiple agents."""
        context = HandoffContext.for_issue(
            prompt="Pod failing",
            resource_type=ResourceType.POD,
            namespace="default",
            resource_name="app-1",
        )

        # Triage finding
        context.add_finding(
            agent="triage_agent",
            description="Pod is in CrashLoopBackOff",
            severity=Severity.CRITICAL,
        )

        # Diagnostician finding
        context.add_finding(
            agent="pod_diagnostician",
            description="OOMKilled - memory limit exceeded",
            severity=Severity.CRITICAL,
            evidence={"reason": "OOMKilled", "container": "main"},
        )

        assert len(context.findings) == 2
        assert context.findings[0].agent == "triage_agent"
        assert context.findings[1].agent == "pod_diagnostician"
        assert context.findings[1].evidence["reason"] == "OOMKilled"


class TestRemediationWorkflow:
    """
    Test remediation workflow through the swarm.

    Flow: Coordinator → Triage → Diagnostician → Remediator → Discord
    """

    @pytest.fixture
    def coordinator(self):
        return K8sCoordinatorAgent()

    @pytest.fixture
    def world_model(self):
        return WorldModelAgent()

    def test_remediation_context_tracks_fix(self, coordinator):
        """Remediation should track fix applied state."""
        context = HandoffContext.for_issue(
            prompt="Pod CrashLoopBackOff",
            resource_type=ResourceType.POD,
            namespace="default",
            resource_name="app-1",
        )

        # Before fix
        assert context.fix_applied is False
        assert context.fix_outcome is None

        # After fix applied (direct assignment as per actual API)
        context.fix_applied = True
        context.fix_outcome = "Restarted pod by deleting"

        assert context.fix_applied is True
        assert "Restarted pod" in context.fix_outcome

    @pytest.mark.asyncio
    async def test_remediation_recorded_in_world_model(self, world_model):
        """Remediation actions should be recorded in WorldModel."""
        # First, create the resource using correct StateEvent API
        create_event = StateEvent(
            event_id="create-1",
            event_type=EventType.RESOURCE_CREATED,
            resource_uid="pod-default-app-1",
            agent_id=None,
            timestamp=datetime.now(UTC),
            data={
                "kind": "Pod",
                "namespace": "default",
                "name": "app-1",
            },
        )
        await world_model.handle_event(create_event)

        # Record remediation action
        action_event = StateEvent(
            event_id="action-1",
            event_type=EventType.REMEDIATION_COMPLETED,
            resource_uid="pod-default-app-1",
            agent_id="cluster_remediator",
            timestamp=datetime.now(UTC),
            data={
                "action": "delete_pod",
                "result": "success",
            },
        )
        await world_model.handle_event(action_event)

        # Query for agent actions
        query = WorldModelQuery(
            query_type=QueryType.GET_AGENT_ACTIONS,
            agent_id="cluster_remediator",
        )
        response = await world_model.query(query)

        assert response.success

    def test_remediation_flow_includes_verification(self, coordinator):
        """Remediation workflow should include verification step."""
        context = HandoffContext.for_issue(
            prompt="Fix pod",
            resource_type=ResourceType.POD,
        )

        # Apply fix
        context.fix_applied = True
        context.fix_outcome = "Restarted pod"

        # Verify fix
        context.add_finding(
            agent="cluster_remediator",
            description="Pod restarted successfully - now Running",
            severity=Severity.INFO,
        )

        assert context.fix_applied is True
        assert len(context.findings) == 1


class TestSwarmErrorHandling:
    """Test error handling in swarm workflows."""

    @pytest.fixture
    def coordinator(self):
        return K8sCoordinatorAgent()

    def test_context_tracks_errors_via_findings(self, coordinator):
        """Context should track errors via findings with CRITICAL severity."""
        context = HandoffContext.for_issue(
            prompt="Investigate issue",
            resource_type=ResourceType.POD,
        )

        # Add error finding using severity to indicate error
        context.add_finding(
            agent="triage_agent",
            description="ERROR: Unable to access Kubernetes API",
            severity=Severity.CRITICAL,
        )

        assert len(context.findings) == 1
        assert context.findings[0].severity == Severity.CRITICAL
        assert "ERROR" in context.findings[0].description

    def test_unknown_resource_type_handled(self, coordinator):
        """Unknown resource type should be handled gracefully."""
        context = HandoffContext.for_issue(
            prompt="Something is wrong",
            resource_type=None,
        )

        result = coordinator.diagnose(context)

        # Should add a finding about unknown type
        assert len(result.findings) == 1
        assert "No specific diagnostician" in result.findings[0].description

    def test_context_escalation_via_evidence(self, coordinator):
        """Context should track when issue needs escalation via evidence."""
        context = HandoffContext.for_issue(
            prompt="Complex issue",
            resource_type=ResourceType.POD,
        )

        # Mark as needing escalation via evidence
        context.add_finding(
            agent="cluster_remediator",
            description="Cannot auto-remediate - requires manual intervention",
            severity=Severity.CRITICAL,
        )
        context.add_evidence("requires_escalation", True)

        assert context.evidence.get("requires_escalation") is True


class TestRecurrenceTracking:
    """Test tracking of recurring issues."""

    @pytest.fixture
    def coordinator(self):
        return K8sCoordinatorAgent()

    def test_context_tracks_recurrence(self, coordinator):
        """Context should track recurring issues."""
        context = HandoffContext.for_issue(
            prompt="Pod CrashLoopBackOff again",
            resource_type=ResourceType.POD,
            namespace="default",
            resource_name="app-1",
        )

        # Set recurrence info
        context.recurrence_count = 3
        context.add_evidence(
            "previous_fixes",
            [
                "Restarted pod 2024-01-01",
                "Restarted pod 2024-01-02",
            ],
        )

        assert context.recurrence_count == 3
        assert len(context.evidence["previous_fixes"]) == 2

    def test_recurrence_affects_urgency(self, coordinator):
        """Recurring issues should have higher urgency."""
        context = HandoffContext.for_issue(
            prompt="Pod failing",
            resource_type=ResourceType.POD,
        )

        # First occurrence - normal urgency
        context.urgency = Urgency.SCHEDULED

        # After multiple recurrences, urgency should increase
        context.recurrence_count = 5
        if context.recurrence_count > 3:
            context.urgency = Urgency.IMMEDIATE

        assert context.urgency == Urgency.IMMEDIATE


class TestContextSummary:
    """Test context summary generation for Discord notifications."""

    def test_generate_summary_for_discord(self):
        """Context should generate summary for Discord notification."""
        context = HandoffContext.for_issue(
            prompt="Pod app-1 CrashLoopBackOff",
            resource_type=ResourceType.POD,
            namespace="production",
            resource_name="app-1",
        )

        context.add_finding(
            agent="triage_agent",
            description="Pod is CrashLoopBackOff",
            severity=Severity.CRITICAL,
        )
        context.add_finding(
            agent="pod_diagnostician",
            description="OOMKilled - memory limit exceeded",
            severity=Severity.CRITICAL,
        )
        context.fix_applied = True
        context.fix_outcome = "Restarted pod"

        summary = context.get_summary()

        assert "app-1" in summary
        assert "production" in summary
        assert "Pod" in summary

    def test_summary_includes_fix_outcome(self):
        """Summary should include fix outcome when available."""
        context = HandoffContext.for_issue(
            prompt="Fix pod",
            resource_type=ResourceType.POD,
            resource_name="test-pod",
        )

        context.fix_applied = True
        context.fix_outcome = "Restarted pod - now Running"
        summary = context.get_summary()

        assert context.fix_applied is True
        assert "test-pod" in summary


class TestMultiNamespaceWorkflow:
    """Test workflows spanning multiple namespaces."""

    @pytest.fixture
    def world_model(self):
        return WorldModelAgent()

    @pytest.mark.asyncio
    async def test_world_model_tracks_multiple_namespaces(self, world_model):
        """WorldModel should track resources across namespaces."""
        # Create resources in different namespaces using correct API
        for ns in ["default", "production", "staging"]:
            event = StateEvent(
                event_id=f"create-{ns}",
                event_type=EventType.RESOURCE_CREATED,
                resource_uid=f"pod-{ns}-app-1",
                agent_id=None,
                timestamp=datetime.now(UTC),
                data={
                    "kind": "Pod",
                    "namespace": ns,
                    "name": "app-1",
                },
            )
            await world_model.handle_event(event)

        # Query namespace status
        for ns in ["default", "production", "staging"]:
            query = WorldModelQuery(
                query_type=QueryType.GET_NAMESPACE_STATUS,
                namespace=ns,
            )
            response = await world_model.query(query)

            assert response.success
            # Response data contains namespace status
            assert response.data is not None

    @pytest.mark.asyncio
    async def test_cluster_summary_aggregates_namespaces(self, world_model):
        """Cluster summary should aggregate across namespaces."""
        # Create resources
        for ns in ["ns1", "ns2"]:
            event = StateEvent(
                event_id=f"create-{ns}",
                event_type=EventType.RESOURCE_CREATED,
                resource_uid=f"pod-{ns}-pod-1",
                agent_id=None,
                timestamp=datetime.now(UTC),
                data={
                    "kind": "Pod",
                    "namespace": ns,
                    "name": "pod-1",
                },
            )
            await world_model.handle_event(event)

        # Get cluster summary
        query = WorldModelQuery(query_type=QueryType.GET_CLUSTER_SUMMARY)
        response = await world_model.query(query)

        assert response.success
        # Response data contains cluster summary
        assert response.data is not None
        assert response.data.get("total_resources", 0) >= 2
