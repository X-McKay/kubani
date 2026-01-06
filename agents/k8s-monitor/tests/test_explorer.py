"""Tests for the Explorer agent."""

from datetime import UTC, datetime

from k8s_monitor.federated.explorer import (
    ExplorerAgent,
    IncidentCluster,
    SkillProposal,
    UnmatchedIncident,
)


class TestUnmatchedIncident:
    """Tests for UnmatchedIncident dataclass."""

    def test_create_incident(self):
        """Test creating an unmatched incident."""
        incident = UnmatchedIncident(
            timestamp=datetime.now(UTC),
            reason="OOMKilled",
            message="Container was killed due to OOM",
            namespace="production",
            resource_name="my-pod-abc123",
            resource_kind="Pod",
        )

        assert incident.reason == "OOMKilled"
        assert incident.namespace == "production"
        assert incident.resource_kind == "Pod"


class TestIncidentCluster:
    """Tests for IncidentCluster dataclass."""

    def test_create_cluster(self):
        """Test creating an incident cluster."""
        incidents = [
            UnmatchedIncident(
                timestamp=datetime.now(UTC),
                reason="OOMKilled",
                message="Container killed",
                namespace="default",
                resource_name="pod-1",
                resource_kind="Pod",
            ),
            UnmatchedIncident(
                timestamp=datetime.now(UTC),
                reason="OOMKilled",
                message="Container killed",
                namespace="default",
                resource_name="pod-2",
                resource_kind="Pod",
            ),
        ]

        cluster = IncidentCluster(
            pattern="OOMKilled",
            incidents=incidents,
            frequency=2,
        )

        assert cluster.pattern == "OOMKilled"
        assert cluster.frequency == 2
        assert len(cluster.incidents) == 2

    def test_sample_incident(self):
        """Test getting sample incident from cluster."""
        incident = UnmatchedIncident(
            timestamp=datetime.now(UTC),
            reason="FailedMount",
            message="Volume mount failed",
            namespace="default",
            resource_name="pod-1",
            resource_kind="Pod",
        )

        cluster = IncidentCluster(
            pattern="FailedMount",
            incidents=[incident],
            frequency=1,
        )

        assert cluster.sample_incident is not None
        assert cluster.sample_incident.reason == "FailedMount"

    def test_sample_incident_empty(self):
        """Test sample incident when cluster is empty."""
        cluster = IncidentCluster(
            pattern="Empty",
            incidents=[],
            frequency=0,
        )

        assert cluster.sample_incident is None


class TestExplorerAgent:
    """Tests for ExplorerAgent."""

    def test_init(self):
        """Test Explorer initialization."""
        explorer = ExplorerAgent(
            min_cluster_size=5,
            lookback_days=14,
        )

        assert explorer.min_cluster_size == 5
        assert explorer.lookback_days == 14
        assert explorer.source_name == "k8s-explorer"

    def test_normalize_reason(self):
        """Test reason normalization for clustering."""
        explorer = ExplorerAgent()

        # Numbers should be replaced
        assert "N" in explorer._normalize_reason("Error after 5 retries")

        # Hashes should be replaced
        normalized = explorer._normalize_reason(
            "Pod abc123def456 failed"
        )  # pragma: allowlist secret
        assert "HASH" in normalized or "abc123def456" not in normalized  # pragma: allowlist secret

    def test_cluster_incidents(self):
        """Test clustering incidents by reason."""
        explorer = ExplorerAgent(min_cluster_size=2)

        # Add incidents with same pattern
        explorer._unmatched_incidents = [
            UnmatchedIncident(
                timestamp=datetime.now(UTC),
                reason="OOMKilled",
                message="Container 1 killed",
                namespace="default",
                resource_name="pod-1",
                resource_kind="Pod",
            ),
            UnmatchedIncident(
                timestamp=datetime.now(UTC),
                reason="OOMKilled",
                message="Container 2 killed",
                namespace="default",
                resource_name="pod-2",
                resource_kind="Pod",
            ),
            UnmatchedIncident(
                timestamp=datetime.now(UTC),
                reason="ImagePullBackOff",
                message="Single occurrence",
                namespace="default",
                resource_name="pod-3",
                resource_kind="Pod",
            ),
        ]

        clusters = explorer._cluster_incidents()

        # Only OOMKilled should form a cluster (2 >= min_cluster_size)
        assert len(clusters) == 1
        assert clusters[0].pattern == "OOMKilled"
        assert clusters[0].frequency == 2

    def test_cluster_incidents_sorted_by_frequency(self):
        """Test that clusters are sorted by frequency."""
        explorer = ExplorerAgent(min_cluster_size=2)

        # Add incidents
        explorer._unmatched_incidents = [
            UnmatchedIncident(
                timestamp=datetime.now(UTC),
                reason="OOMKilled",
                message="OOM 1",
                namespace="default",
                resource_name="pod-1",
                resource_kind="Pod",
            ),
            UnmatchedIncident(
                timestamp=datetime.now(UTC),
                reason="OOMKilled",
                message="OOM 2",
                namespace="default",
                resource_name="pod-2",
                resource_kind="Pod",
            ),
            UnmatchedIncident(
                timestamp=datetime.now(UTC),
                reason="FailedMount",
                message="Mount 1",
                namespace="default",
                resource_name="pod-3",
                resource_kind="Pod",
            ),
            UnmatchedIncident(
                timestamp=datetime.now(UTC),
                reason="FailedMount",
                message="Mount 2",
                namespace="default",
                resource_name="pod-4",
                resource_kind="Pod",
            ),
            UnmatchedIncident(
                timestamp=datetime.now(UTC),
                reason="FailedMount",
                message="Mount 3",
                namespace="default",
                resource_name="pod-5",
                resource_kind="Pod",
            ),
        ]

        clusters = explorer._cluster_incidents()

        # FailedMount should be first (3 > 2)
        assert len(clusters) == 2
        assert clusters[0].pattern == "FailedMount"
        assert clusters[0].frequency == 3
        assert clusters[1].pattern == "OOMKilled"
        assert clusters[1].frequency == 2

    def test_template_propose(self):
        """Test template-based skill proposal."""
        explorer = ExplorerAgent()

        incident = UnmatchedIncident(
            timestamp=datetime.now(UTC),
            reason="FailedScheduling",
            message="No nodes available",
            namespace="production",
            resource_name="my-pod",
            resource_kind="Pod",
        )

        cluster = IncidentCluster(
            pattern="FailedScheduling",
            incidents=[incident, incident, incident],
            frequency=3,
        )

        proposal = explorer._template_propose(cluster)

        assert proposal is not None
        assert isinstance(proposal, SkillProposal)
        assert "FailedScheduling" in proposal.skill.name
        assert proposal.skill.domain.value == "k8s"
        assert proposal.skill.category.value == "remediation"
        assert proposal.based_on_incidents == 3
        assert proposal.skill.requires_approval is True  # Template proposals require approval
        assert proposal.skill.confidence == 0.2  # Low initial confidence


class TestSkillProposal:
    """Tests for SkillProposal model."""

    def test_create_proposal(self):
        """Test creating a skill proposal."""
        from core_agents.skills import Skill, SkillCategory, SkillDomain

        skill = Skill(
            id="test-skill",
            name="Test Skill",
            domain=SkillDomain.K8S,
            category=SkillCategory.REMEDIATION,
            description="A test skill",
            preconditions=["Test precondition"],
            actions=[],
            success_criteria=["Test criterion"],
            failure_handling="Escalate",
        )

        proposal = SkillProposal(
            skill=skill,
            based_on_incidents=5,
            confidence_reason="Based on 5 similar incidents",
        )

        assert proposal.skill.id == "test-skill"
        assert proposal.based_on_incidents == 5
        assert proposal.requires_mcp_server is None

    def test_proposal_with_mcp_requirement(self):
        """Test proposal that requires an MCP server."""
        from core_agents.skills import Skill, SkillCategory, SkillDomain

        skill = Skill(
            id="metrics-skill",
            name="Metrics Analysis",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="Analyze metrics",
            preconditions=[],
            actions=[],
            success_criteria=[],
            failure_handling="",
        )

        proposal = SkillProposal(
            skill=skill,
            based_on_incidents=10,
            requires_mcp_server="prometheus-mcp-server",
            confidence_reason="Would need Prometheus for metrics queries",
        )

        assert proposal.requires_mcp_server == "prometheus-mcp-server"
