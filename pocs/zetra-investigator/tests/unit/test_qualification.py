"""Qualification must not credit stale runs or unrelated effect failures."""

import importlib.util
from pathlib import Path

import pytest
from temporalio.api.enums.v1 import TimeoutType
from temporalio.api.failure.v1 import Failure, TimeoutFailureInfo
from temporalio.api.history.v1 import ActivityTaskTimedOutEventAttributes, History, HistoryEvent


def module(name):
    path = Path(__file__).resolve().parents[2] / "evals" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_hard_loss_requires_exact_injected_timeout():
    qualify = module("qualify_kubani")
    history = History(
        events=[
            HistoryEvent(
                activity_task_timed_out_event_attributes=ActivityTaskTimedOutEventAttributes(
                    scheduled_event_id=3,
                    failure=Failure(
                        timeout_failure_info=TimeoutFailureInfo(
                            timeout_type=TimeoutType.TIMEOUT_TYPE_HEARTBEAT
                        )
                    ),
                )
            )
        ]
    )
    effects = [{"operation_id": "a", "scheduled_event_id": 3}]
    qualify.check_hard_loss(history, effects, "a", "a")
    with pytest.raises(AssertionError):
        qualify.check_hard_loss(history, effects, "b", "b")
    with pytest.raises(AssertionError):
        qualify.check_hard_loss(history, effects, "a", "b")
    with pytest.raises(AssertionError):
        qualify.check_hard_loss(History(), effects, "a", "a")


def test_probe_attempts_every_cleanup_and_reports_unknown():
    probe = module("probe_credentials")

    class Ref:
        def __init__(self, name):
            self.name = self.id = name

    class Client:
        def __init__(self):
            self.attempts = []

        def get(self, name, **kwargs):
            return Ref(name)

        def stop(self, name, **kwargs):
            self.attempts.append(name)
            if name == "a":
                raise TimeoutError("private secret must not appear")

        def delete(self, name, **kwargs):
            pass

        def wait_deleted(self, name, **kwargs):
            pass

    client = Client()
    result = probe.cleanup_refs(client, [Ref("a"), Ref("b")])
    assert client.attempts == ["a", "b"]
    assert result == [
        {"sandbox_id": "a", "cleanup": "NOT_CONFIRMED"},
        {"sandbox_id": "b", "cleanup": "DELETED"},
    ]


def test_provider_unknown_cannot_qualify_cancellation():
    qualify = module("qualify_kubani")
    with pytest.raises(AssertionError):
        qualify.check_cancellation(History(), "COMPLETED")
    with pytest.raises(AssertionError):
        qualify.check_cancellation(History(), "CANCELED")
