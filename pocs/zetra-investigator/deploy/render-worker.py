"""Render ordinary application resources using an immutable SDK release."""

import argparse
import json
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
if args.session:
    import copy

    from kubani_investigator.runtime import parse_args

    parse_args(["run", "--session", args.session])
    if len(args.session) > 55:
        raise ValueError("Keep session under 56 characters for its Kubernetes Job name")
    pod = copy.deepcopy(worker["spec"]["template"])
    spec = pod["spec"]
    spec["restartPolicy"] = "OnFailure"
    spec["volumes"] = [v for v in spec["volumes"] if v["name"] not in ("tls", "key")]
    container = spec["containers"][0]
    container["name"] = "investigator"
    container["command"][-1:] = ["run", "--session", args.session]
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
