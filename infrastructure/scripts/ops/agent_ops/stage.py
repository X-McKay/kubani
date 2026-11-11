"""Stage one published release as an unapproved AgentRelease from its exact assets."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

import yaml

import outcome

from . import layout, live, sync

ASSETS = ("agent.yaml", "agentrelease.yaml", "policy-bundle.json", "predicate.json", "SHA256SUMS", "image")
SUMMED = frozenset(ASSETS[:4])
PINNED = ("image", "manifestSha256", "policySha256", "lockSha256", "buildRevision")
PRAGMA = "  # pragma: allowlist secret (verified public release fingerprint)"


class StageError(outcome.Coded):
    default_code = "validation-failed"

    pass


def download(repo: str, tag: str, dest: Path) -> None:
    cmd = ["gh", "release", "download", tag, "-R", repo, "-D", str(dest)]
    for name in ASSETS:
        cmd += ["-p", name]
    what = f"gh release download {tag} from {repo} failed"
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
    except FileNotFoundError as exc:
        raise StageError(f"{what}: gh is not installed or not on PATH", "unavailable") from exc
    except subprocess.TimeoutExpired as exc:
        raise StageError(f"{what}: timed out after 120 seconds", "timeout") from exc
    except subprocess.CalledProcessError as exc:
        raise StageError(f"{what}: gh exited {exc.returncode}{live.last_line(exc.stderr)}; check `gh auth status`", "unavailable") from exc
    except OSError as exc:
        raise StageError(f"{what}: gh could not be run: {exc.strerror or type(exc).__name__}", "unavailable") from exc
    missing = [n for n in ASSETS if not (dest / n).is_file()]
    if missing:
        raise StageError(f"release {tag} is missing assets: {', '.join(missing)}")


def verify_sums(dest: Path) -> dict[str, str]:
    listed = {}
    for line in (dest / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 2 or not layout.SHA256.match(parts[0]):
            raise StageError("SHA256SUMS has an unexpected line")
        listed[parts[1]] = parts[0]
    if set(listed) != SUMMED:
        raise StageError(f"SHA256SUMS must list exactly {sorted(SUMMED)}")
    for name, digest in listed.items():
        actual = hashlib.sha256((dest / name).read_bytes()).hexdigest()
        if actual != digest:
            raise StageError(f"{name} does not match SHA256SUMS")
    return listed


def verify_assets(root: Path, d: layout.AgentDir, repo: str, tag: str, dest: Path, source: Path | None) -> dict:
    agent = layout.load_one(dest / "agent.yaml", "Agent")
    release = layout.load_one(dest / "agentrelease.yaml", "AgentRelease")
    predicate = json.loads((dest / "predicate.json").read_text(encoding="utf-8"))
    bundle = json.loads((dest / "policy-bundle.json").read_text(encoding="utf-8"))
    image = (dest / "image").read_text(encoding="utf-8").strip()
    spec = release["spec"]
    meta = release["metadata"]
    name = meta.get("name", "")

    if meta.get("namespace") != d.tenant or spec.get("agent") != d.agent:
        raise StageError("release does not target this agent and tenant")
    if not re.fullmatch(re.escape(d.agent) + r"-\d{4}-\d{2}-\d{2}-[0-9a-f]{8}", name):
        raise StageError("release name is not of the form <agent>-<date>-<digest>")
    if spec.get("approval") != {"approved": False}:
        raise StageError("published release must be unapproved")
    for key in PINNED:
        if not isinstance(spec.get(key), str) or not spec[key]:
            raise StageError(f"release spec.{key} is missing")
    for key in ("manifestSha256", "policySha256", "lockSha256"):
        if not layout.SHA256.match(spec[key]):
            raise StageError(f"release spec.{key} is not a sha256 hex digest")
    prefix = f"registry.almckay.io/agents/{d.agent}@sha256:"
    if not spec["image"].startswith(prefix) or not layout.SHA256.match(spec["image"][len(prefix) :]):
        raise StageError("release image must be a digest-pinned registry.almckay.io/agents reference")
    if spec["image"] != image:
        raise StageError("release image differs from the published `image` asset")
    for key in ("buildRevision", "lockSha256", "manifestSha256", "policySha256"):
        if predicate.get(key) != spec[key]:
            raise StageError(f"predicate.{key} differs from the release")
    if predicate.get("release") != name:
        raise StageError("predicate names a different release")
    for key, want in (("agent", d.agent), ("tenant", d.tenant), ("release", name), ("image", spec["image"])):
        if bundle.get(key) != want:
            raise StageError(f"policy bundle {key} differs from the release")

    committed = layout.committed_agent(d)
    if agent != committed:
        raise StageError("published Agent differs from the committed Agent; sync the Agent first or cut a new release")

    subject = layout.expected_subject(repo, tag)
    pin = layout.signer_pin(root, d.tenant)
    if pin["issuer"] != layout.ISSUER or not layout.subject_matches(pin, subject):
        raise StageError(f"tenant signer pin does not accept {subject}")

    evidence = {"sourceHashes": "not-checked"}
    if source is not None:
        rev = spec["buildRevision"]
        manifest = sync._git(source, "show", f"{rev}:agents/{d.agent}/agent.yaml")
        if hashlib.sha256(manifest.encode("utf-8")).hexdigest() != spec["manifestSha256"]:
            raise StageError("manifestSha256 differs from agents/<agent>/agent.yaml at buildRevision")
        # The image lock is the repository's workspace uv.lock; repositories released before
        # the workspace layout locked each agent separately.
        lock_path = "uv.lock" if sync.source_has(source, rev, "uv.lock") else f"agents/{d.agent}/uv.lock"
        lock = sync._git(source, "show", f"{rev}:{lock_path}")
        if hashlib.sha256(lock.encode("utf-8")).hexdigest() != spec["lockSha256"]:
            raise StageError(f"lockSha256 differs from {lock_path} at buildRevision")
        evidence["sourceHashes"] = "verified"
        evidence["lock"] = lock_path
    return {"release": release, "name": name, "subject": subject, "evidence": evidence}


def render(tag: str, release_text: str) -> str:
    lines = [
        "# yamllint disable rule:line-length",
        f"# Exact signed {tag} assets; SHA256SUMS verified by `just agent stage`.",
    ]
    for line in release_text.rstrip("\n").split("\n"):
        key = line.strip().split(":", 1)[0]
        if line.startswith("  ") and key in PINNED:
            line += PRAGMA
        lines.append(line)
    return "\n".join(lines) + "\n"


def stage(root: Path, agent: str, tag: str, *, repo: str | None = None, source: Path | None = None) -> dict:
    m = layout.TAG.match(tag)
    if not m or m.group("agent") != agent:
        raise StageError("tag must be <agent>/v<version> for this agent", "invalid-arguments")
    d = layout.find_agent(root, agent)
    repo = repo or sync.source_repo(d)
    file_name = f"agentrelease-{m.group('version')}.yaml"
    target = d.path / file_name
    if target.exists():
        raise StageError(f"{target.relative_to(root)} already exists", "conflict")
    with tempfile.TemporaryDirectory(prefix="agent-stage-") as tmp:
        dest = Path(tmp)
        download(repo, tag, dest)
        sums = verify_sums(dest)
        verified = verify_assets(root, d, repo, tag, dest, source)
        for file in d.release_files():
            if layout.load_one(file, "AgentRelease")["metadata"].get("name") == verified["name"]:
                raise StageError(f"{file.relative_to(root)} already stages {verified['name']}", "conflict")
        text = (dest / "agentrelease.yaml").read_text(encoding="utf-8")
    rendered = render(tag, text)
    if yaml.safe_load(rendered) != verified["release"]:
        raise StageError("rendered file does not parse back to the published release")
    target.write_text(rendered, encoding="utf-8")
    layout.append_resource(d, file_name)
    spec = verified["release"]["spec"]
    return {
        "agent": agent,
        "tenant": d.tenant,
        "tag": tag,
        "release": verified["name"],
        "file": str(target.relative_to(root)),
        "image": spec["image"],
        "policySha256": spec["policySha256"],
        "buildRevision": spec["buildRevision"],
        "expectedSigner": verified["subject"],
        "checksums": sums,
        "approval": False,
        **verified["evidence"],
        "next": "commit, merge, let Flux reconcile, then `just agent approve " + verified["name"] + "`",
    }
