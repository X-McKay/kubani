"""Qualification must not credit stale runs or unrelated effect failures."""

import importlib.util
from pathlib import Path

import pytest
from temporalio.api.history.v1 import History


def module(name):
    path = Path(__file__).resolve().parents[2] / "evals" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


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


@pytest.mark.parametrize(
    "names",
    [
        ("provision_session", "rebind_session"),
        ("create_session", "create_session"),
    ],
)
def test_creation_bindings_include_initial_and_replacement_without_readiness_duplicates(names):
    qualify = module("qualify_kubani")
    bindings = [
        {"generation": 1, "name": "first", "sandbox_id": "id-first"},
        {"generation": 2, "name": "second", "sandbox_id": "id-second"},
    ]
    completed = []
    for name, binding in zip(names, bindings, strict=True):
        completed.extend(
            [
                {"name": name, "value": binding},
                {"name": "wait_session_ready", "value": binding},
            ]
        )
    completed.append({"name": names[-1], "value": bindings[-1]})
    assert qualify.creation_bindings(completed) == bindings


def test_native_absence_checks_new_creation_generations_and_never_passes_vacuously(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    qualify = module("qualify_kubani")

    class Missing(qualify.grpc.RpcError):
        def code(self):
            return qualify.grpc.StatusCode.NOT_FOUND

    gateway = SimpleNamespace(get=Mock(side_effect=Missing()))
    kube = AsyncMock(return_value="")
    monkeypatch.setattr(qualify, "kube", kube)
    completed = [
        {
            "name": "create_session",
            "value": {"generation": generation, "name": name, "sandbox_id": name + "-id"},
        }
        for generation, name in [(1, "initial"), (2, "replacement")]
    ]
    asyncio.run(qualify.confirm_absence(gateway, completed))
    assert [c.args[0] for c in gateway.get.call_args_list] == ["initial", "replacement"]
    assert kube.await_count == 8
    assert {c.args[4] for c in kube.call_args_list} == {
        "default--initial",
        "os-supervisor-initial-id",
        "workspace-default--initial",
        "default--replacement",
        "os-supervisor-replacement-id",
        "workspace-default--replacement",
    }
    with pytest.raises(AssertionError, match="no completed creation"):
        asyncio.run(
            qualify.confirm_absence(
                gateway, [{"name": "wait_session_ready", "value": completed[0]["value"]}]
            )
        )
    assert gateway.get.call_count == 2 and kube.await_count == 8


@pytest.mark.parametrize("remaining", ["native", "kubernetes"])
def test_native_absence_rejects_remaining_new_generation(monkeypatch, remaining):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    qualify = module("qualify_kubani")

    class Missing(qualify.grpc.RpcError):
        def code(self):
            return qualify.grpc.StatusCode.NOT_FOUND

    gateway = SimpleNamespace(
        get=Mock(side_effect=Missing() if remaining == "kubernetes" else None)
    )
    monkeypatch.setattr(qualify, "kube", AsyncMock(return_value="pod/remains"))
    completed = [
        {
            "name": "create_session",
            "value": {"generation": 1, "name": "initial", "sandbox_id": "initial-id"},
        }
    ]
    with pytest.raises(AssertionError, match="still exists|resource remains"):
        asyncio.run(qualify.confirm_absence(gateway, completed))


def test_creation_bindings_reject_conflicting_generation_identity():
    qualify = module("qualify_kubani")
    completed = [
        {
            "name": "create_session",
            "value": {"generation": 1, "name": "initial", "sandbox_id": sandbox_id},
        }
        for sandbox_id in ["first", "changed"]
    ]
    with pytest.raises(AssertionError, match="changed binding"):
        qualify.creation_bindings(completed)
