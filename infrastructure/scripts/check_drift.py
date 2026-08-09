#!/usr/bin/env python3
"""Report drift between what this repo claims and what actually exists.

Three independent comparators, each answering a question that went unasked
long enough to cause real problems:

  1. scripts vs manifests  — validate_cluster.sh checked chat.almckay.io and
     gitops.almckay.io for months after those services were deleted, reporting
     six failures against a healthy cluster.
  2. docs vs manifests     — the Traefik README described two TCP entry points
     when there were four.
  3. docs vs cluster       — the Service Tiers table called Prometheus and
     Grafana "Always on" while both sat at replicas: 0.

Comparators 1 and 2 are offline and deterministic, so they run in CI.
Comparator 3 needs a cluster and is skipped when none is reachable.

Drift is advisory. This exits 0 even when it finds something, unless --strict
is passed, because resolving drift often needs cluster access or a judgement
call and a blocking check would strand anyone working offline.

Usage:
    check_drift.py [--strict] [--no-cluster] [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("ERROR: PyYAML is required (uv run ...)", file=sys.stderr)
    raise SystemExit(2) from None

REPO = Path(__file__).resolve().parents[2]
GITOPS = REPO / "infrastructure" / "gitops"
SCRIPTS = REPO / "infrastructure" / "scripts"
DOCS_ROOTS = (REPO / "docs", REPO / ".claude", GITOPS)

DOMAIN = "almckay.io"
HOST_RE = re.compile(rf"\b([a-z0-9][a-z0-9-]*\.{re.escape(DOMAIN)})\b")

# Narrative documents: audits record a moment in time, and plans discuss things
# that do not exist yet or no longer do. Neither claims to describe current
# state, so drift in them is expected rather than a finding.
HISTORICAL_PATH_MARKERS = ("/docs/reviews/", "/docs/plans/")

# Generic stand-ins used in how-to examples ("create an Ingress for
# myapp.almckay.io"). Deliberately a short, explicit list rather than a fuzzy
# rule: a real retired service must still be reported. `cluster.almckay.io`, for
# instance, is a live claim about Headlamp and is not exempt.
PLACEHOLDER_SUBDOMAINS = frozenset(
    {"myapp", "myservice", "newapp", "example", "yourapp", "your-app", "app", "service"}
)


def is_placeholder_host(host: str) -> bool:
    return host.split(".", 1)[0] in PLACEHOLDER_SUBDOMAINS


@dataclass
class Findings:
    scripts_vs_manifests: list[str] = field(default_factory=list)
    docs_vs_manifests: list[str] = field(default_factory=list)
    docs_vs_cluster: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def total(self) -> int:
        return (
            len(self.scripts_vs_manifests)
            + len(self.docs_vs_manifests)
            + len(self.docs_vs_cluster)
        )


# ---------------------------------------------------------------- manifests


def iter_manifest_docs():
    for path in sorted(GITOPS.rglob("*.yaml")):
        try:
            for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
                if isinstance(doc, dict):
                    yield path, doc
        except (yaml.YAMLError, UnicodeDecodeError):
            continue


def manifest_facts() -> dict:
    """Collect what the manifests actually declare."""
    ingress_hosts: set[str] = set()
    workloads: set[str] = set()  # bare service names
    entrypoints_defined: set[str] = set()
    entrypoints_used: set[str] = set()

    for path, doc in iter_manifest_docs():
        kind = doc.get("kind")
        meta = doc.get("metadata") or {}
        name = meta.get("name")

        if kind == "Ingress":
            for rule in (doc.get("spec") or {}).get("rules") or []:
                if isinstance(rule, dict) and rule.get("host"):
                    ingress_hosts.add(str(rule["host"]).strip().lower())

        if kind in {"Deployment", "StatefulSet", "DaemonSet"}:
            labels = (meta.get("labels") or {}) | (
                ((doc.get("spec") or {}).get("template") or {}).get("metadata") or {}
            ).get("labels", {})
            svc = labels.get("app.kubernetes.io/name") or name
            if svc:
                workloads.add(str(svc).lower())

        # Helm-deployed services have no workload manifest here; the release
        # name is the closest thing to a declaration that they exist.
        if kind == "HelmRelease" and name:
            workloads.add(str(name).lower())

        if kind == "IngressRouteTCP":
            for ep in (doc.get("spec") or {}).get("entryPoints") or []:
                entrypoints_used.add(str(ep).strip().lower())

        # Traefik entry points live in a HelmChartConfig values blob.
        if kind == "HelmChartConfig" and name == "traefik":
            values = (doc.get("spec") or {}).get("valuesContent") or ""
            for match in re.finditer(
                r"--entrypoints\.([a-z0-9-]+)\.address", str(values)
            ):
                entrypoints_defined.add(match.group(1).lower())

    return {
        "ingress_hosts": ingress_hosts,
        "workloads": workloads,
        "entrypoints_defined": entrypoints_defined,
        "entrypoints_used": entrypoints_used,
    }


# ------------------------------------------------------------------ scripts


def parse_bash_hosts(text: str) -> set[str]:
    return {
        m.group(1).lower()
        for m in HOST_RE.finditer(text)
        if not is_placeholder_host(m.group(1).lower())
    }


def parse_bash_service_table(text: str, array: str) -> dict[str, str]:
    """Pull `["name"]="tier:namespace:selector"` entries out of a bash array.

    The closing paren may be indented: these tables live inside `if` blocks.
    """
    block = re.search(rf"declare -A {array}=\((.*?)\n\s*\)", text, re.DOTALL)
    if not block:
        return {}
    entries: dict[str, str] = {}
    for m in re.finditer(r'\["([^"]+)"\]="([^"]*)"', block.group(1)):
        entries[m.group(1)] = m.group(2)
    return entries


def compare_scripts_to_manifests(facts: dict, findings: Findings) -> None:
    known_hosts = set(facts["ingress_hosts"])

    validate = SCRIPTS / "validate_cluster.sh"
    if validate.is_file():
        text = validate.read_text(encoding="utf-8")

        # Hostnames reachable only over TCP have no Ingress, so the script's own
        # TCP table is the declaration that they are meant to exist.
        for endpoint in parse_bash_service_table(text, "TCP_SERVICES"):
            known_hosts.add(endpoint.split(":")[0].lower())

        for host in parse_bash_hosts(text):
            if host not in known_hosts:
                findings.scripts_vs_manifests.append(
                    f"validate_cluster.sh probes {host}, which no manifest defines"
                )

        for array, prefix in (("INFRA_SERVICES", "infra"), ("APP_SERVICES", "app")):
            for svc, spec in parse_bash_service_table(text, array).items():
                parts = spec.split(":")
                selector = parts[-1]
                sel_value = selector.split("=")[-1].lower() if "=" in selector else ""
                if svc.lower() in facts["workloads"] or sel_value in facts["workloads"]:
                    continue
                findings.scripts_vs_manifests.append(
                    f"validate_cluster.sh {array} lists '{svc}' ({prefix}), "
                    f"which no manifest or HelmRelease declares"
                )

    for name in ("verify_services.sh", "validate_pods.sh"):
        path = SCRIPTS / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for host in parse_bash_hosts(text):
            if host not in known_hosts:
                findings.scripts_vs_manifests.append(
                    f"{name} references {host}, which no manifest defines"
                )

    for ep in sorted(facts["entrypoints_used"] - facts["entrypoints_defined"]):
        findings.scripts_vs_manifests.append(
            f"IngressRouteTCP uses Traefik entry point '{ep}', which traefik-config does not define"
        )


# --------------------------------------------------------------------- docs


def iter_doc_files():
    for root in DOCS_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            if any(marker in path.as_posix() for marker in HISTORICAL_PATH_MARKERS):
                continue
            yield path


def compare_docs_to_manifests(facts: dict, findings: Findings) -> None:
    known_hosts = set(facts["ingress_hosts"])
    validate = SCRIPTS / "validate_cluster.sh"
    if validate.is_file():
        for endpoint in parse_bash_service_table(
            validate.read_text(encoding="utf-8"), "TCP_SERVICES"
        ):
            known_hosts.add(endpoint.split(":")[0].lower())

    for path in iter_doc_files():
        rel = path.relative_to(REPO)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for host in sorted(parse_bash_hosts(text)):
            if host not in known_hosts:
                findings.docs_vs_manifests.append(
                    f"{rel} references {host}, which no manifest defines"
                )


# ------------------------------------------------------------------ cluster


TIER_ROW_RE = re.compile(r"^\|\s*(Core|Platform|Optional)\s*\|(.+?)\|(.+?)\|\s*$")


def parse_service_tiers() -> list[tuple[str, str]]:
    """Return (tier, service) from the Service Tiers table."""
    path = REPO / "docs" / "infrastructure" / "cluster" / "cluster-stability.md"
    if not path.is_file():
        return []
    rows: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = TIER_ROW_RE.match(line.strip())
        if not m:
            continue
        tier = m.group(1)
        for svc in m.group(2).split(","):
            svc = svc.strip().strip("`")
            if svc:
                rows.append((tier, svc))
    return rows


def cluster_running_names() -> set[str] | None:
    """Service names with at least one Running pod, or None if unreachable."""
    try:
        out = subprocess.run(
            [
                "kubectl",
                "get",
                "pods",
                "-A",
                "--field-selector=status.phase=Running",
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    try:
        payload = json.loads(out.stdout)
    except json.JSONDecodeError:
        return None

    names: set[str] = set()
    for item in payload.get("items", []):
        labels = (item.get("metadata") or {}).get("labels") or {}
        for key in ("app.kubernetes.io/name", "app", "k8s-app"):
            if labels.get(key):
                names.add(str(labels[key]).lower())
    return names


def compare_docs_to_cluster(findings: Findings) -> None:
    tiers = parse_service_tiers()
    if not tiers:
        findings.skipped.append("docs vs cluster: Service Tiers table not found")
        return

    running = cluster_running_names()
    if running is None:
        findings.skipped.append("docs vs cluster: no reachable cluster")
        return

    for tier, service in tiers:
        if tier == "Optional":
            continue
        needle = service.lower()
        if any(needle in name or name in needle for name in running):
            continue
        findings.docs_vs_cluster.append(
            f"cluster-stability.md lists '{service}' as {tier} (always on), "
            f"but no Running pod matches it"
        )


# --------------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict", action="store_true", help="exit non-zero when drift is found"
    )
    parser.add_argument(
        "--no-cluster", action="store_true", help="skip cluster-dependent comparators"
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    findings = Findings()
    facts = manifest_facts()

    compare_scripts_to_manifests(facts, findings)
    compare_docs_to_manifests(facts, findings)
    if args.no_cluster:
        findings.skipped.append("docs vs cluster: --no-cluster")
    else:
        compare_docs_to_cluster(findings)

    if args.json:
        print(
            json.dumps(
                {
                    "total": findings.total(),
                    "scripts_vs_manifests": findings.scripts_vs_manifests,
                    "docs_vs_manifests": findings.docs_vs_manifests,
                    "docs_vs_cluster": findings.docs_vs_cluster,
                    "skipped": findings.skipped,
                },
                indent=2,
            )
        )
    else:
        sections = (
            ("Scripts vs manifests", findings.scripts_vs_manifests),
            ("Docs vs manifests", findings.docs_vs_manifests),
            ("Docs vs cluster", findings.docs_vs_cluster),
        )
        if findings.total() == 0:
            print("No drift detected.")
        else:
            print(f"Drift detected ({findings.total()}):\n")
            for title, items in sections:
                if not items:
                    continue
                print(f"  {title}:")
                for item in sorted(set(items)):
                    print(f"    - {item}")
                print()
        for note in findings.skipped:
            print(f"  skipped: {note}")
        if findings.total():
            print(
                "\nDrift is advisory. Fix the claim or the reality, then re-run "
                "`just drift`."
            )

    if args.strict and findings.total():
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
