"""Offline checks and optional bounded, read-only MCP registration evidence."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from types import SimpleNamespace

from mcp_registry import check as registry_check
from mcp_registry import identity, model, render, status

from . import live, source

NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?")
EXCLUSIONS = {
    "live_agent_identity": "Live agent identity is not inspected.",
    "human_authorization": "Human consent and on-behalf-of permissions are not checked.",
    "release_signatures": "AgentRelease signatures are not checked.",
    "five_attestations": "The five release attestations are not checked.",
    "approval_no_drift": "Approval and NoDrift are not checked.",
    "tool_behavior": "Actual tool behavior is not exercised.",
    "remaining_allowance": "Remaining ledger allowance is not queried; configured limits only.",
    "remote_freshness": "Remote freshness and an atomic checkout snapshot are not established.",
    "qualification": "General qualification and deployment readiness are not established.",
}


def services():
    return SimpleNamespace(
        model=model,
        check=registry_check,
        identity=identity,
        render=render,
        status=status,
        transports=live.transports,
    )


def _mapping(value):
    if not isinstance(value, dict):
        raise TypeError("expected mapping")
    return value


def semantics(doc):
    spec = _mapping(doc["spec"])
    ident = _mapping(spec["identity"])
    if set(ident) - {"mode", "onBehalfOf"}:
        raise ValueError("unknown identity semantics")
    mode = ident.get("mode")
    if mode not in ("agent", "on-behalf-of"):
        raise ValueError("unsupported identity mode")
    obo = _mapping(ident.get("onBehalfOf", {}))
    if set(obo) - {"required", "fallback"}:
        raise ValueError("unknown on-behalf-of semantics")
    required, fallback = obo.get("required", True), obo.get("fallback", "deny")
    enabled, owner = spec.get("enabled", True), spec.get("owner")
    if (
        type(required) is not bool
        or type(enabled) is not bool
        or fallback not in ("deny", "agent")
        or not isinstance(owner, str)
        or not owner
    ):
        raise ValueError("invalid identity, owner or enabled type")
    return {
        "identity": {"mode": mode, "required": required, "fallback": fallback},
        "owner": owner,
        "enabled": enabled,
    }


def run(
    root: Path,
    source_root: Path,
    agent: str,
    tag: str,
    *,
    live_scope=False,
    source_check=source.check,
    registry=None,
):
    registry = registry or services()
    root, source_root = root.resolve(), source_root.resolve()
    result = {
        "schemaVersion": 1,
        "agent": agent,
        "tag": tag,
        "scope": "live-registration" if live_scope else "offline-compatibility",
        "ok": False,
        "source": None,
        "checks": [],
        "evidence": {
            "files": [],
            "coverage": "Local input hashes only; no remote freshness or atomic snapshot proof.",
        },
    }

    def add(
        code, state, explanation, remediation, *, backend=None, required=True, **extra
    ):
        item = {
            "code": code,
            "state": state,
            "required": required,
            "agent": agent,
            "backend": backend,
            "explanation": explanation[:1000],
            "remediation": remediation[:1000],
        }
        item.update(extra)
        result["checks"].append(item)

    def record(path):
        # Hash ciphertext when it is an input; never decrypt/read Secret values.
        raw = path.read_bytes()
        result["evidence"]["files"].append(
            {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}
        )
        return raw

    def load_agent(path):
        raw = record(path)
        if len(raw) > 1024 * 1024:
            raise ValueError("Agent input exceeds bound")
        # Existing strict loader rejects duplicates; merge keys are refused too.
        if b"<<:" in raw:
            raise ValueError("YAML merge keys unsupported")
        docs = model.yaml_documents(path)
        found = [d for d in docs if isinstance(d, dict) and d.get("kind") == "Agent"]
        if len(found) != 1 or len(docs) != 1:
            raise ValueError("one Agent required")
        return found[0]

    for code, explanation in EXCLUSIONS.items():
        add(
            code,
            "not_checked",
            explanation,
            "Use the existing release, authorization and qualification gates for this claim.",
            required=False,
        )
    if not isinstance(agent, str) or not NAME.fullmatch(agent):
        add(
            "agent_input",
            "fail",
            "Agent must be a DNS label of at most 32 characters.",
            "Select an existing source agent name.",
        )
        return result
    try:
        result["source"] = source_check(source_root, root, agent, tag)
        add(
            "source_compatibility",
            "pass" if result["source"]["ok"] else "fail",
            "Existing source preflight checked capabilities, configured budget reservation, signer and checkout provenance.",
            "Resolve the bounded source receipt errors and rerun with a clean source and unused prospective tag.",
        )
    except source.SourceEnvironmentError as exc:
        add(
            "source_compatibility",
            "unavailable",
            f"{exc}",
            "Run `uv sync --locked` in the source checkout, then rerun the preflight.",
        )
    except Exception:  # noqa: BLE001 - sanitize credential/process-bearing exceptions
        add(
            "source_compatibility",
            "unavailable",
            "The source checker failed, timed out or returned an invalid bounded receipt "
            "(its own output is discarded).",
            "In the source checkout run `uv sync --locked`, then `uv run --locked zetra-agents "
            "preflight AGENT --tag TAG --kubani KUBANI` to see its diagnostics, and retry.",
        )
    candidate = None
    candidate_semantics = None
    try:
        original = load_agent(source_root / "agents" / agent / "deploy/agent.yaml")
        metadata = _mapping(original["metadata"])
        namespace = metadata.get("namespace")
        if (
            metadata.get("name") != agent
            or not isinstance(namespace, str)
            or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", namespace)
        ):
            raise ValueError("invalid source Agent identity")
        path = model.safe_path(
            root, f"infrastructure/gitops/apps/agents/{namespace}/{agent}/agent.yaml"
        )
        candidate = load_agent(path)
        if (
            candidate.get("metadata", {}).get("name") != agent
            or candidate["metadata"].get("namespace") != namespace
        ):
            raise ValueError("candidate Agent identity mismatch")
        left, candidate_semantics = semantics(original), semantics(candidate)
        differences = [key for key in left if left[key] != candidate_semantics[key]]
        add(
            "agent_semantics",
            "fail" if differences else "pass",
            "Source/candidate identity, owner and enabled semantics "
            + (
                "differ: " + ", ".join(differences)
                if differences
                else "match (CRD defaults applied)."
            ),
            "Review and align source and candidate Agent identity, owner and enabled fields.",
        )
    except Exception:  # noqa: BLE001 - sanitize credential/process-bearing exceptions
        add(
            "agent_semantics",
            "fail",
            "Cannot validate source/candidate Agent identity, owner and enabled semantics.",
            "Provide one correctly named Agent in the source and candidate with supported typed identity, owner and enabled fields.",
        )
    grants = None
    try:
        grants = _mapping(_mapping(candidate)["spec"])["capabilities"].get("mcp", [])
        if not isinstance(grants, list) or len(grants) > 128:
            raise ValueError("invalid MCP grants")
    except Exception:  # noqa: BLE001 - sanitize credential/process-bearing exceptions
        add(
            "mcp_dependencies",
            "unavailable",
            "Candidate MCP dependencies cannot be read.",
            "Correct the candidate Agent capabilities mapping and MCP list.",
        )
    if grants == []:
        add(
            "mcp_dependencies",
            "not_applicable",
            "Agent has no MCP grants.",
            "No MCP registration action required.",
        )
        add(
            "registry_validation",
            "not_applicable",
            "No registry dependency gate applies.",
            "No MCP registration action required.",
        )
        if live_scope:
            add(
                "live_registration",
                "not_applicable",
                "Agent has no MCP dependencies to inspect.",
                "No live MCP action required.",
            )
    elif grants:
        entries = {}
        registry_valid = False
        registry_loaded = False
        try:
            entries = {e["name"]: e for e in registry.model.load_registry(root)}
            registry_loaded = True
            findings = registry.check.check(root)
            # Existing checker can include kubectl's raw stderr. Do not echo it.
            safe = [
                "registry validation failed: Kustomize build failed; inspect the build locally"
                if "Kustomize failed" in v
                else v[:1000]
                for v in findings
            ]
            registry_valid = not findings
            add(
                "registry_validation",
                "pass" if registry_valid else "fail",
                "Full existing offline registry validation "
                + ("passed." if registry_valid else "failed."),
                "Run just mcp-check and resolve the registry findings.",
                findings=safe,
            )
            # Include all registry/generated inputs and shared identity inputs, even
            # when their validation reports stale output. Hashes are local evidence.
            paths = set((root / model.BASE).rglob("*"))
            for entry in entries.values():
                paths.update(model.safe_path(root, p) for p in entry["secrets"])
                if "bootstrap" in entry:
                    paths.update(
                        model.safe_path(root, entry["bootstrap"][k])
                        for k in ("manifest", "sql")
                    )
            for base in (
                "infrastructure/gitops/apps/agent-platform",
                "infrastructure/gitops/apps/ai-gateway",
                "infrastructure/gitops/apps/mcp",
                "infrastructure/gitops/infrastructure/networking",
            ):
                paths.update((root / base).rglob("*.yaml"))
            for path in sorted(paths):
                if path.is_file() and not path.is_symlink():
                    record(path)
        except Exception:  # noqa: BLE001 - sanitize credential/process-bearing exceptions
            add(
                "registry_validation",
                "unavailable",
                "Cannot load or validate registered MCP dependencies.",
                "Run just mcp-check and correct the registry inputs and local build tooling.",
            )
        dependencies = set()
        for grant in grants:
            backend = None
            try:
                grant = _mapping(grant)
                backend = grant.get("backend")
                if not isinstance(backend, str) or not re.fullmatch(
                    r"[a-z0-9-]{1,63}", backend
                ):
                    raise ValueError("invalid backend")
                if backend in dependencies:
                    raise ValueError("duplicate MCP backend")
                dependencies.add(backend)
                tools = grant.get("tools")
                delegation = grant.get("delegation", "inherit")
                if (
                    grant.get("effect") != "remote_read"
                    or delegation not in ("inherit", "agent", "on-behalf-of")
                    or not isinstance(tools, list)
                    or not tools
                    or any(
                        not isinstance(t, str)
                        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", t)
                        for t in tools
                    )
                ):
                    raise ValueError("unsupported grant")
                if delegation == "inherit" and candidate_semantics is None:
                    raise ValueError("unresolved delegation")
                if not registry_loaded:
                    add(
                        "mcp_grant",
                        "unavailable",
                        "Registry input is unavailable; backend authorization cannot be resolved.",
                        "Correct registry input and rerun the dependency check.",
                        backend=backend,
                    )
                    continue
                if backend not in entries:
                    add(
                        "legacy_backend_not_checked",
                        "not_checked",
                        "Backend is unresolved by the registry and may be handwritten legacy configuration.",
                        "Obtain a supported reviewed adapter for this backend or migrate its registration.",
                        backend=backend,
                    )
                    continue
                entry = entries[backend]
                registry.identity.validate_descriptor(registry.model.descriptor(entry))
                if not set(tools) <= set(entry["authorization"]["tools"]):
                    raise ValueError("tools exceed registered authorization")
                add(
                    "mcp_grant",
                    "pass",
                    "Exact descriptor, granted tools, remote_read effect and supported delegation validated.",
                    "Keep grants within the reviewed backend authorization.",
                    backend=backend,
                )
            except Exception:  # noqa: BLE001 - sanitize credential/process-bearing exceptions
                add(
                    "mcp_grant",
                    "fail",
                    "MCP grant has invalid tools, effect, delegation, descriptor or duplicate backend.",
                    "Use registered authorized tools, remote_read effect and inherit/agent/on-behalf-of delegation; remove duplicate backends.",
                    backend=backend
                    if isinstance(backend, str) and NAME.fullmatch(backend)
                    else None,
                )
        if live_scope:
            selected = sorted(dependencies & entries.keys())
            if selected and registry_valid:
                try:
                    reader, api = registry.transports(registry.identity)
                except Exception:  # noqa: BLE001 - sanitize credential/process-bearing exceptions
                    reader = api = None
                for backend in selected:
                    try:
                        if reader is None:
                            raise ValueError("live authentication unavailable")
                        evidence = registry.status.inspect_registration(
                            registry.render.objects(root, backend),
                            registry.model.descriptor(entries[backend]),
                            read_object=reader,
                            api=live.GetOnly(api),
                        )
                        add(
                            "live_registration",
                            "pass" if evidence["complete"] else "unavailable",
                            "Read-only registration evidence "
                            + (
                                "is complete."
                                if evidence["complete"]
                                else "is incomplete or conflicting."
                            ),
                            "Restore read access and reconcile registration through the existing reviewed workflows, then retry.",
                            backend=backend,
                            evidence=evidence,
                        )
                    except Exception:  # noqa: BLE001 - sanitize credential/process-bearing exceptions
                        add(
                            "live_registration",
                            "unavailable",
                            "Read-only registration evidence is unavailable.",
                            "Check operator SOPS authentication, Kubernetes read access and local tooling; no privilege change is attempted.",
                            backend=backend,
                        )
            elif selected:
                add(
                    "live_registration",
                    "unavailable",
                    "Offline registration validation must pass before live inspection.",
                    "Resolve registry validation first.",
                )
        else:
            add(
                "live_registration",
                "not_checked",
                "Live MCP registration was not requested; no live transport initialized.",
                "Add --live for optional read-only registration evidence.",
                required=False,
            )
    result["evidence"]["files"] = sorted(
        {v["path"]: v for v in result["evidence"]["files"]}.values(),
        key=lambda v: v["path"],
    )
    result["ok"] = not any(
        c["required"] and c["state"] in ("fail", "not_checked", "unavailable")
        for c in result["checks"]
    )
    return result
