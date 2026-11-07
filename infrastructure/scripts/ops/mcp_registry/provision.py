"""Offline prerequisite checks and exclusive, paired SOPS credential preparation."""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
from pathlib import Path
from urllib.parse import quote

import yaml

from . import model

APPS = "infrastructure/gitops/apps"
ADMIN = APPS + "/postgresql/secret.enc.yaml"


def _encrypted(document, desired=None):
    if (
        not isinstance(document, dict)
        or document.get("apiVersion") != "v1"
        or document.get("kind") != "Secret"
    ):
        raise ValueError("encrypted Secret manifest required")
    metadata = document.get("metadata", {})
    model.name(metadata.get("name"))
    model.name(metadata.get("namespace"))
    if set(document.get("data", {})) & set(document.get("stringData", {})):
        raise ValueError("overlapping encrypted Secret keys refused")
    values = dict(document.get("data", {}))
    values.update(document.get("stringData", {}))
    sops = document.get("sops")
    if (
        not values
        or not isinstance(sops, dict)
        or not sops.get("age")
        or not isinstance(sops.get("mac"), str)
        or not sops["mac"].startswith("ENC[")
    ):
        raise ValueError("encrypted Secret metadata required")
    if any(not isinstance(v, str) or not v.startswith("ENC[") for v in values.values()):
        raise ValueError("plaintext Secret prohibited")
    if desired and (
        (metadata.get("namespace"), metadata.get("name"))
        != (desired["namespace"], desired["name"])
        or set(values) != {desired["key"]}
    ):
        raise ValueError("encrypted Secret identity/key mismatch")
    return (metadata["namespace"], metadata["name"]), set(values)


def _policy(root, pair):
    path = root / ".sops.yaml"
    if path.is_symlink():
        raise ValueError("symlink recipient policy refused")
    docs = model.yaml_documents(path)
    if len(docs) != 1:
        raise ValueError("recipient policy required")
    for item in pair:
        rule = next(
            (
                r
                for r in docs[0].get("creation_rules", [])
                if re.search(r.get("path_regex", ""), item["path"])
            ),
            None,
        )
        if (
            not rule
            or rule.get("encrypted_regex") != "^(data|stringData)$"
            or not isinstance(rule.get("age"), str)
            or not rule["age"].strip()
            or set(rule) - {"path_regex", "encrypted_regex", "age"}
        ):
            raise ValueError("unsupported or missing age recipient policy")
        if any(
            not re.fullmatch(r"age1[0-9a-z]+", v.strip())
            for v in rule["age"].split(",")
        ):
            raise ValueError("invalid age recipient policy")


def _sources(root, planned):
    """Traverse explicit local resources only; this is not Kustomize evaluation."""
    included, documents, generators = set(), [], []
    visited = set()
    missing = []

    def visit(relative):
        path = model.safe_path(root, relative)
        if not path.exists() and relative not in planned:
            missing.append("missing source dependency: " + relative)
            return
        if relative in visited:
            return
        visited.add(relative)
        if path.is_dir():
            candidates = [
                path / n
                for n in ("kustomization.yaml", "kustomization.yml", "Kustomization")
                if (path / n).is_file()
            ]
            if len(candidates) != 1:
                raise ValueError("unique source Kustomization required")
            kpath = candidates[0]
            model.safe_path(root, str(kpath.relative_to(root)))
            docs = model.yaml_documents(kpath)
            if len(docs) != 1:
                raise ValueError("unique source Kustomization required")
            config = docs[0]
            # Transformations remain subject to the mandatory full render/check.
            for resource in config.get("resources", []):
                if (
                    not isinstance(resource, str)
                    or ":" in resource
                    or Path(resource).is_absolute()
                ):
                    raise ValueError("unsupported source resource")
                child = path / resource
                cursor = path
                for part in Path(resource).parts:
                    cursor = cursor / part
                    if cursor.is_symlink():
                        raise ValueError("symlink source resource refused")
                normalized = os.path.normpath(str(child.relative_to(root)))
                visit(normalized)
            for generator in config.get("configMapGenerator", []):
                generators.append((path, generator))
        else:
            included.add(relative)
            if relative in planned and not path.exists():
                return
            for document in model.yaml_documents(path):
                if isinstance(document, dict):
                    documents.append((relative, document))
                    if document.get("kind") == "Kustomization" and document.get(
                        "apiVersion", ""
                    ).startswith("kustomize.toolkit.fluxcd.io/"):
                        source = document.get("spec", {}).get("path", "")
                        if not source.startswith("./infrastructure/"):
                            raise ValueError("unsupported Flux source path")
                        visit(source[2:])

    visit("infrastructure/gitops/flux-system")
    return included, documents, generators, missing


def _preflight(root, entry):
    model.validate(entry, root, provisioning=True)
    pair = model.provision_pair(entry, root)
    _policy(root, pair)
    included, documents, generators, missing = _sources(root, {v["path"] for v in pair})
    issues = list(missing)
    for item in pair:
        if item["path"] not in included:
            issues.append("missing source inclusion: " + item["path"])
    b = entry["bootstrap"]
    if b["manifest"] not in included:
        issues.append("missing source inclusion: " + b["manifest"])
    matches = []
    for directory, generator in generators:
        if (
            generator.get("name") == b["configMap"]
            and generator.get("namespace") == b["namespace"]
        ):
            expected = (
                b["key"]
                + "="
                + str(Path(b["sql"]).relative_to(directory.relative_to(root)))
            )
            if (
                generator.get("files") == [expected]
                and generator.get("options", {}).get("disableNameSuffixHash") is True
            ):
                matches.append(generator)
    if len(matches) != 1:
        issues.append(
            "missing or ambiguous reviewed ConfigMap/SQL source: " + b["configMap"]
        )
    inventory_path = model.safe_path(root, "infrastructure/mcp/inventory.json")
    if inventory_path.exists():
        previous = (
            json.loads(inventory_path.read_text())
            .get("backends", {})
            .get(entry["name"], {})
            .get("bootstrap")
        )
        if (
            previous
            and previous["sqlSha256"] != b["sqlSha256"]
            and previous["revision"] == b["revision"]
        ):
            issues.append("SQL hash changed without reviewed bootstrap revision")
    available = {}
    origins = {}
    # Include raw source metadata even for unreferenced YAML to detect collisions.
    source_paths = {relative for relative, _ in documents}
    source_paths.update(
        str(p.relative_to(root))
        for p in (root / "infrastructure/gitops").rglob("*.yaml")
    )
    for relative in sorted(source_paths):
        path = model.safe_path(root, relative)
        for document in model.yaml_documents(path):
            if not isinstance(document, dict) or document.get("kind") != "Secret":
                continue
            meta = document.get("metadata", {})
            identity = (meta.get("namespace"), meta.get("name"))
            if identity in origins:
                issues.append(
                    "duplicate Secret identity: " + "/".join(str(v) for v in identity)
                )
            origins[identity] = relative
            # Only included and encrypted sources satisfy credential dependencies.
            if relative in included:
                identity, keys = _encrypted(document)
                available[identity] = keys
    for item in pair:
        path = model.safe_path(root, item["path"])
        if path.exists():
            docs = model.yaml_documents(path)
            if len(docs) != 1:
                raise ValueError("one encrypted Secret per credential path required")
            _encrypted(docs[0], item)
        elif (item["namespace"], item["name"]) in origins:
            issues.append(
                "planned Secret identity already exists: "
                + item["namespace"]
                + "/"
                + item["name"]
            )
    job = next(
        d
        for d in model.yaml_documents(model.safe_path(root, b["manifest"]))
        if d.get("kind") == "Job"
    )
    spec = job["spec"]["template"]["spec"]
    references = []
    if spec.get("imagePullSecrets"):
        issues.append("unsupported bootstrap imagePullSecrets dependency")
    for container in spec.get("containers", []) + spec.get("initContainers", []):
        if container.get("envFrom"):
            issues.append("unsupported bootstrap envFrom dependency")
        for env in container.get("env", []):
            ref = env.get("valueFrom", {}).get("secretKeyRef")
            if ref:
                references.append(
                    {
                        "namespace": b["namespace"],
                        "name": ref["name"],
                        "key": ref["key"],
                    }
                )
    for volume in spec.get("volumes", []):
        if "secret" in volume or "projected" in volume:
            issues.append("unsupported bootstrap volume credential dependency")
    admin = [
        ref
        for ref in references
        if ref not in [{k: v for k, v in item.items() if k != "path"} for item in pair]
    ]
    for ref in admin:
        identity = (ref["namespace"], ref["name"])
        if ref["key"] not in available.get(identity, set()):
            issues.append(
                "missing encrypted dependency: " + "/".join(identity) + ":" + ref["key"]
            )
        if (
            identity == ("database", "postgresql-credentials")
            and origins.get(identity) != ADMIN
        ):
            issues.append("administrator source must be " + ADMIN)
    operations = [
        dict(item, action="preserve" if (root / item["path"]).exists() else "create")
        for item in pair
    ]
    return {
        "status": "conflict" if issues else "ready",
        "profile": entry["provision"]["profile"],
        "operations": operations,
        "issues": issues,
        "administratorReferences": admin,
        "bootstrap": {
            k: b[k]
            for k in (
                "manifest",
                "name",
                "namespace",
                "revision",
                "sql",
                "sqlSha256",
                "configMap",
                "key",
            )
        },
        "policyDescription": entry["provision"]["policyDescription"],
        "scope": "explicit local source prerequisites; full render/check required",
        "values": "existing credentials unverified; no decryption or live verification",
        "next": [
            "Run render --write and check after preparation; review diff.",
            "Use identity plan/apply separately; Flux deploys the reviewed Job.",
            "Verify Flux, Job completion and an approved functional session.",
        ],
    }


def plan(root: Path, entry: dict) -> dict:
    """Return sanitized metadata; never generate a password or invoke a process."""
    try:
        return _preflight(Path(root), entry)
    except Exception:  # noqa: BLE001 - source/process exceptions must never expose credentials
        return {
            "status": "conflict",
            "issues": ["invalid provisioning declaration or source dependency"],
            "operations": [],
        }


def apply(root: Path, entry: dict, *, run=None) -> dict:
    """Encrypt both in memory before publishing either, exclusively and without adoption."""
    root = Path(root)
    result = plan(root, entry)
    if result["status"] != "ready":
        return result
    if all(v["action"] == "preserve" for v in result["operations"]):
        return dict(result, status="preserved")
    published = []
    try:
        password = secrets.token_urlsafe(36)
        p = entry["provision"]
        uri = f"postgresql://{quote(p['username'], safe='')}:{quote(password, safe='')}@{p['host']}:{p['port']}/{quote(p['database'], safe='')}"
        ciphertexts = []
        for operation, value in zip(result["operations"], (password, uri), strict=True):
            manifest = {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {
                    "name": operation["name"],
                    "namespace": operation["namespace"],
                },
                "type": "Opaque",
                "stringData": {operation["key"]: value},
            }
            encrypted = (run or subprocess.run)(
                [
                    "sops",
                    "--encrypt",
                    "--config",
                    str(root / ".sops.yaml"),
                    "--filename-override",
                    operation["path"],
                    "--input-type",
                    "yaml",
                    "--output-type",
                    "yaml",
                    "/dev/stdin",
                ],
                input=yaml.safe_dump(manifest),
                capture_output=True,
                text=True,
                cwd=root,
                timeout=30,
                check=False,
            )
            if encrypted.returncode:
                raise ValueError("encryption failed")
            documents = list(yaml.load_all(encrypted.stdout, Loader=model.UniqueLoader))
            if len(documents) != 1:
                raise ValueError("unexpected encrypted output")
            _encrypted(documents[0], operation)
            if password in encrypted.stdout or uri in encrypted.stdout:
                raise ValueError("encryption leaked credential")
            ciphertexts.append(encrypted.stdout.encode())
        for operation, ciphertext in zip(
            result["operations"], ciphertexts, strict=True
        ):
            target = model.safe_path(root, operation["path"])
            with target.open("xb") as output:
                published.append(operation["path"])
                os.fchmod(output.fileno(), 0o600)
                output.write(ciphertext)
                output.flush()
                os.fsync(output.fileno())
        return dict(result, status="created")
    except Exception:  # noqa: BLE001 - source/process exceptions must never expose credentials
        return dict(
            result,
            status="partial" if published else "conflict",
            published=published,
            issues=[
                "credential preparation failed; inspect encrypted paths; existing files are never adopted or overwritten"
            ],
        )
