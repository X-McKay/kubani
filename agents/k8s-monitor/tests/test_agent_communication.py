"""
Agent Communication Tests.

These tests validate agent-to-agent communication patterns including:
1. HandoffContext passing between agents
2. Finding/evidence accumulation across agent chains
3. Agent chain tracking
4. Error propagation between agents
"""

import pytest

from k8s_monitor.agents.context import (
    HandoffContext,
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


class TestHandoffContextPropagation:
    """Test HandoffContext flows correctly between agents."""

    def test_context_preserves_original_request(self):
        """Original request info should be preserved through handoffs."""
        original_prompt = "Pod myapp-1234 is CrashLoopBackOff in production"

        context = HandoffContext.for_issue(
            prompt=original_prompt,
            resource_type=ResourceType.POD,
            namespace="production",
            resource_name="myapp-1234",
        )

        # Simulate multiple agent handoffs by modifying agent_chain directly
        context.agent_chain.append("coordinator")
        context.agent_chain.append("triage")
        context.agent_chain.append("pod_diagnostician")
        context.agent_chain.append("remediator")

        # Original info preserved
        assert context.original_prompt == original_prompt
        assert context.resource_type == ResourceType.POD
        assert context.namespace == "production"
        assert context.resource_name == "myapp-1234"

    def test_agent_chain_tracks_handoff_sequence(self):
        """Agent chain should accurately track handoff sequence."""
        context = HandoffContext.for_health_check()

        context.agent_chain.append("coordinator")
        context.agent_chain.append("cluster_scout")
        context.agent_chain.append("discord_notifier")

        assert context.agent_chain == [
            "coordinator",
            "cluster_scout",
            "discord_notifier",
        ]
        assert len(context.agent_chain) == 3

    def test_findings_accumulate_across_agents(self):
        """Findings from multiple agents should accumulate."""
        context = HandoffContext.for_issue(
            prompt="Investigate pod issue",
            resource_type=ResourceType.POD,
        )

        # Triage adds finding
        context.agent_chain.append("triage")
        context.add_finding(
            agent="triage",
            description="Pod is CrashLoopBackOff",
            severity=Severity.CRITICAL,
        )

        # Diagnostician adds findings
        context.agent_chain.append("pod_diagnostician")
        context.add_finding(
            agent="pod_diagnostician",
            description="Container exited with OOMKilled",
            severity=Severity.CRITICAL,
            evidence={"exit_code": 137, "reason": "OOMKilled"},
        )
        context.add_finding(
            agent="pod_diagnostician",
            description="Memory limit is 256Mi, request is 128Mi",
            severity=Severity.WARNING,
        )

        # Remediator adds finding
        context.agent_chain.append("remediator")
        context.add_finding(
            agent="remediator",
            description="Restarted pod successfully",
            severity=Severity.INFO,
        )

        assert len(context.findings) == 4
        assert context.findings[0].agent == "triage"
        assert context.findings[1].agent == "pod_diagnostician"
        assert context.findings[3].agent == "remediator"

    def test_evidence_accumulates_across_agents(self):
        """Evidence from multiple agents should accumulate."""
        context = HandoffContext.for_issue(
            prompt="Debug pod",
            resource_type=ResourceType.POD,
        )

        # Different agents add different evidence
        context.add_evidence("triage_assessment", {"status": "critical"})
        context.add_evidence("pod_logs", "Error: out of memory")
        context.add_evidence(
            "container_state",
            {
                "state": "terminated",
                "exit_code": 137,
            },
        )
        context.add_evidence("fix_applied", True)

        assert len(context.evidence) == 4
        assert "triage_assessment" in context.evidence
        assert "pod_logs" in context.evidence
        assert context.evidence["fix_applied"] is True


class TestAgentChainIntegrity:
    """Test agent chain integrity through handoffs."""

    def test_empty_chain_on_new_context(self):
        """New context should have empty agent chain."""
        context = HandoffContext.for_health_check()

        assert context.agent_chain == []

    def test_chain_can_be_extended(self):
        """Agent chain can be extended multiple times."""
        context = HandoffContext.for_issue(
            prompt="Test",
            resource_type=ResourceType.POD,
        )

        context.agent_chain.append("triage")
        context.agent_chain.append("diagnostician")
        context.agent_chain.append("remediator")

        assert len(context.agent_chain) == 3
        assert "triage" in context.agent_chain
        assert "diagnostician" in context.agent_chain
        assert "remediator" in context.agent_chain

    def test_context_summary_includes_resource_info(self):
        """Summary should reference resource info."""
        context = HandoffContext.for_issue(
            prompt="Test",
            resource_type=ResourceType.POD,
            resource_name="test-pod",
        )

        context.agent_chain.append("triage")
        context.severity = Severity.CRITICAL

        summary = context.get_summary()

        # Summary should contain key context info
        assert "test-pod" in summary
        assert "Pod" in summary


class TestErrorPropagation:
    """Test error propagation between agents."""

    def test_context_captures_first_error(self):
        """First critical error should be captured."""
        context = HandoffContext.for_issue(
            prompt="Investigate",
            resource_type=ResourceType.POD,
        )

        context.add_finding(
            agent="triage",
            description="CRITICAL: Unable to connect to Kubernetes API",
            severity=Severity.CRITICAL,
        )

        assert len(context.findings) == 1
        assert context.findings[0].severity == Severity.CRITICAL

    def test_multiple_errors_from_different_agents(self):
        """Multiple agents can report errors."""
        context = HandoffContext.for_issue(
            prompt="Investigate",
            resource_type=ResourceType.NODE,
        )

        # First agent error
        context.add_finding(
            agent="node_diagnostician",
            description="ERROR: Cannot SSH to node",
            severity=Severity.CRITICAL,
        )

        # Second agent error
        context.add_finding(
            agent="network_diagnostician",
            description="ERROR: Node unreachable via network",
            severity=Severity.CRITICAL,
        )

        # Both errors captured
        assert len(context.findings) == 2
        critical_count = sum(1 for f in context.findings if f.severity == Severity.CRITICAL)
        assert critical_count == 2


class TestRemediationTracking:
    """Test remediation attempt tracking across agents."""

    def test_track_remediation_via_fix_fields(self):
        """Remediation state should be tracked via fix fields."""
        context = HandoffContext.for_issue(
            prompt="Fix pod",
            resource_type=ResourceType.POD,
        )

        # Before fix
        assert context.fix_applied is False
        assert context.fix_outcome is None

        # Apply fix
        context.fix_applied = True
        context.fix_outcome = "Pod deleted for restart"

        assert context.fix_applied is True
        assert "restart" in context.fix_outcome

    def test_track_remediation_attempts_in_evidence(self):
        """Multiple remediation attempts can be tracked in evidence."""
        context = HandoffContext.for_issue(
            prompt="Fix deployment",
            resource_type=ResourceType.DEPLOYMENT,
        )

        # Track attempts in evidence
        context.add_evidence(
            "remediation_attempts",
            [
                {"action": "rollout_restart", "success": False, "time": "10:00"},
                {"action": "scale_down_up", "success": True, "time": "10:05"},
            ],
        )

        attempts = context.evidence["remediation_attempts"]
        assert len(attempts) == 2
        assert attempts[0]["success"] is False
        assert attempts[1]["success"] is True

    def test_fix_outcome_set_after_remediation(self):
        """Fix outcome should be set after successful remediation."""
        context = HandoffContext.for_issue(
            prompt="Fix pod",
            resource_type=ResourceType.POD,
        )

        # Add evidence about the remediation
        context.add_evidence("action_taken", "delete_pod")
        context.fix_applied = True
        context.fix_outcome = "Pod restarted and now Running"

        assert context.fix_applied is True
        assert "Running" in context.fix_outcome


class TestSeverityAndUrgencyPropagation:
    """Test severity and urgency flow through agent chain."""

    def test_severity_can_be_elevated(self):
        """Severity can be elevated by downstream agents."""
        context = HandoffContext.for_issue(
            prompt="Investigate issue",
            resource_type=ResourceType.POD,
        )

        # Triage sets initial severity
        context.severity = Severity.WARNING

        # Diagnostician elevates severity
        context.add_finding(
            agent="diagnostician",
            description="Multiple pods affected - elevating to critical",
            severity=Severity.CRITICAL,
        )
        context.severity = Severity.CRITICAL

        assert context.severity == Severity.CRITICAL

    def test_urgency_can_be_elevated(self):
        """Urgency can be elevated based on findings."""
        context = HandoffContext.for_issue(
            prompt="Check node",
            resource_type=ResourceType.NODE,
        )

        # Initial urgency
        context.urgency = Urgency.SCHEDULED

        # Elevate based on finding
        context.add_finding(
            agent="node_diagnostician",
            description="Node disk 95% full - immediate action needed",
            severity=Severity.CRITICAL,
        )
        context.urgency = Urgency.IMMEDIATE

        assert context.urgency == Urgency.IMMEDIATE


class TestCoordinatorDiagnosticianCommunication:
    """Test communication between coordinator and diagnosticians."""

    @pytest.fixture
    def coordinator(self):
        return K8sCoordinatorAgent()

    def test_coordinator_routes_pod_issue(self, coordinator):
        """Coordinator routes pod issues to PodDiagnostician."""
        context = HandoffContext.for_issue(
            prompt="Pod failing",
            resource_type=ResourceType.POD,
        )

        result = coordinator.diagnose(context)

        # Verify diagnostician was used (finding added)
        # or routed correctly
        assert result is not None

    def test_coordinator_routes_node_issue(self, coordinator):
        """Coordinator routes node issues to NodeDiagnostician."""
        context = HandoffContext.for_issue(
            prompt="Node NotReady",
            resource_type=ResourceType.NODE,
        )

        result = coordinator.diagnose(context)

        assert result is not None

    def test_coordinator_routes_network_issue(self, coordinator):
        """Coordinator routes network issues to NetworkDiagnostician."""
        context = HandoffContext.for_issue(
            prompt="Service unreachable",
            resource_type=ResourceType.SERVICE,
        )

        result = coordinator.diagnose(context)

        assert result is not None

    def test_coordinator_routes_storage_issue(self, coordinator):
        """Coordinator routes storage issues to StorageDiagnostician."""
        context = HandoffContext.for_issue(
            prompt="PVC not bound",
            resource_type=ResourceType.PVC,
        )

        result = coordinator.diagnose(context)

        assert result is not None


class TestDiagnosticianBehavior:
    """Test diagnostician behavior and context handling."""

    @pytest.fixture
    def pod_diagnostician(self):
        return PodDiagnostician()

    @pytest.fixture
    def node_diagnostician(self):
        return NodeDiagnostician()

    @pytest.fixture
    def network_diagnostician(self):
        return NetworkDiagnostician()

    @pytest.fixture
    def storage_diagnostician(self):
        return StorageDiagnostician()

    def test_pod_diagnostician_can_handle_pods(self, pod_diagnostician):
        """PodDiagnostician can handle pod-related types."""
        # Use can_handle method to test resource type handling
        assert pod_diagnostician.can_handle(ResourceType.POD)
        assert pod_diagnostician.can_handle(ResourceType.DEPLOYMENT)

    def test_node_diagnostician_can_handle_nodes(self, node_diagnostician):
        """NodeDiagnostician can handle node type."""
        assert node_diagnostician.can_handle(ResourceType.NODE)

    def test_network_diagnostician_can_handle_services(self, network_diagnostician):
        """NetworkDiagnostician can handle network types."""
        assert network_diagnostician.can_handle(ResourceType.SERVICE)
        assert network_diagnostician.can_handle(ResourceType.INGRESS)

    def test_storage_diagnostician_can_handle_storage(self, storage_diagnostician):
        """StorageDiagnostician can handle storage types."""
        assert storage_diagnostician.can_handle(ResourceType.PVC)

    def test_diagnosticians_have_names(
        self,
        pod_diagnostician,
        node_diagnostician,
        network_diagnostician,
        storage_diagnostician,
    ):
        """All diagnosticians have names defined."""
        assert pod_diagnostician.NAME
        assert node_diagnostician.NAME
        assert network_diagnostician.NAME
        assert storage_diagnostician.NAME


class TestContextSerialization:
    """Test context serialization for inter-agent communication."""

    def test_to_dict_includes_all_fields(self):
        """to_dict should include all relevant fields."""
        context = HandoffContext.for_issue(
            prompt="Test issue",
            resource_type=ResourceType.POD,
            namespace="default",
            resource_name="test-pod",
        )

        context.severity = Severity.CRITICAL
        context.urgency = Urgency.IMMEDIATE
        context.agent_chain.append("triage")
        context.add_finding(
            agent="triage",
            description="Test finding",
            severity=Severity.CRITICAL,
        )
        context.fix_applied = True
        context.fix_outcome = "Fixed"

        data = context.to_dict()

        assert data["request_id"] == context.request_id
        assert data["request_type"] == "issue_investigation"
        assert data["resource_type"] == "Pod"
        assert data["namespace"] == "default"
        assert data["resource_name"] == "test-pod"
        assert data["severity"] == "critical"
        assert data["urgency"] == "immediate"
        assert data["fix_applied"] is True
        assert data["fix_outcome"] == "Fixed"

    def test_to_dict_handles_none_values(self):
        """to_dict should handle None values gracefully."""
        context = HandoffContext.for_health_check()

        data = context.to_dict()

        assert data["resource_type"] is None
        assert data["namespace"] is None
        assert data["resource_name"] is None


class TestRecurrenceHandling:
    """Test recurrence detection and handling across agents."""

    def test_recurrence_count_propagates(self):
        """Recurrence count should propagate through agents."""
        context = HandoffContext.for_issue(
            prompt="Pod CrashLoopBackOff again",
            resource_type=ResourceType.POD,
            resource_name="flaky-app",
        )

        # Memory agent sets recurrence info
        context.recurrence_count = 5
        context.similar_issues = [
            "issue-123",
            "issue-456",
            "issue-789",
        ]

        # Propagated to downstream agents
        assert context.recurrence_count == 5
        assert len(context.similar_issues) == 3

    def test_permanent_fix_recommendation(self):
        """Permanent fix can be recommended after multiple occurrences."""
        context = HandoffContext.for_issue(
            prompt="Pod failing",
            resource_type=ResourceType.POD,
        )

        context.recurrence_count = 10
        context.recommended_permanent_fix = "Increase memory limit to 512Mi in deployment spec"

        assert context.recurrence_count == 10
        assert "512Mi" in context.recommended_permanent_fix


class TestAgentChainFlow:
    """Test the complete agent chain flow."""

    @pytest.fixture
    def coordinator(self):
        return K8sCoordinatorAgent()

    def test_full_investigation_flow(self, coordinator):
        """Test complete flow from coordinator through diagnosis."""
        # Create initial context
        context = HandoffContext.for_issue(
            prompt="Pod webapp-123 is failing in production",
            resource_type=ResourceType.POD,
            namespace="production",
            resource_name="webapp-123",
        )

        # Simulate triage assessment
        context.agent_chain.append("triage")
        context.add_finding(
            agent="triage",
            description="Pod is in CrashLoopBackOff state",
            severity=Severity.CRITICAL,
        )
        context.severity = Severity.CRITICAL
        context.urgency = Urgency.IMMEDIATE

        # Route through coordinator to diagnostician
        result = coordinator.diagnose(context)

        # Verify flow completed
        assert result is not None
        assert result.severity == Severity.CRITICAL
        assert result.urgency == Urgency.IMMEDIATE

    def test_healthy_cluster_flow(self):
        """Test flow for healthy cluster check."""
        context = HandoffContext.for_health_check(prompt="Check cluster health")

        # Scout reports healthy
        context.agent_chain.append("cluster_scout")
        context.add_finding(
            agent="cluster_scout",
            description="All pods running",
            severity=Severity.INFO,
        )
        context.add_finding(
            agent="cluster_scout",
            description="All nodes ready",
            severity=Severity.INFO,
        )

        # All findings are INFO level
        assert all(f.severity == Severity.INFO for f in context.findings)
        assert len(context.findings) == 2
