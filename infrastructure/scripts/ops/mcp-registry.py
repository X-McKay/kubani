#!/usr/bin/env python3
"""Generate and verify registered MCP backends; live writes require identity apply."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
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
    result = argparse.ArgumentParser(description=__doc__)
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
        raise ValueError("invalid backend name")
    parent = root
    for part in ("infrastructure", "mcp", "backends"):
        parent = parent / part
        if parent.is_symlink():
            raise ValueError("refusing symlinked registry path")
    for path in parent.glob("*.yaml"):
        if path.is_symlink():
            raise ValueError("symlink declaration refused")
        # Collision inventory only: a previous add intentionally leaves a scaffold.
        for entry in model.yaml_documents(path):
            if isinstance(entry, dict) and entry.get("name") == name:
                raise ValueError("backend already registered")
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
                raise ValueError("backend must be uniquely registered")
            operation = getattr(services.provision, args.action)
            output = operation(root, selected[0])
            if output.get("status") not in {"ready", "preserved", "created"}:
                print(json.dumps(output, sort_keys=True))
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
                    print(json.dumps(output, sort_keys=True))
                    return 1
        else:
            issues = services.check.check(root)
            if issues:
                print(
                    json.dumps(
                        {"status": "invalid-registration", "issues": issues},
                        sort_keys=True,
                    )
                )
                return 1
            if args.command == "check":
                output = {"status": "valid", "scope": "offline-registration"}
            else:
                entries = services.model.load_registry(root)
                selected = [entry for entry in entries if entry["name"] == args.name]
                if len(selected) != 1:
                    raise ValueError("backend must be uniquely registered")
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
                        print(json.dumps(output, sort_keys=True))
                        return 1
        print(json.dumps(output, sort_keys=True))
        return 0
    except Exception as error:  # noqa: BLE001 - never expose credential-bearing exceptions
        # Exceptions can contain credential-bearing HTTP/process responses.
        print(
            json.dumps(
                {
                    "status": "refused",
                    "stage": stage,
                    "error_type": type(error).__name__,
                    "note": "No conflicting identity is overwritten. Inspect configuration and any partial operation before retry.",
                },
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
