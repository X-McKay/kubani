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
