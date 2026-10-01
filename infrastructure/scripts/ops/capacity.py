#!/usr/bin/env python3
"""Compare the cluster's real resource use against the capacity ledger.

Parses the first table in docs/infrastructure/cluster/capacity.md (headed
`| Node | Role | CPU alloc | Mem alloc (GiB) | Mem ceiling % | Notes |`,
tolerant of column order — matched by header name, not position), then runs
`kubectl top nodes` and `kubectl get nodes -o json` to compare real memory
use against each node's ceiling. Also sums container requests per namespace
from `kubectl get pods -A -o json`.

    capacity.py            # full check against the live cluster
    capacity.py --offline  # print the ledger only, no kubectl calls

Exit 1 if any node is over its ceiling. Stdlib only (no PyYAML, no requests
library) so it runs anywhere python3 is available, same constraint as the
rest of infrastructure/scripts.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LEDGER = REPO / "docs/infrastructure/cluster/capacity.md"

os.environ.setdefault("KUBECONFIG", "/home/al/.kube/config")


def parse_quantity_bytes(value: str) -> float:
    """Parse a Kubernetes memory quantity (e.g. '131072000Ki', '45Gi', '512Mi',
    '1000000', '1G') into bytes."""
    value = value.strip()
    binary = {"Ki": 2**10, "Mi": 2**20, "Gi": 2**30, "Ti": 2**40}
    decimal = {"K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}
    for suffix, mult in binary.items():
        if value.endswith(suffix):
            return float(value[: -len(suffix)]) * mult
    for suffix, mult in decimal.items():
        if value.endswith(suffix):
            return float(value[: -len(suffix)]) * mult
    return float(value)


def parse_quantity_millicores(value: str) -> float:
    value = value.strip()
    if value.endswith("m"):
        return float(value[:-1])
    return float(value) * 1000


def parse_ledger(path: Path) -> dict:
    """Returns {node_name: ceiling_pct} from the first markdown table whose
    header row contains both a 'Node' and a 'Mem ceiling %'-prefixed column.
    Column order is not assumed — headers are matched by name."""
    if not path.exists():
        print(f"capacity ledger not found: {path}", file=sys.stderr)
        sys.exit(2)
    lines = path.read_text().splitlines()
    header_idx = None
    headers: list[str] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if "Node" in cells and any(c.startswith("Mem ceiling") for c in cells):
            headers = cells
            header_idx = i
            break
    if header_idx is None:
        print(f"no capacity table header found in {path}", file=sys.stderr)
        sys.exit(2)

    node_col = headers.index("Node")
    ceiling_col = next(i for i, h in enumerate(headers) if h.startswith("Mem ceiling"))

    ledger: dict[str, float] = {}
    # Row after the header is the '---' separator; data rows follow until the
    # table ends (a line that isn't a pipe-delimited row).
    for line in lines[header_idx + 2 :]:
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            break
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) <= max(node_col, ceiling_col):
            continue
        node = cells[node_col]
        ceiling_raw = cells[ceiling_col].rstrip("%").strip()
        try:
            ledger[node] = float(ceiling_raw)
        except ValueError:
            continue
    return ledger


def kubectl_json(*args: str) -> dict:
    out = subprocess.run(
        ["kubectl", *args, "-o", "json"], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


def kubectl_top_nodes() -> dict:
    """Returns {node_name: used_bytes} parsed from `kubectl top nodes`
    (metrics-server text output; there is no stable JSON form for `top`)."""
    out = subprocess.run(
        ["kubectl", "top", "nodes", "--no-headers"],
        capture_output=True,
        text=True,
        check=True,
    )
    used: dict[str, float] = {}
    for line in out.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        name, _cpu_cores, _cpu_pct, mem_bytes, _mem_pct = parts[:5]
        used[name] = parse_quantity_bytes(mem_bytes)
    return used


def node_allocatable_bytes() -> dict:
    data = kubectl_json("get", "nodes")
    alloc: dict[str, float] = {}
    for item in data.get("items", []):
        name = item["metadata"]["name"]
        mem = item.get("status", {}).get("allocatable", {}).get("memory")
        if mem:
            alloc[name] = parse_quantity_bytes(mem)
    return alloc


def namespace_request_sums() -> dict:
    data = kubectl_json("get", "pods", "-A")
    sums: dict[str, dict[str, float]] = {}
    for pod in data.get("items", []):
        ns = pod["metadata"]["namespace"]
        containers = pod.get("spec", {}).get("containers", [])
        bucket = sums.setdefault(ns, {"cpu_m": 0.0, "mem_bytes": 0.0})
        for c in containers:
            req = c.get("resources", {}).get("requests", {})
            if "cpu" in req:
                bucket["cpu_m"] += parse_quantity_millicores(req["cpu"])
            if "memory" in req:
                bucket["mem_bytes"] += parse_quantity_bytes(req["memory"])
    return sums


def fmt_gib(b: float) -> str:
    return f"{b / 2**30:.1f} GiB"


def main() -> int:
    offline = "--offline" in sys.argv[1:]

    ledger = parse_ledger(LEDGER)

    print("Capacity ledger (docs/infrastructure/cluster/capacity.md):")
    for node, ceiling in ledger.items():
        print(f"  {node:10s} ceiling {ceiling:.0f}%")
    print()

    if offline:
        return 0

    try:
        used = kubectl_top_nodes()
        alloc = node_allocatable_bytes()
    except subprocess.CalledProcessError as exc:
        print(f"kubectl call failed: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError:
        print("kubectl not found on PATH", file=sys.stderr)
        return 2

    over = False
    print(f"{'Node':10s} {'Used':>10s} {'Alloc':>10s} {'Used %':>8s} {'Ceiling':>8s}  Status")
    for node, ceiling in ledger.items():
        if node not in alloc:
            print(f"{node:10s}  -- node not found in cluster --")
            continue
        used_bytes = used.get(node, 0.0)
        alloc_bytes = alloc[node]
        used_pct = (used_bytes / alloc_bytes * 100) if alloc_bytes else 0.0
        status = "OVER" if used_pct > ceiling else "OK"
        if status == "OVER":
            over = True
        print(
            f"{node:10s} {fmt_gib(used_bytes):>10s} {fmt_gib(alloc_bytes):>10s} "
            f"{used_pct:7.1f}% {ceiling:7.0f}%  {status}"
        )

    print()
    print("Per-namespace container requests (kubectl get pods -A):")
    try:
        sums = namespace_request_sums()
        print(f"  {'Namespace':20s} {'CPU req (cores)':>16s} {'Mem req':>10s}")
        for ns in sorted(sums):
            bucket = sums[ns]
            print(
                f"  {ns:20s} {bucket['cpu_m'] / 1000:16.2f} {fmt_gib(bucket['mem_bytes']):>10s}"
            )
    except subprocess.CalledProcessError as exc:
        print(f"  kubectl get pods -A failed: {exc}", file=sys.stderr)

    if over:
        print()
        print("FAIL: at least one node is over its capacity ceiling", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
