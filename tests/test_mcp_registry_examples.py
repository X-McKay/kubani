"""The MCP backend example corpus is executable documentation.

infrastructure/mcp/examples/valid/*.yaml must be accepted and every entry in
infrastructure/mcp/examples/invalid/ must be refused as its <name>.expect.json
says. Each example goes through model.load_registry, the function the real
`just mcp check` path calls, against a throwaway repository root, so nothing
here reads a cluster, a credential or sops.

An invalid example is either one file (<name>.yaml, or <name>.yaml.txt when it
is deliberately not YAML) or, for a rule about the set
of backends, a directory (<name>/) of backend files. Files a definition points
at come from infrastructure/mcp/examples/support/ plus fake "encrypted" Secret
manifests built below; see infrastructure/mcp/examples/README.md.
"""

import ast
import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "infrastructure/scripts/ops"))

from mcp_registry import model  # noqa: E402

CORPUS = ROOT / "infrastructure/mcp/examples"
VALID = sorted((CORPUS / "valid").glob("*.yaml"))
INVALID_DIR = CORPUS / "invalid"
# Examples that are not parseable YAML carry a .yaml.txt name so the repository's
# YAML linters do not reject them; they are installed as .yaml for the loader.
INVALID = sorted(
    p
    for p in INVALID_DIR.iterdir()
    if p.is_dir() or p.name.endswith((".yaml", ".yaml.txt"))
)
EXPECTATIONS = sorted(INVALID_DIR.glob("*.expect.json"))

# Messages raised in model.py that no example can trigger, with the reason.
# The coverage test fails when this list is stale as well as when it is short.
UNREACHABLE = {}


def _secret(namespace, name, keys, *, encrypted=True, kind="Secret"):
    """A fake SOPS-looking manifest. Values are placeholders, never real."""
    value = "ENC[AES256_GCM,data:example,type:str]" if encrypted else "not-encrypted"
    doc = {
        "apiVersion": "v1",
        "kind": kind,
        "metadata": {"name": name, "namespace": namespace},
        "stringData": {k: value for k in keys},
    }
    if kind == "Secret":  # the plaintext variant claims sops but holds a bare value
        doc["sops"] = {"version": "example"}
    return yaml.safe_dump(doc)


FAKE_SECRETS = {
    "api-token": ("mcp", "example-api", ["API_TOKEN"], {}),
    "db-role": ("database", "example-db-role", ["password"], {}),
    "db-workload": ("mcp", "example-db", ["DATABASE_URI"], {}),
    "wrong-identity": ("mcp", "some-other-name", ["password"], {}),
    "missing-key": ("database", "example-db-role", ["other"], {}),
    "plaintext": ("mcp", "example-api", ["API_TOKEN"], {"encrypted": False}),
    "not-a-secret": ("mcp", "example-api", ["API_TOKEN"], {"kind": "ConfigMap"}),
}


def build_root(tmp_path, example: Path) -> Path:
    """A repository root holding the support files and the example(s)."""
    root = tmp_path / "repo"
    shutil.copytree(CORPUS / "support", root)
    support = root / "infrastructure/example"
    for stem, (ns, name, keys, extra) in FAKE_SECRETS.items():
        (support / f"{stem}.enc.yaml").write_text(_secret(ns, name, keys, **extra))
    (support / "linked").symlink_to(".")
    backends = root / "infrastructure/mcp/backends"
    backends.mkdir(parents=True)
    files = sorted(example.glob("*.yaml")) if example.is_dir() else [example]
    for f in files:
        # A single example is installed under its own file name, so the
        # <name>.yaml rule is judged on the example's real name; valid examples
        # are named after their definition.
        shutil.copy(f, backends / f.name.removesuffix(".txt"))
    return root


def refusal(tmp_path, example: Path):
    """The exception the real loader raises for this example, or None."""
    try:
        model.load_registry(build_root(tmp_path, example))
    except Exception as exc:  # noqa: BLE001 - the type is part of the expectation
        return exc
    return None


def chain_text(exc) -> str:
    parts = []
    while exc is not None:
        parts.append(str(exc))
        exc = exc.__cause__
    return " | ".join(parts)


def expectation_for(example: Path) -> Path:
    name = example.name.removesuffix(".txt").removesuffix(".yaml")
    return INVALID_DIR / f"{name}.expect.json"


def test_corpus_is_present():
    assert len(VALID) >= 2 and len(INVALID) >= 10


def test_every_invalid_example_has_an_expectation_and_back():
    examples = {expectation_for(p).name for p in INVALID}
    expectations = {p.name for p in EXPECTATIONS}
    assert examples - expectations == set(), "invalid examples without .expect.json"
    assert expectations - examples == set(), ".expect.json without an example"


def test_the_corpus_is_not_registered_as_a_backend():
    names = {p.stem for p in (ROOT / "infrastructure/mcp/backends").glob("*.yaml")}
    assert names.isdisjoint({p.stem for p in VALID})


@pytest.mark.parametrize("example", VALID, ids=lambda p: p.name)
def test_valid_example_is_accepted(example, tmp_path):
    root = build_root(tmp_path, example)
    entries = model.load_registry(root)
    assert [e["name"] for e in entries] == [example.stem]


@pytest.mark.parametrize("example", INVALID, ids=lambda p: p.stem)
def test_invalid_example_is_refused_as_expected(example, tmp_path):
    expect_file = expectation_for(example)
    assert expect_file.is_file(), f"{example.name} has no {expect_file.name}"
    expect = json.loads(expect_file.read_text())
    assert set(expect) == {"error", "message_contains"}
    assert expect["message_contains"].strip(), "an empty substring matches everything"
    exc = refusal(tmp_path, example)
    assert exc is not None, f"{example.name} was accepted"
    assert type(exc).__name__ == expect["error"], chain_text(exc)
    assert expect["message_contains"] in chain_text(exc)


def _raised_messages(path: Path) -> set[str]:
    """Leading literal text of every ValueError/TypeError raised in a module."""
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if not (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)):
            continue
        func = node.exc.func
        if getattr(func, "id", None) not in ("ValueError", "TypeError"):
            continue
        arg = node.exc.args[0]
        while isinstance(arg, ast.BinOp):  # "text: " + ", ".join(...)
            arg = arg.left
        if isinstance(arg, ast.JoinedStr):  # f"text: {value}"
            arg = arg.values[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            found.add(arg.value)
    return found


def test_every_raise_in_model_is_exercised_by_an_invalid_example(tmp_path):
    observed = []
    for i, example in enumerate(INVALID):
        exc = refusal(tmp_path / str(i), example)
        if exc is not None:
            observed.append(chain_text(exc))
    uncovered = {
        m
        for m in _raised_messages(ROOT / "infrastructure/scripts/ops/mcp_registry/model.py")
        if not any(m in text for text in observed)
    }
    assert uncovered == set(UNREACHABLE), (
        "model.py messages with no invalid example (add one, or list it in "
        f"UNREACHABLE with the reason): {sorted(uncovered - set(UNREACHABLE))}; "
        f"stale UNREACHABLE entries: {sorted(set(UNREACHABLE) - uncovered)}"
    )
