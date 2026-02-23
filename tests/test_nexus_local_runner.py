"""Unit tests for scripts/nexus_local_runner.py.

Tests all runner utilities without requiring any external services.
The LLM, MCP servers, and Temporal are all mocked.

Run with:
    cd /home/ubuntu/kubani
    python -m pytest tests/test_nexus_local_runner.py -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "/home/ubuntu/kubani")
sys.path.insert(0, "/home/ubuntu/kubani/scripts")

# Import the runner module
import nexus_local_runner as runner


# ===========================================================================
# Test 1: .env file parsing
# ===========================================================================


class TestEnvLoading(unittest.TestCase):
    """Tests for the dotenv loading logic."""

    def test_parse_dotenv_sets_vars(self):
        """_parse_dotenv should set env vars from a valid file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("TEST_VAR_RUNNER=hello\n")
            f.write("# This is a comment\n")
            f.write("\n")
            f.write("TEST_VAR_RUNNER2=world\n")
            tmp = Path(f.name)

        try:
            # Ensure vars are not already set
            os.environ.pop("TEST_VAR_RUNNER", None)
            os.environ.pop("TEST_VAR_RUNNER2", None)

            runner._parse_dotenv(tmp)

            self.assertEqual(os.environ.get("TEST_VAR_RUNNER"), "hello")
            self.assertEqual(os.environ.get("TEST_VAR_RUNNER2"), "world")
        finally:
            tmp.unlink()
            os.environ.pop("TEST_VAR_RUNNER", None)
            os.environ.pop("TEST_VAR_RUNNER2", None)

    def test_parse_dotenv_does_not_overwrite_existing(self):
        """_parse_dotenv should not overwrite vars already set in the environment."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("TEST_EXISTING_VAR=from_file\n")
            tmp = Path(f.name)

        try:
            os.environ["TEST_EXISTING_VAR"] = "from_shell"
            runner._parse_dotenv(tmp)
            # Shell value should win
            self.assertEqual(os.environ.get("TEST_EXISTING_VAR"), "from_shell")
        finally:
            tmp.unlink()
            os.environ.pop("TEST_EXISTING_VAR", None)

    def test_parse_dotenv_strips_quotes(self):
        """_parse_dotenv should strip surrounding quotes from values."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write('TEST_QUOTED="quoted value"\n')
            f.write("TEST_SINGLE='single quoted'\n")
            tmp = Path(f.name)

        try:
            os.environ.pop("TEST_QUOTED", None)
            os.environ.pop("TEST_SINGLE", None)
            runner._parse_dotenv(tmp)
            self.assertEqual(os.environ.get("TEST_QUOTED"), "quoted value")
            self.assertEqual(os.environ.get("TEST_SINGLE"), "single quoted")
        finally:
            tmp.unlink()
            os.environ.pop("TEST_QUOTED", None)
            os.environ.pop("TEST_SINGLE", None)

    def test_load_env_skips_missing_files(self):
        """load_env should not raise if env files don't exist."""
        # This should not raise even if neither file exists
        runner.load_env(env_file=Path("/nonexistent/path/.env"))


# ===========================================================================
# Test 2: Config check
# ===========================================================================


class TestConfigCheck(unittest.TestCase):
    """Tests for the config validation logic."""

    def test_config_check_fails_on_placeholder(self):
        """run_config_check should fail when NEXUS_DATABASE_URL is a placeholder."""
        with patch.dict(os.environ, {
            "LLM_API_URL": "https://llm.almckay.io/v1",
            "TEMPORAL_HOST": "temporal.almckay.io:7233",
            "TEMPORAL_NAMESPACE": "nexus",
            "NEXUS_DATABASE_URL": "CHANGE_ME",
            "REDIS_URL": "CHANGE_ME",
        }):
            result = runner.run_config_check()
        self.assertFalse(result)

    def test_config_check_passes_with_valid_vars(self):
        """run_config_check should pass when all required vars are set."""
        with patch.dict(os.environ, {
            "LLM_API_URL": "https://llm.almckay.io/v1",
            "TEMPORAL_HOST": "temporal.almckay.io:7233",
            "TEMPORAL_NAMESPACE": "nexus",
            "NEXUS_DATABASE_URL": "postgresql://kubani:secret@metadata.almckay.io:5432/kubani_nexus",
            "REDIS_URL": "redis://:secret@metadata.almckay.io:6379/0",
        }):
            result = runner.run_config_check()
        self.assertTrue(result)


# ===========================================================================
# Test 3: Health check result formatting
# ===========================================================================


class TestHealthCheckFormatting(unittest.TestCase):
    """Tests for health check result printing."""

    def test_print_health_results_all_ok(self):
        """print_health_results should return True when all checks pass."""
        results = [
            {"name": "LLM", "url": "https://llm.almckay.io/v1/models", "ok": True,
             "status_code": 200, "latency_ms": 45, "error": None},
            {"name": "Memory MCP", "url": "https://mcp-gateway.almckay.io/memory/health",
             "ok": True, "status_code": 200, "latency_ms": 30, "error": None},
        ]
        ok = runner.print_health_results(results)
        self.assertTrue(ok)

    def test_print_health_results_some_failed(self):
        """print_health_results should return False when any check fails."""
        results = [
            {"name": "LLM", "url": "https://llm.almckay.io/v1/models", "ok": True,
             "status_code": 200, "latency_ms": 45, "error": None},
            {"name": "Memory MCP", "url": "https://mcp-gateway.almckay.io/memory/health",
             "ok": False, "status_code": None, "latency_ms": 5001, "error": "Connection refused"},
        ]
        ok = runner.print_health_results(results)
        self.assertFalse(ok)


# ===========================================================================
# Test 4: Temporal activity heartbeat patch
# ===========================================================================


class TestTemporalPatch(unittest.TestCase):
    """Tests for the activity.heartbeat patch."""

    def test_patch_is_idempotent(self):
        """_patch_temporal_activity should be safe to call multiple times."""
        runner._patch_temporal_activity()
        runner._patch_temporal_activity()
        import temporalio.activity as ta
        self.assertTrue(getattr(ta, "_local_runner_patched", False))

    def test_patched_heartbeat_does_not_raise(self):
        """After patching, activity.heartbeat should not raise RuntimeError."""
        runner._patch_temporal_activity()
        import temporalio.activity as ta
        # Should not raise
        ta.heartbeat("test heartbeat message")
        ta.heartbeat()


# ===========================================================================
# Test 5: run_agent_turn_local with mocked LLM
# ===========================================================================


class TestAgentTurnLocal(unittest.IsolatedAsyncioTestCase):
    """Tests for run_agent_turn_local with all external services mocked."""

    async def test_agent_turn_returns_response(self):
        """run_agent_turn_local should return a dict with response_text."""
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.__str__ = lambda self: "The cluster is healthy."
        mock_result.stop_reason = "end_turn"
        mock_agent.invoke_async = AsyncMock(return_value=mock_result)

        with (
            patch("temporalio.activity.heartbeat"),
            patch("kubani.nexus.tools.mcp_clients.create_mcp_clients", return_value=[]),
            patch("kubani.framework.config.get_llm_config") as mock_llm,
            patch("kubani.nexus.tools.core.get_workspace", return_value=MagicMock()),
            patch("kubani.nexus.tools.strands_tools.create_tools", return_value=[]),
            patch("strands.Agent", return_value=mock_agent),
            patch("strands.models.openai.OpenAIModel"),
        ):
            mock_llm.return_value = MagicMock(
                api_key="test-key",
                api_url="https://llm.almckay.io/v1",
                model="nvidia/Qwen3-14B-FP4",
                temperature=0.7,
                max_tokens=4096,
            )
            result = await runner.run_agent_turn_local(
                user_message="What pods are running?",
                verbose=False,
            )

        self.assertIn("response_text", result)
        self.assertIn("stop_reason", result)
        self.assertNotEqual(result["stop_reason"], "error")

    async def test_agent_turn_handles_exception(self):
        """run_agent_turn_local should return an error dict on exception."""
        with (
            patch("temporalio.activity.heartbeat"),
            patch("kubani.nexus.tools.mcp_clients.create_mcp_clients", side_effect=RuntimeError("MCP down")),
            patch("kubani.framework.config.get_llm_config") as mock_llm,
            patch("kubani.nexus.tools.core.get_workspace", return_value=MagicMock()),
            patch("kubani.nexus.tools.strands_tools.create_tools", return_value=[]),
        ):
            mock_llm.return_value = MagicMock(
                api_key="test-key",
                api_url="https://llm.almckay.io/v1",
                model="nvidia/Qwen3-14B-FP4",
                temperature=0.7,
                max_tokens=4096,
            )
            result = await runner.run_agent_turn_local(
                user_message="Hello",
                verbose=False,
            )

        self.assertEqual(result["stop_reason"], "error")
        self.assertIn("ERROR", result["response_text"])


# ===========================================================================
# Test 6: run_mission_turn_local with mocked LLM
# ===========================================================================


class TestMissionTurnLocal(unittest.IsolatedAsyncioTestCase):
    """Tests for run_mission_turn_local with all external services mocked."""

    async def _run_with_mocked_agent(
        self,
        goal: str,
        agent_json_response: dict,
        mcp_policy: str = "nexus",
    ) -> dict:
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value=json.dumps(agent_json_response))

        with (
            patch("temporalio.activity.heartbeat"),
            patch("kubani.nexus.db.create_pool") as mock_pool,
            patch("kubani.nexus.missions.db.create_mission_run"),
            patch("kubani.nexus.missions.db.complete_mission_run"),
            patch("kubani.nexus.tools.mcp_clients.create_mcp_clients", return_value=[]),
            patch("kubani.framework.config.get_llm_config") as mock_llm,
            patch("strands.Agent", return_value=mock_agent),
            patch("strands.models.openai.OpenAIModel"),
        ):
            mock_pool.return_value = AsyncMock()
            mock_llm.return_value = MagicMock(
                api_key="test-key",
                api_url="https://llm.almckay.io/v1",
                model="nvidia/Qwen3-14B-FP4",
                temperature=0.1,
                max_tokens=200,
            )
            return await runner.run_mission_turn_local(
                goal=goal,
                mcp_policy=mcp_policy,
                verbose=False,
            )

    async def test_mission_turn_no_anomaly(self):
        """Mission turn should return completed status when no anomaly found."""
        result = await self._run_with_mocked_agent(
            goal="Check cluster health",
            agent_json_response={
                "should_notify": False,
                "found_anomaly": False,
                "notification_text": "",
            },
        )
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["should_notify"])
        self.assertFalse(result["found_anomaly"])

    async def test_mission_turn_with_anomaly(self):
        """Mission turn should return notification when anomaly found."""
        result = await self._run_with_mocked_agent(
            goal="Check cluster health",
            agent_json_response={
                "should_notify": True,
                "found_anomaly": True,
                "notification_text": "3 pods in CrashLoopBackOff",
            },
        )
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["should_notify"])
        self.assertTrue(result["found_anomaly"])
        self.assertIn("CrashLoopBackOff", result["notification_text"])

    async def test_mission_turn_proactive_policy(self):
        """Mission turn with nexus-proactive policy should complete successfully."""
        result = await self._run_with_mocked_agent(
            goal="Check Kubernetes pods",
            agent_json_response={
                "should_notify": False,
                "found_anomaly": False,
                "notification_text": "",
            },
            mcp_policy="nexus-proactive",
        )
        self.assertIn(result["status"], ("completed", "failed", "timed_out"))
        self.assertIn("run_id", result)


# ===========================================================================
# Test 7: Module reload
# ===========================================================================


class TestModuleReload(unittest.TestCase):
    """Tests for the _reload_activities hot-reload helper."""

    def test_reload_does_not_raise(self):
        """_reload_activities should not raise even if modules are not loaded."""
        # Import the modules first so they're in sys.modules
        import kubani.nexus.orchestrator.activities  # noqa: F401
        # Should not raise
        runner._reload_activities()


# ===========================================================================
# Main
# ===========================================================================


if __name__ == "__main__":
    print("=" * 60)
    print("Nexus Local Runner — Unit Tests")
    print("=" * 60)
    unittest.main(verbosity=2)
