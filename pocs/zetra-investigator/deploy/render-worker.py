"""Render ordinary application resources using an immutable SDK release."""

import argparse
import json
import re
from pathlib import Path

import yaml
from zetra.manifest import load_release

parser = argparse.ArgumentParser()
parser.add_argument("release", type=Path)
parser.add_argument("--session", help="Also render a one-shot run Job for this reusable session")
args = parser.parse_args()
release = load_release(args.release)
resources = list(yaml.safe_load_all(Path(__file__).with_name("worker.yaml").read_text()))
worker = resources[-1]
worker["spec"]["template"]["spec"]["containers"][0]["image"] = release.image
resources.append(
    {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "investigator-release", "namespace": "zetra-poc"},
        "data": {"release.json": release.model_dump_json()},
    }
)
if args.session is not None:
    import copy

    if not re.fullmatch(r"investigate-[a-z0-9-]{1,40}", args.session):
        raise ValueError("Use a short investigate- session identity")
    pod = copy.deepcopy(worker["spec"]["template"])
    spec = pod["spec"]
    spec["restartPolicy"] = "OnFailure"
    spec["volumes"] = [v for v in spec["volumes"] if v["name"] not in ("tls", "key")]
    container = spec["containers"][0]
    container["name"] = "investigator"
    container["command"] = container["command"][: container["command"].index("worker")] + [
        "run",
        "/etc/zetra/release.json",
        "--session",
        args.session,
        "--input",
        "Investigate investigator-demo-broken in zetra-poc-fixtures. Explain the startup problem using MCP evidence, compare the healthy pod, and write report.md.",
        "--output",
        "/artifacts/results/" + args.session,
    ]
    container["volumeMounts"] = [
        v for v in container["volumeMounts"] if v["name"] not in ("tls", "key")
    ]
    pod["metadata"]["labels"] = {"app": "investigator-run"}
    resources.append(
        {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {"name": "run-" + args.session, "namespace": "zetra-poc"},
            "spec": {"backoffLimit": 2, "ttlSecondsAfterFinished": 3600, "template": pod},
        }
    )
print(json.dumps({"apiVersion": "v1", "kind": "List", "items": resources}, indent=2))
