"""Tests for model comparison matrix."""

from agent_framework.evaluation import MatrixResult, ModelMatrix
from agent_framework.evaluation.matrix import MatrixConfig


class TestModelMatrix:
    """Tests for ModelMatrix."""

    def test_parse_from_string(self):
        """Test matrix parsing from string."""
        matrix = ModelMatrix.from_string("model:opus,haiku thinking:on,off")

        assert len(matrix.dimensions) == 2
        assert matrix.dimensions[0].name == "model"
        assert matrix.dimensions[0].values == ["opus", "haiku"]
        assert matrix.dimensions[1].name == "thinking"
        assert matrix.dimensions[1].values == [True, False]

    def test_parse_single_dimension(self):
        """Test parsing single dimension."""
        matrix = ModelMatrix.from_string("model:local")

        assert len(matrix.dimensions) == 1
        assert matrix.dimensions[0].name == "model"
        assert matrix.dimensions[0].values == ["local"]

    def test_parse_empty_string(self):
        """Test parsing empty string."""
        matrix = ModelMatrix.from_string("")
        assert len(matrix.dimensions) == 0

    def test_generate_configs(self):
        """Test configuration generation."""
        matrix = ModelMatrix(
            [
                MatrixConfig("model", ["a", "b"]),
                MatrixConfig("thinking", [True, False]),
            ]
        )

        configs = matrix._generate_configs()

        assert len(configs) == 4
        assert {"model": "a", "thinking": True} in configs
        assert {"model": "a", "thinking": False} in configs
        assert {"model": "b", "thinking": True} in configs
        assert {"model": "b", "thinking": False} in configs

    def test_generate_configs_empty(self):
        """Test configuration generation with no dimensions."""
        matrix = ModelMatrix([])
        configs = matrix._generate_configs()
        assert configs == [{}]

    def test_check_assertions_exact_match(self):
        """Test assertion checking with exact match."""
        matrix = ModelMatrix([])

        assert matrix._check_assertions(
            {"status": "success"},
            {"status": "success"},
        )

        assert not matrix._check_assertions(
            {"status": "failure"},
            {"status": "success"},
        )

    def test_check_assertions_contains(self):
        """Test assertion checking with contains."""
        matrix = ModelMatrix([])

        assert matrix._check_assertions(
            {"summary": "Found OOM kill in logs"},
            {"summary": "contains:OOM"},
        )

        assert not matrix._check_assertions(
            {"summary": "Everything is fine"},
            {"summary": "contains:OOM"},
        )

    def test_check_assertions_empty_expected(self):
        """Test assertion checking with no expectations."""
        matrix = ModelMatrix([])

        assert matrix._check_assertions({"anything": "here"}, {})

    def test_model_configs_exist(self):
        """Test that known model configs are defined."""
        assert "local" in ModelMatrix.MODEL_CONFIGS
        assert "opus" in ModelMatrix.MODEL_CONFIGS
        assert "sonnet" in ModelMatrix.MODEL_CONFIGS
        assert "haiku" in ModelMatrix.MODEL_CONFIGS

    def test_create_llm_client(self):
        """Test LLM client creation from config."""
        matrix = ModelMatrix([])

        client = matrix._create_llm_client({"model": "local", "thinking": False})
        assert client.model == "Qwen3.5-9B-NVFP4"
        assert client.enable_thinking is False


class TestMatrixResult:
    """Tests for MatrixResult."""

    def test_result_creation(self):
        """Test MatrixResult can be created."""
        result = MatrixResult(
            config={"model": "local"},
            trace=None,
            metrics={"accuracy": 0.9, "latency_ms": 100, "tokens": 500},
        )

        assert result.config["model"] == "local"
        assert result.metrics["accuracy"] == 0.9
