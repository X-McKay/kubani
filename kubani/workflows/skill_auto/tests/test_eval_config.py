"""Tests for evaluation configuration."""

import pytest

from kubani.workflows.skill_auto.eval_config import (
    ComparisonReport,
    ConfigurationResult,
    EvalConfiguration,
    EvalMode,
    get_default_configurations,
    get_eval_mode,
    get_quick_configuration,
)


class TestEvalConfiguration:
    """Tests for EvalConfiguration dataclass."""

    def test_basic_creation(self):
        """Test basic config creation."""
        config = EvalConfiguration(
            name="test",
            display_name="Test Config",
            model="test-model",
            base_url="http://localhost:8000/v1",
            enable_thinking=True,
        )

        assert config.name == "test"
        assert config.display_name == "Test Config"
        assert config.model == "test-model"
        assert config.enable_thinking is True
        assert config.timeout == 300  # default

    def test_auto_description(self):
        """Test automatic description generation."""
        config = EvalConfiguration(
            name="test",
            display_name="Test",
            model="my-model",
            base_url="http://localhost/v1",
            enable_thinking=True,
        )
        assert "my-model" in config.description
        assert "reasoning" in config.description

        config_no_think = EvalConfiguration(
            name="test",
            display_name="Test",
            model="my-model",
            base_url="http://localhost/v1",
            enable_thinking=False,
        )
        assert "direct response" in config_no_think.description

    def test_custom_description(self):
        """Test custom description is preserved."""
        config = EvalConfiguration(
            name="test",
            display_name="Test",
            model="my-model",
            base_url="http://localhost/v1",
            enable_thinking=True,
            description="My custom description",
        )
        assert config.description == "My custom description"


class TestEvalMode:
    """Tests for EvalMode dataclass."""

    def test_basic_creation(self):
        """Test basic mode creation."""
        configs = [
            EvalConfiguration(
                name="test1",
                display_name="Test 1",
                model="model1",
                base_url="http://localhost/v1",
                enable_thinking=True,
            ),
            EvalConfiguration(
                name="test2",
                display_name="Test 2",
                model="model2",
                base_url="http://localhost/v1",
                enable_thinking=False,
            ),
        ]

        mode = EvalMode(
            name="test-mode",
            description="A test mode",
            configurations=configs,
        )

        assert mode.name == "test-mode"
        assert len(mode.configurations) == 2


class TestGetDefaultConfigurations:
    """Tests for get_default_configurations function."""

    def test_returns_four_configs(self):
        """Test that full mode returns 4 configurations."""
        configs = get_default_configurations()
        assert len(configs) == 4

    def test_config_names(self):
        """Test that configs have expected names."""
        configs = get_default_configurations()
        names = {c.name for c in configs}
        assert names == {"large-thinking", "large-no-think", "small-thinking", "small-no-think"}

    def test_thinking_modes(self):
        """Test that thinking modes are correctly set."""
        configs = get_default_configurations()
        config_dict = {c.name: c for c in configs}

        assert config_dict["large-thinking"].enable_thinking is True
        assert config_dict["large-no-think"].enable_thinking is False
        assert config_dict["small-thinking"].enable_thinking is True
        assert config_dict["small-no-think"].enable_thinking is False


class TestGetQuickConfiguration:
    """Tests for get_quick_configuration function."""

    def test_returns_single_config(self):
        """Test that quick mode returns single configuration."""
        config = get_quick_configuration()
        assert isinstance(config, EvalConfiguration)
        assert config.name == "default"

    def test_thinking_enabled(self):
        """Test that quick mode has thinking enabled."""
        config = get_quick_configuration()
        assert config.enable_thinking is True

    def test_custom_overrides(self):
        """Test that custom values override defaults."""
        config = get_quick_configuration(
            base_url="http://custom:8000/v1",
            model="custom-model",
        )
        assert config.base_url == "http://custom:8000/v1"
        assert config.model == "custom-model"


class TestGetEvalMode:
    """Tests for get_eval_mode function."""

    def test_quick_mode(self):
        """Test getting quick mode."""
        mode = get_eval_mode("quick")
        assert mode.name == "quick"
        assert len(mode.configurations) == 1

    def test_full_mode(self):
        """Test getting full mode."""
        mode = get_eval_mode("full")
        assert mode.name == "full"
        assert len(mode.configurations) == 4

    def test_invalid_mode(self):
        """Test that invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="Unknown eval mode"):
            get_eval_mode("invalid")


class TestConfigurationResult:
    """Tests for ConfigurationResult dataclass."""

    def test_basic_creation(self):
        """Test basic result creation."""
        config = EvalConfiguration(
            name="test",
            display_name="Test",
            model="model",
            base_url="http://localhost/v1",
            enable_thinking=True,
        )

        result = ConfigurationResult(
            config=config,
            metrics={
                "accuracy": 0.85,
                "avg_latency_ms": 250.0,
                "tests_passed": 8,
                "tests_total": 10,
                "avg_tokens_per_test": {"total": 500.0},
                "total_tokens": {"total": 5000},
            },
            test_results=[{"name": "test1", "passed": True}],
        )

        assert result.accuracy == 0.85
        assert result.avg_latency_ms == 250.0
        assert result.tests_passed == 8
        assert result.tests_total == 10
        assert result.avg_tokens == 500.0
        assert result.total_tokens == 5000

    def test_error_result(self):
        """Test result with error."""
        config = EvalConfiguration(
            name="test",
            display_name="Test",
            model="model",
            base_url="http://localhost/v1",
            enable_thinking=True,
        )

        result = ConfigurationResult(
            config=config,
            metrics={},
            test_results=[],
            error="Connection failed",
        )

        assert result.error == "Connection failed"
        assert result.accuracy == 0.0  # default when missing


class TestComparisonReport:
    """Tests for ComparisonReport dataclass."""

    def _create_result(self, name: str, accuracy: float, latency: float) -> ConfigurationResult:
        """Helper to create test results."""
        config = EvalConfiguration(
            name=name,
            display_name=name.title(),
            model="model",
            base_url="http://localhost/v1",
            enable_thinking=True,
        )
        return ConfigurationResult(
            config=config,
            metrics={
                "accuracy": accuracy,
                "avg_latency_ms": latency,
                "tests_passed": int(accuracy * 10),
                "tests_total": 10,
                "avg_tokens_per_test": {"total": 500.0},
                "total_tokens": {"total": 5000},
            },
            test_results=[],
        )

    def test_basic_creation(self):
        """Test basic report creation."""
        report = ComparisonReport(
            skill_name="test-skill",
            mode="full",
            timestamp="2024-01-01T00:00:00",
        )

        assert report.skill_name == "test-skill"
        assert report.mode == "full"
        assert len(report.results) == 0

    def test_configurations_property(self):
        """Test configurations property."""
        report = ComparisonReport(
            skill_name="test-skill",
            mode="full",
            timestamp="2024-01-01T00:00:00",
            results={
                "config1": self._create_result("config1", 0.9, 200),
                "config2": self._create_result("config2", 0.8, 150),
            },
        )

        assert set(report.configurations) == {"config1", "config2"}

    def test_get_result(self):
        """Test get_result method."""
        result1 = self._create_result("config1", 0.9, 200)
        report = ComparisonReport(
            skill_name="test-skill",
            mode="full",
            timestamp="2024-01-01T00:00:00",
            results={"config1": result1},
        )

        assert report.get_result("config1") is result1
        assert report.get_result("nonexistent") is None

    def test_comparison_matrix(self):
        """Test comparison matrix generation."""
        report = ComparisonReport(
            skill_name="test-skill",
            mode="full",
            timestamp="2024-01-01T00:00:00",
            results={
                "config1": self._create_result("config1", 0.9, 200),
                "config2": self._create_result("config2", 0.8, 150),
            },
        )

        matrix = report.get_comparison_matrix()
        assert matrix["accuracy"]["config1"] == 0.9
        assert matrix["accuracy"]["config2"] == 0.8
        assert matrix["avg_latency_ms"]["config1"] == 200
        assert matrix["avg_latency_ms"]["config2"] == 150

    def test_rankings(self):
        """Test rankings generation."""
        report = ComparisonReport(
            skill_name="test-skill",
            mode="full",
            timestamp="2024-01-01T00:00:00",
            results={
                "config1": self._create_result("config1", 0.9, 200),
                "config2": self._create_result("config2", 0.8, 150),
            },
        )

        rankings = report.get_rankings()

        # Higher accuracy is better, so config1 should be first
        assert rankings["accuracy"] == ["config1", "config2"]

        # Lower latency is better, so config2 should be first
        assert rankings["latency"] == ["config2", "config1"]

    def test_to_dict(self):
        """Test serialization to dict."""
        report = ComparisonReport(
            skill_name="test-skill",
            mode="full",
            timestamp="2024-01-01T00:00:00",
            results={"config1": self._create_result("config1", 0.9, 200)},
            summary="Test summary",
        )

        data = report.to_dict()

        assert data["skill_name"] == "test-skill"
        assert data["mode"] == "full"
        assert data["summary"] == "Test summary"
        assert "config1" in data["configurations"]
        assert "comparison" in data
        assert "rankings" in data
