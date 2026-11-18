"""Hand an agent's authority between the pull request path and the registry.

Flux deletes (prunes) objects whose files leave its tree unless they carry `kustomize.toolkit.fluxcd.io/prune: disabled`.
So `take` refuses until that annotation is in git and, while the directory is still listed, live on every object of the
agent; only then does it ask the registry and take the directory out of `apps/agents/kustomization.yaml`. `return` writes
back what the registry holds, so git can own the agent again.
"""

from __future__ import annotations

from pathlib import Path

import yaml

import outcome

from . import layout, live, registry_client, stage

PRUNE = "kustomize.toolkit.fluxcd.io/prune"
LIST_FILE = str(layout.AGENTS_LIST)
HEADER = ("# yamllint disable rule:line-length", "# Written by `just agent authority return` from the registry's record of this release.")


class AuthorityError(outcome.Coded):
    default_code = "refused"


def _annotation(doc: dict | None) -> object:
    meta = (doc or {}).get("metadata") or {}
    return (meta.get("annotations") or {}).get(PRUNE)


def _rel(root: Path, path: Path) -> str:
    return str(path.relative_to(root))


def take(root: Path, agent: str, *, kube: live.Kube | None = None) -> dict:
    d = layout.find_agent(root, agent)
    if (layout.load_one_plain(d.kustomization).get("commonAnnotations") or {}).get(PRUNE) != "disabled":
        raise AuthorityError(f"{_rel(root, d.kustomization)} does not carry the commonAnnotations entry {PRUNE}: disabled; merge the pull request that adds it and let Flux apply it first, or Flux deletes the agent's objects when its directory leaves the list")
    listed = layout.is_listed(root, d)
    if listed:
        kube = kube or live.Kube()
        objects = [("Agent " + agent, kube.get("agents", agent, d.tenant))]
        releases = kube.get("agentreleases", None, d.tenant).get("items", [])
        objects += [("AgentRelease " + r["metadata"]["name"], r) for r in releases if (r.get("spec") or {}).get("agent") == agent]
        bare = [name for name, obj in objects if _annotation(obj) != "disabled"]
        if bare:
            raise AuthorityError(f"these live objects do not yet carry {PRUNE}: disabled, so removing the directory from the list would delete them: {', '.join(bare)}; let Flux apply the annotation pull request first")
    cfg = registry_client.settings()
    client = registry_client.Client(cfg, registry_client.person_token())
    answer = client.post(registry_client.deployment_path(cfg, d.tenant, agent) + "/authority/take", {})
    files = []
    if listed:
        layout.unlist(root, d)
        files.append(LIST_FILE)
    return {
        "agent": agent,
        "deployment": registry_client.deployment_id(cfg, d.tenant, agent),
        "authority": "registry",
        "changed": answer.get("changed") is True,
        "files": files,
        "next": "commit and open a pull request; the provisioner starts writing when Flux no longer lists the objects" if files else "the directory was not listed, so no file changed; `just agent status` shows the result",
    }


def render_release(doc: dict) -> str:
    lines = list(HEADER)
    for line in yaml.safe_dump(doc, sort_keys=False).rstrip("\n").split("\n"):
        if line.startswith("  ") and line.strip().split(":", 1)[0] in stage.PINNED:
            line += stage.PRAGMA
        lines.append(line)
    text = "\n".join(lines) + "\n"
    if yaml.safe_load(text) != doc:
        raise AuthorityError("a release from the registry does not parse back to the document received; nothing was written", "validation-failed")
    return text


def _differing(returned: dict, applied: dict) -> list[str]:
    """Where the registry's Agent and the committed one differ: `spec.<key>` for the spec, the top-level key otherwise."""
    found = [key for key in sorted(set(returned) | set(applied)) if key != "spec" and returned.get(key) != applied.get(key)]
    ours, theirs = applied.get("spec") or {}, returned.get("spec")
    if not isinstance(theirs, dict):
        return [*found, "spec"]
    return found + [f"spec.{key}" for key in sorted(set(ours) | set(theirs)) if ours.get(key) != theirs.get(key)]


def give_back(root: Path, agent: str) -> dict:
    d = layout.find_agent(root, agent)
    cfg = registry_client.settings()
    client = registry_client.Client(cfg, registry_client.person_token())
    answer = client.post(registry_client.deployment_path(cfg, d.tenant, agent) + "/authority/return", {})
    documents = answer.get("agentReleases")
    if not isinstance(documents, list) or not all(isinstance(x, dict) for x in documents):
        raise registry_client.RegistryError("the registry's answer did not carry agentReleases")
    committed = {layout.load_one(f, "AgentRelease")["metadata"].get("name"): (f, layout.load_one(f, "AgentRelease")) for f in d.release_files()}
    writes: list[tuple[Path, str]] = []
    added: list[str] = []
    for doc in documents:
        name = (doc.get("metadata") or {}).get("name")
        if not isinstance(name, str) or not name:
            raise AuthorityError("a release from the registry has no name; nothing was written", "validation-failed")
        if name in committed:
            file, existing = committed[name]
            if existing != doc:
                writes.append((file, render_release(doc)))
            continue
        file_name = f"agentrelease-{name.removeprefix(agent + '-')}.yaml"
        target = d.path / file_name
        if target.exists() or file_name in layout.kustomization_resources(d):
            raise AuthorityError(f"{_rel(root, target)} already exists but does not hold {name}; nothing was written", "conflict")
        writes.append((target, render_release(doc)))
        added.append(file_name)
    returned = answer.get("agent")
    if not isinstance(returned, dict):
        raise registry_client.RegistryError("the registry's answer did not carry the agent")
    # The registry keeps the Agent as the cluster holds it, with the definition's defaults filled in; agent.yaml leaves them out.
    applied = layout.applied_agent(root, d)
    same = returned == applied
    differing = _differing(returned, applied)
    if added:
        layout.listed_resources(d.kustomization)  # refuses a kustomization a new entry cannot be appended to, before any file is written
    files = []
    for file, text in writes:
        file.write_text(text, encoding="utf-8")
        files.append(_rel(root, file))
    for file_name in added:
        layout.append_resource(d, file_name)
    if added:
        files.append(_rel(root, d.kustomization))
    if same and not layout.is_listed(root, d):
        layout.relist(root, d)
        files.append(LIST_FILE)
    if same:
        follow = "commit and open a pull request; Flux owns the agent again once it is merged" if files else "nothing to commit; the pull request path already owns this agent"
    else:
        follow = f"the registry's Agent differs from agent.yaml in {', '.join(differing)}, so the directory stays unlisted: listing it would put agent.yaml back on the cluster. "
        if "spec.enabled" in differing:
            follow += f"The registry holds `enabled: {str(returned['spec'].get('enabled')).lower()}`; set that in the source repository's deploy/agent.yaml first. "
        follow += f"Bring agent.yaml to the released one with `just agent sync {agent} --source <checkout>`, then run `just agent authority return {agent}` again"
    return {
        "agent": agent,
        "deployment": registry_client.deployment_id(cfg, d.tenant, agent),
        "authority": "pull-request",
        "changed": answer.get("changed") is True,
        "files": files,
        "agentInGit": "same" if same else "differs",
        "agentDiffers": differing,
        "listed": layout.is_listed(root, d),
        "next": follow,
    }
