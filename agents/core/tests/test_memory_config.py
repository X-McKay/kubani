"""
Tests for core_agents.memory.config module.

Tests the mem0 configuration builders for Qdrant and Neo4j backends.
"""


class TestGetMem0Config:
    """Tests for get_mem0_config()."""

    def test_returns_valid_structure(self, mock_env_vars):
        """Test that config has all required keys."""
        from core_agents.memory import get_mem0_config

        config = get_mem0_config()

        assert "llm" in config
        assert "embedder" in config
        assert "vector_store" in config
        assert "version" in config

    def test_llm_config_structure(self, mock_env_vars):
        """Test LLM configuration structure."""
        from core_agents.memory import get_mem0_config

        config = get_mem0_config()

        assert config["llm"]["provider"] == "openai"
        assert "model" in config["llm"]["config"]
        assert "openai_base_url" in config["llm"]["config"]
        assert config["llm"]["config"]["temperature"] == 0.1

    def test_embedder_uses_lmstudio_provider(self, mock_env_vars):
        """Test that embedder uses lmstudio provider (for vLLM compatibility)."""
        from core_agents.memory import get_mem0_config

        config = get_mem0_config()

        # lmstudio provider doesn't pass dimensions= to API
        assert config["embedder"]["provider"] == "lmstudio"
        assert "lmstudio_base_url" in config["embedder"]["config"]

    def test_vector_store_uses_qdrant(self, mock_env_vars):
        """Test that vector store uses Qdrant."""
        from core_agents.memory import get_mem0_config

        config = get_mem0_config()

        assert config["vector_store"]["provider"] == "qdrant"
        assert "url" in config["vector_store"]["config"]
        assert "collection_name" in config["vector_store"]["config"]

    def test_environment_variable_resolution(self, mock_env_vars):
        """Test that config respects environment variables."""
        from core_agents.memory import get_mem0_config

        config = get_mem0_config()

        assert "localhost:6333" in config["vector_store"]["config"]["url"]
        assert config["vector_store"]["config"]["collection_name"] == "test-collection"
        assert config["llm"]["config"]["model"] == "test-model"

    def test_explicit_parameters_override_env(self, mock_env_vars):
        """Test that explicit parameters override environment variables."""
        from core_agents.memory import get_mem0_config

        config = get_mem0_config(
            qdrant_host="custom-host",
            collection_name="custom-collection",
            llm_model="custom-model",
        )

        assert "custom-host" in config["vector_store"]["config"]["url"]
        assert config["vector_store"]["config"]["collection_name"] == "custom-collection"
        assert config["llm"]["config"]["model"] == "custom-model"

    def test_includes_custom_fact_extraction_prompt(self, mock_env_vars):
        """Test that config includes custom fact extraction prompt for vLLM."""
        from core_agents.memory import get_mem0_config

        config = get_mem0_config()

        assert "custom_fact_extraction_prompt" in config
        assert "facts" in config["custom_fact_extraction_prompt"]


class TestGetGraphMem0Config:
    """Tests for get_graph_mem0_config()."""

    def test_includes_neo4j_config(self, mock_env_vars):
        """Test that graph config includes Neo4j configuration."""
        from core_agents.memory import get_graph_mem0_config

        config = get_graph_mem0_config()

        assert "graph_store" in config
        assert config["graph_store"]["provider"] == "neo4j"
        assert "url" in config["graph_store"]["config"]
        assert "username" in config["graph_store"]["config"]

    def test_inherits_base_config(self, mock_env_vars):
        """Test that graph config inherits from base mem0 config."""
        from core_agents.memory import get_graph_mem0_config

        config = get_graph_mem0_config()

        # Should have all base config keys
        assert "llm" in config
        assert "embedder" in config
        assert "vector_store" in config

    def test_custom_prompt_injection(self, mock_env_vars):
        """Test that custom graph prompt can be injected."""
        from core_agents.memory import get_graph_mem0_config

        custom_prompt = "Extract entities and relationships for testing."
        config = get_graph_mem0_config(graph_custom_prompt=custom_prompt)

        assert config["graph_store"]["custom_prompt"] == custom_prompt

    def test_neo4j_env_resolution(self, mock_env_vars):
        """Test that Neo4j config respects environment variables."""
        from core_agents.memory import get_graph_mem0_config

        config = get_graph_mem0_config()

        assert config["graph_store"]["config"]["url"] == "bolt://localhost:7687"
        assert config["graph_store"]["config"]["username"] == "neo4j"


class TestVLLMModelDimensions:
    """Tests for VLLM_MODEL_DIMENSIONS constant."""

    def test_known_models_have_dimensions(self):
        """Test that known models have dimension mappings."""
        from core_agents.memory import VLLM_MODEL_DIMENSIONS

        assert "Qwen/Qwen3-Embedding-0.6B" in VLLM_MODEL_DIMENSIONS
        assert VLLM_MODEL_DIMENSIONS["Qwen/Qwen3-Embedding-0.6B"] == 1024

    def test_auto_detection_for_known_model(self, mock_env_vars):
        """Test that dimensions are auto-detected for known models."""
        from core_agents.memory import get_mem0_config

        config = get_mem0_config()

        # Qwen3-Embedding-0.6B should auto-detect to 1024
        assert config["embedder"]["config"]["embedding_dims"] == 1024

    def test_explicit_dims_override_auto(self, mock_env_vars):
        """Test that explicit dimensions override auto-detection."""
        from core_agents.memory import get_mem0_config

        config = get_mem0_config(embedding_dims=2048)

        assert config["embedder"]["config"]["embedding_dims"] == 2048


class TestNoAgentSpecificContent:
    """Tests verifying core library is domain-agnostic."""

    def test_no_k8s_graph_prompt_in_core(self):
        """Test that K8S_GRAPH_PROMPT is not exported from core."""
        from core_agents import memory

        assert not hasattr(memory, "K8S_GRAPH_PROMPT")

    def test_no_news_graph_prompt_in_core(self):
        """Test that NEWS_GRAPH_PROMPT is not exported from core."""
        from core_agents import memory

        assert not hasattr(memory, "NEWS_GRAPH_PROMPT")

    def test_no_k8s_config_func_in_core(self):
        """Test that get_k8s_graph_mem0_config is not exported from core."""
        from core_agents import memory

        assert not hasattr(memory, "get_k8s_graph_mem0_config")

    def test_no_news_config_func_in_core(self):
        """Test that get_news_graph_mem0_config is not exported from core."""
        from core_agents import memory

        assert not hasattr(memory, "get_news_graph_mem0_config")
