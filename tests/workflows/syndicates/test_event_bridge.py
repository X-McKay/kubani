"""Tests for Event Bus to Temporal Bridge.

These tests verify the bridge configuration and trigger utilities.
Full integration tests require running Temporal and Redis.
"""


class TestWorkflowTrigger:
    """Tests for WorkflowTrigger configuration."""

    def test_workflow_trigger_imports(self):
        """Test that WorkflowTrigger can be imported."""
        from kubani.framework.temporal import WorkflowTrigger

        assert WorkflowTrigger is not None

    def test_workflow_trigger_basic_config(self):
        """Test basic WorkflowTrigger configuration."""
        from datetime import timedelta

        from kubani.framework.temporal import WorkflowTrigger

        trigger = WorkflowTrigger(
            event_type="k8s:issue_detected",
            workflow_type=object,  # Placeholder
            task_queue="test-queue",
            input_mapper=lambda e: {"event_id": e.id},
        )

        assert trigger.event_type == "k8s:issue_detected"
        assert trigger.task_queue == "test-queue"
        assert trigger.condition is None
        assert trigger.publish_result is True
        assert trigger.execution_timeout == timedelta(hours=1)

    def test_workflow_trigger_with_condition(self):
        """Test WorkflowTrigger with condition function."""
        from kubani.framework.temporal import WorkflowTrigger

        def is_critical(event):
            return event.payload.get("severity") == "critical"

        trigger = WorkflowTrigger(
            event_type="k8s:issue_detected",
            workflow_type=object,
            task_queue="test-queue",
            input_mapper=lambda e: {},
            condition=is_critical,
        )

        assert trigger.condition is not None
        # The condition function is stored and can be called
        assert callable(trigger.condition)

    def test_workflow_trigger_custom_id_template(self):
        """Test WorkflowTrigger with custom ID template."""
        from kubani.framework.temporal import WorkflowTrigger

        trigger = WorkflowTrigger(
            event_type="k8s:issue_detected",
            workflow_type=object,
            task_queue="test-queue",
            input_mapper=lambda e: {},
            workflow_id_template="custom-{event_id}-{timestamp}",
        )

        assert trigger.workflow_id_template == "custom-{event_id}-{timestamp}"


class TestBridgeConfig:
    """Tests for BridgeConfig."""

    def test_bridge_config_imports(self):
        """Test that BridgeConfig can be imported."""
        from kubani.framework.temporal import BridgeConfig

        assert BridgeConfig is not None

    def test_bridge_config_defaults(self):
        """Test BridgeConfig default values."""
        from kubani.framework.temporal import BridgeConfig

        config = BridgeConfig()

        assert config.consumer_group == "temporal-bridge"
        assert config.consumer_name == "bridge-0"
        assert config.batch_size == 10
        assert config.poll_interval_ms == 1000
        assert config.max_retries == 3
        assert config.retry_delay_seconds == 5.0

    def test_bridge_config_custom_values(self):
        """Test BridgeConfig with custom values."""
        from kubani.framework.temporal import BridgeConfig

        config = BridgeConfig(
            consumer_group="custom-bridge",
            consumer_name="custom-0",
            batch_size=50,
            poll_interval_ms=500,
            max_retries=5,
            retry_delay_seconds=10.0,
        )

        assert config.consumer_group == "custom-bridge"
        assert config.consumer_name == "custom-0"
        assert config.batch_size == 50
        assert config.poll_interval_ms == 500
        assert config.max_retries == 5
        assert config.retry_delay_seconds == 10.0


class TestEventBridge:
    """Tests for EventBridge class."""

    def test_event_bridge_imports(self):
        """Test that EventBridge can be imported."""
        from kubani.framework.temporal import EventBridge

        assert EventBridge is not None

    def test_event_bridge_trigger_indexing(self):
        """Test that EventBridge indexes triggers by event type."""
        from unittest.mock import MagicMock

        from kubani.framework.temporal import EventBridge, WorkflowTrigger

        # Create mock client
        mock_client = MagicMock()

        # Create triggers with different event types
        triggers = [
            WorkflowTrigger(
                event_type="k8s:issue_detected",
                workflow_type=object,
                task_queue="queue-1",
                input_mapper=lambda e: {},
            ),
            WorkflowTrigger(
                event_type="k8s:issue_detected",
                workflow_type=object,
                task_queue="queue-2",
                input_mapper=lambda e: {},
            ),
            WorkflowTrigger(
                event_type="news:collection_requested",
                workflow_type=object,
                task_queue="queue-3",
                input_mapper=lambda e: {},
            ),
        ]

        bridge = EventBridge(mock_client, triggers)

        # Check trigger map
        assert "k8s:issue_detected" in bridge._trigger_map
        assert "news:collection_requested" in bridge._trigger_map
        assert len(bridge._trigger_map["k8s:issue_detected"]) == 2
        assert len(bridge._trigger_map["news:collection_requested"]) == 1


class TestNewsTriggerFactory:
    """Tests for create_news_triggers factory function."""

    def test_create_news_triggers_imports(self):
        """Test that create_news_triggers can be imported."""
        from kubani.framework.temporal import create_news_triggers

        assert create_news_triggers is not None
        assert callable(create_news_triggers)

    def test_create_news_triggers_returns_list(self):
        """Test that create_news_triggers returns a list of triggers."""
        from kubani.framework.temporal import WorkflowTrigger, create_news_triggers

        triggers = create_news_triggers()

        assert isinstance(triggers, list)
        assert len(triggers) >= 1
        for trigger in triggers:
            assert isinstance(trigger, WorkflowTrigger)

    def test_news_triggers_event_types(self):
        """Test that news triggers cover expected event types."""
        from kubani.framework.temporal import create_news_triggers

        triggers = create_news_triggers()
        event_types = [t.event_type for t in triggers]

        # Should have trigger for collection requests
        assert "news:collection_requested" in event_types


class TestWorkflowResultPublisher:
    """Tests for WorkflowResultPublisher."""

    def test_result_publisher_imports(self):
        """Test that WorkflowResultPublisher can be imported."""
        from kubani.framework.temporal import WorkflowResultPublisher

        assert WorkflowResultPublisher is not None

    def test_result_publisher_methods(self):
        """Test that WorkflowResultPublisher has expected methods."""
        from unittest.mock import MagicMock

        from kubani.framework.temporal import WorkflowResultPublisher

        mock_bus = MagicMock()
        publisher = WorkflowResultPublisher(mock_bus)

        assert hasattr(publisher, "publish_success")
        assert hasattr(publisher, "publish_failure")
        assert callable(publisher.publish_success)
        assert callable(publisher.publish_failure)
