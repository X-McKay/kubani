"""
Tests for the hierarchical agent structure.

Tests HandoffContext, TriageAgent, Diagnosticians, and K8sCoordinatorAgent.
"""

from datetime import UTC, datetime

from k8s_monitor.agents.context import (
    Finding,
    HandoffContext,
    RequestType,
    ResourceType,
    Severity,
    Urgency,
)
from k8s_monitor.agents.coordinator import K8sCoordinatorAgent, create_coordinator
from k8s_monitor.agents.diagnosis import (
    NetworkDiagnostician,
    NodeDiagnostician,
    PodDiagnostician,
    StorageDiagnostician,
)
from k8s_monitor.agents.triage import TriageAgent


class TestHandoffContext:
    """Tests for HandoffContext."""

    def test_create_for_health_check(self):
        """Test creating context for health check."""
        context = HandoffContext.for_health_check("Check cluster status")

        assert context.request_type == RequestType.HEALTH_CHECK
        assert context.original_prompt == "Check cluster status"
        assert context.request_id is not None
        assert len(context.request_id) > 0

    def test_create_for_issue(self):
        """Test creating context for issue investigation."""
        context = HandoffContext.for_issue(
            prompt="Pod crashing",
            resource_type=ResourceType.POD,
            resource_name="my-pod",
            namespace="default",
        )

        assert context.request_type == RequestType.ISSUE_INVESTIGATION
        assert context.resource_type == ResourceType.POD
        assert context.resource_name == "my-pod"
        assert context.namespace == "default"

    def test_add_finding(self):
        """Test adding findings to context."""
        context = HandoffContext.for_issue("Pod issue")
        context.add_finding(
            agent="test_agent",
            description="Found OOMKilled",
            evidence={"restart_count": 5},
            severity=Severity.CRITICAL,
        )

        assert len(context.findings) == 1
        finding = context.findings[0]
        assert finding.agent == "test_agent"
        assert finding.description == "Found OOMKilled"
        assert finding.evidence == {"restart_count": 5}
        assert finding.severity == Severity.CRITICAL

    def test_add_evidence(self):
        """Test adding evidence to context."""
        context = HandoffContext.for_issue("Node issue")
        context.add_evidence("node_status", "NotReady")
        context.add_evidence("memory_pressure", True)

        assert context.evidence["node_status"] == "NotReady"
        assert context.evidence["memory_pressure"] is True

    def test_get_summary(self):
        """Test context summary generation."""
        context = HandoffContext.for_issue(
            prompt="Pod crashing",
            resource_type=ResourceType.POD,
            resource_name="my-pod",
            namespace="production",
        )
        context.severity = Severity.WARNING
        context.add_finding(
            agent="triage",
            description="Pod in CrashLoopBackOff",
            severity=Severity.WARNING,
        )

        summary = context.get_summary()

        assert "issue_investigation" in summary.lower()
        assert "pod" in summary.lower()
        assert "my-pod" in summary.lower()
        assert "warning" in summary.lower()

    def test_to_dict(self):
        """Test context serialization."""
        context = HandoffContext.for_issue("Test issue")
        context.severity = Severity.INFO
        context.add_finding(
            agent="test",
            description="Test finding",
            severity=Severity.INFO,
        )

        data = context.to_dict()

        assert "request_id" in data
        assert "request_type" in data
        assert "original_prompt" in data
        # to_dict returns findings_count, not findings list
        assert "findings_count" in data
        assert data["findings_count"] == 1


class TestFinding:
    """Tests for Finding dataclass."""

    def test_finding_creation(self):
        """Test creating a Finding."""
        finding = Finding(
            agent="pod_diagnostician",
            timestamp=datetime.now(UTC),
            description="Container OOMKilled",
            evidence={"exit_code": 137},
            severity=Severity.CRITICAL,
        )

        assert finding.agent == "pod_diagnostician"
        assert finding.severity == Severity.CRITICAL
        assert finding.evidence["exit_code"] == 137

    def test_finding_default_severity(self):
        """Test Finding default severity is None."""
        finding = Finding(
            agent="test",
            timestamp=datetime.now(UTC),
            description="Just info",
        )

        # Default severity is None in the dataclass
        assert finding.severity is None


class TestResourceType:
    """Tests for ResourceType enum."""

    def test_resource_types(self):
        """Test all expected resource types exist."""
        # Values are capitalized Kubernetes resource names
        assert ResourceType.POD.value == "Pod"
        assert ResourceType.NODE.value == "Node"
        assert ResourceType.DEPLOYMENT.value == "Deployment"
        assert ResourceType.SERVICE.value == "Service"
        assert ResourceType.PVC.value == "PersistentVolumeClaim"
        assert ResourceType.INGRESS.value == "Ingress"
        assert ResourceType.NETWORK_POLICY.value == "NetworkPolicy"


class TestSeverity:
    """Tests for Severity enum."""

    def test_severity_levels(self):
        """Test severity levels."""
        assert Severity.CRITICAL.value == "critical"
        assert Severity.WARNING.value == "warning"
        assert Severity.INFO.value == "info"


class TestUrgency:
    """Tests for Urgency enum."""

    def test_urgency_levels(self):
        """Test urgency levels."""
        assert Urgency.IMMEDIATE.value == "immediate"
        assert Urgency.SOON.value == "soon"
        assert Urgency.SCHEDULED.value == "scheduled"


class TestDiagnosticians:
    """Tests for diagnostician agents."""

    def test_pod_diagnostician_can_handle(self):
        """Test PodDiagnostician handles pod resources."""
        diag = PodDiagnostician()

        assert diag.can_handle(ResourceType.POD)
        assert diag.can_handle(ResourceType.DEPLOYMENT)
        assert not diag.can_handle(ResourceType.NODE)

    def test_node_diagnostician_can_handle(self):
        """Test NodeDiagnostician handles node resources."""
        diag = NodeDiagnostician()

        assert diag.can_handle(ResourceType.NODE)
        assert not diag.can_handle(ResourceType.POD)

    def test_network_diagnostician_can_handle(self):
        """Test NetworkDiagnostician handles network resources."""
        diag = NetworkDiagnostician()

        # NetworkDiagnostician handles SERVICE, INGRESS, NETWORK_POLICY
        assert diag.can_handle(ResourceType.SERVICE)
        assert diag.can_handle(ResourceType.INGRESS)
        assert diag.can_handle(ResourceType.NETWORK_POLICY)
        assert not diag.can_handle(ResourceType.NODE)

    def test_storage_diagnostician_can_handle(self):
        """Test StorageDiagnostician handles storage resources."""
        diag = StorageDiagnostician()

        # StorageDiagnostician handles PVC
        assert diag.can_handle(ResourceType.PVC)
        assert not diag.can_handle(ResourceType.POD)

    def test_diagnostician_diagnostic_steps(self):
        """Test diagnosticians return diagnostic steps."""
        diag = PodDiagnostician()
        steps = diag.get_diagnostic_steps()

        assert isinstance(steps, list)
        assert len(steps) > 0


class TestTriageAgent:
    """Tests for TriageAgent."""

    def test_triage_agent_creation(self):
        """Test TriageAgent can be instantiated."""
        agent = TriageAgent()

        assert agent.NAME == "triage_agent"
        assert agent.DESCRIPTION is not None

    def test_triage_extracts_resource_type(self):
        """Test TriageAgent extracts resource type from result."""
        agent = TriageAgent()

        # TriageAgent maps lowercase "pod" to ResourceType.POD
        result = """
RESOURCE_TYPE: pod
SEVERITY: warning
URGENCY: immediate
SUMMARY: Pod is crashing
"""
        resource_type = agent._extract_resource_type(result)

        assert resource_type == ResourceType.POD

    def test_triage_extracts_severity(self):
        """Test TriageAgent extracts severity from result."""
        agent = TriageAgent()

        result = "SEVERITY: critical\nRESOURCE_TYPE: node"
        severity = agent._extract_severity(result)

        assert severity == Severity.CRITICAL

    def test_triage_extracts_urgency(self):
        """Test TriageAgent extracts urgency from result."""
        agent = TriageAgent()

        # Urgency values: immediate, soon, scheduled
        result = "URGENCY: immediate\nSEVERITY: critical"
        urgency = agent._extract_urgency(result)

        assert urgency == Urgency.IMMEDIATE

    def test_triage_handles_missing_fields(self):
        """Test TriageAgent handles missing fields gracefully."""
        agent = TriageAgent()

        result = "Some unstructured text response"

        assert agent._extract_resource_type(result) is None
        assert agent._extract_severity(result) is None
        assert agent._extract_urgency(result) is None


class TestK8sCoordinatorAgent:
    """Tests for K8sCoordinatorAgent."""

    def test_coordinator_creation(self):
        """Test K8sCoordinatorAgent can be instantiated."""
        coordinator = K8sCoordinatorAgent()

        assert coordinator.NAME == "k8s_coordinator"

    def test_create_coordinator_factory(self):
        """Test create_coordinator factory function."""
        coordinator = create_coordinator()

        assert isinstance(coordinator, K8sCoordinatorAgent)

    def test_coordinator_has_sub_agents(self):
        """Test coordinator initializes sub-agents."""
        coordinator = K8sCoordinatorAgent()

        assert coordinator._triage is not None
        assert coordinator._scout is not None
        assert coordinator._discord is not None
        assert coordinator._remediator is not None
        assert coordinator._memory is not None

    def test_coordinator_has_diagnosticians(self):
        """Test coordinator initializes diagnosticians."""
        coordinator = K8sCoordinatorAgent()

        assert coordinator._pod_diag is not None
        assert coordinator._node_diag is not None
        assert coordinator._network_diag is not None
        assert coordinator._storage_diag is not None

    def test_coordinator_selects_diagnostician(self):
        """Test coordinator selects appropriate diagnostician."""
        coordinator = K8sCoordinatorAgent()

        pod_diag = coordinator._select_diagnostician(ResourceType.POD)
        assert isinstance(pod_diag, PodDiagnostician)

        node_diag = coordinator._select_diagnostician(ResourceType.NODE)
        assert isinstance(node_diag, NodeDiagnostician)

        network_diag = coordinator._select_diagnostician(ResourceType.SERVICE)
        assert isinstance(network_diag, NetworkDiagnostician)

        storage_diag = coordinator._select_diagnostician(ResourceType.PVC)
        assert isinstance(storage_diag, StorageDiagnostician)

    def test_coordinator_selects_none_for_unknown(self):
        """Test coordinator returns None for unknown resource type."""
        coordinator = K8sCoordinatorAgent()

        result = coordinator._select_diagnostician(None)
        assert result is None


class TestBaseDiagnostician:
    """Tests for BaseDiagnostician base class."""

    def test_extract_field(self):
        """Test _extract_field helper."""
        diag = PodDiagnostician()

        text = """
ROOT_CAUSE: Memory limit exceeded
SEVERITY: critical
EVIDENCE: Container exceeded 512Mi limit
REMEDIABLE: yes
PROPOSED_FIX: Increase memory limit
"""
        assert diag._extract_field(text, "ROOT_CAUSE") == "Memory limit exceeded"
        assert diag._extract_field(text, "SEVERITY") == "critical"
        assert diag._extract_field(text, "REMEDIABLE") == "yes"

    def test_extract_field_handles_missing(self):
        """Test _extract_field returns None for missing fields."""
        diag = PodDiagnostician()

        text = "Some text without the field"
        assert diag._extract_field(text, "NONEXISTENT") is None
