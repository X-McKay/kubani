"""Credential preparation uses local encrypted sources, never live administration."""

import importlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "infrastructure/scripts/ops"))
PROVISION = {
    "profile": "postgres-secret-pair-v1",
    "roleManifest": "infrastructure/gitops/apps/mcp/postgres-admin-mcp-role.enc.yaml",
    "workloadManifest": "infrastructure/gitops/apps/mcp/postgres-admin-mcp.enc.yaml",
    "username": "db_admin_monitor",
    "database": "postgres",
    "host": "postgresql.database.svc.cluster.local",
    "port": 5432,
    "policyDescription": "Reviewed metadata-only monitor role and interface grants",
}


class ProvisionModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "infrastructure", self.root / "infrastructure")
        shutil.copyfile(ROOT / ".sops.yaml", self.root / ".sops.yaml")
        self.model = importlib.import_module("mcp_registry.model")
        self.path = self.root / "infrastructure/mcp/backends/postgres-admin.yaml"
        self.entry = yaml.safe_load(self.path.read_text())
        self.entry["provision"] = dict(PROVISION)
        self.save()

    def save(self):
        self.path.write_text(yaml.safe_dump(self.entry))

    def absent(self):
        for field in ("roleManifest", "workloadManifest"):
            (self.root / PROVISION[field]).unlink()

    def test_absent_pair_is_allowed_only_in_provisioning_mode(self):
        self.absent()
        self.assertEqual(
            self.model.load_registry(self.root, provisioning=True)[0]["name"],
            "postgres-admin",
        )
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.model.load_registry(self.root)

    def test_complete_pair_and_exact_schema(self):
        self.assertEqual(self.model.load_registry(self.root)[0]["provision"], PROVISION)
        for key, value in [
            ("profile", "arbitrary-sql"),
            ("unknown", True),
            ("username", "a;drop"),
            ("host", "example.com"),
            ("port", 5433),
            ("roleManifest", PROVISION["workloadManifest"]),
        ]:
            with self.subTest(key=key):
                self.entry["provision"] = dict(PROVISION, **{key: value})
                self.save()
                with self.assertRaises(ValueError):
                    self.model.load_registry(self.root, provisioning=True)

    def test_partial_pair_and_wrong_secret_identity_refuse(self):
        (self.root / PROVISION["roleManifest"]).unlink()
        with self.assertRaises(ValueError):
            self.model.load_registry(self.root, provisioning=True)
        self.absent_if_present()
        self.entry["workload"]["secretEnv"][0]["secretKeyRef"]["key"] = "other"
        self.save()
        with self.assertRaises(ValueError):
            self.model.load_registry(self.root, provisioning=True)

    def absent_if_present(self):
        for field in ("roleManifest", "workloadManifest"):
            (self.root / PROVISION[field]).unlink(missing_ok=True)

    def test_pair_collision_across_backends_refuses(self):
        other = dict(self.entry, name="example")
        other["authorization"] = dict(
            self.entry["authorization"], role="agent-role-example-read"
        )
        self.path.with_name("example.yaml").write_text(yaml.safe_dump(other))
        with self.assertRaises(ValueError):
            self.model.load_registry(self.root, provisioning=True)


class ProvisionTests(unittest.TestCase):
    save = ProvisionModelTests.save
    absent = ProvisionModelTests.absent
    absent_if_present = ProvisionModelTests.absent_if_present

    def setUp(self):
        ProvisionModelTests.setUp(self)
        self.provision = importlib.import_module("mcp_registry.provision")

    def test_plan_absent_pair_is_readonly_and_lists_admin(self):
        self.absent()
        result = self.provision.plan(self.root, self.entry)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(
            [v["action"] for v in result["operations"]], ["create", "create"]
        )
        self.assertIn(
            {
                "namespace": "database",
                "name": "postgresql-credentials",
                "key": "postgres-password",
            },
            result["administratorReferences"],
        )
        self.assertFalse((self.root / PROVISION["roleManifest"]).exists())

    def test_complete_pair_is_preserved_without_sops(self):
        before = {
            v: (self.root / PROVISION[v]).read_bytes()
            for v in ("roleManifest", "workloadManifest")
        }

        def forbidden(*args, **kwargs):
            self.fail("complete pair invoked encryption")

        result = self.provision.apply(self.root, self.entry, run=forbidden)
        self.assertEqual(result["status"], "preserved")
        for v, data in before.items():
            self.assertEqual((self.root / PROVISION[v]).read_bytes(), data)

    def test_missing_dependencies_and_inclusion_refuse(self):
        for relative in (
            "infrastructure/gitops/apps/postgresql/secret.enc.yaml",
            "infrastructure/gitops/apps/mcp/kustomization.yaml",
        ):
            path = self.root / relative
            original = path.read_bytes()
            if "kustomization" in relative:
                path.write_text(
                    path.read_text().replace("  - postgres-admin-role-job.yaml\n", "")
                )
            else:
                path.unlink()
            self.assertEqual(
                self.provision.plan(self.root, self.entry)["status"], "conflict"
            )
            path.write_bytes(original)

    def test_ciphertexts_published_only_after_both_encryptions_and_share_password(self):
        from types import SimpleNamespace
        from urllib.parse import urlparse

        self.absent()
        inputs = []

        def encrypt(argv, **kwargs):
            self.assertNotIn("db_admin_monitor", " ".join(argv))
            self.assertIn("--filename-override", argv)
            plain = yaml.safe_load(kwargs["input"])
            import copy

            inputs.append(copy.deepcopy(plain))
            self.assertFalse((self.root / PROVISION["roleManifest"]).exists())
            self.assertFalse((self.root / PROVISION["workloadManifest"]).exists())
            plain["stringData"] = {
                k: "ENC[AES256_GCM,data:cipher]" for k in plain["stringData"]
            }
            plain["sops"] = {
                "age": [{"recipient": "age1fake", "enc": "cipher"}],
                "mac": "ENC[AES256_GCM,data:mac]",
            }
            return SimpleNamespace(
                returncode=0, stdout=yaml.safe_dump(plain), stderr=""
            )

        result = self.provision.apply(self.root, self.entry, run=encrypt)
        self.assertEqual(result["status"], "created")
        password = inputs[0]["stringData"]["password"]
        self.assertEqual(
            urlparse(inputs[1]["stringData"]["DATABASE_URI"]).password, password
        )
        self.assertNotIn(password, str(result))
        self.assertEqual(len(list(self.root.rglob(".mcp-*"))), 0)

    def test_failed_or_plaintext_sops_output_publishes_nothing(self):
        from types import SimpleNamespace

        self.absent()
        for code, output in (
            (1, "sensitive"),
            (0, "kind: Secret\nstringData:\n  password: sensitive\n"),
        ):

            def encrypt(*args, code=code, output=output, **kwargs):
                return SimpleNamespace(
                    returncode=code, stdout=output, stderr="sensitive"
                )

            result = self.provision.apply(self.root, self.entry, run=encrypt)
            self.assertEqual(result["status"], "conflict")
            self.assertNotIn("sensitive", str(result))
            self.assertFalse((self.root / PROVISION["roleManifest"]).exists())

    def test_bad_policy_and_symlink_refuse(self):
        (self.root / ".sops.yaml").write_text("creation_rules: []\n")
        self.assertEqual(
            self.provision.plan(self.root, self.entry)["status"], "conflict"
        )
        self.absent()
        (self.root / PROVISION["roleManifest"]).symlink_to(
            "/tmp/missing-provision-secret"
        )
        self.assertEqual(
            self.provision.plan(self.root, self.entry)["status"], "conflict"
        )

    def test_partial_publication_is_reported_and_retry_refuses(self):
        from types import SimpleNamespace

        self.absent()
        calls = 0

        def encrypt(argv, **kwargs):
            nonlocal calls
            calls += 1
            doc = yaml.safe_load(kwargs["input"])
            doc["stringData"] = {
                k: "ENC[AES256_GCM,data:cipher]" for k in doc["stringData"]
            }
            doc["sops"] = {
                "age": [{"recipient": "age1fake", "enc": "cipher"}],
                "mac": "ENC[AES256_GCM,data:mac]",
            }
            if calls == 2:
                (self.root / PROVISION["workloadManifest"]).write_text(
                    "concurrent owner"
                )
            return SimpleNamespace(returncode=0, stdout=yaml.safe_dump(doc), stderr="")

        result = self.provision.apply(self.root, self.entry, run=encrypt)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["published"], [PROVISION["roleManifest"]])
        self.assertEqual(
            (self.root / PROVISION["workloadManifest"]).read_text(), "concurrent owner"
        )
        self.assertEqual(
            self.provision.apply(self.root, self.entry, run=encrypt)["status"],
            "conflict",
        )
        self.assertEqual(calls, 2)

    def test_reviewed_sql_revision_guard_and_duplicate_source_identity(self):
        import hashlib

        sql = self.root / self.entry["bootstrap"]["sql"]
        sql.write_text(sql.read_text() + "\n-- review\n")
        self.entry["bootstrap"]["sqlSha256"] = (
            "sha256:" + hashlib.sha256(sql.read_bytes()).hexdigest()
        )
        self.assertIn(
            "SQL hash changed without reviewed bootstrap revision",
            self.provision.plan(self.root, self.entry)["issues"],
        )
        self.entry["bootstrap"]["sqlSha256"] = yaml.safe_load(self.path.read_text())[
            "bootstrap"
        ]["sqlSha256"]
        sql.write_bytes((ROOT / self.entry["bootstrap"]["sql"]).read_bytes())
        source = self.root / PROVISION["roleManifest"]
        source.with_name("duplicate.enc.yaml").write_bytes(source.read_bytes())
        self.assertTrue(
            any(
                "duplicate Secret identity" in v
                for v in self.provision.plan(self.root, self.entry)["issues"]
            )
        )

    @unittest.skipUnless(
        shutil.which("sops") and shutil.which("age-keygen"),
        "requires real sops and age-keygen",
    )
    def test_disposable_real_sops_round_trip(self):
        import os
        import subprocess
        from urllib.parse import urlparse

        self.absent()
        # Disposable key is test-only, outside all repository production paths.
        key = self.root / "disposable-age-key.txt"
        generated = subprocess.run(
            ["age-keygen", "-o", str(key)], capture_output=True, text=True, check=True
        )
        recipient = generated.stderr.strip().split()[-1]
        (self.root / ".sops.yaml").write_text(
            yaml.safe_dump(
                {
                    "creation_rules": [
                        {
                            "path_regex": r"\.enc\.yaml$",
                            "encrypted_regex": "^(data|stringData)$",
                            "age": recipient,
                        }
                    ]
                }
            )
        )
        captured = []

        def encrypt(argv, **kwargs):
            captured.append(yaml.safe_load(kwargs["input"]))
            check = kwargs.pop("check")
            return subprocess.run(argv, check=check, **kwargs)

        result = self.provision.apply(self.root, self.entry, run=encrypt)
        self.assertEqual(result["status"], "created")
        decrypted = []
        for field in ("roleManifest", "workloadManifest"):
            output = subprocess.run(
                ["sops", "--decrypt", str(self.root / PROVISION[field])],
                env={**os.environ, "SOPS_AGE_KEY_FILE": str(key)},
                capture_output=True,
                text=True,
                check=True,
            )
            decrypted.append(yaml.safe_load(output.stdout))
        password = decrypted[0]["stringData"]["password"]
        self.assertEqual(
            urlparse(decrypted[1]["stringData"]["DATABASE_URI"]).password, password
        )
        self.assertEqual(password, captured[0]["stringData"]["password"])
        self.assertNotIn(password, str(result))

    def test_managed_pair_refuses_extra_or_overlapping_keys(self):
        path = self.root / PROVISION["roleManifest"]
        original = yaml.safe_load(path.read_text())
        for duplicate in (False, True):
            import copy

            doc = copy.deepcopy(original)
            if duplicate:
                doc["data"] = dict(original["stringData"])
            else:
                doc["stringData"]["extra"] = next(iter(original["stringData"].values()))
            path.write_text(yaml.safe_dump(doc))
            self.assertEqual(
                self.provision.plan(self.root, self.entry)["status"], "conflict"
            )

    def test_bootstrap_image_pull_credentials_are_explicitly_refused(self):
        path = self.root / self.entry["bootstrap"]["manifest"]
        docs = list(yaml.safe_load_all(path.read_text()))
        docs[0]["spec"]["template"]["spec"]["imagePullSecrets"] = [
            {"name": "unresolved-pull-credentials"}
        ]
        path.write_text(yaml.safe_dump_all(docs))
        result = self.provision.plan(self.root, self.entry)
        self.assertEqual(result["status"], "conflict")
        self.assertIn(
            "unsupported bootstrap imagePullSecrets dependency", result["issues"]
        )
