"""Docker's default bridge must inherit the surrounding Kata guest's MTU."""

import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCALE_SET = ROOT / "infrastructure/gitops/apps/arc-runners/scale-set-zetra-agents.yaml"
MTU_PATH = "/sys/class/net/eth0/mtu"
ENTRYPOINT = "/usr/local/bin/dockerd-entrypoint.sh"


class DindMTU(unittest.TestCase):
    def run_startup(self, mtu):
        spec = yaml.safe_load(SCALE_SET.read_text())["spec"]["values"]["template"][
            "spec"
        ]
        dind = next(c for c in spec["initContainers"] if c["name"] == "dind")
        self.assertEqual(dind.get("command"), ["/bin/sh", "-ec"])
        self.assertEqual(len(dind["args"]), 1)
        script = dind["args"][0]
        self.assertIn(MTU_PATH, script)
        self.assertIn(ENTRYPOINT, script)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, stub, result = root / "mtu", root / "entrypoint", root / "argv"
            if mtu is not None:
                source.write_text(mtu)
            stub.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$ARC_TEST_ARGV"\n')
            stub.chmod(0o700)
            script = script.replace(MTU_PATH, shlex.quote(str(source)))
            script = script.replace(ENTRYPOINT, shlex.quote(str(stub)))
            process = subprocess.run(
                [*dind["command"], script],
                env={
                    **os.environ,
                    "DOCKER_GROUP_GID": "123",
                    "ARC_TEST_ARGV": str(result),
                },
                capture_output=True,
                text=True,
                timeout=3,
            )
            return process, result.read_text().splitlines() if result.exists() else None

    def test_dockerd_inherits_guest_mtu_and_preserves_startup_flags(self):
        for mtu in ("1230", "1500", "576", "65535"):
            with self.subTest(mtu=mtu):
                process, argv = self.run_startup(mtu + "\n")
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertEqual(
                    argv,
                    [
                        "dockerd",
                        "--host=unix:///var/run/docker.sock",
                        "--group=123",
                        "--mtu=" + mtu,
                    ],
                )

    def test_invalid_or_missing_guest_mtu_prevents_daemon_start(self):
        for mtu in (
            None,
            "",
            "0\n",
            "575\n",
            "65536\n",
            "bad\n",
            "1230;id\n",
            "999999999999999999999999999\n",
        ):
            with self.subTest(mtu=mtu):
                process, argv = self.run_startup(mtu)
                self.assertNotEqual(process.returncode, 0)
                self.assertIsNone(argv)
