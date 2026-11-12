"""Lazy adapters for registration evidence; no deployment or functional sessions."""

from __future__ import annotations

import os


class GetOnly:
    def __init__(self, api):
        self.api = api

    def call(self, path, method="GET", *args, **kwargs):
        if method != "GET":
            raise ValueError("preflight permits GET only")
        return self.api.call(path, *args, method=method, **kwargs)


def transports(identity):
    from mcp_registry.kube import KubeReader

    # This uses the existing operator SOPS administrator authentication. It may
    # decrypt that credential, but never requests backend Secret values.
    return KubeReader(os.environ.get("KUBECONFIG")), GetOnly(identity.admin())
