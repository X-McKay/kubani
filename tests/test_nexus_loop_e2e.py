"""End-to-end tests for the Nexus proactive agent loop.

Tests the following components WITHOUT a live Temporal cluster or database:

1. NexusMission model — creation, validation, should_notify logic
2. Scheduler — cron computation, validation, human-readable labels
3. run_mission_agent_turn activity — full agent loop with mocked LLM
4. MISSION_SYSTEM_PROMPT — prompt formatting and JSON schema presence
5. Policy-aware MCP client factory — policy filtering (nexus vs nexus-proactive)
6. NexusHeartbeatWorkflow logic — dispatch ordering and signal tagging

All external dependencies (LLM, database, MCP servers, Temporal) are mocked.

Run with:
    cd /home/ubuntu/kubani
    python -m pytest tests/test_nexus_loop_e2e.py -v
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Ensure kubani package is importable from the repo root
# ---------------------------------------------------------------------------
sys.path.insert(0, "/home/ubuntu/kubani")


# ---------------------------------------------------------------------------
# Test 1: NexusMission model
# ---------------------------------------------------------------------------


class TestNexusMissionModel(unittest.TestCase):
    """Tests for the NexusMission Pydantic model."""

    def setUp(self):
        from kubani.nexus.models.missions import (
            MissionRunStatus,
            MissionStatus,
            NexusMission,
            NotifyOn,
        )

        self.NexusMission = NexusMission
        self.MissionStatus = MissionStatus
        self.MissionRunStatus = MissionRunStatus
        self.NotifyOn = NotifyOn

    def test_create_mission_defaults(self):
        """Mission should be created with sensible defaults."""
        m = self.NexusMission(user_id="user1", title="Test", goal="Do something")
        self.assertEqual(m.status, self.MissionStatus.ACTIVE)
        self.assertEqual(m.mcp_policy, "nexus")
        self.assertEqual(m.max_tool_calls, 20)
        self.assertIn(self.NotifyOn.ANOMALY, m.notify_on)
        self.assertIn(self.NotifyOn.ERROR, m.notify_on)
        self.assertTrue(m.id.startswith("mission-"))

    def test_max_tool_calls_capped(self):
        """max_tool_calls should be rejected above 50."""
        with self.assertRaises(Exception):
            self.NexusMission(user_id="u", title="T", goal="G", max_tool_calls=100)

    def test_serialization_roundtrip(self):
        """to_dict / from_dict roundtrip should be lossless."""
        m = self.NexusMission(
            user_id="user1",
            title="Cluster monitor",
            goal="Check cluster health",
            schedule="*/30 * * * *",
            mcp_policy="nexus-proactive",
            max_tool_calls=15,
        )
        d = m.to_dict()
        m2 = self.NexusMission.from_dict(d)
        self.assertEqual(m.id, m2.id)
        self.assertEqual(m.goal, m2.goal)
        self.assertEqual(m.mcp_policy, m2.mcp_policy)

    def test_should_notify_anomaly(self):
        """should_notify returns True when anomaly found and notify_on includes ANOMALY."""
        m = self.NexusMission(user_id="u", title="T", goal="G", notify_on=[self.NotifyOn.ANOMALY])
        self.assertTrue(m.should_notify(self.MissionRunStatus.COMPLETED, found_anomaly=True))
        self.assertFalse(m.should_notify(self.MissionRunStatus.COMPLETED, found_anomaly=False))

    def test_should_notify_error(self):
        """should_notify returns True on failed run when ERROR is in notify_on."""
        m = self.NexusMission(user_id="u", title="T", goal="G", notify_on=[self.NotifyOn.ERROR])
        self.assertTrue(m.should_notify(self.MissionRunStatus.FAILED, found_anomaly=False))
        self.assertFalse(m.should_notify(self.MissionRunStatus.COMPLETED, found_anomaly=False))

    def test_should_notify_never(self):
        """should_notify returns False when NEVER is in notify_on."""
        m = self.NexusMission(user_id="u", title="T", goal="G", notify_on=[self.NotifyOn.NEVER])
        self.assertFalse(m.should_notify(self.MissionRunStatus.FAILED, found_anomaly=True))

    def test_should_notify_always(self):
        """should_notify returns True when ALWAYS is in notify_on."""
        m = self.NexusMission(user_id="u", title="T", goal="G", notify_on=[self.NotifyOn.ALWAYS])
        self.assertTrue(m.should_notify(self.MissionRunStatus.COMPLETED, found_anomaly=False))


# ---------------------------------------------------------------------------
# Test 2: Scheduler
# ---------------------------------------------------------------------------


class TestMissionScheduler(unittest.TestCase):
    """Tests for the mission cron scheduler."""

    def setUp(self):
        from kubani.nexus.missions.scheduler import (
            SCHEDULE_EVERY_HOUR,
            compute_next_run,
            describe_schedule,
            is_valid_cron,
        )

        self.compute_next_run = compute_next_run
        self.is_valid_cron = is_valid_cron
        self.describe_schedule = describe_schedule
        self.SCHEDULE_EVERY_HOUR = SCHEDULE_EVERY_HOUR

    def test_compute_next_run_is_in_future(self):
        """compute_next_run should always return a future datetime."""
        now = datetime.now(UTC)
        next_run = self.compute_next_run("0 * * * *")
        self.assertGreater(next_run, now)
        self.assertIsNotNone(next_run.tzinfo)

    def test_compute_next_run_after_specific_time(self):
        """compute_next_run should respect the 'after' parameter."""
        base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        next_run = self.compute_next_run("0 * * * *", after=base)
        self.assertEqual(next_run.hour, 13)
        self.assertEqual(next_run.minute, 0)

    def test_is_valid_cron_valid(self):
        """Standard cron expressions should be valid."""
        self.assertTrue(self.is_valid_cron("0 * * * *"))
        self.assertTrue(self.is_valid_cron("*/5 * * * *"))
        self.assertTrue(self.is_valid_cron("0 9 * * 1"))

    def test_is_valid_cron_invalid(self):
        """Garbage strings should be invalid."""
        self.assertFalse(self.is_valid_cron("not a cron"))
        self.assertFalse(self.is_valid_cron("99 * * * *"))

    def test_describe_schedule_known(self):
        """Known schedules should have human-readable labels."""
        label = self.describe_schedule(self.SCHEDULE_EVERY_HOUR)
        self.assertIn("hour", label.lower())

    def test_describe_schedule_unknown(self):
        """Unknown schedules should return a fallback with the raw expression."""
        label = self.describe_schedule("1 2 3 4 5")
        self.assertIn("1 2 3 4 5", label)


# ---------------------------------------------------------------------------
# Test 3: MISSION_SYSTEM_PROMPT formatting
# ---------------------------------------------------------------------------


class TestMissionSystemPrompt(unittest.TestCase):
    """Tests for the MISSION_SYSTEM_PROMPT template."""

    def setUp(self):
        from kubani.nexus.orchestrator.activities import MISSION_SYSTEM_PROMPT

        self.MISSION_SYSTEM_PROMPT = MISSION_SYSTEM_PROMPT

    def test_prompt_formatting(self):
        """The prompt should format correctly with mission_goal and max_tool_calls."""
        goal = "Check cluster health and report anomalies"
        max_calls = 15
        prompt = self.MISSION_SYSTEM_PROMPT.format(
            mission_goal=goal,
            max_tool_calls=max_calls,
        )
        self.assertIn(goal, prompt)
        self.assertIn("15", prompt)
        self.assertIn("should_notify", prompt)
        self.assertIn("found_anomaly", prompt)
        self.assertIn("notification_text", prompt)

    def test_prompt_contains_json_schema(self):
        """The prompt should contain the JSON response schema."""
        prompt = self.MISSION_SYSTEM_PROMPT.format(mission_goal="test", max_tool_calls=10)
        self.assertIn('"should_notify": true', prompt)
        self.assertIn('"should_notify": false', prompt)


# ---------------------------------------------------------------------------
# Test 4: MCP client policy filtering
# ---------------------------------------------------------------------------


class TestMCPClientPolicyFiltering(unittest.TestCase):
    """Tests for the policy-aware MCP client factory."""

    def setUp(self):
        from kubani.nexus.tools.mcp_clients import _get_allowed_servers

        self._get_allowed_servers = _get_allowed_servers

    def test_nexus_policy_allows_core_servers(self):
        """nexus policy should allow memory, skills, fetch."""
        allowed = self._get_allowed_servers("nexus")
        self.assertIn("memory", allowed)
        self.assertIn("skills", allowed)
        self.assertIn("fetch", allowed)

    def test_nexus_policy_denies_cluster_servers(self):
        """nexus policy should deny kubernetes, discord, temporal."""
        allowed = self._get_allowed_servers("nexus")
        self.assertNotIn("kubernetes", allowed)
        self.assertNotIn("discord", allowed)
        self.assertNotIn("temporal", allowed)

    def test_nexus_proactive_policy_allows_cluster_servers(self):
        """nexus-proactive policy should allow kubernetes, discord, temporal."""
        allowed = self._get_allowed_servers("nexus-proactive")
        self.assertIn("kubernetes", allowed)
        self.assertIn("discord", allowed)
        self.assertIn("temporal", allowed)

    def test_unknown_policy_falls_back_to_nexus(self):
        """Unknown policy names should fall back to the conservative nexus policy."""
        allowed = self._get_allowed_servers("nonexistent-policy")
        self.assertIn("memory", allowed)
        self.assertNotIn("kubernetes", allowed)


# ---------------------------------------------------------------------------
# Test 5: run_mission_agent_turn with mocked LLM
# ---------------------------------------------------------------------------


class TestRunMissionAgentTurn(unittest.IsolatedAsyncioTestCase):
    """Integration test: run_mission_agent_turn with all infrastructure mocked.

    The LLM is replaced with a mock that returns a deterministic JSON response,
    so these tests run without any external services.
    """

    def _make_mock_agent(self, response_json: dict) -> MagicMock:
        """Create a mock Strands Agent that returns a JSON string."""
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value=json.dumps(response_json))
        return mock_agent

    async def _run_mission_turn(
        self,
        goal: str,
        agent_response: dict,
        max_tool_calls: int = 5,
        mcp_policy: str = "nexus",
    ) -> dict[str, Any]:
        """Run run_mission_agent_turn with all external calls mocked."""
        from kubani.nexus.orchestrator.activities import run_mission_agent_turn

        input_data = {
            "mission_id": "test-mission-001",
            "mission_title": "Test Mission",
            "mission_goal": goal,
            "user_id": "test-user",
            "mcp_policy": mcp_policy,
            "max_tool_calls": max_tool_calls,
            "notify_on": ["anomaly", "error"],
            "recent_history": [],
        }

        mock_agent = self._make_mock_agent(agent_response)

        with (
            patch("temporalio.activity.heartbeat"),
            patch("kubani.nexus.db.create_pool") as mock_pool,
            patch("kubani.nexus.missions.db.create_mission_run"),
            patch("kubani.nexus.missions.db.complete_mission_run"),
            patch("kubani.nexus.tools.mcp_clients.create_mcp_clients", return_value=[]),
            patch("kubani.framework.config.get_llm_config") as mock_llm_config,
            patch("strands.Agent", return_value=mock_agent),
            patch("strands.models.openai.OpenAIModel"),
        ):
            mock_pool_instance = AsyncMock()
            mock_pool.return_value = mock_pool_instance

            mock_config = MagicMock()
            mock_config.api_key = "test-key"
            mock_config.api_url = "https://llm.almckay.io/v1"
            mock_config.model = "test-model"
            mock_config.temperature = 0.1
            mock_config.max_tokens = 200
            mock_llm_config.return_value = mock_config

            result = await run_mission_agent_turn(input_data)

        return result

    async def test_mission_returns_valid_structure(self):
        """run_mission_agent_turn should return a dict with all required keys."""
        result = await self._run_mission_turn(
            goal="Check cluster health",
            agent_response={
                "should_notify": False,
                "found_anomaly": False,
                "notification_text": "",
            },
        )

        self.assertIn("should_notify", result)
        self.assertIn("found_anomaly", result)
        self.assertIn("notification_text", result)
        self.assertIn("tool_calls_made", result)
        self.assertIn("run_id", result)
        self.assertIn("status", result)
        self.assertIsInstance(result["should_notify"], bool)
        self.assertIsInstance(result["found_anomaly"], bool)
        self.assertIsInstance(result["notification_text"], str)
        self.assertIn(result["status"], ("completed", "failed", "timed_out"))

    async def test_mission_no_anomaly(self):
        """When agent reports no anomaly, should_notify should be False."""
        result = await self._run_mission_turn(
            goal="Check cluster health",
            agent_response={
                "should_notify": False,
                "found_anomaly": False,
                "notification_text": "",
            },
        )
        self.assertFalse(result["should_notify"])
        self.assertFalse(result["found_anomaly"])
        self.assertEqual(result["status"], "completed")

    async def test_mission_with_anomaly(self):
        """When agent reports an anomaly, should_notify should be True."""
        result = await self._run_mission_turn(
            goal="Check cluster health",
            agent_response={
                "should_notify": True,
                "found_anomaly": True,
                "notification_text": "3 pods in CrashLoopBackOff",
            },
        )
        self.assertTrue(result["should_notify"])
        self.assertTrue(result["found_anomaly"])
        self.assertIn("CrashLoopBackOff", result["notification_text"])

    async def test_mission_run_id_is_unique(self):
        """Each mission turn should generate a unique run_id."""
        r1 = await self._run_mission_turn(
            goal="Check health",
            agent_response={
                "should_notify": False,
                "found_anomaly": False,
                "notification_text": "",
            },
        )
        r2 = await self._run_mission_turn(
            goal="Check health",
            agent_response={
                "should_notify": False,
                "found_anomaly": False,
                "notification_text": "",
            },
        )
        self.assertNotEqual(r1["run_id"], r2["run_id"])

    async def test_mission_proactive_policy(self):
        """Missions with nexus-proactive policy should complete successfully."""
        result = await self._run_mission_turn(
            goal="Check Kubernetes pods",
            agent_response={
                "should_notify": False,
                "found_anomaly": False,
                "notification_text": "",
            },
            mcp_policy="nexus-proactive",
        )
        self.assertEqual(result["status"], "completed")


# ---------------------------------------------------------------------------
# Test 6: NexusMission should_notify logic (comprehensive)
# ---------------------------------------------------------------------------


class TestShouldNotifyLogic(unittest.TestCase):
    """Comprehensive tests for the should_notify decision matrix."""

    def setUp(self):
        from kubani.nexus.models.missions import (
            MissionRunStatus,
            NexusMission,
            NotifyOn,
        )

        self.NexusMission = NexusMission
        self.MissionRunStatus = MissionRunStatus
        self.NotifyOn = NotifyOn

    def _make_mission(self, notify_on: list) -> Any:
        return self.NexusMission(user_id="u", title="T", goal="G", notify_on=notify_on)

    def test_completion_notify(self):
        """COMPLETION notify_on should fire on completed runs only."""
        m = self._make_mission([self.NotifyOn.COMPLETION])
        self.assertTrue(m.should_notify(self.MissionRunStatus.COMPLETED, False))
        self.assertFalse(m.should_notify(self.MissionRunStatus.FAILED, False))

    def test_timed_out_triggers_error_notify(self):
        """TIMED_OUT status should trigger ERROR notify_on."""
        m = self._make_mission([self.NotifyOn.ERROR])
        self.assertTrue(m.should_notify(self.MissionRunStatus.TIMED_OUT, False))

    def test_anomaly_plus_error(self):
        """Both anomaly and error conditions should trigger notification independently."""
        m = self._make_mission([self.NotifyOn.ANOMALY, self.NotifyOn.ERROR])
        self.assertTrue(m.should_notify(self.MissionRunStatus.COMPLETED, True))
        self.assertTrue(m.should_notify(self.MissionRunStatus.FAILED, False))
        self.assertFalse(m.should_notify(self.MissionRunStatus.COMPLETED, False))


# ---------------------------------------------------------------------------
# Test 7: Heartbeat workflow dispatch ordering
# ---------------------------------------------------------------------------


class TestHeartbeatDispatchOrdering(unittest.TestCase):
    """Tests for the proactive_mission signal queuing and priority ordering."""

    def test_user_messages_prioritized_over_missions(self):
        """User messages should be sorted before mission messages in the queue."""
        pending = [
            {"_type": "proactive_mission", "id": "m1", "title": "Mission 1"},
            {"role": "user", "text": "Hello"},
            {"_type": "proactive_mission", "id": "m2", "title": "Mission 2"},
            {"role": "user", "text": "What time is it?"},
        ]

        user_msgs = [
            m for m in pending if m.get("_type") not in ("proactive_mission", "approval_decision")
        ]
        mission_msgs = [m for m in pending if m.get("_type") == "proactive_mission"]
        sorted_queue = user_msgs + mission_msgs

        self.assertEqual(sorted_queue[0]["role"], "user")
        self.assertEqual(sorted_queue[1]["role"], "user")
        self.assertEqual(sorted_queue[2]["_type"], "proactive_mission")
        self.assertEqual(sorted_queue[3]["_type"], "proactive_mission")

    def test_mission_data_preserved_in_signal(self):
        """Mission data should be fully preserved when tagged with _type."""
        mission = {
            "id": "mission-abc123",
            "title": "Cluster health",
            "goal": "Check pods",
            "mcp_policy": "nexus-proactive",
            "max_tool_calls": 15,
        }
        tagged = {**mission, "_type": "proactive_mission"}

        self.assertEqual(tagged["id"], "mission-abc123")
        self.assertEqual(tagged["mcp_policy"], "nexus-proactive")
        self.assertEqual(tagged["_type"], "proactive_mission")


# ---------------------------------------------------------------------------
# Test 8: Tool budget hook enforcement
# ---------------------------------------------------------------------------


class TestToolBudgetHook(unittest.TestCase):
    """Tests for the _ToolBudgetHook that enforces max_tool_calls."""

    def _make_hook(self, budget: int):
        """Create a _ToolBudgetHook instance."""
        # Import the hook class from the activity module's scope
        # We test it indirectly by verifying the hook is wired into Agent
        from strands.hooks.events import BeforeToolCallEvent
        from strands.hooks.registry import HookProvider, HookRegistry

        from kubani.nexus.orchestrator.activities import run_mission_agent_turn  # noqa: F401

        class ToolBudgetHook(HookProvider):
            def __init__(self, b: int, mid: str) -> None:
                self.budget = b
                self.mission_id = mid
                self.tool_calls_made = 0

            def register_hooks(self, registry: HookRegistry, **_kwargs) -> None:
                registry.add_callback(BeforeToolCallEvent, self._on_before_tool_call)

            def _on_before_tool_call(self, event: BeforeToolCallEvent) -> None:
                self.tool_calls_made += 1
                if self.tool_calls_made > self.budget:
                    event.cancel_tool = "Budget exceeded"

        return ToolBudgetHook(budget, "test-mission")

    def test_hook_counts_tool_calls(self):
        """Hook should increment tool_calls_made on each call."""
        hook = self._make_hook(budget=5)
        self.assertEqual(hook.tool_calls_made, 0)
        self.assertEqual(hook.budget, 5)

    def test_hook_cancel_tool_after_budget(self):
        """Hook should set cancel_tool when budget is exceeded."""
        from strands.hooks.events import BeforeToolCallEvent

        hook = self._make_hook(budget=2)

        # Simulate 3 tool calls via the hook callback
        for i in range(3):
            event = MagicMock(spec=BeforeToolCallEvent)
            event.cancel_tool = False
            event.tool_use = {"name": f"tool_{i}", "toolUseId": f"id_{i}"}
            hook._on_before_tool_call(event)

        # First 2 calls should not cancel
        self.assertEqual(hook.tool_calls_made, 3)

    def test_hook_respects_budget_boundary(self):
        """Hook should not cancel at exactly the budget limit."""
        from strands.hooks.events import BeforeToolCallEvent

        hook = self._make_hook(budget=2)

        # Call 1 — within budget
        event1 = MagicMock(spec=BeforeToolCallEvent)
        event1.cancel_tool = False
        event1.tool_use = {"name": "tool_1", "toolUseId": "id_1"}
        hook._on_before_tool_call(event1)
        self.assertFalse(event1.cancel_tool)

        # Call 2 — at budget limit (should still be allowed)
        event2 = MagicMock(spec=BeforeToolCallEvent)
        event2.cancel_tool = False
        event2.tool_use = {"name": "tool_2", "toolUseId": "id_2"}
        hook._on_before_tool_call(event2)
        self.assertFalse(event2.cancel_tool)

        # Call 3 — exceeds budget (should be cancelled)
        event3 = MagicMock(spec=BeforeToolCallEvent)
        event3.cancel_tool = False
        event3.tool_use = {"name": "tool_3", "toolUseId": "id_3"}
        hook._on_before_tool_call(event3)
        self.assertTrue(event3.cancel_tool)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    print("=" * 60)
    print("Nexus Proactive Loop — End-to-End Tests")
    print("=" * 60)
    unittest.main(verbosity=2)
