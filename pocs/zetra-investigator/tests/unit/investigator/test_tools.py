import asyncio
import json

from google.adk.agents import LlmAgent
from zetra import AgentContext


class FakeRemote:
    async def call(self, tool, arguments):
        return {
            "tool": tool,
            "namespace": arguments["namespace"],
            "text": "configmap demo-config not found",
        }


def registered(tmp_path, remote):
    from kubani_investigator.agents.investigator.toolset import tools

    ctx = AgentContext(object(), workspace=tmp_path, model="fixture")
    wrapped = tools(ctx, remote)
    ctx.seal(LlmAgent(name="investigator", model=ctx.model, tools=wrapped))
    return ctx.executors()


def test_observation_is_saved_with_evidence_identity(tmp_path):
    functions = registered(tmp_path, FakeRemote())
    result = asyncio.run(functions["get_pod"]({"name": "investigator-demo-broken"}, {}, "id"))
    saved = json.loads((tmp_path / result["evidence"]).read_text())
    assert saved["tool"] == "pods_get"
    assert saved["namespace"] == "zetra-poc-fixtures"
    assert result["evidence"].startswith("evidence/pod-investigator-demo-broken-")
    assert "demo-config not found" in result["text"]


def test_out_of_scope_pod_never_reaches_remote(tmp_path):
    class NeverRemote:
        async def call(self, *args):
            raise AssertionError("out-of-scope call reached the gateway")

    functions = registered(tmp_path, NeverRemote())
    result = asyncio.run(functions["get_pod"]({"name": "authentik-server"}, {}, "id"))
    assert "error" in result
    assert not (tmp_path / "evidence").exists()


def test_report_is_written_only_inside_workspace(tmp_path):
    functions = registered(tmp_path, FakeRemote())
    result = asyncio.run(
        functions["write_report"]({"content": "Evidence: evidence/pods.json"}, {}, "id")
    )
    assert result == {"path": "report.md"}
    assert (tmp_path / "report.md").read_text() == "Evidence: evidence/pods.json"


def test_oversized_report_is_rejected(tmp_path):
    functions = registered(tmp_path, FakeRemote())
    result = asyncio.run(functions["write_report"]({"content": "x" * 8001}, {}, "id"))
    assert "error" in result
    assert not (tmp_path / "report.md").exists()


def test_changed_observation_preserves_prior_citation(tmp_path):
    class ChangingRemote:
        count = 0

        async def call(self, tool, arguments):
            self.count += 1
            return {"tool": tool, "namespace": arguments["namespace"], "text": str(self.count)}

    functions = registered(tmp_path, ChangingRemote())
    first = asyncio.run(functions["list_pods"]({}, {}, "one"))
    second = asyncio.run(functions["list_pods"]({}, {}, "two"))
    assert first["evidence"] != second["evidence"]
    assert json.loads((tmp_path / first["evidence"]).read_text())["text"] == "1"
    assert json.loads((tmp_path / second["evidence"]).read_text())["text"] == "2"
