"""Bounded adapter to an explicitly trusted source checkout's existing checker."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

LIMIT = 1024 * 1024
TIMEOUT = 45
BRIDGE = r"""
import contextlib, json, os, sys
from pathlib import Path
if sys.argv[1]:  # legacy checkout only; a workspace checkout's own environment supplies the package
    sys.path.insert(0, sys.argv[1])
# Source is explicitly selected executable trusted local input, not a sandbox.
with open(os.devnull, "w") as discard, contextlib.redirect_stdout(discard), contextlib.redirect_stderr(discard):
    from zetra_agents import layout, preflight
    result = preflight.check(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], sys.argv[5])
sys.stdout.write(json.dumps(result, allow_nan=False, sort_keys=True))
"""


NO_ENVIRONMENT = "The source checkout has no environment (.venv); the preflight never installs one."


class SourceEnvironmentError(RuntimeError):
    """The selected checkout cannot run its checker; the message is fixed and safe to show."""


def interpreter(source: Path):
    """Return (python, extra sys.path entry) for the selected checkout.

    A workspace checkout gets its tooling from the environment `uv sync --locked`
    builds in `.venv`; that interpreter is used as is (never resolved, so it still
    finds its pyvenv.cfg, which `-I` does not disturb). A checkout from before the
    workspace move keeps its `tools/zetra_agents` and runs on this interpreter.
    """
    legacy = source / "tools"
    if (legacy / "zetra_agents").is_dir():
        return sys.executable, str(legacy)
    python = source / ".venv" / "bin" / "python"
    if not python.is_file():
        raise SourceEnvironmentError(NO_ENVIRONMENT)
    return str(python), ""


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def validate(value, agent, tag):
    if (
        not isinstance(value, dict)
        or type(value.get("schemaVersion")) is not int
        or value["schemaVersion"] != 1
        or type(value.get("ok")) is not bool
        or value.get("scope") != "candidate-desired-gitops"
        or not isinstance(value.get("receipt"), dict)
        or not isinstance(value.get("errors"), list)
    ):
        raise ValueError("unsupported source receipt")
    receipt = value["receipt"]
    if receipt.get("agent") != agent or receipt.get("tag") != tag:
        raise ValueError("source receipt subject mismatch")
    if any(
        not isinstance(v, dict)
        or set(v) != {"code", "path", "message"}
        or any(not isinstance(s, str) or len(s) > 1024 for s in v.values())
        for v in value["errors"]
    ):
        raise ValueError("invalid source errors")
    if value["ok"] != (not value["errors"]):
        raise ValueError("inconsistent source result")
    if not isinstance(receipt.get("files"), list) or len(receipt["files"]) > 4096:
        raise ValueError("invalid source file evidence")
    for item in receipt["files"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"path", "sha256"}
            or not isinstance(item["path"], str)
            or len(item["path"]) > 4096
            or not isinstance(item["sha256"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"])
        ):
            raise ValueError("invalid source file evidence")
    for key in ("source", "kubani"):
        checkout = receipt.get(key)
        if checkout is None:
            if value["ok"]:
                raise ValueError("successful source result lacks checkout evidence")
            continue
        if (
            not isinstance(checkout, dict)
            or not isinstance(checkout.get("path"), str)
            or not isinstance(checkout.get("head"), str)
            or not re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", checkout["head"])
            or type(checkout.get("dirty")) is not bool
        ):
            raise ValueError("invalid source checkout evidence")
        main = checkout.get("main")
        if main is not None and (
            not isinstance(main, dict)
            or main.get("ref") not in ("refs/remotes/origin/main", "refs/heads/main")
            or not isinstance(main.get("head"), str)
            or not re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", main["head"])
            or type(main.get("ancestor")) is not bool
        ):
            raise ValueError("invalid local-main evidence")
    return value


def check(source: Path, root: Path, agent: str, tag: str):
    """No shell, CLI imports, credentials or network setup; never expose stderr."""
    # Files bound memory while polling bounds output on disk and execution time.
    python, extra_path = interpreter(source)
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(
            [
                python,
                "-I",
                "-B",
                "-c",
                BRIDGE,
                extra_path,
                str(source),
                str(root),
                agent,
                tag,
            ],
            stdout=out,
            stderr=err,
        )
        import time

        deadline = time.monotonic() + TIMEOUT
        try:
            while proc.poll() is None:
                if out.tell() > LIMIT or err.tell() > LIMIT:
                    raise ValueError("source output exceeds bound")
                if time.monotonic() >= deadline:
                    raise TimeoutError("source checker timed out")
                time.sleep(0.02)
            if proc.returncode or out.tell() > LIMIT or err.tell() > LIMIT:
                raise ValueError("source checker unavailable or output exceeds bound")
            out.seek(0)
            raw = out.read(LIMIT + 1)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()

    def invalid_constant(_):
        raise ValueError("invalid JSON constant")

    return validate(
        json.loads(raw, object_pairs_hook=_pairs, parse_constant=invalid_constant),
        agent,
        tag,
    )
