"""Run the SDK fixture evaluator through a local official MCP server."""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
with socket.socket() as binding:
    binding.bind(("127.0.0.1", 0))
    port = binding.getsockname()[1]
with tempfile.TemporaryDirectory() as directory:
    directory = Path(directory)
    with (directory / "server.log").open("w") as log:
        server = subprocess.Popen(
            [sys.executable, str(root / "tests/fixtures_mcp.py"), "--port", str(port)],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError((directory / "server.log").read_text())
                    time.sleep(0.05)
            else:
                raise TimeoutError("fixture MCP server did not start")
            project = directory / "project"
            project.mkdir()
            for name in ("src", "evals"):
                shutil.copytree(
                    root / name, project / name, ignore=shutil.ignore_patterns("__pycache__")
                )
            for name in ("pyproject.toml", "uv.lock", "README.md"):
                shutil.copy2(root / name, project / name)
            manifest = project / "src/kubani_investigator/agents/investigator/agent.yaml"
            text = (
                manifest.read_text()
                .replace("model: vllm", "model: fixture")
                .replace("policy: vllm-chat", "policy: workspace")
            )
            manifest.write_text(text)
            env = {
                **os.environ,
                "MCP_ENDPOINT": f"http://127.0.0.1:{port}/mcp",
                "MCP_ACCESS_TOKEN": "fixture-placeholder",
            }
            completed = subprocess.run(
                [sys.executable, "-m", "zetra", "eval", str(project), "--mode", "fixture"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            if completed.returncode:
                raise RuntimeError(completed.stderr)
            report = json.loads(completed.stdout)
            assert report["status"] == "PASSED", report
            print(json.dumps(report, indent=2))
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
