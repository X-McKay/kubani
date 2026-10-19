"""Static read-only tools; each MCP observation is an existing SDK tool boundary."""

import hashlib
import json
import re

from zetra import Tool

from .dependencies import NAMESPACE, KubernetesMcp


def tools(ctx, remote=None):
    remote = remote or KubernetesMcp()

    async def observe(name, arguments, evidence):
        result = await remote.call(name, {"namespace": NAMESPACE, **arguments})
        encoded = json.dumps(result, sort_keys=True, indent=2).encode()
        filename = evidence + "-" + hashlib.sha256(encoded).hexdigest() + ".json"
        target = ctx.workspace / "evidence" / filename
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(encoded)
        return {**result, "evidence": "evidence/" + filename}

    async def list_pods() -> dict:
        """List only the synthetic investigator demonstration pods."""
        return await observe(
            "pods_list_in_namespace", {"labelSelector": "app=investigator-demo"}, "pods"
        )

    async def get_pod(name: str = "investigator-demo-broken") -> dict:
        """Inspect a demonstration pod; name must start with investigator-demo-."""
        if not re.fullmatch(r"investigator-demo-[a-z0-9-]{1,40}", name):
            return {"error": "Choose an investigator-demo- pod from list_pods."}
        return await observe("pods_get", {"name": name}, "pod-" + name)

    async def list_events() -> dict:
        """Read namespace events to explain observed pod startup failures."""
        return await observe("events_list", {}, "events")

    async def write_report(content: str = "Completed.") -> dict:
        """Write a concise Markdown investigation citing evidence paths."""
        if len(content.encode()) > 8_000:
            return {"error": "Keep the report below 8000 UTF-8 bytes."}
        (ctx.workspace / "report.md").write_text(content, encoding="utf-8")
        return {"path": "report.md"}

    return ctx.tools(
        Tool(list_pods, "remote_read"),
        Tool(get_pod, "remote_read"),
        Tool(list_events, "remote_read"),
        Tool(write_report, "workspace_write"),
    )
