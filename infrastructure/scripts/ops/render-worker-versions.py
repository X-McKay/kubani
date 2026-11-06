#!/usr/bin/env python3
"""Render zero-replica, non-active worker templates; never applies resources."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = ROOT / "infrastructure/gitops/apps/agent-platform/worker-versions"
IMAGE_RE = re.compile(
    r"registry\.almckay\.io/platform/session-runner(?::[A-Za-z0-9._-]+)?@sha256:([a-f0-9]{64})\Z"
)
# This known legacy binary ignores WORKER_POOL and cannot poll governed queues.
LEGACY_DIGEST = "48ef7c54e41b4ccf0958ff29fd88a3263d59fe6d7d455f0589cac4f0788feca1"  # pragma: allowlist secret


def render(image: str, source_commit: str, output: Path) -> None:
    match = IMAGE_RE.fullmatch(image)
    if not match or match[1] in {"0" * 64, LEGACY_DIGEST}:
        raise ValueError("published governed-capable runner RepoDigest required")
    if not re.fullmatch(r"[a-f0-9]{40}", source_commit) or source_commit == "0" * 40:
        raise ValueError("full merged source commit required")
    build = "b-" + source_commit[:12]
    rendered = {}
    for name in ("sessions", "cleanup", "netpol"):
        text = (TEMPLATES / (name + ".yaml.in")).read_text()
        for marker, value in {
            "__RUNNER_IMAGE__": image,
            "__SOURCE_COMMIT__": source_commit,
            "__BUILD_ID__": build,
        }.items():
            text = text.replace(marker, value)
        if "__" in text:
            raise ValueError("unresolved template marker")
        docs = list(yaml.safe_load_all(text))
        for doc in docs:
            if doc.get("kind") == "Deployment" and (
                doc["spec"]["replicas"] != 0 or len(doc["metadata"]["name"]) > 63
            ):
                raise ValueError("worker must be inactive with a valid disjoint name")
        rendered[name + ".yaml"] = text
    rendered["kustomization.yaml"] = yaml.safe_dump(
        {
            "apiVersion": "kustomize.config.k8s.io/v1beta1",
            "kind": "Kustomization",
            "resources": ["sessions.yaml", "cleanup.yaml", "netpol.yaml"],
        },
        sort_keys=False,
    )
    # No overwrite, kubectl, cluster client, Scale or routing mutation here.
    output.mkdir(parents=True, exist_ok=False)
    for name, text in rendered.items():
        with (output / name).open("x") as target:
            target.write(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-image", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        render(args.runner_image, args.source_commit, args.output)
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
