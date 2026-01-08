"""Tests for AgentWorker class."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core_agents.worker import (
    AgentWorker,
    AgentWorkerConfig,
    CommandConfig,
    ScheduledWorkflowConfig,
    setup_logging,
)


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_default(self):
        """Test default logging setup."""
        with patch("logging.basicConfig") as mock_basic_config:
            setup_logging()
            mock_basic_config.assert_called_once()

    def test_setup_logging_custom_level(self):
        """Test logging setup with custom level."""
        import logging

        with patch("logging.basicConfig") as mock_basic_config:
            setup_logging(level=logging.DEBUG)
            mock_basic_config.assert_called_once()
            call_kwargs = mock_basic_config.call_args[1]
            assert call_kwargs["level"] == logging.DEBUG


class TestAgentWorkerConfig:
    """Tests for AgentWorkerConfig dataclass."""

    def test_minimal_config(self):
        """Test creating config with minimal required fields."""
        config = AgentWorkerConfig(
            task_queue="test-queue",
            workflows=[],
            activities=[],
        )
        assert config.task_queue == "test-queue"
        assert config.workflows == []
        assert config.activities == []
        assert config.name == ""
        assert config.scheduled_workflows == []

    def test_full_config(self):
        """Test creating config with all fields."""

        class MockWorkflow:
            pass

        def mock_activity():
            pass

        async def mock_federated():
            pass

        config = AgentWorkerConfig(
            task_queue="test-queue",
            workflows=[MockWorkflow],
            activities=[mock_activity],
            name="test-agent",
            description="Test agent for testing",
            temporal_host_default="localhost:7233",
            temporal_namespace_default="test-ns",
            federated_agents_factory=mock_federated,
        )

        assert config.task_queue == "test-queue"
        assert config.name == "test-agent"
        assert config.temporal_host_default == "localhost:7233"
        assert config.federated_agents_factory is mock_federated


class TestScheduledWorkflowConfig:
    """Tests for ScheduledWorkflowConfig dataclass."""

    def test_scheduled_config(self):
        """Test creating scheduled workflow config."""

        class MockWorkflow:
            pass

        config = ScheduledWorkflowConfig(
            workflow_class=MockWorkflow,
            workflow_id="test-scheduled",
            default_interval_hours=2,
        )

        assert config.workflow_class is MockWorkflow
        assert config.workflow_id == "test-scheduled"
        assert config.default_interval_hours == 2
        assert config.default_args == []


class TestCommandConfig:
    """Tests for CommandConfig dataclass."""

    def test_command_config(self):
        """Test creating command config."""

        async def mock_handler(worker):
            pass

        config = CommandConfig(
            name="test-cmd",
            description="Test command",
            handler=mock_handler,
            args=["arg1"],
        )

        assert config.name == "test-cmd"
        assert config.description == "Test command"
        assert config.handler is mock_handler
        assert config.args == ["arg1"]


class TestAgentWorker:
    """Tests for AgentWorker class."""

    @pytest.fixture
    def basic_config(self):
        """Create a basic config for testing."""
        return AgentWorkerConfig(
            task_queue="test-agent",
            workflows=[],
            activities=[],
        )

    @pytest.fixture
    def worker(self, basic_config):
        """Create a worker with basic config."""
        return AgentWorker(basic_config)

    def test_init(self, basic_config):
        """Test worker initialization."""
        worker = AgentWorker(basic_config)
        assert worker.config is basic_config
        assert worker._client is None
        assert worker._worker is None

    def test_name_defaults_to_task_queue(self, worker):
        """Test that name defaults to task queue if not set."""
        assert worker.name == "test-agent"

    def test_name_uses_config_name(self):
        """Test that name uses config.name if set."""
        config = AgentWorkerConfig(
            task_queue="test-queue",
            workflows=[],
            activities=[],
            name="custom-name",
        )
        worker = AgentWorker(config)
        assert worker.name == "custom-name"

    def test_temporal_host_default(self, worker):
        """Test default Temporal host."""
        with patch.dict("os.environ", {}, clear=True):
            assert "temporal-frontend" in worker.temporal_host

    def test_temporal_host_from_env(self, worker):
        """Test Temporal host from environment."""
        with patch.dict("os.environ", {"TEMPORAL_HOST": "custom:7233"}):
            assert worker.temporal_host == "custom:7233"

    def test_temporal_namespace_default(self, worker):
        """Test default Temporal namespace."""
        with patch.dict("os.environ", {}, clear=True):
            assert worker.temporal_namespace == "default"

    def test_temporal_namespace_from_env(self, worker):
        """Test Temporal namespace from environment."""
        with patch.dict("os.environ", {"TEMPORAL_NAMESPACE": "custom-ns"}):
            assert worker.temporal_namespace == "custom-ns"

    def test_federated_agents_enabled_default(self, worker):
        """Test federated agents enabled by default."""
        with patch.dict("os.environ", {}, clear=True):
            assert worker.federated_agents_enabled is True

    def test_federated_agents_disabled(self, worker):
        """Test federated agents can be disabled."""
        with patch.dict("os.environ", {"ENABLE_FEDERATED_AGENTS": "false"}):
            assert worker.federated_agents_enabled is False

    @pytest.mark.asyncio
    async def test_connect(self, worker):
        """Test connecting to Temporal."""
        mock_client = MagicMock()

        with patch("core_agents.worker.Client") as MockClient:  # noqa: N806
            MockClient.connect = AsyncMock(return_value=mock_client)

            client = await worker.connect()

            assert client is mock_client
            MockClient.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_reuses_connection(self, worker):
        """Test that connect reuses existing connection."""
        mock_client = MagicMock()

        with patch("core_agents.worker.Client") as MockClient:  # noqa: N806
            MockClient.connect = AsyncMock(return_value=mock_client)

            client1 = await worker.connect()
            client2 = await worker.connect()

            assert client1 is client2
            assert MockClient.connect.call_count == 1

    @pytest.mark.asyncio
    async def test_run_startup_hooks(self, basic_config):
        """Test running startup hooks."""
        hook1 = AsyncMock()
        hook2 = AsyncMock()
        basic_config.startup_hooks = [hook1, hook2]

        worker = AgentWorker(basic_config)
        mock_client = MagicMock()

        with patch("core_agents.worker.Client") as MockClient:  # noqa: N806
            MockClient.connect = AsyncMock(return_value=mock_client)
            await worker.run_startup_hooks()

        hook1.assert_called_once_with(mock_client)
        hook2.assert_called_once_with(mock_client)

    @pytest.mark.asyncio
    async def test_run_startup_hooks_continues_on_error(self, basic_config):
        """Test that startup hooks continue even if one fails."""
        hook1 = AsyncMock(side_effect=Exception("hook1 failed"))
        hook2 = AsyncMock()
        basic_config.startup_hooks = [hook1, hook2]

        worker = AgentWorker(basic_config)
        mock_client = MagicMock()

        with patch("core_agents.worker.Client") as MockClient:  # noqa: N806
            MockClient.connect = AsyncMock(return_value=mock_client)
            await worker.run_startup_hooks()

        # hook2 should still be called despite hook1 failure
        hook2.assert_called_once_with(mock_client)

    @pytest.mark.asyncio
    async def test_start_scheduled_workflow_already_running(self, worker):
        """Test that scheduled workflow is not started if already running."""

        class MockWorkflow:
            pass

        sw_config = ScheduledWorkflowConfig(
            workflow_class=MockWorkflow,
            workflow_id="test-scheduled",
        )

        mock_client = MagicMock()
        mock_handle = MagicMock()
        mock_desc = MagicMock()
        mock_desc.status.name = "RUNNING"
        mock_handle.describe = AsyncMock(return_value=mock_desc)
        mock_client.get_workflow_handle.return_value = mock_handle

        with patch("core_agents.worker.Client") as MockClient:  # noqa: N806
            MockClient.connect = AsyncMock(return_value=mock_client)
            result = await worker.start_scheduled_workflow(sw_config)

        assert result is None

    @pytest.mark.asyncio
    async def test_start_scheduled_workflow_new(self, worker):
        """Test starting a new scheduled workflow."""

        class MockWorkflow:
            @staticmethod
            def run():
                pass

        sw_config = ScheduledWorkflowConfig(
            workflow_class=MockWorkflow,
            workflow_id="test-scheduled",
            default_interval_hours=4,
        )

        mock_client = MagicMock()
        mock_client.get_workflow_handle.side_effect = Exception("not found")
        mock_client.start_workflow = AsyncMock()

        with patch("core_agents.worker.Client") as MockClient:  # noqa: N806
            MockClient.connect = AsyncMock(return_value=mock_client)
            result = await worker.start_scheduled_workflow(sw_config)

        assert result == "test-scheduled"
        mock_client.start_workflow.assert_called_once()

    def test_run_with_help(self, worker, capsys):
        """Test run with --help shows help."""
        worker.run(["--help"])
        captured = capsys.readouterr()
        assert "Usage:" in captured.out
        assert "worker" in captured.out

    def test_run_unknown_command(self, worker, capsys):
        """Test run with unknown command shows error."""
        with pytest.raises(SystemExit):
            worker.run(["unknown-command"])

        captured = capsys.readouterr()
        assert "Unknown command" in captured.out


class TestAgentWorkerWithFederated:
    """Tests for AgentWorker with federated agents."""

    @pytest.fixture
    def federated_config(self):
        """Create config with federated agents."""

        async def mock_federated():
            await asyncio.sleep(0.1)

        return AgentWorkerConfig(
            task_queue="test-agent",
            workflows=[],
            activities=[],
            federated_agents_factory=mock_federated,
        )

    def test_run_federated_only_help(self, federated_config, capsys):
        """Test that federated-only appears in help."""
        worker = AgentWorker(federated_config)
        worker.run(["--help"])
        captured = capsys.readouterr()
        assert "federated-only" in captured.out
