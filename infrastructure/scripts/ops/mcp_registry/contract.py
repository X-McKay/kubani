"""Record what a tool server lists (`tools/list`) as infrastructure/mcp/contracts/<server>.json, and the digest of its flags.

The file is generated here and reviewed, never edited by hand. It holds no time and no host, so an unchanged server gives the
same bytes. No credential is read, sent or stored: the server is reached directly (a URL the operator vouches for, or a
port-forward to its Deployment).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
import select
import subprocess
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
import yaml

import outcome

from . import kube

PROTOCOL_VERSION = "2025-06-18"
CONTRACTS = Path("infrastructure/mcp/contracts")
BACKENDS = Path("infrastructure/mcp/backends")
SCHEMA_VERSION = 1
TIMEOUT = (5, 30)  # seconds: connect, then each read
DEADLINE = 120  # seconds for one capture; a stream that keeps the connection busy cannot hold it longer
MAX_PAGES = 100
PINNED = re.compile(r"@sha256:[0-9a-f]{64}$")
SERVER_NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
TRANSPORTS = ("streamable-http", "sse")


def config_digest(container: dict) -> str:
    """`sha256:` and the SHA-256 of the canonical JSON of the container's command, args and env as the manifest states them."""
    env = []
    for item in container.get("env") or []:
        entry = {"name": item["name"]}
        for key in ("value", "valueFrom"):
            if key in item:
                entry[key] = item[key]
        env.append(entry)
    env.sort(key=lambda entry: entry["name"])
    document = {"command": list(container.get("command") or []), "args": list(container.get("args") or []), "env": env}
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def contract_path(server: str) -> Path:
    return CONTRACTS / f"{server}.json"


def image_digest(image: str) -> str | None:
    """The `sha256:...` of an image reference pinned by digest, else None."""
    return "sha256:" + image.rpartition("@sha256:")[2] if "@sha256:" in image else None


def render_bytes(document: dict) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


# ---- the MCP client ----------------------------------------------------------------------------------------------------


@contextlib.contextmanager
def _network():
    """Requests failures as outcome codes with fixed sentences; the exception text (a URL, a header) is never shown."""
    try:
        yield
    except outcome.Coded:
        raise
    except requests.RequestException as error:
        if isinstance(error, requests.Timeout) or "timed out" in str(error).lower():
            raise outcome.Coded("the server did not answer in time", "timeout") from None
        raise outcome.Coded("the server could not be reached", "unavailable") from None


def _failed(message: str):
    return outcome.Coded(message, "failed")


def _status(response) -> None:
    if response.status_code >= 500:
        raise outcome.Coded(f"the server answered HTTP {response.status_code}", "unavailable")
    if response.status_code >= 300:
        raise _failed(f"the server answered HTTP {response.status_code}, which is not an MCP answer")


def _events(response, deadline: float):
    """(event, data) of each server-sent event in the stream, in order."""
    event, data = "message", []
    for raw in response.iter_lines(chunk_size=1):
        if time.monotonic() > deadline:
            raise outcome.Coded("the server did not finish answering in time", "timeout")
        line = raw.decode("utf-8", errors="replace")
        if line == "":
            if data:
                yield event, "\n".join(data)
            event, data = "message", []
        elif not line.startswith(":"):
            field, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if field == "event":
                event = value
            elif field == "data":
                data.append(value)
    if data:
        yield event, "\n".join(data)


def _answer(messages, request_id):
    """The JSON-RPC result for `request_id` out of an iterable of decoded messages; anything else (notifications, server requests) is skipped."""
    for message in messages:
        if isinstance(message, dict) and message.get("id") == request_id and ("result" in message or "error" in message):
            if "error" in message:
                raise _failed("the server answered a request with an error")
            if not isinstance(message["result"], dict):
                raise _failed("the server's answer has no result object")
            return message["result"]
    raise _failed("the server's answer did not include a response to the request")


def _decode(text: str):
    try:
        return json.loads(text)
    except ValueError:
        raise _failed("the server sent something that is not JSON") from None


class StreamableHTTP:
    """JSON-RPC by POST to one URL; the answer is JSON or a server-sent event stream."""

    def __init__(self, url, http, deadline):
        self.url, self.http, self.deadline = url, http, deadline
        self.session_id = None
        self.version = None
        self.next_id = 0

    def _post(self, body):
        headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if self.version:
            headers["MCP-Protocol-Version"] = self.version
        return self.http.post(self.url, data=json.dumps(body), headers=headers, timeout=TIMEOUT, stream=True, allow_redirects=False)

    def request(self, method, params):
        self.next_id += 1
        request_id = self.next_id
        with _network():
            with self._post({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}) as response:
                _status(response)
                self.session_id = response.headers.get("Mcp-Session-Id") or self.session_id
                if response.headers.get("Content-Type", "").lower().startswith("text/event-stream"):
                    messages = (_decode(data) for _, data in _events(response, self.deadline))
                else:
                    body = _decode(response.content.decode("utf-8", errors="replace"))
                    messages = body if isinstance(body, list) else [body]
                return _answer(messages, request_id)

    def notify(self, method, params):
        with _network():
            with self._post({"jsonrpc": "2.0", "method": method, "params": params}) as response:
                _status(response)

    def initialized(self, version):
        self.version = version

    def close(self):
        pass


class LegacySSE:
    """The older HTTP+SSE transport: GET the stream, read its `endpoint` event, POST requests there, read answers from the stream."""

    def __init__(self, url, http, deadline):
        self.url, self.http, self.deadline = url, http, deadline
        self.next_id = 0
        with _network():
            self.stream = http.get(url, headers={"Accept": "text/event-stream"}, timeout=TIMEOUT, stream=True, allow_redirects=False)
            try:
                _status(self.stream)
                self.events = _events(self.stream, deadline)
                for event, data in self.events:
                    if event == "endpoint":
                        break
                else:
                    raise _failed("the server's stream ended without an endpoint event")
            except BaseException:
                self.stream.close()
                raise
        self.endpoint = urljoin(url, data.strip())
        if urlsplit(self.endpoint)[:2] != urlsplit(url)[:2]:
            self.stream.close()
            raise outcome.Coded("the server's endpoint names another host than the stream", "refused")

    def _post(self, body):
        response = self.http.post(self.endpoint, data=json.dumps(body), headers={"Content-Type": "application/json"}, timeout=TIMEOUT, allow_redirects=False)
        with response:
            _status(response)

    def request(self, method, params):
        self.next_id += 1
        request_id = self.next_id
        with _network():
            self._post({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
            messages = (_decode(data) for event, data in self.events if event == "message")
            return _answer(messages, request_id)

    def notify(self, method, params):
        with _network():
            self._post({"jsonrpc": "2.0", "method": method, "params": params})

    def initialized(self, version):
        pass

    def close(self):
        self.stream.close()


def list_tools(url: str, transport: str, *, http=None, deadline: float | None = None) -> list[dict]:
    """Every tool the server at `url` lists: initialize, notifications/initialized, then tools/list until there is no nextCursor."""
    if transport not in TRANSPORTS:
        raise outcome.Coded(f"transport must be one of {', '.join(TRANSPORTS)}", "invalid-arguments")
    http = http or requests
    deadline = deadline or time.monotonic() + DEADLINE
    client = (StreamableHTTP if transport == "streamable-http" else LegacySSE)(url, http, deadline)
    try:
        init = client.request(
            "initialize",
            {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "kubani-mcp-contract", "version": "1"}},
        )
        client.initialized(init.get("protocolVersion") if isinstance(init.get("protocolVersion"), str) else PROTOCOL_VERSION)
        client.notify("notifications/initialized", {})
        tools, cursor = [], None
        for _ in range(MAX_PAGES):
            page = client.request("tools/list", {"cursor": cursor} if cursor else {})
            listed = page.get("tools")
            if not isinstance(listed, list):
                raise _failed("the server's tools/list answer has no tools list")
            tools.extend(listed)
            cursor = page.get("nextCursor")
            if not cursor:
                return tools
            if not isinstance(cursor, str):
                raise _failed("the server's nextCursor is not a string")
        raise _failed("the server's tool listing did not end")
    finally:
        client.close()


# ---- the record --------------------------------------------------------------------------------------------------------


def build_document(server, backend, image, digest, tools, readable) -> dict:
    """The file's content. A tool the backend's authorization lists is remote_read; every other tool is remote_write."""
    entries, seen = [], set()
    for tool in tools:
        name = tool.get("name") if isinstance(tool, dict) else None
        if not isinstance(name, str) or not name or name in seen:
            raise _failed("the server lists a tool without a name, or one name twice")
        seen.add(name)
        description = tool.get("description")
        entries.append(
            {
                "name": name,
                "description": description if isinstance(description, str) else "",
                "effect": "remote_read" if name in readable else "remote_write",
                "inputSchema": tool.get("inputSchema"),
                "outputSchema": tool.get("outputSchema"),
            }
        )
    entries.sort(key=lambda entry: entry["name"])
    return {"schemaVersion": SCHEMA_VERSION, "server": server, "backend": backend, "image": image, "configDigest": digest, "tools": entries}


def resolve(root: Path, server: str) -> dict:
    """What the committed files say about `server`: entry, container, image, config digest, and the backend's tools and defaults."""
    import registry_feed as feed  # here, not at the top: registry_feed imports this module

    if not SERVER_NAME.fullmatch(server):
        raise outcome.Coded("the server name is not a tool server name", "not-found")
    cat = feed._catalog(root)
    found = [item for item in feed._entries(cat, "toolServers", feed.TOOL_KEYS, identity="name") if item["name"] == server]
    if not found:
        raise outcome.Coded(f"{feed.CATALOG}: no tool server named {server!r}", "not-found")
    entry = found[0]
    where = f"{feed.CATALOG}: toolServers {server!r}"
    deployment = feed._deployment(root, entry["manifest"], server, entry["namespace"], where)
    container = feed._container(deployment, entry["container"], where, entry["manifest"])
    image = container.get("image")
    if not isinstance(image, str) or not image:
        raise ValueError(f"{where}: container {entry['container']} in {entry['manifest']} has no image")
    backend, readable, defaults = entry["backend"], frozenset(), {"transport": "streamable-http", "path": "/mcp", "port": None}
    if backend is not None:
        definition = yaml.safe_load(feed._inside(root, BACKENDS / f"{backend}.yaml").read_text(encoding="utf-8")) or {}
        readable = frozenset(((definition.get("authorization") or {}).get("tools")) or [])
        workload = definition.get("workload") or {}
        sse = workload.get("protocol") == "SSE" or "sse" in str(definition.get("profile", ""))
        defaults = {"transport": "sse" if sse else "streamable-http", "path": workload.get("path") or ("/sse" if sse else "/mcp"), "port": workload.get("port")}
    return {
        "entry": entry,
        "backend": backend,
        "container": container,
        "image": image,
        "configDigest": config_digest(container),
        "readable": readable,
        "defaults": defaults,
    }


class Cluster:
    """Everything that touches the cluster: one read of a Deployment's container image, one port-forward. Tests replace it."""

    def __init__(self, kubeconfig, *, run=None, popen=None):
        self.kubeconfig = kubeconfig
        self.run = run
        self.popen = popen or subprocess.Popen

    def container_image(self, namespace, deployment, container):
        live = kube.KubeReader(self.kubeconfig, run=self.run)("apps/v1", "Deployment", namespace, deployment)
        if live is None:
            return None
        for item in (((live.get("spec") or {}).get("template") or {}).get("spec") or {}).get("containers") or []:
            if isinstance(item, dict) and item.get("name") == container:
                return item.get("image")
        return None

    @contextlib.contextmanager
    def forward(self, namespace, deployment, port):
        """Port-forward to the Deployment's pod and yield `http://127.0.0.1:<local port>`; the process ends when the block does."""
        argv = ["kubectl"] + (["--kubeconfig", str(self.kubeconfig)] if self.kubeconfig else [])
        argv += ["--namespace", namespace, "port-forward", f"deployment/{deployment}", f":{int(port)}", "--address", "127.0.0.1"]
        process = self.popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        try:
            ready, _, _ = select.select([process.stdout], [], [], 20)
            line = process.stdout.readline() if ready else ""
            match = re.search(r"127\.0\.0\.1:(\d+) ->", line)
            if not match:
                raise outcome.Coded("the port-forward to the server did not start", "unavailable")
            yield f"http://127.0.0.1:{match.group(1)}"
        finally:
            process.terminate()
            try:
                process.wait(5)
            except subprocess.TimeoutExpired:
                process.kill()


def capture(root: Path, server: str, *, url=None, transport=None, port=None, path=None, check=False, cluster=None, http=None) -> dict:
    """Capture `server` and write its file (or, with `check`, only compare). Raises outcome.Coded; returns the output document."""
    if transport is not None and transport not in TRANSPORTS:
        raise outcome.Coded(f"transport must be one of {', '.join(TRANSPORTS)}", "invalid-arguments")
    if url is not None and (port is not None or path is not None):
        raise outcome.Coded("--url names the whole address; do not give --port or --path with it", "invalid-arguments")
    target = resolve(root, server)
    entry, image = target["entry"], target["image"]
    if not PINNED.search(image):
        raise outcome.Coded(f"{server}: the committed image is not pinned by digest; pin it before recording what it lists", "refused")
    transport = transport or target["defaults"]["transport"]
    if url is not None:
        tools = list_tools(url, transport, http=http)
    else:
        port = port or target["defaults"]["port"]
        if port is None:
            raise outcome.Coded(f"{server} is not registered, so there is no default port; give --port or --url", "invalid-arguments")
        if cluster is None:
            raise outcome.Coded("no cluster access was given", "internal")
        if cluster.container_image(entry["namespace"], server, entry["container"]) != image:
            raise outcome.Coded(f"{server}: the cluster does not run the committed image yet; deploy it, or start it elsewhere and give --url", "refused")
        with cluster.forward(entry["namespace"], server, port) as base:
            tools = list_tools(base + (path or target["defaults"]["path"]), transport, http=http)
    document = build_document(server, target["backend"], image, target["configDigest"], tools, target["readable"])
    data = render_bytes(document)
    file = Path(root) / contract_path(server)
    current = file.read_bytes() if file.is_file() else None
    status = "current" if current == data else "missing" if current is None else "stale"
    if not check and status != "current":
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
        status = "written"
    return {"status": status, "server": server, "path": contract_path(server).as_posix(), "tools": len(document["tools"]), "changed": status != "current"}
