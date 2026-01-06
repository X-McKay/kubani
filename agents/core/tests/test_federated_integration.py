"""
Integration tests for the federated agent architecture.

These tests validate the end-to-end flow of:
1. Event publishing and subscription
2. Skill retrieval and matching
3. Approval flow mechanics
4. Cross-agent communication patterns
"""

from datetime import UTC, datetime

from core_agents.approvals import ApprovalRequest, ApprovalResult, ApprovalStatus
from core_agents.events import Event, EventType
from core_agents.skills import (
    MCPToolReference,
    Skill,
    SkillAction,
    SkillCategory,
    SkillDomain,
    SkillOutcome,
)


class TestEventFlow:
    """Test event publishing and subscription patterns."""

    def test_event_serialization_roundtrip(self):
        """Test that events can be serialized and deserialized."""
        original = Event(
            id="test-123",
            type=EventType.K8S_ISSUE_DETECTED,
            source="test-sentinel",
            payload={
                "pod_name": "my-pod",
                "namespace": "default",
                "reason": "CrashLoopBackOff",
            },
            correlation_id="corr-456",
        )

        # Serialize to stream format
        stream_data = original.to_stream_data()

        # Verify all fields are strings
        assert all(isinstance(v, str) for v in stream_data.values())

        # Deserialize back
        stream_bytes = {k.encode(): v.encode() for k, v in stream_data.items()}
        restored = Event.from_stream_data(stream_bytes)

        assert restored.id == original.id
        assert restored.type == original.type
        assert restored.source == original.source
        assert restored.payload == original.payload
        assert restored.correlation_id == original.correlation_id

    def test_event_types_cover_all_domains(self):
        """Test that event types cover K8s, News, and System domains."""
        k8s_events = [e for e in EventType if e.value.startswith("k8s:")]
        news_events = [e for e in EventType if e.value.startswith("news:")]
        system_events = [e for e in EventType if e.value.startswith("system:")]
        agent_events = [e for e in EventType if e.value.startswith("agent:")]

        assert len(k8s_events) >= 4, "Should have K8s events for issue detection and remediation"
        assert len(news_events) >= 3, "Should have News events for articles and trends"
        assert len(system_events) >= 3, "Should have System events for approvals and MCP requests"
        assert len(agent_events) >= 3, "Should have Agent lifecycle events"

    def test_event_correlation_chain(self):
        """Test that events can be correlated in a chain."""
        correlation_id = "incident-001"

        # Simulate a chain of related events
        events = [
            Event(
                id="detect-1",
                type=EventType.K8S_ISSUE_DETECTED,
                source="sentinel",
                payload={"reason": "CrashLoopBackOff"},
                correlation_id=correlation_id,
            ),
            Event(
                id="start-1",
                type=EventType.K8S_REMEDIATION_STARTED,
                source="healer",
                payload={"skill_id": "k8s-restart-crashloop"},
                correlation_id=correlation_id,
            ),
            Event(
                id="complete-1",
                type=EventType.K8S_REMEDIATION_COMPLETED,
                source="healer",
                payload={"success": True},
                correlation_id=correlation_id,
            ),
        ]

        # All should share correlation ID
        assert all(e.correlation_id == correlation_id for e in events)

        # Can trace the chain
        chain_types = [e.type for e in events]
        assert chain_types == [
            EventType.K8S_ISSUE_DETECTED,
            EventType.K8S_REMEDIATION_STARTED,
            EventType.K8S_REMEDIATION_COMPLETED,
        ]


class TestSkillMatching:
    """Test skill retrieval and matching logic."""

    def test_skill_searchable_text_contains_key_fields(self):
        """Test that searchable text includes all relevant fields."""
        skill = Skill(
            id="k8s-restart-crashloop",
            name="Restart CrashLoopBackOff Pod",
            domain=SkillDomain.K8S,
            category=SkillCategory.REMEDIATION,
            description="Restart a pod stuck in CrashLoopBackOff state",
            preconditions=[
                "Pod status is CrashLoopBackOff",
                "Restart count exceeds 3",
            ],
            actions=[
                SkillAction(
                    description="Delete pod to trigger recreation",
                    mcp_tool=MCPToolReference(
                        server="kubernetes-mcp-server",
                        tool="pods_delete",
                        params={"name": "$pod_name", "namespace": "$namespace"},
                    ),
                )
            ],
            success_criteria=["Pod reaches Running state"],
            failure_handling="Escalate to human operator",
            tags=["pod", "restart", "crashloop"],
        )

        searchable = skill.get_searchable_text()

        # Should include name
        assert "CrashLoopBackOff" in searchable

        # Should include description
        assert "Restart" in searchable

        # Should include preconditions
        assert "status" in searchable.lower()

        # Should include tags
        assert "crashloop" in searchable.lower()

    def test_skill_confidence_updates(self):
        """Test that skill confidence updates correctly."""
        skill = Skill(
            id="test-skill",
            name="Test Skill",
            domain=SkillDomain.K8S,
            category=SkillCategory.REMEDIATION,
            description="Test",
            preconditions=[],
            actions=[],
            success_criteria=[],
            failure_handling="",
            confidence=0.5,
        )

        # Record successes
        for _ in range(5):
            skill.record_outcome(success=True)

        assert skill.success_count == 5
        assert skill.failure_count == 0
        assert skill.confidence > 0.5  # Should increase

        # Record failures
        for _ in range(3):
            skill.record_outcome(success=False)

        assert skill.success_count == 5
        assert skill.failure_count == 3
        # Confidence should have adjusted

    def test_skill_domain_filtering(self):
        """Test that skills can be filtered by domain."""
        k8s_skill = Skill(
            id="k8s-skill",
            name="K8s Skill",
            domain=SkillDomain.K8S,
            category=SkillCategory.REMEDIATION,
            description="K8s skill",
            preconditions=[],
            actions=[],
            success_criteria=[],
            failure_handling="",
        )

        news_skill = Skill(
            id="news-skill",
            name="News Skill",
            domain=SkillDomain.NEWS,
            category=SkillCategory.COLLECTION,
            description="News skill",
            preconditions=[],
            actions=[],
            success_criteria=[],
            failure_handling="",
        )

        # Can distinguish by domain
        assert k8s_skill.domain == SkillDomain.K8S
        assert news_skill.domain == SkillDomain.NEWS

    def test_mcp_tool_reference_parameter_templates(self):
        """Test that MCP tool references support parameter templates."""
        tool_ref = MCPToolReference(
            server="kubernetes-mcp-server",
            tool="pods_delete",
            params={
                "name": "$pod_name",
                "namespace": "$namespace",
                "grace_period": 30,
            },
        )

        # Should have template variables
        assert "$pod_name" in tool_ref.params.values()
        assert "$namespace" in tool_ref.params.values()

        # Can have literal values too
        assert 30 in tool_ref.params.values()


class TestApprovalFlow:
    """Test approval request and response handling."""

    def test_approval_request_formatting(self):
        """Test that approval requests format correctly for Discord."""
        request = ApprovalRequest(
            action="scale_deployment",
            resource="deployment/my-app",
            reason="High load detected, need to scale up",
            skill_id="k8s-scale-deployment",
            agent="healer-agent",
            context={
                "current_replicas": 3,
                "target_replicas": 5,
                "cpu_usage": "85%",
            },
        )

        message = request.format_discord_message()

        # Should include key information
        assert "scale_deployment" in message
        assert "deployment/my-app" in message
        assert "High load" in message

        # Should have approval/reject buttons (emojis)
        assert "✅" in message
        assert "❌" in message

    def test_approval_result_states(self):
        """Test all approval result states."""
        request = ApprovalRequest(
            action="test_action",
            resource="test/resource",
            reason="Testing",
        )

        # Test approved
        approved = ApprovalResult.approved_result(request, responder="user123")
        assert approved.status == ApprovalStatus.APPROVED
        assert approved.approved is True
        assert approved.responder == "user123"

        # Test rejected
        rejected = ApprovalResult.rejected_result(request, responder="admin", reason="Too risky")
        assert rejected.status == ApprovalStatus.REJECTED
        assert rejected.approved is False
        assert rejected.response_reason == "Too risky"

        # Test timeout
        timeout = ApprovalResult.timeout_result(request)
        assert timeout.status == ApprovalStatus.TIMEOUT
        assert timeout.approved is False

        # Test error
        error = ApprovalResult.error_result(request, "Connection failed")
        assert error.status == ApprovalStatus.ERROR
        assert error.approved is False

    def test_approval_request_with_skill_context(self):
        """Test approval requests include skill context."""
        request = ApprovalRequest(
            action="restart_pod",
            resource="pod/failing-pod",
            reason="Pod is in CrashLoopBackOff",
            skill_id="k8s-restart-crashloop",
            agent="healer",
            context={
                "restart_count": 5,
                "last_error": "OOMKilled",
            },
        )

        assert request.skill_id == "k8s-restart-crashloop"
        assert request.agent == "healer"
        assert request.context["restart_count"] == 5


class TestCrossAgentCommunication:
    """Test patterns for cross-agent communication."""

    def test_sentinel_to_healer_event_format(self):
        """Test the event format from Sentinel to Healer."""
        # Sentinel detects an issue and publishes
        issue_event = Event(
            id="issue-123",
            type=EventType.K8S_ISSUE_DETECTED,
            source="k8s-sentinel",
            payload={
                "event": {
                    "type": "Warning",
                    "reason": "CrashLoopBackOff",
                    "message": "Back-off restarting failed container",
                    "namespace": "production",
                    "name": "api-server-abc123",
                    "kind": "Pod",
                },
                "classification": {
                    "severity": "high",
                    "category": "pod_health",
                    "reason": "Matched known pattern: CrashLoopBackOff",
                },
                "matching_skills": ["k8s-restart-crashloop"],
                "detected_at": datetime.now(UTC).isoformat(),
            },
        )

        # Healer should be able to extract needed info
        payload = issue_event.payload
        k8s_event = payload["event"]

        assert k8s_event["reason"] == "CrashLoopBackOff"
        assert k8s_event["namespace"] == "production"
        assert k8s_event["name"] == "api-server-abc123"
        assert "k8s-restart-crashloop" in payload["matching_skills"]

    def test_healer_remediation_complete_event(self):
        """Test the event format when Healer completes remediation."""
        complete_event = Event(
            id="remediation-456",
            type=EventType.K8S_REMEDIATION_COMPLETED,
            source="k8s-healer",
            payload={
                "issue_id": "issue-123",
                "skill_id": "k8s-restart-crashloop",
                "resource": "Pod/api-server-abc123",
                "namespace": "production",
                "success": True,
                "duration_seconds": 45.2,
                "verification": {
                    "criteria_met": ["Pod reaches Running state"],
                    "explanation": "Pod is now in Running state",
                },
            },
            correlation_id="issue-123",
        )

        payload = complete_event.payload
        assert payload["success"] is True
        assert payload["skill_id"] == "k8s-restart-crashloop"
        assert complete_event.correlation_id == "issue-123"

    def test_explorer_skill_learned_event(self):
        """Test the event format when Explorer learns a new skill."""
        learned_event = Event(
            id="learned-789",
            type=EventType.AGENT_SKILL_LEARNED,
            source="k8s-explorer",
            payload={
                "skill_id": "k8s-handle-oomkilled",
                "skill_name": "Handle OOMKilled Pods",
                "based_on_incidents": 5,
                "approved_by": "admin",
                "confidence": 0.3,
            },
        )

        payload = learned_event.payload
        assert payload["skill_id"] == "k8s-handle-oomkilled"
        assert payload["based_on_incidents"] == 5
        assert payload["approved_by"] == "admin"


class TestSkillOutcomeTracking:
    """Test skill outcome recording and confidence updates."""

    def test_skill_outcome_creation(self):
        """Test creating skill outcomes."""
        success_outcome = SkillOutcome(
            skill_id="k8s-restart-crashloop",
            success=True,
        )

        assert success_outcome.skill_id == "k8s-restart-crashloop"
        assert success_outcome.success is True
        assert success_outcome.timestamp is not None

        failure_outcome = SkillOutcome(
            skill_id="k8s-restart-crashloop",
            success=False,
            error_message="Pod still in CrashLoopBackOff after restart",
        )

        assert failure_outcome.success is False
        assert "CrashLoopBackOff" in failure_outcome.error_message

    def test_confidence_bounds(self):
        """Test that confidence stays within valid bounds."""
        skill = Skill(
            id="test-skill",
            name="Test",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="Test",
            preconditions=[],
            actions=[],
            success_criteria=[],
            failure_handling="",
            confidence=0.5,
        )

        # Many successes should not exceed 1.0
        for _ in range(100):
            skill.record_outcome(success=True)

        assert skill.confidence <= 1.0

        # Many failures should not go below 0.0
        skill.confidence = 0.5
        skill.success_count = 0
        skill.failure_count = 0

        for _ in range(100):
            skill.record_outcome(success=False)

        assert skill.confidence >= 0.0


class TestMCPServerRequestFlow:
    """Test the flow for requesting new MCP servers."""

    def test_mcp_server_request_event(self):
        """Test the event format for requesting an MCP server."""
        request_event = Event(
            id="mcp-req-001",
            type=EventType.SYSTEM_MCP_SERVER_REQUESTED,
            source="k8s-explorer",
            payload={
                "server": "prometheus-mcp-server",
                "reason": "Required for capacity forecasting skill",
                "requested_by": "k8s-explorer",
                "priority": "high",
                "affected_incidents": 15,
                "skill_id": "k8s-capacity-forecast",
            },
        )

        payload = request_event.payload
        assert payload["server"] == "prometheus-mcp-server"
        assert payload["priority"] == "high"
        assert payload["affected_incidents"] == 15
