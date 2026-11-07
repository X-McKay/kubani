"""Lazy adapters for registration evidence; no deployment or functional sessions."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path


class GetOnly:
    def __init__(self, api):
        self.api = api

    def call(self, path, method="GET", *args, **kwargs):
        if method != "GET":
            raise ValueError("preflight permits GET only")
        return self.api.call(path, *args, method=method, **kwargs)


def transports(identity):
    spec = importlib.util.spec_from_file_location(
        "agent_preflight_registry_reader",
        Path(__file__).resolve().parents[1] / "mcp-registry.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # This uses the existing operator SOPS administrator authentication. It may
    # decrypt that credential, but never requests backend Secret values.
    return module.KubeReader(os.environ.get("KUBECONFIG")), GetOnly(identity.admin())
