"""Unit tests for database models."""

from datetime import UTC, datetime

from kubani_registry.db.models import (
    Agent,
    AgentCapability,
    Deployment,
    Endpoint,
    MCPServer,
    Model,
    SkillMetadata,
)


class TestAgentModel:
    """Test Agent model."""

    def test_to_dict_basic(self):
        """Test basic to_dict conversion."""
        agent = Agent(
            id="test-agent",
            name="Test Agent",
            description="A test agent",
            version="1.0.0",
            status="healthy",
            metadata_={"env": "test"},
        )
        agent.capabilities = []
        agent.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        agent.updated_at = datetime(2024, 1, 1, tzinfo=UTC)

        result = agent.to_dict()

        assert result["id"] == "test-agent"
        assert result["name"] == "Test Agent"
        assert result["metadata"] == {"env": "test"}
        assert result["status"] == "healthy"
        assert result["capabilities"] == []

    def test_to_dict_with_capabilities(self):
        """Test to_dict with capabilities."""
        agent = Agent(
            id="cap-agent",
            name="Cap Agent",
            status="healthy",
            metadata_={},
        )
        agent.capabilities = [
            AgentCapability(
                name="analyze",
                description="Analyze things",
                input_schema={"type": "object"},
                output_schema={"type": "string"},
                tags=["analysis"],
            ),
        ]
        agent.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        agent.updated_at = datetime(2024, 1, 1, tzinfo=UTC)

        result = agent.to_dict()

        assert len(result["capabilities"]) == 1
        assert result["capabilities"][0]["name"] == "analyze"
        assert result["capabilities"][0]["tags"] == ["analysis"]

    def test_to_dict_empty_metadata(self):
        """Test to_dict handles None metadata."""
        agent = Agent(
            id="no-meta",
            name="No Metadata",
            status="unknown",
            metadata_=None,
        )
        agent.capabilities = []
        agent.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        agent.updated_at = datetime(2024, 1, 1, tzinfo=UTC)

        result = agent.to_dict()

        assert result["metadata"] == {}


class TestModelModel:
    """Test Model model."""

    def test_to_dict_basic(self):
        """Test basic to_dict conversion."""
        model = Model(
            id="nvidia/Qwen3-14B-FP4",
            name="Qwen3-14B-FP4",
            model_type="general",
            provider="nvidia",
            quantization="FP4",
            context_length=32768,
            vram_required_gb=8.0,
            capabilities={"tool_use": True},
            status="available",
            metadata_={"source": "huggingface"},
        )
        model.created_at = datetime(2024, 1, 1, tzinfo=UTC)

        result = model.to_dict()

        assert result["id"] == "nvidia/Qwen3-14B-FP4"
        assert result["model_type"] == "general"
        assert result["capabilities"] == {"tool_use": True}
        assert result["metadata"] == {"source": "huggingface"}

    def test_to_dict_empty_metadata(self):
        """Test to_dict handles None metadata."""
        model = Model(
            id="test-model",
            name="Test Model",
            model_type="embeddings",
            capabilities={},
            metadata_=None,
        )
        model.created_at = datetime(2024, 1, 1, tzinfo=UTC)

        result = model.to_dict()

        assert result["metadata"] == {}


class TestEndpointModel:
    """Test Endpoint model."""

    def test_to_dict_basic(self):
        """Test basic to_dict conversion."""
        endpoint = Endpoint(
            id="vllm-general",
            name="vLLM General",
            service_type="llm",
            internal_url="http://vllm.vllm.svc:8000/v1",
            external_url="https://llm.almckay.io/v1",
            health_check_path="/health",
            status="healthy",
            namespace="vllm",
            environment="production",
            metadata_={"gpu": "rtx4090"},
        )
        endpoint.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        endpoint.updated_at = datetime(2024, 1, 1, tzinfo=UTC)

        result = endpoint.to_dict()

        assert result["id"] == "vllm-general"
        assert result["service_type"] == "llm"
        assert result["internal_url"] == "http://vllm.vllm.svc:8000/v1"
        assert result["metadata"] == {"gpu": "rtx4090"}

    def test_to_dict_empty_metadata(self):
        """Test to_dict handles None metadata."""
        endpoint = Endpoint(
            id="test-endpoint",
            name="Test Endpoint",
            service_type="database",
            health_check_path="/health",
            status="unknown",
            environment="production",
            metadata_=None,
        )
        endpoint.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        endpoint.updated_at = datetime(2024, 1, 1, tzinfo=UTC)

        result = endpoint.to_dict()

        assert result["metadata"] == {}


class TestMCPServerModel:
    """Test MCPServer model."""

    def test_create_mcp_server(self):
        """Test creating an MCP server."""
        server = MCPServer(
            id="kubernetes-mcp",
            name="Kubernetes MCP",
            transport="stdio",
            connection_config={"command": "uv", "args": ["run", "kubernetes-mcp"]},
            capabilities=["pods_list", "pods_log"],
            namespaces=["ai-agents"],
            read_only=True,
        )

        assert server.id == "kubernetes-mcp"
        assert server.transport == "stdio"
        assert server.read_only is True


class TestSkillMetadataModel:
    """Test SkillMetadata model."""

    def test_create_skill_metadata(self):
        """Test creating skill metadata."""
        skill = SkillMetadata(
            id="diagnose-pod-crash",
            name="Diagnose Pod Crash",
            domain="kubernetes",
            category="diagnostics",
            confidence=0.8,
            success_count=10,
            failure_count=2,
        )

        assert skill.id == "diagnose-pod-crash"
        assert skill.confidence == 0.8
        assert skill.success_count == 10


class TestDeploymentModel:
    """Test Deployment model."""

    def test_create_deployment(self):
        """Test creating a deployment."""
        deployment = Deployment(
            agent_id="k8s-monitor",
            version="0.2.15",
            image_tag="0.2.15-abc1234",
            git_sha="abc1234",
            deployed_by="ci-bot",
            status="active",
        )

        assert deployment.agent_id == "k8s-monitor"
        assert deployment.version == "0.2.15"
        assert deployment.status == "active"


class TestSyndicateModel:
    """Test Syndicate model."""

    def test_create_syndicate(self):
        """Test creating a syndicate."""
        from kubani_registry.db.models import Syndicate

        syndicate = Syndicate(
            id="k8s-monitor",
            name="K8s Monitor",
            description="Kubernetes monitoring syndicate",
            status="draft",
            created_by="human",
        )
        syndicate.versions = []
        syndicate.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        syndicate.updated_at = datetime(2024, 1, 1, tzinfo=UTC)

        assert syndicate.id == "k8s-monitor"
        assert syndicate.name == "K8s Monitor"
        assert syndicate.status == "draft"
        assert syndicate.versions == []

    def test_syndicate_to_dict(self):
        """Test Syndicate to_dict conversion."""
        from kubani_registry.db.models import Syndicate

        syndicate = Syndicate(
            id="k8s-monitor",
            name="K8s Monitor",
            description="Kubernetes monitoring syndicate",
            status="production",
            current_version="1.0.0",
            oci_repository="registry.almckay.io/syndicates/k8s-monitor",
            created_by="human",
            metadata_={"team": "platform"},
        )
        syndicate.versions = []
        syndicate.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        syndicate.updated_at = datetime(2024, 1, 1, tzinfo=UTC)

        result = syndicate.to_dict()

        assert result["id"] == "k8s-monitor"
        assert result["name"] == "K8s Monitor"
        assert result["current_version"] == "1.0.0"
        assert result["oci_repository"] == "registry.almckay.io/syndicates/k8s-monitor"
        assert result["metadata"] == {"team": "platform"}


class TestSyndicateVersionModel:
    """Test SyndicateVersion model."""

    def test_create_syndicate_version(self):
        """Test creating a syndicate version."""
        from kubani_registry.db.models import SyndicateVersion

        version = SyndicateVersion(
            syndicate_id="k8s-monitor",
            version="1.0.0",
            oci_tag="v1.0.0",
            oci_digest="sha256:abc123",
            status="draft",
            agent_refs=[
                {"agent": "event-classifier", "version": "2.0.0"},
                {"agent": "remediator", "version": "1.5.0"},
            ],
            created_by="human",
        )
        version.created_at = datetime(2024, 1, 1, tzinfo=UTC)

        assert version.syndicate_id == "k8s-monitor"
        assert version.version == "1.0.0"
        assert version.oci_tag == "v1.0.0"
        assert len(version.agent_refs) == 2
        assert version.agent_refs[0]["agent"] == "event-classifier"


class TestAgentVersionModel:
    """Test AgentVersion model."""

    def test_create_agent_version(self):
        """Test creating an agent version."""
        from kubani_registry.db.models import AgentVersion

        version = AgentVersion(
            agent_id="event-classifier",
            version="2.0.0",
            oci_tag="v2.0.0",
            oci_digest="sha256:def456",
            status="production",
            created_by="human",
            changelog="Added new event types support",
        )
        version.created_at = datetime(2024, 1, 1, tzinfo=UTC)

        assert version.agent_id == "event-classifier"
        assert version.version == "2.0.0"
        assert version.status == "production"
        assert version.oci_digest == "sha256:def456"


class TestSkillModel:
    """Test Skill model."""

    def test_create_skill_with_oci_fields(self):
        """Test creating a skill with OCI fields."""
        from kubani_registry.db.models import Skill

        skill = Skill(
            name="investigate-pod-failure",
            description="Investigate why a pod is failing",
            category="k8s/diagnostic",
            status="production",
            current_version="1.0.0",
            oci_repository="registry.almckay.io/skills/investigate-pod-failure",
            domain="kubernetes",
            confidence=0.85,
            success_count=100,
            failure_count=5,
            requires_approval=False,
        )
        skill.versions = []
        skill.evaluations = []
        skill.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        skill.updated_at = datetime(2024, 1, 1, tzinfo=UTC)

        assert skill.name == "investigate-pod-failure"
        assert skill.oci_repository == "registry.almckay.io/skills/investigate-pod-failure"
        assert skill.confidence == 0.85
        assert skill.success_count == 100


class TestSkillVersionModel:
    """Test SkillVersion model."""

    def test_create_skill_version_with_oci_fields(self):
        """Test creating a skill version with OCI fields."""
        from kubani_registry.db.models import SkillVersion

        version = SkillVersion(
            skill_id=1,
            version="1.0.0",
            oci_tag="v1.0.0",
            oci_digest="sha256:ghi789",
            status="production",
            created_by="agent:skill-learner",
            changelog="Initial version",
        )
        version.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        version.promoted_at = datetime(2024, 1, 2, tzinfo=UTC)
        version.promoted_by = "human:admin"

        assert version.version == "1.0.0"
        assert version.oci_tag == "v1.0.0"
        assert version.status == "production"
        assert version.promoted_by == "human:admin"


class TestResourceStatus:
    """Test ResourceStatus enum."""

    def test_promotion_order(self):
        """Test the promotion order."""
        from kubani_registry.constants import ResourceStatus

        order = ResourceStatus.promotion_order()

        assert order == [
            ResourceStatus.DRAFT,
            ResourceStatus.TESTING,
            ResourceStatus.STAGING,
            ResourceStatus.PRODUCTION,
        ]

    def test_can_promote_to_valid(self):
        """Test valid promotion paths."""
        from kubani_registry.constants import ResourceStatus

        assert ResourceStatus.DRAFT.can_promote_to(ResourceStatus.TESTING)
        assert ResourceStatus.TESTING.can_promote_to(ResourceStatus.STAGING)
        assert ResourceStatus.STAGING.can_promote_to(ResourceStatus.PRODUCTION)

    def test_can_promote_to_invalid(self):
        """Test invalid promotion paths."""
        from kubani_registry.constants import ResourceStatus

        # Can't skip stages
        assert not ResourceStatus.DRAFT.can_promote_to(ResourceStatus.PRODUCTION)
        assert not ResourceStatus.DRAFT.can_promote_to(ResourceStatus.STAGING)

        # Can't go backwards
        assert not ResourceStatus.PRODUCTION.can_promote_to(ResourceStatus.DRAFT)
        assert not ResourceStatus.STAGING.can_promote_to(ResourceStatus.TESTING)

        # Deprecated is not in promotion order
        assert not ResourceStatus.DEPRECATED.can_promote_to(ResourceStatus.TESTING)
        assert not ResourceStatus.PRODUCTION.can_promote_to(ResourceStatus.DEPRECATED)


class TestResourceType:
    """Test ResourceType enum."""

    def test_resource_types(self):
        """Test resource type values."""
        from kubani_registry.constants import ResourceType

        assert ResourceType.SKILL.value == "skill"
        assert ResourceType.AGENT.value == "agent"
        assert ResourceType.SYNDICATE.value == "syndicate"


class TestAgentModelWithOciFields:
    """Test Agent model with new OCI fields."""

    def test_agent_with_oci_fields(self):
        """Test Agent with OCI repository and version fields."""
        agent = Agent(
            id="event-classifier",
            name="Event Classifier",
            description="Classifies Kubernetes events",
            version="2.0.0",
            status="healthy",
            current_version="2.0.0",
            oci_repository="registry.almckay.io/agents/event-classifier",
            created_by="human",
            metadata_={},
        )
        agent.capabilities = []
        agent.versions = []
        agent.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        agent.updated_at = datetime(2024, 1, 1, tzinfo=UTC)

        result = agent.to_dict()

        assert result["current_version"] == "2.0.0"
        assert result["oci_repository"] == "registry.almckay.io/agents/event-classifier"
        assert result["created_by"] == "human"
