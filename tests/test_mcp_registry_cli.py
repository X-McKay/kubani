"""Operator command boundaries: offline add, explicit identity writes, safe reads."""

import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

PATH = (
    Path(__file__).resolve().parents[1] / "infrastructure/scripts/ops/mcp-registry.py"
)
SPEC = importlib.util.spec_from_file_location("mcp_registry_cli", PATH)
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.modules = SimpleNamespace(
            model=SimpleNamespace(
                load_registry=Mock(return_value=[{"name": "existing"}]),
                scaffold=Mock(return_value="version: 1\nname: extra\n"),
                descriptor=Mock(return_value={"role": {}}),
            ),
            render=SimpleNamespace(
                render=Mock(return_value={}),
                write=Mock(),
                objects=Mock(return_value=[]),
            ),
            check=SimpleNamespace(check=Mock(return_value=[])),
            identity=SimpleNamespace(
                admin=Mock(),
                configure=Mock(return_value={"planned": [], "changed": []}),
            ),
            status=SimpleNamespace(
                inspect_registration=Mock(
                    return_value={"complete": True, "functional": "not-tested"}
                )
            ),
        )

    def invoke(self, args):
        output = io.StringIO()
        with (
            patch.object(cli, "modules", return_value=self.modules),
            patch("sys.stdout", output),
        ):
            code = cli.main(["--root", str(self.root), *args])
        return code, json.loads(output.getvalue())

    def test_add_writes_only_definition_without_auth_or_render(self):
        code, result = self.invoke(["add", "extra"])
        self.assertEqual(code, 0)
        p = self.root / "infrastructure/mcp/backends/extra.yaml"
        self.assertEqual(p.read_text(), "version: 1\nname: extra\n")
        self.assertEqual(
            [
                str(x.relative_to(self.root))
                for x in self.root.rglob("*")
                if x.is_file()
            ],
            [str(p.relative_to(self.root))],
        )
        self.modules.identity.admin.assert_not_called()
        self.modules.render.write.assert_not_called()
        self.assertFalse(result["deployed"])

    def test_add_refuses_existing_name_and_file_without_overwriting(self):
        self.assertEqual(self.invoke(["add", "existing"])[0], 1)
        self.assertEqual(self.invoke(["add", "extra"])[0], 0)
        p = self.root / "infrastructure/mcp/backends/extra.yaml"
        p.write_text("retain me")
        self.assertEqual(self.invoke(["add", "extra"])[0], 1)
        self.assertEqual(p.read_text(), "retain me")

    def test_add_refuses_symlink_escape(self):
        (self.root / "infrastructure").symlink_to("/tmp", target_is_directory=True)
        self.assertEqual(self.invoke(["add", "extra"])[0], 1)
        self.modules.identity.admin.assert_not_called()

    def test_identity_plan_is_readonly_and_apply_is_explicit(self):
        self.assertEqual(self.invoke(["identity", "plan", "existing"])[0], 0)
        self.assertFalse(self.modules.identity.configure.call_args.kwargs["apply"])
        self.assertEqual(self.invoke(["identity", "apply", "existing"])[0], 0)
        self.assertTrue(self.modules.identity.configure.call_args.kwargs["apply"])

    def test_bad_registry_prevents_auth_or_cluster_calls(self):
        self.modules.check.check.return_value = ["missing JWT protection"]
        self.assertEqual(self.invoke(["identity", "apply", "existing"])[0], 1)
        self.assertEqual(self.invoke(["status", "existing"])[0], 1)
        self.modules.identity.admin.assert_not_called()
        self.modules.status.inspect_registration.assert_not_called()

    def test_status_incomplete_has_nonzero_exit_and_does_not_apply(self):
        self.modules.status.inspect_registration.return_value = {
            "complete": False,
            "functional": "not-tested",
        }
        self.assertEqual(self.invoke(["status", "existing"])[0], 1)
        self.modules.identity.configure.assert_not_called()

    def test_exception_text_is_not_printed(self):
        self.modules.identity.admin.side_effect = RuntimeError(
            "PRIVATE_CREDENTIAL_MARKER"
        )
        code, result = self.invoke(["identity", "plan", "existing"])
        self.assertEqual(code, 1)
        self.assertNotIn("PRIVATE_CREDENTIAL_MARKER", json.dumps(result))
        self.assertEqual(result["error_type"], "RuntimeError")

    def test_kubectl_secret_read_requests_name_only(self):
        run = Mock(return_value=subprocess.CompletedProcess([], 0, "db-secret", ""))
        reader = cli.KubeReader("/example/config", run=run)
        actual = reader("v1", "Secret", "mcp", "db-secret")
        self.assertEqual(actual["metadata"]["name"], "db-secret")
        argv = run.call_args.args[0]
        self.assertIn("jsonpath={.metadata.name}", argv)
        self.assertNotIn("json", argv)
        self.assertIn("/example/config", argv)

    def test_kubectl_notfound_is_none_and_errors_never_expose_output(self):
        run = Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
        reader = cli.KubeReader(None, run=run)
        self.assertIsNone(reader("v1", "Service", "mcp", "server"))
        run.return_value = subprocess.CompletedProcess([], 1, "", "PRIVATE_ERROR")
        with self.assertRaisesRegex(RuntimeError, "cluster read failed") as found:
            reader("v1", "Service", "mcp", "server")
        self.assertNotIn("PRIVATE_ERROR", str(found.exception))

    def test_kubectl_refuses_unapproved_kind_and_flag_names(self):
        run = Mock()
        reader = cli.KubeReader(None, run=run)
        for version, kind, namespace, name in [
            ("v1", "Pod", "mcp", "server"),
            ("v1", "Secret", "mcp", "--all"),
        ]:
            with self.assertRaises(ValueError):
                reader(version, kind, namespace, name)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
