#!/usr/bin/env python3
"""Generate and verify registered MCP backends; live writes require identity apply."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import outcome  # noqa: E402

OFFLINE_STAGES = frozenset({"add", "render", "check"})
NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
# What a stage that can touch a credential says about a failure: one fixed sentence per code, never the exception's text.
FIXED_MESSAGES = {
    "unavailable": "a service or tool this stage depends on could not be reached or did not answer; the exception text is withheld",
    "timeout": "a service or tool this stage depends on did not answer in time; the exception text is withheld",
    "not-found": "the named backend is not registered",
    "conflict": "existing state conflicts with the request; the exception text is withheld",
    "validation-failed": "an input or a response broke a rule; the exception text is withheld",
    "internal": "an unexpected error occurred; only its type is shown",
}


class Refusal(ValueError):
    """A refusal this file raises itself, with the outcome code it ends as. Its message is a fixed sentence written here."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def emit(document):
    print(json.dumps(document, sort_keys=True))


class Parser(argparse.ArgumentParser):
    """argparse, which still prints usage and the message to stderr and exits 2, plus the `invalid-arguments` document on stdout."""

    def error(self, message):
        emit(outcome.document({}, outcome.error("invalid-arguments", message)))
        super().error(message)


def classify(stage, error):
    """The outcome code of an exception raised in `stage`, decided from its type and stage, never from its text."""
    if isinstance(error, Refusal):
        return error.code
    if isinstance(error, (subprocess.TimeoutExpired, TimeoutError)):
        return "timeout"
    if stage in OFFLINE_STAGES:
        if isinstance(error, FileExistsError):
            return "conflict"
        if isinstance(error, FileNotFoundError):
            return "unavailable" if error.filename in ("kubectl", "kustomize") else "not-found"
        if isinstance(error, ValueError):
            return "validation-failed"
        return "failed" if isinstance(error, OSError) else "internal"
    if isinstance(error, (OSError, RuntimeError, subprocess.SubprocessError, urllib.error.URLError)):
        return "unavailable"
    if isinstance(error, ValueError):
        return "unavailable" if stage == "identity-authentication" else "conflict" if stage == "identity" else "validation-failed"
    return "internal"


def invalid_registration(issues):
    proofs = [{"check": "registry-validation", "ok": False, "detail": issue} for issue in issues]
    return outcome.error("check-failed", f"{len(issues)} registration checks did not hold; see proofs", proofs=proofs)
def modules():
    # Import lazily: help and offline commands do not initialize credentials.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    return SimpleNamespace(
        **{
            name: importlib.import_module("mcp_registry." + name)
            for name in (
                "model",
                "render",
                "check",
                "identity",
                "status",
                "provision",
                "kube",
            )
        }
    )


def parser():
    result = Parser(description=__doc__)
    result.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[3]
    )
    result.add_argument("--kubeconfig", default=os.environ.get("KUBECONFIG"))
    commands = result.add_subparsers(dest="command", required=True)
    add = commands.add_parser(
        "add", help="create one non-secret SSE definition; does not deploy"
    )
    add.add_argument("name")
    render = commands.add_parser("render", help="deterministic generated GitOps files")
    mode = render.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    commands.add_parser("check", help="offline full registration consistency checks")
    provision = commands.add_parser(
        "provision", help="local encrypted credential preparation; Flux deploys"
    )
    provision.add_argument("action", choices=("plan", "apply"))
    provision.add_argument("name")
    identity = commands.add_parser("identity", help="explicit Keycloak operations")
    identity.add_argument("action", choices=("plan", "apply"))
    identity.add_argument("name")
    status = commands.add_parser(
        "status", help="read-only registration status; not a functional test"
    )
    status.add_argument("name")
    return result


def add_definition(root, name, model):
    if not NAME.fullmatch(name) or len(name) > 40:
        raise Refusal("invalid backend name", "invalid-arguments")
    parent = root
    for part in ("infrastructure", "mcp", "backends"):
        parent = parent / part
        if parent.is_symlink():
            raise Refusal("refusing symlinked registry path", "refused")
    for path in parent.glob("*.yaml"):
        if path.is_symlink():
            raise Refusal("symlink declaration refused", "refused")
        # Collision inventory only: a previous add intentionally leaves a scaffold.
        for entry in model.yaml_documents(path):
            if isinstance(entry, dict) and entry.get("name") == name:
                raise Refusal("backend already registered", "conflict")
    text = model.scaffold(name)
    target = parent / (name + ".yaml")
    parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also refuses an existing/dangling symlink target.
    with target.open("x", encoding="utf-8") as output:
        output.write(text)
    return {
        "status": "definition-created",
        "path": str(target.relative_to(root)),
        "deployed": False,
        "next": "Fill required values, then render --write and check; review the GitOps diff before merge.",
    }


def main(argv=None):
    args = parser().parse_args(argv)
    stage = args.command
    try:
        root = args.root.resolve(strict=True)
        services = modules()
        if args.command == "add":
            output = add_definition(root, args.name, services.model)
        elif args.command == "provision":
            entries = services.model.load_registry(root, provisioning=True)
            selected = [entry for entry in entries if entry["name"] == args.name]
            if len(selected) != 1:
                raise Refusal("backend must be uniquely registered", "not-found" if not selected else "conflict")
            operation = getattr(services.provision, args.action)
            output = operation(root, selected[0])
            if output.get("status") not in {"ready", "preserved", "created"}:
                emit(outcome.document(output, outcome.error("conflict", "existing state or sources prevent credential preparation; see status and issues")))
                return 1
        elif args.command == "render":
            if args.write:
                services.render.write(root)
                output = {"status": "rendered"}
            else:
                expected = services.render.render(
                    root, services.model.load_registry(root)
                )
                stale = [
                    path
                    for path, content in expected.items()
                    if not (root / path).is_file()
                    or (root / path).read_bytes() != content
                ]
                output = {"status": "current" if not stale else "stale", "files": stale}
                if stale:
                    proofs = [{"path": path, "state": "stale" if path in stale else "current"} for path in sorted(expected)]
                    emit(outcome.document(output, outcome.error("check-failed", f"{len(stale)} generated files are stale or missing; see proofs", proofs=proofs)))
                    return 1
        else:
            issues = services.check.check(root)
            if issues:
                emit(outcome.document({"status": "invalid-registration", "issues": issues}, invalid_registration(issues)))
                return 1
            if args.command == "check":
                output = {"status": "valid", "scope": "offline-registration"}
            else:
                entries = services.model.load_registry(root)
                selected = [entry for entry in entries if entry["name"] == args.name]
                if len(selected) != 1:
                    raise Refusal("backend must be uniquely registered", "not-found" if not selected else "conflict")
                descriptor = services.model.descriptor(selected[0])
                stage = "identity-authentication"
                api = services.identity.admin()
                stage = args.command
                if args.command == "identity":
                    output = services.identity.configure(
                        api, descriptor, apply=args.action == "apply"
                    )
                else:
                    output = services.status.inspect_registration(
                        services.render.objects(root, args.name),
                        descriptor,
                        read_object=services.kube.KubeReader(args.kubeconfig),
                        api=api,
                    )
                    if not output.get("complete"):
                        layers = output.get("layers", [])
                        open_layers = [layer for layer in layers if not layer.get("complete")]
                        if open_layers and all(str(layer.get("state", "")).startswith("unavailable") for layer in open_layers):
                            failure = outcome.error("unavailable", f"{len(open_layers)} registration layers could not be read; see layers")
                        else:
                            failure = outcome.error("check-failed", f"{len(open_layers)} registration layers are not current and ready; see proofs", proofs=list(layers))
                        emit(outcome.document(output, failure))
                        return 1
        emit(outcome.document(output))
        return 0
    except KeyboardInterrupt:
        emit(outcome.document({}, outcome.error("interrupted", "interrupted before the command finished")))
        raise
    except Exception as error:  # noqa: BLE001 - never expose credential-bearing exceptions
        # Exceptions can contain credential-bearing HTTP/process responses.
        refusal = {
            "status": "refused",
            "stage": stage,
            "error_type": "ValueError" if isinstance(error, Refusal) else type(error).__name__,
            "note": "No conflicting identity is overwritten. Inspect configuration and any partial operation before retry.",
        }
        # Only stages that read committed files may show the message: nothing
        # there touches a credential. Every other stage reports the type only.
        code = classify(stage, error)
        if stage in OFFLINE_STAGES and isinstance(error, (ValueError, OSError)):
            message = str(error) or type(error).__name__
        elif stage in OFFLINE_STAGES:
            message = "an unexpected error ended the stage; only the exception type is shown" if code == "internal" else "the stage did not finish; only the exception type is shown"
        else:
            message = FIXED_MESSAGES.get(code, FIXED_MESSAGES["internal"])
        # `error` was a string here for offline refusals; it is now the contract's object and its `message` is that string.
        emit(outcome.document(refusal, outcome.error(code, message)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
