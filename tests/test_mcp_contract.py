"""`just mcp contract`: capture what a fake MCP server lists, over both transports, on a temporary tree. Nothing leaves localhost."""

from __future__ import annotations

import contextlib
import importlib
import importlib.util
import io
import json
import queue
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

OPS = Path(__file__).resolve().parents[1] / "infrastructure/scripts/ops"
sys.path.insert(0, str(OPS))
import outcome  # noqa: E402

contract = importlib.import_module("mcp_registry.contract")
SPEC = importlib.util.spec_from_file_location("mcp_registry_cli", OPS / "mcp-registry.py")
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)

DIGEST = "a" * 64
PINNED = f"quay.io/example/server:v1@sha256:{DIGEST}"


def tool(name, schema=None):
    return {"name": name, "description": f"does {name}", "inputSchema": schema or {"type": "object", "properties": {}}}


class FakeMcp:
    """An MCP server on localhost: Streamable HTTP at /mcp and the older HTTP+SSE transport at /sse, two pages of tools."""

    def __init__(self, tools):
        self.tools = tools
        self.requests = 0
        self.stop = threading.Event()
        self.outbox = queue.Queue()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def body(self):
                return json.loads(self.rfile.read(int(self.headers["Content-Length"])))

            def reply(self, status, payload=None, headers=None, kind="application/json"):
                data = b"" if payload is None else payload.encode()
                self.send_response(status)
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                if data:
                    self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def result(self, message):
                if message["method"] == "initialize":
                    return {"protocolVersion": contract.PROTOCOL_VERSION, "capabilities": {"tools": {}}, "serverInfo": {"name": "fake"}}
                cursor = message["params"].get("cursor")
                half = (len(fake.tools) + 1) // 2
                return {"tools": fake.tools[half:], "nextCursor": None} if cursor == "page-2" else {"tools": fake.tools[:half], "nextCursor": "page-2"}

            def do_POST(self):
                fake.requests += 1
                message = self.body()
                if self.path == "/mcp":
                    if message["method"] != "initialize" and self.headers.get("Mcp-Session-Id") != "s1":
                        return self.reply(400, "{}")
                    if "id" not in message:
                        return self.reply(202)
                    answer = json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": self.result(message)})
                    headers = {"Mcp-Session-Id": "s1"}
                    if message["method"] == "tools/list":  # this answer is an event stream, the others are JSON
                        return self.reply(200, f"event: message\ndata: {answer}\n\n", headers, "text/event-stream")
                    return self.reply(200, answer, headers)
                if self.path == "/messages?session=1" and "id" in message:
                    fake.outbox.put(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": self.result(message)}))
                return self.reply(202)

            def do_GET(self):
                fake.requests += 1
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                try:
                    self.wfile.write(b"event: endpoint\ndata: /messages?session=1\n\n")
                    self.wfile.flush()
                    while not fake.stop.is_set():
                        try:
                            data = fake.outbox.get(timeout=0.05)
                        except queue.Empty:
                            continue
                        self.wfile.write(f"event: message\ndata: {data}\n\n".encode())
                        self.wfile.flush()
                except OSError:
                    pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def __enter__(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.httpd.shutdown()
        self.httpd.server_close()


class FakeCluster:
    def __init__(self, image, base=None):
        self.image, self.base, self.forwarded = image, base, []

    def container_image(self, namespace, deployment, container):
        return self.image

    @contextlib.contextmanager
    def forward(self, namespace, deployment, port):
        self.forwarded.append((namespace, deployment, port))
        yield self.base


def write(root, rel, doc):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def deployment(name, container):
    return {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": name, "namespace": "mcp"}, "spec": {"template": {"spec": {"containers": [container]}}}}


def build_tree(root):
    """kubernetes-mcp (registered, Streamable HTTP), postgres-admin-mcp (registered, SSE), graphiti-mcp (not registered), github-mcp (not pinned)."""
    servers = [("kubernetes-mcp", "kubernetes"), ("postgres-admin-mcp", "postgres-admin"), ("graphiti-mcp", None), ("github-mcp", None)]
    catalog = {
        "version": 1,
        "cluster": {"name": "kubani", "trustDomain": "cluster.local", "gateway": "http://ai", "fluxInventories": []},
        "toolServers": [
            {"name": n, "namespace": "mcp", "owner": "platform", "description": "d", "source": "s", "manifest": f"m/{n}.yaml", "container": n, "backend": b}
            for n, b in servers
        ],
        "modelEngines": [],
        "aliases": [],
    }
    write(root, "infrastructure/registry/catalog.yaml", catalog)
    for name, _ in servers:
        image = "quay.io/example/server:v1" if name == "github-mcp" else PINNED
        box = {"name": name, "image": image, "args": ["--flag"], "env": [{"name": "A", "value": "1"}]}
        write(root, f"m/{name}.yaml", deployment(name, box))
    write(
        root,
        "infrastructure/mcp/backends/kubernetes.yaml",
        {"name": "kubernetes", "profile": "existing-streamable-http-v1", "workload": {"port": 8080, "path": "/mcp", "protocol": "StreamableHTTP"}, "authorization": {"tools": ["pods_list", "pods_get"]}},
    )
    write(
        root,
        "infrastructure/mcp/backends/postgres-admin.yaml",
        {"name": "postgres-admin", "profile": "container-sse-v1", "workload": {"port": 8000}, "authorization": {"tools": ["execute_sql"]}},
    )


def run_cli(root, *argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(["--root", str(root), *argv])
    return code, json.loads(out.getvalue())


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        build_tree(self.root)

    def file(self, server):
        return self.root / "infrastructure/mcp/contracts" / f"{server}.json"

    def test_streamable_http_through_the_cluster_two_pages(self):
        tools = [tool("resources_delete"), tool("pods_list"), tool("pods_get"), tool("events_list")]
        with FakeMcp(tools) as fake:
            cluster = FakeCluster(PINNED, fake.base)
            out = contract.capture(self.root, "kubernetes-mcp", cluster=cluster)
        document = json.loads(self.file("kubernetes-mcp").read_text())
        self.assertEqual(cluster.forwarded, [("mcp", "kubernetes-mcp", 8080)])
        self.assertEqual([t["name"] for t in document["tools"]], ["events_list", "pods_get", "pods_list", "resources_delete"])
        self.assertEqual({t["name"]: t["effect"] for t in document["tools"]}, {"events_list": "remote_write", "pods_get": "remote_read", "pods_list": "remote_read", "resources_delete": "remote_write"})
        self.assertEqual((document["server"], document["backend"], document["image"], document["schemaVersion"]), ("kubernetes-mcp", "kubernetes", PINNED, 1))
        self.assertTrue(document["configDigest"].startswith("sha256:"))
        self.assertEqual(document["tools"][0]["outputSchema"], None)
        self.assertEqual((out["tools"], out["changed"], out["path"]), (4, True, "infrastructure/mcp/contracts/kubernetes-mcp.json"))

    def test_sse_transport_two_pages(self):
        tools = [tool("execute_sql"), tool("analyze_db_health"), tool("get_top_queries")]
        with FakeMcp(tools) as fake:
            out = contract.capture(self.root, "postgres-admin-mcp", url=fake.base + "/sse")
        document = json.loads(self.file("postgres-admin-mcp").read_text())
        self.assertEqual({t["name"]: t["effect"] for t in document["tools"]}, {"analyze_db_health": "remote_write", "execute_sql": "remote_read", "get_top_queries": "remote_write"})
        self.assertEqual(out["tools"], 3)

    def test_same_answer_same_bytes_and_a_schema_change_shows(self):
        first = [tool("pods_list"), tool("pods_get")]
        with FakeMcp(first) as fake:
            contract.capture(self.root, "kubernetes-mcp", url=fake.base + "/mcp")
            before = self.file("kubernetes-mcp").read_bytes()
            again = contract.capture(self.root, "kubernetes-mcp", url=fake.base + "/mcp")
            self.assertEqual((self.file("kubernetes-mcp").read_bytes(), again["changed"]), (before, False))
            code, document = run_cli(self.root, "contract", "kubernetes-mcp", "--url", fake.base + "/mcp", "--check")
            self.assertEqual((code, document["ok"]), (0, True))
            fake.tools = [tool("pods_list", {"type": "object", "required": ["namespace"]}), tool("pods_get")]
            code, document = run_cli(self.root, "contract", "kubernetes-mcp", "--url", fake.base + "/mcp", "--check")
            self.assertEqual((code, document["error"]["code"]), (1, "check-failed"))
            self.assertEqual(self.file("kubernetes-mcp").read_bytes(), before)
            contract.capture(self.root, "kubernetes-mcp", url=fake.base + "/mcp")
        self.assertNotEqual(self.file("kubernetes-mcp").read_bytes(), before)

    def test_check_with_no_file_fails_and_writes_nothing(self):
        with FakeMcp([tool("pods_list")]) as fake:
            code, document = run_cli(self.root, "contract", "kubernetes-mcp", "--url", fake.base + "/mcp", "--check")
        self.assertEqual((code, document["error"]["code"]), (1, "check-failed"))
        self.assertFalse(self.file("kubernetes-mcp").exists())

    def test_a_tool_without_an_input_schema_object_is_refused_and_nothing_is_written(self):
        with FakeMcp([{"name": "pods_list", "description": "lists pods"}]) as fake:
            code, document = run_cli(self.root, "contract", "kubernetes-mcp", "--url", fake.base + "/mcp")
        self.assertEqual((code, document["error"]["code"]), (1, "failed"))
        self.assertIn("pods_list", document["error"]["message"])
        self.assertFalse(self.file("kubernetes-mcp").exists())

    def test_image_not_pinned_is_refused_before_connecting(self):
        with FakeMcp([tool("a")]) as fake:
            code, document = run_cli(self.root, "contract", "github-mcp", "--url", fake.base + "/mcp")
            self.assertEqual((code, document["error"]["code"], fake.requests), (1, "refused", 0))

    def test_live_deployment_on_another_image_is_refused(self):
        cluster = FakeCluster("quay.io/example/server:v0@sha256:" + "b" * 64)
        with self.assertRaises(outcome.Coded) as caught:
            contract.capture(self.root, "kubernetes-mcp", cluster=cluster)
        self.assertEqual(caught.exception.code, "refused")
        self.assertEqual(cluster.forwarded, [])

    def test_unknown_server_is_not_found(self):
        code, document = run_cli(self.root, "contract", "nope-mcp", "--url", "http://127.0.0.1:1/mcp")
        self.assertEqual((code, document["error"]["code"]), (1, "not-found"))

    def test_unregistered_server_has_no_backend_and_only_remote_write(self):
        with FakeMcp([tool("pods_list"), tool("execute_sql")]) as fake:
            contract.capture(self.root, "graphiti-mcp", url=fake.base + "/mcp")
        document = json.loads(self.file("graphiti-mcp").read_text())
        self.assertIsNone(document["backend"])
        self.assertEqual({t["effect"] for t in document["tools"]}, {"remote_write"})

    def test_config_digest(self):
        base = {"name": "x", "image": "i@sha256:" + DIGEST, "args": ["--a"], "env": [{"name": "A", "value": "1"}, {"name": "B", "valueFrom": {"secretKeyRef": {"name": "s", "key": "k"}}}]}
        digest = contract.config_digest(base)
        self.assertRegex(digest, r"^sha256:[0-9a-f]{64}$")
        self.assertNotEqual(digest, contract.config_digest({**base, "args": ["--a", "--b"]}))
        self.assertNotEqual(digest, contract.config_digest({**base, "env": [{"name": "A", "value": "2"}, base["env"][1]]}))
        self.assertEqual(digest, contract.config_digest({**base, "image": "other@sha256:" + "c" * 64}))
        self.assertEqual(digest, contract.config_digest({**base, "env": list(reversed(base["env"])), "resources": {"limits": {}}}))
        self.assertEqual(contract.config_digest({"name": "x"}), contract.config_digest({"name": "x", "command": [], "args": [], "env": []}))


if __name__ == "__main__":
    unittest.main()
