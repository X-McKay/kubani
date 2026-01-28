"""Tests for K8s Monitor Temporal workflows.

These tests verify the workflow definitions compile correctly and
that the input/output types are properly structured. Full integration
tests require a running Temporal server.
"""



class TestK8sRemediationWorkflow:
    """Tests for K8sRemediationWorkflow."""

    def test_workflow_imports(self):
        """Test that workflow can be imported."""
        from kubani.syndicates.k8s_monitor.workflows import K8sRemediationWorkflow

        assert K8sRemediationWorkflow is not None
        assert hasattr(K8sRemediationWorkflow, "run")

    def test_workflow_has_observability(self):
        """Test that workflow inherits from ObservableWorkflowMixin."""
        from kubani.syndicates.k8s_monitor.workflows.remediation import (
            K8sRemediationWorkflow,
        )

        # Check for mixin methods
        instance = K8sRemediationWorkflow()
        assert hasattr(instance, "_init_observability")
        assert hasattr(instance, "_set_status")
        assert hasattr(instance, "_log_event")
        assert hasattr(instance, "_wait_if_paused")

    def test_remediation_input_structure(self):
        """Test RemediationInput dataclass structure."""
        from kubani.syndicates.k8s_monitor.workflows.remediation import RemediationInput

        # Create with required fields
        input_data = RemediationInput(
            event_id="test-event-123",
            resource_kind="Pod",
            resource_name="api-server-xyz",
            namespace="production",
            reason="OOMKilled",
            message="Container was killed due to OOM",
        )

        assert input_data.event_id == "test-event-123"
        assert input_data.resource_kind == "Pod"
        assert input_data.resource_name == "api-server-xyz"
        assert input_data.namespace == "production"
        assert input_data.reason == "OOMKilled"
        assert input_data.severity == "warning"  # default
        assert input_data.auto_remediate is True  # default
        assert input_data.notify_channel == "k8s-alerts"  # default

    def test_remediation_input_with_optional_fields(self):
        """Test RemediationInput with optional fields."""
        from kubani.syndicates.k8s_monitor.workflows.remediation import RemediationInput

        input_data = RemediationInput(
            event_id="test-event-456",
            resource_kind="Deployment",
            resource_name="web-app",
            namespace="staging",
            reason="FailedScheduling",
            message="Not enough resources",
            severity="critical",
            auto_remediate=False,
            notify_channel="ops-alerts",
            correlation_id="corr-123",
        )

        assert input_data.severity == "critical"
        assert input_data.auto_remediate is False
        assert input_data.notify_channel == "ops-alerts"
        assert input_data.correlation_id == "corr-123"

    def test_remediation_result_structure(self):
        """Test RemediationResult dataclass structure."""
        from kubani.syndicates.k8s_monitor.workflows.remediation import (
            RemediationResult,
        )

        # Create with defaults
        result = RemediationResult(event_id="test-event-123")

        assert result.event_id == "test-event-123"
        assert result.classification is None
        assert result.skills_matched is None
        assert result.remediation_applied is False
        assert result.verified is False
        assert result.escalated is False
        assert result.learning_stored is False
        assert result.success is True
        assert result.error is None

    def test_workflow_queries(self):
        """Test that workflow has query methods."""
        from kubani.syndicates.k8s_monitor.workflows.remediation import (
            K8sRemediationWorkflow,
        )

        instance = K8sRemediationWorkflow()

        # Check for query methods
        assert hasattr(instance, "get_remediation_stats")
        # Standard queries from mixin
        assert hasattr(instance, "get_status")
        assert hasattr(instance, "get_events")


class TestK8sInvestigationSwarm:
    """Tests for K8sInvestigationSwarm."""

    def test_workflow_imports(self):
        """Test that swarm workflow can be imported."""
        from kubani.syndicates.k8s_monitor.workflows import K8sInvestigationSwarm

        assert K8sInvestigationSwarm is not None
        assert hasattr(K8sInvestigationSwarm, "run")

    def test_swarm_has_observability(self):
        """Test that swarm inherits from ObservableWorkflowMixin."""
        from kubani.syndicates.k8s_monitor.workflows.investigation import (
            K8sInvestigationSwarm,
        )

        instance = K8sInvestigationSwarm()
        assert hasattr(instance, "_init_observability")
        assert hasattr(instance, "_set_status")
        assert hasattr(instance, "_log_event")

    def test_investigation_input_structure(self):
        """Test InvestigationInput dataclass structure."""
        from kubani.syndicates.k8s_monitor.workflows.investigation import (
            InvestigationInput,
        )

        input_data = InvestigationInput(
            trigger_event_id="event-123",
            resource_kind="Node",
            resource_name="worker-1",
            namespace="kube-system",
        )

        assert input_data.trigger_event_id == "event-123"
        assert input_data.resource_kind == "Node"
        assert input_data.symptoms == []  # default
        assert input_data.priority == 3  # default
        assert input_data.max_depth == 5  # default
        assert input_data.timeout_minutes == 30  # default

    def test_investigation_input_with_symptoms(self):
        """Test InvestigationInput with symptoms."""
        from kubani.syndicates.k8s_monitor.workflows.investigation import (
            InvestigationInput,
        )

        input_data = InvestigationInput(
            trigger_event_id="event-456",
            resource_kind="Pod",
            resource_name="api-server",
            namespace="production",
            symptoms=["OOMKilled", "HighCPU", "NetworkLatency"],
            priority=1,
            max_depth=3,
            timeout_minutes=15,
        )

        assert len(input_data.symptoms) == 3
        assert input_data.priority == 1
        assert input_data.max_depth == 3
        assert input_data.timeout_minutes == 15

    def test_investigation_result_structure(self):
        """Test InvestigationResult dataclass structure."""
        from kubani.syndicates.k8s_monitor.workflows.investigation import (
            InvestigationResult,
        )

        result = InvestigationResult(trigger_event_id="event-123")

        assert result.trigger_event_id == "event-123"
        assert result.root_causes == []
        assert result.impact_assessment == {}
        assert result.recommendations == []
        assert result.evidence == []
        assert result.agents_invoked == []
        assert result.tasks_completed == 0
        assert result.tasks_failed == 0
        assert result.confidence == 0.0
        assert result.success is True

    def test_swarm_agents_configuration(self):
        """Test SWARM_AGENTS configuration."""
        from kubani.syndicates.k8s_monitor.workflows.investigation import SWARM_AGENTS

        assert "diagnostics" in SWARM_AGENTS
        assert "root-cause" in SWARM_AGENTS
        assert "impact" in SWARM_AGENTS
        assert "recommendation" in SWARM_AGENTS

        # Verify spawn relationships
        diag = SWARM_AGENTS["diagnostics"]
        assert "root-cause" in diag["can_spawn"]
        assert "impact" in diag["can_spawn"]

        # Recommendation can't spawn anything
        rec = SWARM_AGENTS["recommendation"]
        assert rec["can_spawn"] == []

    def test_swarm_queries(self):
        """Test that swarm has query methods."""
        from kubani.syndicates.k8s_monitor.workflows.investigation import (
            K8sInvestigationSwarm,
        )

        instance = K8sInvestigationSwarm()

        # Swarm-specific queries
        assert hasattr(instance, "get_swarm_status")
        assert hasattr(instance, "get_findings")
        # Standard queries from mixin
        assert hasattr(instance, "get_status")
        assert hasattr(instance, "get_events")

    def test_swarm_signals(self):
        """Test that swarm has signal handlers."""
        from kubani.syndicates.k8s_monitor.workflows.investigation import (
            K8sInvestigationSwarm,
        )

        instance = K8sInvestigationSwarm()

        # Swarm-specific signals
        assert hasattr(instance, "add_symptom")
        # Standard signals from mixin
        assert hasattr(instance, "pause")
        assert hasattr(instance, "resume")
        assert hasattr(instance, "cancel")


class TestK8sWorkerRegistration:
    """Tests for K8s Monitor worker registration."""

    def test_get_workflows(self):
        """Test that get_workflows returns correct workflows."""
        from kubani.syndicates.k8s_monitor.src.k8s_monitor_syndicate.worker import (
            get_workflows,
        )

        workflows = get_workflows()

        assert len(workflows) == 2
        workflow_names = [w.__name__ for w in workflows]
        assert "K8sRemediationWorkflow" in workflow_names
        assert "K8sInvestigationSwarm" in workflow_names

    def test_get_activities(self):
        """Test that get_activities returns correct activities."""
        from kubani.syndicates.k8s_monitor.src.k8s_monitor_syndicate.worker import (
            get_activities,
        )

        activities = get_activities()

        # Should have at least the core activities
        assert len(activities) >= 10
        activity_names = [a.__name__ for a in activities]
        assert "run_agent_activity" in activity_names
        assert "classify_event_activity" in activity_names
        assert "remediate_issue_activity" in activity_names
        assert "store_learning_activity" in activity_names

    def test_is_complex_issue_detection(self):
        """Test _is_complex_issue helper function."""
        from kubani.syndicates.k8s_monitor.src.k8s_monitor_syndicate.worker import (
            _is_complex_issue,
        )

        # Simple issues
        assert not _is_complex_issue({"reason": "OOMKilled", "severity": "warning"})
        assert not _is_complex_issue({"reason": "CrashLoopBackOff", "severity": "warning"})

        # Complex issues
        assert _is_complex_issue({"reason": "NodeNotReady", "severity": "warning"})
        assert _is_complex_issue({"reason": "OOMKilled", "severity": "critical"})
        assert _is_complex_issue({"reason": "Unknown", "message": "cascade failure detected"})
        assert _is_complex_issue({"reason": "Unknown", "count": 10})
