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
# Keyed by the message as test_..._exercised prints it: "{}" stands for a formatted value.
UNREACHABLE = {
    "{}: resolves outside the repository": (
        "defence in depth: every symlink component is refused first, so a path "
        "that passes the earlier checks cannot resolve outside the root"
    ),
    "{}: name is already used by another backend": (
        "the file name must equal the name (checked first) and file names are "
        "unique within a directory, so two files cannot share a name"
    ),
}


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
RAW_SUPPORT = {"not-a-mapping.enc.yaml": "- not\n- a mapping\n"}


def build_root(tmp_path, example: Path) -> Path:
    """A repository root holding the support files and the example(s)."""
    root = tmp_path / "repo"
    shutil.copytree(CORPUS / "support", root)
    support = root / "infrastructure/example"
    for stem, (ns, name, keys, extra) in FAKE_SECRETS.items():
        (support / f"{stem}.enc.yaml").write_text(_secret(ns, name, keys, **extra))
    for file_name, text in RAW_SUPPORT.items():
        (support / file_name).write_text(text)
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


def _signature(call: ast.Call) -> str:
    """The message of a raise as text, with "{}" where a value is formatted in."""

    def text(node) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            return "".join(text(v) for v in node.values)
        if isinstance(node, ast.FormattedValue):
            return "{}"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return text(node.left) + text(node.right)
        return "{}"

    return text(call.args[0])


def _raise_sites(path: Path) -> dict[int, str]:
    """Line -> message signature for every `raise ValueError/TypeError(...)` in a module."""
    sites = {}
    for node in ast.walk(ast.parse(path.read_text())):
        if not (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)):
            continue
        if getattr(node.exc.func, "id", None) in ("ValueError", "TypeError"):
            sites[node.lineno] = _signature(node.exc)
    return sites


def _raised_lines(path: Path, examples, tmp_path) -> set[int]:
    """Lines of `path` where an exception was raised while loading any example.

    Uses sys.settrace, restricted to that one file, and records the line of
    every 'exception' event; only lines that are raise statements are kept by
    the caller. This is exact about which raise statement ran, whatever its
    message says, so messages may be built from field paths.
    """
    target = str(path)
    seen: set[int] = set()

    def local(frame, event, arg):
        if event == "exception":
            seen.add(frame.f_lineno)
        return local

    def tracer(frame, event, arg):
        return local if frame.f_code.co_filename == target else None

    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        for i, example in enumerate(examples):
            refusal(tmp_path / str(i), example)
    finally:
        sys.settrace(previous)
    return seen


def test_every_raise_in_model_is_exercised_by_an_invalid_example(tmp_path):
    path = ROOT / "infrastructure/scripts/ops/mcp_registry/model.py"
    sites = _raise_sites(path)
    hit = _raised_lines(path, INVALID, tmp_path)
    uncovered = {sig for line, sig in sites.items() if line not in hit}
    assert uncovered == set(UNREACHABLE), (
        "model.py refusals no invalid example reaches (add an example, or list "
        f"the message in UNREACHABLE with the reason): {sorted(uncovered - set(UNREACHABLE))}; "
        f"stale UNREACHABLE entries: {sorted(set(UNREACHABLE) - uncovered)}"
    )


def test_each_refusal_in_model_has_its_own_message():
    sigs = list(_raise_sites(ROOT / "infrastructure/scripts/ops/mcp_registry/model.py").values())
    dupes = sorted({s for s in sigs if sigs.count(s) > 1})
    assert dupes == [], f"two raise sites share a message: {dupes}"


def test_expectations_name_a_field_or_a_file():
    """A message_contains of only a generic phrase pins nothing about the field."""
    generic = ("must be", "unknown field", "missing field", "still holds")
    for expect_file in EXPECTATIONS:
        phrase = json.loads(expect_file.read_text())["message_contains"]
        if any(phrase.startswith(g) for g in generic):
            raise AssertionError(f"{expect_file.name}: {phrase!r} does not name a field path")
