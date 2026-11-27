"""A tenant's committed pieces: written from the reference tenant by `add`, held to it by `check`.

A tenant is a Namespace plus a Session Runner, a session interface and a cleanup reconciler of its own, four
NetworkPolicies, two Roles, a ServiceAccount, a Temporal client certificate and its entry in the Temporal endpoint's
allow-list, a Temporal namespace, a payload key and the kustomization entries that list them. They sit in thirteen
places, and a tenant that misses one fails at run time, not at review.

So nothing here is written by hand. Every piece of a tenant is the reference tenant's piece with the tenant's name in
place of the reference's: `add` writes them, `sync` rewrites them after the reference changed (an image pin, a
resource limit), and `check` fails when a tenant misses a piece or a piece differs from the reference in anything but
the name. Comments are not compared.

Three things are deliberately not copied from the reference:

- the payload key. It is a Secret a person creates (docs/infrastructure/configuration/agent-operations.md, "Tenants");
  `add` lists its file and `check` fails until the file exists.
- the signer pin. A tenant with no agents trusts no one: `just agent register` writes the pin with its first agent.
- the effects the tenant grants (`agentplatform.io/granted-effects`). A new tenant grants none.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

import outcome

from . import layout, register

REFERENCE = "tenant-test"
# The Registry Controller may write only in namespaces that match ^tenant-[a-z0-9-]{1,50}$
# (apps/agent-platform/workloads/registry-controller-scope.yaml); layout.NAME keeps every derived name a DNS label.
PREFIX = "tenant-"
GITOPS = Path("infrastructure/gitops")
PLATFORM = GITOPS / "apps/agent-platform"
WORKLOADS = PLATFORM / "workloads"
NETPOL = GITOPS / "infrastructure/agent-platform-netpol"
MTLS = WORKLOADS / "temporal-mtls.yaml"
RBAC = PLATFORM / "registry-rbac.yaml"
ENVOY = ("ConfigMap", "temporal-mtls-envoy")
SAN = "spiffe://cluster.local/ns/agent-platform/sa/session-api-"
# The reference's session interface certificate predates per-tenant names.
REFERENCE_CERTIFICATE = "session-api-temporal-tls"
SIGNER_ANNOTATIONS = ("agentplatform.io/signer-issuer", register.ANNOTATION)
HEADER = """# Tenant {tenant}. Written by `just agent tenant add {tenant}` from
# {source}, whose comments explain every setting.
# `just agent tenant check` holds this file equal to that one apart from the
# tenant's name: change the reference, then run `just agent tenant sync`.
"""
NAMESPACE = """---
# Added by `just agent tenant add {tenant}`. It grants no effects, and it has
# no signer pin until `just agent register` adds its first agent: a tenant
# with no agents trusts no one.
apiVersion: v1
kind: Namespace
metadata:
  name: {tenant}
  labels:
{labels}
"""


class TenantError(outcome.Coded):
    default_code = "validation-failed"


def require_name(tenant: str) -> None:
    if not layout.NAME.match(tenant) or not tenant.startswith(PREFIX) or len(tenant) == len(PREFIX):
        raise TenantError(f"a tenant's name is `{PREFIX}` and a DNS label, at most 32 characters in all", "invalid-arguments")


def _sub(text: str, tenant: str) -> str:
    """The reference's text with `tenant` in place of the reference's name."""
    if tenant == REFERENCE:
        return text
    return text.replace(REFERENCE_CERTIFICATE, f"session-api-{tenant}-temporal-tls").replace(REFERENCE, tenant)


def _cleanup(tenant: str) -> str:
    # The reference's file was named before there was a second tenant, and three tests read it by that name.
    return "cleanup-reconciler.yaml" if tenant == REFERENCE else f"cleanup-reconciler-{tenant}.yaml"


def files(tenant: str) -> dict[Path, Path]:
    """The files that belong to `tenant` alone -> the reference's file each is written from."""
    return {
        WORKLOADS / f"session-runner-{tenant}.yaml": WORKLOADS / f"session-runner-{REFERENCE}.yaml",
        WORKLOADS / f"session-api-{tenant}.yaml": WORKLOADS / f"session-api-{REFERENCE}.yaml",
        WORKLOADS / _cleanup(tenant): WORKLOADS / _cleanup(REFERENCE),
        NETPOL / f"{tenant}.yaml": NETPOL / f"{REFERENCE}.yaml",
        layout.AGENTS_DIR / tenant / "registry-provisioner-rbac.yaml": layout.AGENTS_DIR / REFERENCE / "registry-provisioner-rbac.yaml",
        layout.AGENTS_DIR / tenant / "session-api-rbac.yaml": layout.AGENTS_DIR / REFERENCE / "session-api-rbac.yaml",
    }


def documents(tenant: str) -> list[tuple[Path, str, str]]:
    """The tenant's documents in files it shares with the platform: (file, kind, name)."""
    return [
        (RBAC, "ServiceAccount", f"session-api-{tenant}"),
        (MTLS, "Certificate", _sub(REFERENCE_CERTIFICATE, tenant)),
        (MTLS, "Job", f"temporal-namespace-agents-{tenant}-v1"),
    ]


def entries(tenant: str) -> list[tuple[Path, str]]:
    """Where the tenant is listed: (kustomization, entry)."""
    return [
        (WORKLOADS / "kustomization.yaml", f"session-runner-{tenant}.yaml"),
        (WORKLOADS / "kustomization.yaml", _cleanup(tenant)),
        (WORKLOADS / "kustomization.yaml", f"session-api-{tenant}.yaml"),
        (NETPOL / "kustomization.yaml", f"{tenant}.yaml"),
        (layout.AGENTS_DIR / "kustomization.yaml", f"{tenant}/registry-provisioner-rbac.yaml"),
        (layout.AGENTS_DIR / "kustomization.yaml", f"{tenant}/session-api-rbac.yaml"),
        (PLATFORM / "kustomization.yaml", payload_key(tenant).name),
    ]


def payload_key(tenant: str) -> Path:
    """The tenant's payload key: a SOPS file a person creates. This module looks only at whether it exists."""
    return PLATFORM / f"session-payload-key-{tenant}.enc.yaml"


def render(root: Path, tenant: str) -> dict[Path, str]:
    """The text of each file that belongs to `tenant` alone, from the reference's files as they are now."""
    out = {}
    for path, source in files(tenant).items():
        lines = _read(root, source).split("\n")
        while lines and lines[0].startswith("#"):  # the reference's heading comment describes the reference
            lines.pop(0)
        out[path] = HEADER.format(tenant=tenant, source=source) + _sub("\n".join(lines), tenant)
    return out


def _read(root: Path, path: Path) -> str:
    try:
        return (root / path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise TenantError(f"{path} is missing", "not-found") from None


def _parsed(text: str, path: Path) -> list:
    try:
        return [d for d in yaml.safe_load_all(text) if d is not None]
    except yaml.YAMLError as exc:
        raise TenantError(f"{path}: not valid YAML: {exc}") from None


def _chunks(text: str) -> list[str]:
    """The text between `---` lines; joined with "---\\n" they are the file again."""
    return re.split(r"(?m)^---\n", text)


def _chunk(text: str, kind: str, name: str, path: Path) -> int | None:
    """Which chunk holds the one document of that kind and name; None when there is none."""
    hits = []
    for i, chunk in enumerate(_chunks(text)):
        docs = _parsed(chunk, path)
        if len(docs) == 1 and isinstance(docs[0], dict) and docs[0].get("kind") == kind and (docs[0].get("metadata") or {}).get("name") == name:
            hits.append(i)
    if len(hits) > 1:
        raise TenantError(f"{path}: {kind} {name} is declared {len(hits)} times")
    return hits[0] if hits else None


def _reference_chunk(text: str, kind: str, name: str, path: Path) -> str:
    i = _chunk(text, kind, name, path)
    if i is None:
        raise TenantError(f"{path}: the reference's {kind} {name} is missing", "not-found")
    return _chunks(text)[i]


def _with_document(text: str, path: Path, tenant: str, reference: tuple[str, str], own: tuple[str, str]) -> str:
    """`text` with the tenant's copy of the reference's document: replaced where it is, else appended."""
    wanted = _sub(_reference_chunk(text, *reference, path), tenant).strip("\n") + "\n"
    chunks = _chunks(text)
    i = _chunk(text, *own, path)
    if i is None:
        return text.rstrip("\n") + "\n---\n" + wanted
    chunks[i] = wanted
    return "---\n".join(chunks)


def _sans(text: str) -> set[str]:
    """The tenants whose session interface the Temporal endpoint admits, read from the Envoy configuration itself."""
    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            exact = node.get("exact")
            if isinstance(exact, str) and exact.startswith(SAN):
                found.add(exact[len(SAN) :])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for doc in _parsed(text, MTLS):
        if isinstance(doc, dict) and (doc.get("kind"), (doc.get("metadata") or {}).get("name")) == ENVOY:
            for value in (doc.get("data") or {}).values():
                walk(yaml.safe_load(value))
    return found


def _with_san(text: str, tenant: str) -> str:
    """`text` with the tenant's session interface admitted, on the two lines after the reference's own."""
    if tenant in _sans(text):
        return text
    lines = text.split("\n")
    hits = [i for i, line in enumerate(lines) if line.strip() == "matcher: {exact: " + SAN + REFERENCE + "}"]
    if len(hits) != 1 or lines[hits[0] - 1].strip() != "- san_type: URI":
        raise TenantError(f"{MTLS}: expected the reference's session interface exactly once in the endpoint's allow-list")
    i = hits[0]
    lines[i + 1 : i + 1] = [lines[i - 1], lines[i].replace(SAN + REFERENCE, SAN + tenant)]
    return "\n".join(lines)


def _with_entry(text: str, path: Path, reference: str, entry: str) -> str:
    """`text` with `entry` listed on the line after the reference's entry."""
    lines = text.split("\n")
    if f"  - {entry}" in lines:
        return text
    hits = [i for i, line in enumerate(lines) if line == f"  - {reference}"]
    if len(hits) != 1:
        raise TenantError(f"{path}: expected exactly one line `  - {reference}`, found {len(hits)}")
    lines.insert(hits[0] + 1, f"  - {entry}")
    return "\n".join(lines)


def _with_namespace(text: str, tenant: str) -> str:
    labels = register.declared_tenants_in(text).get(REFERENCE, {}).get("labels")
    if not labels:
        raise TenantError(f"{register.NAMESPACES}: the reference's Namespace is missing", "not-found")
    shown = "\n".join(f"    {key}: {_sub(str(value), tenant)}" for key, value in labels.items())
    return text.rstrip("\n") + "\n" + NAMESPACE.format(tenant=tenant, labels=shown)


def planned(root: Path, tenant: str, *, new: bool) -> dict[Path, str]:
    """Every file of the repository that `tenant` changes -> its whole new text.

    With `new`, the Namespace and the kustomization entries are added too; without it only what follows the reference
    is rewritten, which is what `sync` does after the reference changed."""
    out = render(root, tenant)
    shared: dict[Path, str] = {}

    def text_of(path: Path) -> str:
        return shared[path] if path in shared else _read(root, path)

    for (path, kind, name), (_, _, reference) in zip(documents(tenant), documents(REFERENCE), strict=True):
        shared[path] = _with_document(text_of(path), path, tenant, (kind, reference), (kind, name))
    shared[MTLS] = _with_san(text_of(MTLS), tenant)
    if new:
        shared[register.NAMESPACES] = _with_namespace(text_of(register.NAMESPACES), tenant)
        for (path, entry), (_, reference) in zip(entries(tenant), entries(REFERENCE), strict=True):
            shared[path] = _with_entry(text_of(path), path, reference, entry)
    for path, text in shared.items():
        _parsed(text, path)
    return {**out, **shared}


def tenants(root: Path) -> list[str]:
    """Every tenant the repository names anywhere: a Namespace, a committed Agent, a signer pin or a file of its own."""
    names = set(register.declared_tenants(root)) | {d.tenant for d in layout.agent_dirs(root)} | set(register.pinned_tenants(root))
    for base, prefix, suffix in (
        (WORKLOADS, "session-runner-", ".yaml"),
        (WORKLOADS, "session-api-", ".yaml"),
        (WORKLOADS, "cleanup-reconciler-", ".yaml"),
        (NETPOL, "", ".yaml"),
        (PLATFORM, "session-payload-key-", ".enc.yaml"),
        (layout.AGENTS_DIR, "", ""),
    ):
        for path in (root / base).glob(f"{prefix}{PREFIX}*{suffix}"):
            names.add(path.name[len(prefix) : len(path.name) - len(suffix)])
    return sorted(names)


def problems(root: Path, tenant: str) -> list[str]:
    """What `tenant` is missing, and where one of its pieces differs from the reference's."""
    found: list[str] = []
    declared = register.declared_tenants(root)
    reference_labels = declared.get(REFERENCE, {}).get("labels") or {}
    meta = declared.get(tenant)
    if meta is None:
        found.append(f"{register.NAMESPACES}: no Namespace {tenant} with the label agentplatform.io/tenant")
    else:
        if meta.get("labels") != {key: _sub(str(value), tenant) for key, value in reference_labels.items()}:
            found.append(f"{register.NAMESPACES}: Namespace {tenant} does not carry the reference's labels")
        if not any(d.tenant == tenant for d in layout.agent_dirs(root)) and any(a in (meta.get("annotations") or {}) for a in SIGNER_ANNOTATIONS):
            found.append(f"{register.NAMESPACES}: Namespace {tenant} carries a signer pin and has no committed Agents")
    wanted = render(root, tenant) if tenant != REFERENCE else {}
    for path in files(tenant):
        if not (root / path).is_file():
            found.append(f"{path} is missing")
        elif path in wanted and _parsed(_read(root, path), path) != _parsed(wanted[path], path):
            found.append(f"{path} differs from the reference's; run `just agent tenant sync`")
    for (path, kind, name), (_, _, reference) in zip(documents(tenant), documents(REFERENCE), strict=True):
        text = _read(root, path)
        i = _chunk(text, kind, name, path)
        if i is None:
            found.append(f"{path}: no {kind} {name}")
        elif _parsed(_chunks(text)[i], path) != _parsed(_sub(_reference_chunk(text, kind, reference, path), tenant), path):
            found.append(f"{path}: {kind} {name} differs from the reference's; run `just agent tenant sync`")
    if tenant not in _sans(_read(root, MTLS)):
        found.append(f"{MTLS}: the Temporal endpoint does not admit {SAN}{tenant}")
    for path, entry in entries(tenant):
        listed = (_parsed(_read(root, path), path) or [{}])[0].get("resources") or []
        if entry not in listed:
            found.append(f"{path}: {entry} is not listed")
    if not (root / payload_key(tenant)).is_file():
        found.append(_no_key(tenant))
    return found


def _no_key(tenant: str) -> str:
    return f"{payload_key(tenant)} is missing; a person creates it (agent-operations.md, Tenants)"


def check(root: Path) -> dict:
    """Every tenant the repository names has every piece, each equal to the reference's apart from the name."""
    rows = []
    names = tenants(root)
    agents: dict[str, int] = {}
    for d in layout.agent_dirs(root):
        agents[d.tenant] = agents.get(d.tenant, 0) + 1
    for tenant in names:
        try:
            require_name(tenant)
            found = problems(root, tenant)
        except (TenantError, register.RegisterError, layout.LayoutError) as exc:
            found = [str(exc)]
        rows.append({"tenant": tenant, "agents": agents.get(tenant, 0), "state": "ok" if not found else "fail", "problems": found})
    strangers = sorted(_sans(_read(root, MTLS)) - set(names))
    if strangers:
        rows.append({"tenant": "*", "agents": 0, "state": "fail", "problems": [f"{MTLS}: the Temporal endpoint admits a session interface of no tenant: {', '.join(strangers)}"]})
    return {"ok": all(r["state"] == "ok" for r in rows), "reference": REFERENCE, "tenants": rows}


def _write(root: Path, texts: dict[Path, str]) -> tuple[dict[Path, bytes | None], list[str]]:
    before = {path: (root / path).read_bytes() if (root / path).is_file() else None for path in texts}
    changed = []
    for path, text in texts.items():
        if before[path] != text.encode("utf-8"):
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text(text, encoding="utf-8")
            changed.append(str(path))
    return before, sorted(changed)


def _restore(root: Path, before: dict[Path, bytes | None]) -> None:
    for path, content in before.items():
        if content is None:
            (root / path).unlink(missing_ok=True)
        else:
            (root / path).write_bytes(content)


def add(root: Path, tenant: str) -> dict:
    """Write every piece of a new, empty tenant. Nothing is kept unless `check` then finds only the payload key missing."""
    require_name(tenant)
    if tenant in tenants(root):
        raise TenantError(f"{tenant} already exists; `just agent tenant check` says what it is missing", "conflict")
    before, changed = _write(root, planned(root, tenant, new=True))
    made = root / layout.AGENTS_DIR / tenant
    try:
        left = [p for p in problems(root, tenant) if p != _no_key(tenant)]
    except BaseException:
        _restore(root, before)
        raise
    if left:
        _restore(root, before)
        if made.is_dir() and not any(made.iterdir()):
            made.rmdir()
        raise TenantError(f"nothing was kept: the written tenant would not pass the check: {'; '.join(left)}")
    key = payload_key(tenant)
    return {
        "tenant": tenant,
        "files": changed,
        "missing": [] if (root / key).is_file() else [str(key)],
        "next": [
            f"a person creates {key} (docs/infrastructure/configuration/agent-operations.md, Tenants); the build fails until it exists",
            "add the tenant's runner, session interface and cleanup reconciler to docs/infrastructure/cluster/capacity.md",
            "`just agent tenant check`, then commit as one pull request; applying it restarts the Temporal mTLS endpoint once",
            f"`just agent register {tenant} <owner/repo> <agent>...` adds the first agent and writes the tenant's signer pin",
        ],
    }


def sync(root: Path, tenant: str | None = None) -> dict:
    """Rewrite what follows the reference, for one tenant or for every tenant but the reference."""
    if tenant is not None:
        require_name(tenant)
        if tenant == REFERENCE or tenant not in tenants(root):
            raise TenantError(f"{tenant} is the reference itself or not a tenant here; `just agent tenant add` creates one", "not-found")
    changed: list[str] = []
    names = [tenant] if tenant else [t for t in tenants(root) if t != REFERENCE]
    for name in names:
        changed += _write(root, planned(root, name, new=False))[1]
    return {"tenants": names, "files": sorted(set(changed)), "next": "`just agent tenant check`, then commit"}
