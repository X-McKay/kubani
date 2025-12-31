"""
Tests for shared testing utilities.

These tests verify that the testing utilities themselves work correctly,
ensuring reliable test infrastructure for agents.
"""

import pytest

from core_agents.testing import DiscordWebhookCapture, ErrorInjector


class TestErrorInjector:
    """Tests for ErrorInjector utility."""

    def test_fail_on_always_raises(self) -> None:
        """fail_on should always raise the configured error."""
        injector = ErrorInjector()
        error = ValueError("Test error")
        injector.fail_on("test_point", error)

        with pytest.raises(ValueError, match="Test error"):
            injector.check_and_raise("test_point")

        # Should raise again on subsequent calls
        with pytest.raises(ValueError, match="Test error"):
            injector.check_and_raise("test_point")

    def test_fail_on_nth_call_only_raises_on_nth(self) -> None:
        """fail_on_nth_call should only raise on the specified call."""
        injector = ErrorInjector()
        error = RuntimeError("Third time fails")
        injector.fail_on_nth_call("test_point", 3, error)

        # First two calls succeed
        injector.check_and_raise("test_point")
        injector.check_and_raise("test_point")

        # Third call fails
        with pytest.raises(RuntimeError, match="Third time fails"):
            injector.check_and_raise("test_point")

        # Fourth call succeeds (only fails on exact nth call)
        injector.check_and_raise("test_point")

    def test_clear_removes_all_injections(self) -> None:
        """clear should remove all configured error injections."""
        injector = ErrorInjector()
        injector.fail_on("point1", ValueError("Error 1"))
        injector.fail_on_nth_call("point2", 2, RuntimeError("Error 2"))

        injector.clear()

        # Neither should raise after clear
        injector.check_and_raise("point1")
        injector.check_and_raise("point2")
        injector.check_and_raise("point2")

    def test_unconfigured_point_does_not_raise(self) -> None:
        """Unconfigured points should not raise errors."""
        injector = ErrorInjector()

        # Should not raise
        injector.check_and_raise("unconfigured_point")
        injector.check_and_raise("another_point")

    def test_record_result_tracks_values(self) -> None:
        """record_result should track values passed through a point."""
        injector = ErrorInjector()

        injector.record_result("api_response", {"status": 200})
        injector.record_result("api_response", {"status": 201})
        injector.record_result("other_point", "data")

        results = injector.get_results("api_response")
        assert len(results) == 2
        assert results[0] == {"status": 200}
        assert results[1] == {"status": 201}

        other_results = injector.get_results("other_point")
        assert other_results == ["data"]

    def test_get_results_empty_for_unknown_point(self) -> None:
        """get_results should return empty list for unknown points."""
        injector = ErrorInjector()

        results = injector.get_results("unknown_point")
        assert results == []

    def test_get_call_count_tracks_calls(self) -> None:
        """get_call_count should track check_and_raise calls."""
        injector = ErrorInjector()
        injector.fail_on_nth_call("tracked_point", 100, ValueError("Never"))

        injector.check_and_raise("tracked_point")
        injector.check_and_raise("tracked_point")
        injector.check_and_raise("tracked_point")

        assert injector.get_call_count("tracked_point") == 3

    def test_multiple_error_points(self) -> None:
        """Multiple error points should work independently."""
        injector = ErrorInjector()

        injector.fail_on("point_a", ValueError("A fails"))
        injector.fail_on_nth_call("point_b", 2, RuntimeError("B fails on 2nd"))

        # Point A always fails
        with pytest.raises(ValueError, match="A fails"):
            injector.check_and_raise("point_a")

        # Point B succeeds first time
        injector.check_and_raise("point_b")

        # Point B fails second time
        with pytest.raises(RuntimeError, match="B fails on 2nd"):
            injector.check_and_raise("point_b")


class TestDiscordWebhookCapture:
    """Tests for DiscordWebhookCapture utility."""

    def test_capture_records_payloads(self) -> None:
        """capture should record webhook payloads."""
        capture = DiscordWebhookCapture()

        msg_id1 = capture.capture({"content": "Hello"})
        msg_id2 = capture.capture({"embeds": [{"title": "Test"}]})

        assert capture.call_count == 2
        assert capture.calls[0] == {"content": "Hello"}
        assert capture.calls[1] == {"embeds": [{"title": "Test"}]}
        assert msg_id1 == "discord-msg-1"
        assert msg_id2 == "discord-msg-2"

    def test_set_failure_makes_capture_raise(self) -> None:
        """set_failure should make capture raise the configured error."""
        capture = DiscordWebhookCapture()
        capture.set_failure(ConnectionError("Webhook failed"))

        with pytest.raises(ConnectionError, match="Webhook failed"):
            capture.capture({"content": "Will fail"})

        # Call was still recorded before raising
        assert capture.call_count == 1

    def test_set_failure_on_specific_call(self) -> None:
        """set_failure with on_call should only fail on that call."""
        capture = DiscordWebhookCapture()
        capture.set_failure(TimeoutError("Third call fails"), on_call=3)

        # First two succeed
        capture.capture({"content": "1"})
        capture.capture({"content": "2"})

        # Third fails
        with pytest.raises(TimeoutError, match="Third call fails"):
            capture.capture({"content": "3"})

        # Fourth succeeds (only fails on exact call number)
        capture.capture({"content": "4"})

        assert capture.call_count == 4

    def test_clear_resets_state(self) -> None:
        """clear should reset all state."""
        capture = DiscordWebhookCapture()
        capture.capture({"content": "Test"})
        capture.set_failure(ValueError("Error"))

        capture.clear()

        assert capture.call_count == 0
        assert capture.calls == []
        assert capture.should_fail is False

        # Should work without raising now
        capture.capture({"content": "After clear"})
        assert capture.call_count == 1

    def test_last_call_returns_most_recent(self) -> None:
        """last_call should return the most recent call."""
        capture = DiscordWebhookCapture()

        assert capture.last_call is None

        capture.capture({"content": "First"})
        capture.capture({"content": "Second"})
        capture.capture({"content": "Third"})

        assert capture.last_call == {"content": "Third"}

    def test_get_embeds_extracts_embeds(self) -> None:
        """get_embeds should extract embeds from calls."""
        capture = DiscordWebhookCapture()

        capture.capture({"content": "No embeds"})
        capture.capture({"embeds": [{"title": "Embed 1"}, {"title": "Embed 2"}]})

        # Default: last call
        embeds = capture.get_embeds()
        assert len(embeds) == 2
        assert embeds[0]["title"] == "Embed 1"

        # First call has no embeds
        embeds_first = capture.get_embeds(call_index=0)
        assert embeds_first == []

    def test_get_embeds_handles_no_calls(self) -> None:
        """get_embeds should return empty list when no calls."""
        capture = DiscordWebhookCapture()

        assert capture.get_embeds() == []

    def test_assert_called_once_success(self) -> None:
        """assert_called_once should pass with exactly one call."""
        capture = DiscordWebhookCapture()
        capture.capture({"content": "Single"})

        capture.assert_called_once()  # Should not raise

    def test_assert_called_once_fails_with_zero(self) -> None:
        """assert_called_once should fail with zero calls."""
        capture = DiscordWebhookCapture()

        with pytest.raises(AssertionError, match="Expected 1 call, got 0"):
            capture.assert_called_once()

    def test_assert_called_once_fails_with_multiple(self) -> None:
        """assert_called_once should fail with multiple calls."""
        capture = DiscordWebhookCapture()
        capture.capture({"content": "1"})
        capture.capture({"content": "2"})

        with pytest.raises(AssertionError, match="Expected 1 call, got 2"):
            capture.assert_called_once()

    def test_assert_called_n_times(self) -> None:
        """assert_called_n_times should verify exact count."""
        capture = DiscordWebhookCapture()
        capture.capture({"content": "1"})
        capture.capture({"content": "2"})
        capture.capture({"content": "3"})

        capture.assert_called_n_times(3)  # Should pass

        with pytest.raises(AssertionError, match="Expected 5 calls, got 3"):
            capture.assert_called_n_times(5)

    def test_assert_not_called(self) -> None:
        """assert_not_called should verify zero calls."""
        capture = DiscordWebhookCapture()

        capture.assert_not_called()  # Should pass

        capture.capture({"content": "Test"})

        with pytest.raises(AssertionError, match="Expected 0 calls, got 1"):
            capture.assert_not_called()


class TestTestingUtilitiesImport:
    """Tests for module import functionality."""

    def test_imports_from_testing_module(self) -> None:
        """Testing utilities should be importable from core_agents.testing."""
        from core_agents.testing import DiscordWebhookCapture, ErrorInjector

        assert ErrorInjector is not None
        assert DiscordWebhookCapture is not None

    def test_creates_instances(self) -> None:
        """Should be able to create instances of testing utilities."""
        from core_agents.testing import DiscordWebhookCapture, ErrorInjector

        injector = ErrorInjector()
        assert injector.error_points == {}

        capture = DiscordWebhookCapture()
        assert capture.calls == []
