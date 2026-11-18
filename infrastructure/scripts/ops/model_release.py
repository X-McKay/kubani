#!/usr/bin/env python3
"""Write the manifest of a new model release of an engine from the committed state of that engine.

The image, served name and stated serving arguments come from the engine's Deployment and model-config, as the
catalog names them; what only the operator knows comes from flags. A manifest is never edited after it is merged,
so this refuses to overwrite one. It edits nothing else and reaches nothing.
Run with: just inference-manifest --engine fast --name <name>
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import outcome  # noqa: E402
import registry_feed  # noqa: E402

RELEASES = Path("docs/infrastructure/inference/releases")
BENCHMARKS = Path("docs/infrastructure/inference/benchmarks")
VARIABLE = re.compile(r"\$(?:\{(\w+)\}|(\w+))")


def emit(document) -> None:
    print(json.dumps(document, sort_keys=True))


class Parser(argparse.ArgumentParser):
    """argparse, which still prints usage to stderr and exits 2, plus the `invalid-arguments` document on stdout."""

    def error(self, message):
        emit(outcome.document({}, outcome.error("invalid-arguments", outcome.usage_message(message))))
        super().error(message)


def _config(root: Path, container: dict) -> dict[str, str]:
    """The container's environment as the repository states it: model-config keys it takes by envFrom, then literal env values."""
    env: dict[str, str] = {}
    wanted = {(item.get("configMapRef") or {}).get("name") for item in container.get("envFrom") or [] if isinstance(item, dict)}
    for doc in registry_feed._docs(root, registry_feed.MODEL_CONFIG):
        if isinstance(doc, dict) and doc.get("kind") == "ConfigMap" and (doc.get("metadata") or {}).get("name") in wanted:
            env.update({k: v for k, v in (doc.get("data") or {}).items() if isinstance(v, str)})
    for item in container.get("env") or []:
        if isinstance(item, dict) and isinstance(item.get("value"), str):
            env[item["name"]] = item["value"]
    return env


def _value(text: str | None, env: dict[str, str]) -> str | None:
    """A literal argument value, or the value of the one variable it is; None when it is neither stated nor resolvable."""
    if text is None:
        return None
    found = VARIABLE.fullmatch(text)
    if found:
        return env.get(found.group(1) or found.group(2))
    return None if "$" in text else text


def _tokens(container: dict) -> list[str]:
    script = "\n".join(str(a) for a in container.get("args") or []).replace("\\\n", " ")
    try:
        return shlex.split(script)
    except ValueError:
        raise ValueError("the container's arguments cannot be read as a command line") from None


def _flag(tokens: list[str], name: str) -> str | None:
    for index, token in enumerate(tokens):
        if token == name and index + 1 < len(tokens):
            return tokens[index + 1]
        if token.startswith(name + "="):
            return token[len(name) + 1 :]
    return None


def _engine_state(root: Path, engine: str) -> dict:
    """What the repository states of the engine: image, served name, model path and the serving arguments."""
    cat = registry_feed._catalog(root)
    entries = registry_feed._entries(cat, "modelEngines", registry_feed.ENGINE_KEYS, identity="name")
    entry = next((e for e in entries if e["name"] == engine), None)
    if entry is None:
        raise outcome.Coded(f"{registry_feed.CATALOG}: no model engine {engine!r}", "not-found")
    where = f"{registry_feed.CATALOG}: modelEngines {engine!r}"
    if not entry.get("manifest") or not entry.get("container"):
        raise outcome.Coded(f"{where}: no manifest and container; an engine without them has no model release", "refused")
    deployment = registry_feed._deployment(root, entry["manifest"], entry["workload"], entry["namespace"], where)
    image = registry_feed._container_image(deployment, entry["container"], where, entry["manifest"])
    spec = ((deployment.get("spec") or {}).get("template") or {}).get("spec") or {}
    container = next(c for c in spec["containers"] if c.get("name") == entry["container"])
    env = _config(root, container)
    tokens = _tokens(container)
    path = None
    for index, token in enumerate(tokens[:-2]):
        if token == "vllm" and tokens[index + 1] == "serve":
            path = _value(tokens[index + 2], env)
            break
    if not path:
        raise ValueError(f"{where}: the model path that {entry['container']} serves is not stated in {entry['manifest']}")
    length = _value(_flag(tokens, "--max-model-len"), env)
    return {
        "served": registry_feed._served_name(root, entry),
        "image": image,
        "path": path,
        "chatTemplate": _value(_flag(tokens, "--chat-template"), env),
        "toolCallParser": _value(_flag(tokens, "--tool-call-parser"), env),
        "contextLength": int(length) if length is not None and length.isdigit() else None,
        "toolCalling": True if "--enable-auto-tool-choice" in tokens else None,
        "aliased": any(a.get("engine") == engine for a in cat.get("aliases") or [] if isinstance(a, dict)),
    }


def _existing(root: Path, rel: str | None, what: str) -> str | None:
    if rel is None:
        return None
    path = registry_feed._inside(root, rel)
    if not path.is_file():
        raise outcome.Coded(f"{what}: {rel} is not a file in the repository", "not-found")
    return path.relative_to(root).as_posix()


def _baseline(root: Path, engine: str) -> str | None:
    marker = root / BENCHMARKS / engine / "BASELINE"
    if not marker.is_file():
        return None
    rel = (BENCHMARKS / engine / marker.read_text(encoding="utf-8").strip()).as_posix()
    return rel if (root / rel).is_file() else None


def _change_record(root: Path, image: str) -> str | None:
    """The newest release record that names the engine image, if any."""
    records = sorted((root / RELEASES).glob("*.md")) if (root / RELEASES).is_dir() else []
    named = [p for p in records if image in p.read_text(encoding="utf-8")]
    return named[-1].relative_to(root).as_posix() if named else None


def new(root: Path, args) -> dict:
    name = args.name
    if registry_feed.release_slug(name) != name:
        raise outcome.Coded(f"name {name!r} is not a release slug; it must be {registry_feed.release_slug(name)!r}", "validation-failed")
    state = _engine_state(root, args.engine)
    target = registry_feed._inside(root, registry_feed.MODELS / args.engine / f"{name}.yaml")
    if target.exists():
        raise outcome.Coded(f"{target.relative_to(root)} exists; a manifest is never edited after it is merged, name a new release", "conflict")
    benchmark = _existing(root, args.benchmark, "--benchmark")
    record = _existing(root, args.change_record, "--change-record")
    tool_calling = state["toolCalling"] if args.tool_calling is None else args.tool_calling == "true"
    manifest = {
        "schemaVersion": 1,
        "engine": args.engine,
        "name": name,
        "servedName": state["served"],
        "weights": {"source": f"hf://{state['path']}", "revision": args.weights_revision, "files": None},
        "format": None,
        "quantisation": None,
        "engineImage": state["image"],
        "serving": {"chatTemplate": state["chatTemplate"], "toolCallParser": state["toolCallParser"], "contextLength": state["contextLength"]},
        "offers": {"contextLength": None, "toolCalling": tool_calling, "structuredOutput": None, "embeddingSize": None},
        "evidence": {
            "benchmark": benchmark if benchmark is not None else _baseline(root, args.engine),
            "changeRecord": record if record is not None else _change_record(root, state["image"]),
        },
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("x", encoding="utf-8") as handle:
            yaml.safe_dump(manifest, handle, sort_keys=False)
    except FileExistsError:
        raise outcome.Coded(f"{target.relative_to(root)} exists; a manifest is never edited after it is merged, name a new release", "conflict") from None
    rel = target.relative_to(root).as_posix()
    steps = [f"review {rel}: every null is a value the repository does not state", f"in the change that moves engine {args.engine!r}, set `release: {name}` on its modelEngines entry in {registry_feed.CATALOG}"]
    if state["aliased"]:
        steps.append(f"engine {args.engine!r} is behind an alias: run `just agent alias plan` first")
    steps.append("render the feed: uv run --locked python infrastructure/scripts/ops/registry_feed.py render --write")
    return {"status": "written", "file": rel, "next": steps}


def parser() -> argparse.ArgumentParser:
    result = Parser(description=__doc__)
    result.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    commands = result.add_subparsers(dest="command", required=True)
    cmd = commands.add_parser("new", help="write the manifest of a new release of an engine")
    cmd.add_argument("--engine", required=True)
    cmd.add_argument("--name", required=True)
    cmd.add_argument("--weights-revision")
    cmd.add_argument("--benchmark", help="a result file in the repository; default: the file the profile's BASELINE names")
    cmd.add_argument("--change-record", help="a release record in the repository; default: the newest that names the engine image")
    cmd.add_argument("--tool-calling", choices=["true", "false"])
    return result


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    root = args.root.resolve()
    try:
        document = new(root, args)
    except outcome.Coded as exc:
        emit(outcome.document({}, outcome.error(exc.code, str(exc))))
        return 1
    except ValueError as exc:
        emit(outcome.document({}, outcome.error("validation-failed", str(exc))))
        return 1
    except OSError as exc:
        code = "not-found" if isinstance(exc, FileNotFoundError) else "failed"
        emit(outcome.document({}, outcome.error(code, f"a file could not be read or written ({type(exc).__name__})")))
        return 1
    emit(outcome.document(document))
    return 0


if __name__ == "__main__":
    sys.exit(main())
