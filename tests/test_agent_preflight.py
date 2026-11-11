"""Generic orchestration fixtures; no credentials, network or live cluster."""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import venv
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import yaml

OPS = Path(__file__).resolve().parents[1] / "infrastructure/scripts/ops"
sys.path.insert(0, str(OPS))
from agent_preflight import core, live, source
from mcp_registry import identity, model


def receipt(agent="sample", tag="sample/v1"):
    return {
        "schemaVersion": 1,
        "scope": "candidate-desired-gitops",
        "ok": True,
        "receipt": {
            "agent": agent,
            "tag": tag,
            "files": [],
            "source": {
                "path": "/source",
                "head": "a" * 40,
                "dirty": False,
                "main": None,
            },
            "kubani": {
                "path": "/kubani",
                "head": "b" * 40,
                "dirty": True,
                "main": None,
            },
        },
        "errors": [],
    }


def grant(backend="alpha", **kwargs):
    return {"backend": backend, "tools": ["query"], "effect": "remote_read", **kwargs}


class Orchestration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "kubani"
        self.src = Path(self.temp.name) / "source"
        self.doc = {
            "apiVersion": "agentplatform.io/v1alpha1",
            "kind": "Agent",
            "metadata": {"name": "sample", "namespace": "tenant-one"},
            "spec": {
                "owner": "owner@example.test",
                "identity": {"mode": "agent"},
                "capabilities": {"models": [], "mcp": []},
            },
        }
        self.source_path = self.src / "agents/sample/deploy/agent.yaml"
        self.candidate_path = (
            self.root / "infrastructure/gitops/apps/agents/tenant-one/sample/agent.yaml"
        )
        self.write(self.source_path, self.doc)
        self.write(self.candidate_path, self.doc)
        self.entries = [
            {
                "name": b,
                "authorization": {
                    "tools": ["query"],
                    "role": f"agent-role-{b}-read",
                    "scopeDescription": "reviewed",
                },
                "secrets": [],
            }
            for b in ("alpha", "beta")
        ]
        self.reg = SimpleNamespace(
            model=SimpleNamespace(
                load_registry=Mock(return_value=self.entries),
                descriptor=model.descriptor,
            ),
            check=SimpleNamespace(check=Mock(return_value=[])),
            identity=identity,
            render=SimpleNamespace(objects=Mock(return_value=[{"kind": "Service"}])),
            status=SimpleNamespace(
                inspect_registration=Mock(
                    return_value={
                        "complete": True,
                        "functional": "not-tested",
                        "layers": [],
                    }
                )
            ),
            transports=Mock(
                side_effect=AssertionError("offline initialized credentials")
            ),
        )
        self.source_check = Mock(return_value=receipt())

    def write(self, path, doc):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(doc))

    def mcp(self, grants):
        self.doc["spec"]["capabilities"]["mcp"] = grants
        self.write(self.source_path, self.doc)
        self.write(self.candidate_path, self.doc)

    def run_check(self, **kwargs):
        return core.run(
            self.root,
            self.src,
            "sample",
            "sample/v1",
            registry=self.reg,
            source_check=self.source_check,
            **kwargs,
        )

    def checks(self, result, code):
        return [c for c in result["checks"] if c["code"] == code]

    def test_no_mcp_has_no_registry_or_live_gate(self):
        result = self.run_check()
        self.assertTrue(result["ok"])
        self.reg.model.load_registry.assert_not_called()
        self.reg.transports.assert_not_called()
        self.assertEqual(
            self.checks(result, "registry_validation")[0]["state"], "not_applicable"
        )
        self.assertEqual(len(result["evidence"]["files"]), 2)
        self.source_check.assert_called_once_with(
            self.src, self.root, "sample", "sample/v1"
        )

    def test_multiple_backends_use_registry_check_once_offline(self):
        self.mcp([grant(), grant("beta", delegation="on-behalf-of")])
        result = self.run_check()
        self.assertTrue(result["ok"])
        self.reg.check.check.assert_called_once_with(self.root)
        self.reg.transports.assert_not_called()
        self.assertEqual(len(self.checks(result, "mcp_grant")), 2)

    def test_defaults_match_explicit(self):
        doc = copy.deepcopy(self.doc)
        doc["spec"].update(enabled=True)
        doc["spec"]["identity"]["onBehalfOf"] = {"required": True, "fallback": "deny"}
        self.write(self.candidate_path, doc)
        self.assertTrue(self.run_check()["ok"])

    def test_identity_owner_enabled_mismatches_and_types(self):
        for field, value in (
            ("owner", "other"),
            ("enabled", False),
            ("enabled", 1),
            ("owner", 17),
            ("identity", {"mode": "on-behalf-of"}),
            ("identity", {"mode": "unknown"}),
            ("identity", {"mode": "agent", "onBehalfOf": {"required": "true"}}),
            ("identity", {"mode": "agent", "onBehalfOf": {"fallback": "other"}}),
        ):
            with self.subTest(field=field, value=value):
                doc = copy.deepcopy(self.doc)
                doc["spec"][field] = value
                self.write(self.candidate_path, doc)
                self.assertFalse(self.run_check()["ok"])

    def test_on_behalf_of_and_explicit_agent_delegation_are_supported(self):
        self.doc["spec"]["identity"]["mode"] = "on-behalf-of"
        self.mcp([grant(), grant("beta", delegation="agent")])
        self.assertTrue(self.run_check()["ok"])

    def test_duplicate_tools_follow_runtime_set_semantics(self):
        self.mcp([grant(tools=["query", "query"])])
        self.assertTrue(self.run_check()["ok"])

    def test_legacy_backend_uses_agent_contract_name_and_tool_constraints(self):
        self.mcp([grant("x" * 63, tools=["1-tool"])])
        result = self.run_check()
        self.assertEqual(len(self.checks(result, "legacy_backend_not_checked")), 1)
        self.assertFalse(self.checks(result, "mcp_grant"))

    def test_legacy_required_not_checked(self):
        self.mcp([grant("handwritten")])
        result = self.run_check()
        self.assertFalse(result["ok"])
        c = self.checks(result, "legacy_backend_not_checked")[0]
        self.assertEqual(c["state"], "not_checked")
        self.assertTrue(c["required"])
        self.assertIn("adapter", c["remediation"])

    def test_bad_tools_effect_delegation_and_duplicates(self):
        for grants in (
            [grant(tools=["write"])],
            [grant(effect="remote_write")],
            [grant(delegation="human")],
            [grant(tools="query")],
            [grant(), grant()],
        ):
            with self.subTest(grants=grants):
                self.mcp(grants)
                self.assertFalse(self.run_check()["ok"])

    def test_source_error_does_not_hide_independent_grant_failure(self):
        self.mcp([grant(tools=["write"])])
        self.source_check.return_value = {
            **receipt(),
            "ok": False,
            "errors": [
                {
                    "code": "capability_drift",
                    "path": "capabilities",
                    "message": "differ",
                }
            ],
        }
        result = self.run_check()
        self.assertEqual(
            self.checks(result, "source_compatibility")[0]["state"], "fail"
        )
        self.assertEqual(self.checks(result, "mcp_grant")[0]["state"], "fail")
        self.assertEqual(result["source"], self.source_check.return_value)

    def test_missing_source_environment_names_the_next_step(self):
        self.source_check.side_effect = source.SourceEnvironmentError(
            "The source checkout has no environment (.venv); the preflight never installs one."
        )
        result = self.run_check()
        (check,) = self.checks(result, "source_compatibility")
        self.assertEqual(check["state"], "unavailable")
        self.assertIn("no environment", check["explanation"])
        self.assertIn("uv sync --locked", check["remediation"])
        self.assertNotIn("tools/zetra_agents", json.dumps(result))

    def test_safe_errors_and_deterministic_output(self):
        self.mcp([grant()])
        self.source_check.side_effect = RuntimeError("credential-sensitive-string")
        self.reg.model.load_registry.side_effect = RuntimeError(
            "credential-sensitive-string"
        )
        result = self.run_check()
        self.assertNotIn("credential-sensitive-string", json.dumps(result))
        self.assertEqual(result, self.run_check())
        self.assertFalse(result["ok"])
        # A registry read failure cannot prove an unresolved handwritten backend.
        self.assertFalse(self.checks(result, "legacy_backend_not_checked"))

    def test_exclusions_are_explicit_and_nonrequired(self):
        result = self.run_check()
        for code in core.EXCLUSIONS:
            c = self.checks(result, code)[0]
            self.assertEqual(c["state"], "not_checked")
            self.assertFalse(c["required"])
        self.assertNotIn("Ready", json.dumps(result))

    def test_live_unavailable_required_and_sanitized(self):
        self.mcp([grant()])
        self.reg.transports.side_effect = RuntimeError("secret-token")
        result = self.run_check(live_scope=True)
        self.assertFalse(result["ok"])
        self.assertEqual(
            self.checks(result, "live_registration")[0]["state"], "unavailable"
        )
        self.assertNotIn("secret-token", json.dumps(result))

    def test_live_dependencies_deduplicated_and_incomplete_fails(self):
        self.mcp([grant(), grant(), grant("beta")])
        self.reg.transports.side_effect = None
        self.reg.transports.return_value = (Mock(), Mock())
        self.reg.status.inspect_registration.return_value = {
            "complete": False,
            "functional": "not-tested",
            "layers": [],
        }
        result = self.run_check(live_scope=True)
        self.assertFalse(result["ok"])
        self.assertEqual(self.reg.status.inspect_registration.call_count, 2)
        self.reg.transports.assert_called_once()

    def test_live_complete_registration_passes_with_exclusions(self):
        self.mcp([grant(), grant("beta")])
        self.reg.transports.side_effect = None
        self.reg.transports.return_value = (Mock(), Mock())
        result = self.run_check(live_scope=True)
        self.assertTrue(result["ok"])
        self.assertEqual(self.reg.status.inspect_registration.call_count, 2)
        self.assertTrue(
            all(
                c["evidence"]["functional"] == "not-tested"
                for c in self.checks(result, "live_registration")
            )
        )

    def test_live_no_mcp_does_not_authenticate(self):
        self.assertTrue(self.run_check(live_scope=True)["ok"])
        self.reg.transports.assert_not_called()

    def test_raw_kustomize_error_sanitized(self):
        self.mcp([grant()])
        self.reg.check.check.return_value = [
            "registry validation failed: Kustomize failed for x: secret raw process response"
        ]
        result = self.run_check()
        self.assertFalse(result["ok"])
        self.assertNotIn("secret raw process", json.dumps(result))


class Adapters(unittest.TestCase):
    def test_cli_live_failure_exits_nonzero_with_json(self):
        spec = importlib.util.spec_from_file_location(
            "agent_preflight_cli_test", OPS / "agent-preflight.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output = io.StringIO()
        with (
            patch.object(module, "run", return_value={"schemaVersion": 1, "ok": False}),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(
                module.main(
                    ["sample", "--source", "/trusted", "--tag", "sample/v1", "--live"]
                ),
                1,
            )
        self.assertFalse(json.loads(output.getvalue())["ok"])

    def test_get_only_rejects_before_dispatch(self):
        api = Mock()
        guard = live.GetOnly(api)
        for method in ("POST", "PUT", "DELETE", "PATCH", "get"):
            with self.assertRaises(ValueError):
                guard.call("clients", method=method)
        api.call.assert_not_called()
        guard.call("clients")
        api.call.assert_called_once_with("clients", method="GET")

    def test_metadata_only_secret_transport_reused(self):
        spec = importlib.util.spec_from_file_location(
            "registry_reader_test", OPS / "mcp-registry.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        process = Mock(
            return_value=SimpleNamespace(returncode=0, stdout="credential-name")
        )
        response = module.KubeReader(None, run=process)(
            "v1", "Secret", "mcp", "credential-name"
        )
        self.assertEqual(set(response), {"kind", "apiVersion", "metadata"})
        self.assertIn("jsonpath={.metadata.name}", process.call_args.args[0])

    FAKE_CHECKER = (
        'def check(repo, kubani, agent, tag):\n print("discard noisy checker output")\n return '
        + repr({**receipt(), "selectedChecker": True})
    )

    @staticmethod
    def fake_package(parent):
        package = parent / "zetra_agents"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("")
        (package / "layout.py").write_text("")
        # Deliberately no CLI or contracts package: only the public checker.
        (package / "preflight.py").write_text(
            Adapters.FAKE_CHECKER
        )

    @staticmethod
    def workspace_checkout(root):
        """A source checkout shaped like `uv sync --locked` output: its own virtual environment."""
        venv.EnvBuilder(with_pip=False).create(root / ".venv")
        site = next((root / ".venv").glob("lib/python*/site-packages"))
        return site

    def test_bridge_actual_selected_checker_and_no_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fake_package(root / "tools")
            result = source.check(root, root, "sample", "sample/v1")
            self.assertTrue(result["selectedChecker"])
            self.assertEqual(list(root.rglob("__pycache__")), [])

    def test_bridge_uses_workspace_checkout_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fake_package(self.workspace_checkout(root))
            self.assertFalse((root / "tools").exists())
            # Isolated mode must not hide the venv's own site-packages.
            result = source.check(root, root, "sample", "sample/v1")
            self.assertTrue(result["selectedChecker"])
            self.assertEqual(list(root.rglob("__pycache__")), [])

    def test_bridge_refuses_checkout_without_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(source.SourceEnvironmentError):
                source.check(Path(directory), Path(directory), "sample", "sample/v1")

    def test_bridge_rejects_invalid_oversize_and_timeout_safely(self):
        for body, timeout, limit, exception in (
            ("print('not-json')", 2, 1000, ValueError),
            ("import sys; sys.stdout.write('x'*10000)", 2, 100, ValueError),
            ("import time; time.sleep(2)", 0.05, 1000, TimeoutError),
        ):
            with (
                self.subTest(body=body),
                tempfile.TemporaryDirectory() as directory,
                patch.object(source, "BRIDGE", body),
                patch.object(source, "TIMEOUT", timeout),
                patch.object(source, "LIMIT", limit),
            ):
                root = Path(directory)
                self.workspace_checkout(root)
                with self.assertRaises(exception):
                    source.check(root, root, "sample", "sample/v1")

    def test_bridge_schema_and_subject_validation(self):
        for value in (
            {},
            {**receipt(), "schemaVersion": True},
            {**receipt(), "ok": False},
            receipt("other"),
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                source.validate(value, "sample", "sample/v1")

    @unittest.skipUnless(
        os.environ.get("AGENT_PREFLIGHT_SOURCE"),
        "explicit trusted source checkout not selected",
    )
    def test_real_trusted_source_checker_integration(self):
        root = OPS.parents[2]
        selected = Path(os.environ["AGENT_PREFLIGHT_SOURCE"])
        result = source.check(
            selected, root, "db-admin", "db-admin/v999.0.0-preflight-test"
        )
        self.assertEqual(result["schemaVersion"], 1)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["receipt"]["source"]["path"], str(selected.resolve()))
        self.assertEqual(result["receipt"]["agent"], "db-admin")
        self.assertIn("kubani", result["receipt"])
        self.assertTrue(result["receipt"]["files"])


if __name__ == "__main__":
    unittest.main()
