"""Thin application deployment entrypoint around ordinary Zetra clients/workers."""

import argparse
import asyncio
import json
import os
import re
import signal
from datetime import timedelta
from pathlib import Path

from openshell import SandboxClient, TlsConfig
from temporalio.client import Client
from zetra.artifacts import FileStore
from zetra.client import SessionClient
from zetra.manifest import load_release
from zetra.worker import create_worker


async def main(mode, session=None):
    temporal = await Client.connect(
        os.getenv("TEMPORAL_ADDRESS", "temporal-frontend.temporal.svc.cluster.local:7233"),
        namespace=os.getenv("TEMPORAL_NAMESPACE", "zetra-poc"),
    )
    root = Path(os.getenv("ZETRA_ARTIFACTS", "/artifacts"))
    store = FileStore(root / "objects")
    options = {
        "task_queue": "zetra-kubernetes-poc-v1",
        "runtime_id": "kubani-kubernetes-poc-v1",
        "artifacts": store,
    }
    release = load_release(os.getenv("ZETRA_RELEASE", "/etc/zetra/release.json"))
    if mode == "worker":
        tls = Path(os.getenv("OPENSHELL_TLS_DIR", "/etc/openshell"))
        gateway = SandboxClient(
            os.getenv("OPENSHELL_ADDRESS", "zetra-poc-openshell.zetra-poc.svc.cluster.local:8080"),
            tls=TlsConfig(
                ca_path=tls / "ca.crt", cert_path=tls / "tls.crt", key_path=tls / "tls.key"
            ),
        )
        try:
            worker = create_worker(
                temporal,
                **options,
                sandbox_client=gateway,
                key=Path("/etc/zetra-key/key").read_bytes(),
                approved_releases={release.identity},
                providers=("kubani-k8s-read",),
                graceful_shutdown_timeout=timedelta(seconds=20),
            )
            await run_worker(worker)
        finally:
            gateway.close()
    else:
        client = SessionClient(temporal, **options)
        await run_investigation(client, release, root, session)


async def run_worker(worker):
    loop = asyncio.get_running_loop()
    shutdown = None

    def request_shutdown():
        nonlocal shutdown
        if shutdown is None:
            shutdown = asyncio.create_task(worker.shutdown())

    for selected in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(selected, request_shutdown)
    try:
        await worker.run()
    finally:
        if shutdown is not None:
            await shutdown
        for selected in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(selected)


async def run_investigation(client, release, root, session):
    if not session or not re.fullmatch(r"investigate-[a-z0-9-]{1,64}", session):
        raise ValueError("A reusable investigate- session identity is required")
    handle = await client.submit(
        release,
        session=session,
        message="Investigate investigator-demo-broken in zetra-poc-fixtures. Explain the startup problem using MCP evidence, compare the healthy pod, and write report.md.",
    )
    output = root / "results" / session
    output.mkdir(parents=True, exist_ok=True)
    receipt = output / "handle.json"
    # The SDK verifies the accepted Temporal start; this file is only a receipt.
    receipt.write_text(handle.model_dump_json())
    result = await client.wait(handle)
    print(
        json.dumps(
            {
                "handle": handle.model_dump(),
                "status": result.get("status"),
                "cleanup": result.get("cleanup"),
                "cursor": (result.get("position") or {}).get("cursor"),
                "final_text": (result.get("result") or {}).get("final_text"),
            },
            indent=2,
        )
    )
    (output / "result.json").write_text(json.dumps(result, indent=2))
    if result.get("status") == "SUCCEEDED":
        for name, data in (await client.read_files(handle)).items():
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        print((output / "report.md").read_text())
    else:
        raise RuntimeError("Investigation did not succeed; result preserved")
    return handle


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("worker", "run"))
    parser.add_argument("--session", help="Reusable investigate-<id>; retry with the same value")
    args = parser.parse_args(argv)
    if args.mode == "run" and (
        not args.session or not re.fullmatch(r"investigate-[a-z0-9-]{1,64}", args.session)
    ):
        parser.error("run requires --session investigate-<id> (lowercase letters, digits, hyphens)")
    return args


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.mode, args.session))
