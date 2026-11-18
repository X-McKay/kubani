#!/usr/bin/env python3
"""The dependency gate for pull requests: does a change to a tool server's contract or to an alias break a running agent?

Run from the base checkout (the reviewed branch) with `--base-root` and `--head-root`. Both roots are rendered with the
`registry_feed` module this file sits beside, which only reads them as data (`yaml.safe_load`, paths kept inside the root);
nothing under the head root is imported, executed or evaluated. Changed contracts go to `/v1/checks/tool-contract` and
changed alias pairs to `/v1/checks/alias` (delivery contract 3.3 and 8). The gate never passes because it could not ask.
Run with: uv run --locked python infrastructure/scripts/ops/dependency_gate.py --base-root DIR --head-root DIR

The run can be split between a machine that may read the pull request and a machine that may reach the registry:
`--offline --feeds-out DIR` compares the two roots, writes the two rendered feeds as `base.json` and `head.json`, asks
nothing and exits 3 when there is a question for the registry; `--base-feed FILE --head-feed FILE` then makes the same
comparison from those two files, which are read as JSON and nothing else, and asks. Exit 0 passed, 1 failed, 3 not decided.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import outcome  # noqa: E402
import registry_feed  # noqa: E402
from agent_ops import registry_client  # noqa: E402

NOT_COVERED = "this check does not cover removals"
UNDECIDED = 3  # the exit status of an --offline run that has a question for the registry and no failure of its own
FEED_FILES = ("base.json", "head.json")
# What this gate reads of a feed: per list, the keys that must be non-empty text and the keys that are text when present.
SHAPE = {"clusters": (("name",), ()), "toolServers": (("name",), ("cluster",)), "modelEngines": (("name",), ("cluster", "release", "servedName")), "aliases": (("alias", "engine"), ("cluster", "move"))}


def release_slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-.")[:128] or "unnamed"


def _selected(feed: dict, cluster: str | None) -> str:
    names = [c.get("name") for c in feed.get("clusters") or [] if isinstance(c, dict)]
    if cluster is None:
        if len(names) != 1:
            raise outcome.Coded(f"the feed names {len(names)} clusters; pass --cluster", "invalid-arguments")
        return names[0]
    if cluster not in names:
        raise outcome.Coded(f"the feed has no cluster {cluster!r}", "invalid-arguments")
    return cluster


def _tools(feed: dict, cluster: str) -> dict[str, dict]:
    return {t["name"]: t for t in feed.get("toolServers") or [] if t.get("cluster", cluster) == cluster}


def _pairs(feed: dict, cluster: str) -> dict[str, dict]:
    """Each alias of the cluster as {engine, release, move}; the release is the engine's, or the slug of its served name."""
    engines = {e["name"]: e for e in feed.get("modelEngines") or [] if e.get("cluster", cluster) == cluster}
    out = {}
    for alias in feed.get("aliases") or []:
        if alias.get("cluster", cluster) != cluster:
            continue
        engine = engines.get(alias["engine"]) or {}
        release = engine.get("release") or release_slug(engine.get("servedName") or "")
        out[alias["alias"]] = {"engine": alias["engine"], "release": release, "move": alias.get("move")}
    return out


def _render(render, root: Path, failure: str):
    try:
        return render(root)
    except outcome.Coded as exc:
        raise outcome.Coded(str(exc), failure) from None
    except (ValueError, KeyError, TypeError, OSError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else f"a file could not be read or was not shaped as expected ({type(exc).__name__})"
        raise outcome.Coded(message or type(exc).__name__, failure) from None


def _shaped(feed, failure: str) -> dict:
    """The feed, when it is shaped as the renderer writes it as far as this gate reads it. A file handed from one job to
    the next is checked the same way as a feed rendered here."""
    if not isinstance(feed, dict):
        raise outcome.Coded("a feed is not a JSON object", failure)
    for key, (required, optional) in SHAPE.items():
        entries = feed.get(key) or []
        good = isinstance(entries, list) and all(
            isinstance(e, dict) and all(isinstance(e.get(k), str) and e[k] for k in required) and all(isinstance(e.get(k, ""), str) for k in optional) for e in entries
        )
        if not good:
            raise outcome.Coded(f"the feed's {key} are not shaped as the renderer writes them", failure)
    return feed


def _load(path: Path, failure: str) -> dict:
    try:
        return _shaped(json.loads(Path(path).read_text(encoding="utf-8")), failure)
    except (OSError, ValueError) as exc:
        raise outcome.Coded(f"the feed file {Path(path).name} could not be read as JSON ({type(exc).__name__})", failure) from None


def rendered(base_root, head_root, render=registry_feed.render) -> tuple[dict, dict]:
    """The two feeds, rendered: `failed` when the base does not render, `check-failed` when the head does not."""
    return _shaped(_render(render, Path(base_root), "failed"), "failed"), _shaped(_render(render, Path(head_root), "check-failed"), "check-failed")


def loaded(base_file, head_file) -> tuple[dict, dict]:
    """The two feeds, read from the files an earlier `--feeds-out` wrote."""
    return _load(base_file, "failed"), _load(head_file, "check-failed")


def write_feeds(directory: Path, base: dict, head: dict) -> None:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        for name, feed in zip(FEED_FILES, (base, head), strict=True):
            (directory / name).write_text(json.dumps(feed, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        raise outcome.Coded(f"the rendered feeds could not be written ({type(exc).__name__})", "failed") from None


def _who(entry) -> str:
    if isinstance(entry, dict):
        agent, tenant = entry.get("agent"), entry.get("tenant")
        return f"{agent} ({tenant})" if agent and tenant else str(entry.get("deployment") or agent or entry)
    return str(entry)


def compare(base: dict, head: dict, cluster, client_factory, *, offline: bool = False) -> dict:
    """The gate's result as a document. `client_factory` is called only when the registry has to be asked, and never when
    `offline`: each question is then listed under `unasked` instead, and the result is not a verdict.

    Raises outcome.Coded for a cluster that cannot be chosen and for anything the registry's client raises: those end the
    run without a verdict, as does a feed that does not render or cannot be read.
    """
    name = _selected(head, cluster)
    if name not in [c.get("name") for c in base.get("clusters") or []]:
        raise outcome.Coded(f"the base feed has no cluster {name!r}", "failed")
    result = {"cluster": name, "toolContracts": [], "aliases": [], "removedContracts": [], "notes": [], "failures": [], "reevaluated": [], "unasked": []}
    client = None

    def ask(path: str, body: dict, about: str) -> dict | None:
        nonlocal client
        if offline:
            result["unasked"].append({"path": path, "about": about})
            return None
        if client is None:
            client = client_factory()
        answer = client.post(path, body)
        if not isinstance(answer, dict):
            raise outcome.Coded("the registry answered with something other than a document", "failed")
        return answer

    base_tools, head_tools = _tools(base, name), _tools(head, name)
    for server, tool in head_tools.items():
        contract, before = tool.get("contract"), (base_tools.get(server) or {}).get("contract")
        if contract is None:
            if before is not None:
                result["removedContracts"].append(server)
                result["failures"].append({"kind": "contract-removed", "server": server, "message": f"the recorded contract of {server} was removed"})
            continue
        if contract == before:
            continue
        answer = ask("/v1/checks/tool-contract", {"cluster": name, "server": server, "contract": contract}, f"contract of {server}")
        if answer is None:
            continue
        findings = [f for f in answer.get("findings") or [] if isinstance(f, dict)]
        reevaluated = list(answer.get("reevaluated") or [])
        blocked = answer.get("blocked") is not False
        result["toolContracts"].append({"server": server, "blocked": blocked, "findings": findings, "reevaluated": reevaluated, "users": answer.get("users")})
        result["reevaluated"] += [r for r in reevaluated if r not in result["reevaluated"]]
        if blocked:
            result["failures"].append({"kind": "contract-blocked", "server": server, "message": f"the change to the contract of {server} breaks an agent that uses it"})
    for server in sorted(set(base_tools) - set(head_tools)):
        result["notes"].append(f"tool server {server} is only in the base; {NOT_COVERED}")

    before_pairs, after_pairs = _pairs(base, name), _pairs(head, name)
    for alias, after in after_pairs.items():
        before = before_pairs.get(alias)
        if before is None or (before["engine"], before["release"]) == (after["engine"], after["release"]):
            continue
        candidate = {"engine": after["engine"], "release": after["release"]}
        pair = f"{before['engine']}/{before['release']} -> {after['engine']}/{after['release']}"
        answer = ask("/v1/checks/alias", {"cluster": name, "alias": alias, "candidate": candidate}, f"alias {alias}: {pair}")
        if answer is None:
            continue
        allowed = answer.get("allowed") is True
        reason = answer.get("reason") if isinstance(answer.get("reason"), str) else ""
        result["aliases"].append({"alias": alias, "from": {"engine": before["engine"], "release": before["release"]}, "to": candidate, "move": after["move"], "allowed": allowed, "reason": reason})
        if not allowed:
            result["failures"].append({"kind": "alias-not-allowed", "alias": alias, "message": f"the move of alias {alias} is not allowed" + (f": {reason}" if reason else "")})
    for alias in sorted(set(before_pairs) - set(after_pairs)):
        result["notes"].append(f"alias {alias} is only in the base; {NOT_COVERED}")
    return result


def lines(result: dict) -> list[str]:
    out = [f"cluster {result['cluster']}"]
    for check in result["toolContracts"]:
        blocking = [f for f in check["findings"] if f.get("blocks")]
        if check["blocked"]:
            out.append(f"BLOCKED  contract of {check['server']}")
        for f in blocking:
            out.append(f"  {f.get('agent')} ({f.get('tenant')}) uses {f.get('tool')}: {f.get('finding')}; {f.get('action')}")
        if check["blocked"] and not blocking:
            out.append("  the registry blocked the change without a finding")
        if not check["blocked"]:
            out.append(f"ok       contract of {check['server']} ({check.get('users')} users, {len(check['findings'])} findings, none blocking)")
        if check["reevaluated"]:
            out.append("  re-evaluated: " + ", ".join(_who(r) for r in check["reevaluated"]))
    for server in result["removedContracts"]:
        out.append(f"BLOCKED  the recorded contract of {server} was removed")
    for a in result["aliases"]:
        pair = f"{a['from']['engine']}/{a['from']['release']} -> {a['to']['engine']}/{a['to']['release']}"
        move = f" (move {a['move']})" if a["move"] else ""
        if a["allowed"]:
            out.append(f"ok       alias {a['alias']}: {pair}{move}")
        else:
            out.append(f"BLOCKED  alias {a['alias']}: {pair}{move}: {a['reason'] or 'the registry gave no reason'}")
    out += [f"to ask   {u['about']}" for u in result["unasked"]]
    out += [f"note     {n}" for n in result["notes"]]
    if not (result["toolContracts"] or result["removedContracts"] or result["aliases"] or result["unasked"]):
        out.append("nothing to check: no contract or alias changed; the registry was not asked")
    if result["failures"]:
        out.append(f"gate failed: {len(result['failures'])} check(s)")
    else:
        out.append(undecided(result) or "gate passed")
    return out


def undecided(result: dict) -> str:
    count = len(result["unasked"])
    return f"not decided: {count} question(s) for the registry were not asked" if count else ""


def document(result: dict) -> dict:
    if not result["failures"]:
        return outcome.document(result, outcome.error("failed", undecided(result))) if result["unasked"] else outcome.document(result)
    return outcome.document(result, outcome.error("check-failed", "; ".join(f["message"] for f in result["failures"]), proofs=result["failures"]))


def parser() -> argparse.ArgumentParser:
    result = registry_feed.Parser(description=__doc__)
    result.add_argument("--base-root", type=Path, help="the checkout before the change")
    result.add_argument("--head-root", type=Path, help="the checkout with the change; read as data only")
    result.add_argument("--base-feed", type=Path, help="base.json of an earlier --feeds-out, instead of --base-root")
    result.add_argument("--head-feed", type=Path, help="head.json of an earlier --feeds-out, instead of --head-root")
    result.add_argument("--feeds-out", type=Path, metavar="DIR", help="write the two rendered feeds here as base.json and head.json")
    result.add_argument("--offline", action="store_true", help="ask the registry nothing; list the questions and exit 3 when there are any")
    result.add_argument("--cluster")
    result.add_argument("--json", action="store_true")
    return result


def main(argv=None, client_factory=None, render=registry_feed.render) -> int:
    cli = parser()
    args = cli.parse_args(argv)
    roots, files = (args.base_root, args.head_root), (args.base_feed, args.head_feed)
    if [x is not None for x in (*roots, *files)] not in ([True, True, False, False], [False, False, True, True]):
        cli.error("give --base-root with --head-root, or --base-feed with --head-feed")
    if args.feeds_out is not None and args.base_root is None:
        cli.error("--feeds-out goes with --base-root and --head-root")
    factory = client_factory or (lambda: registry_client.read_client(registry_client.settings()))
    try:
        base, head = rendered(*roots, render) if args.base_root is not None else loaded(*files)
        if args.feeds_out is not None:
            write_feeds(args.feeds_out, base, head)
        result = compare(base, head, args.cluster, factory, offline=args.offline)
    except outcome.Coded as exc:
        if args.json:
            message = str(exc) or exc.code
            print(json.dumps(outcome.document({}, outcome.error(exc.code, message, proofs=[{"message": message}] if exc.code == "check-failed" else None)), sort_keys=True))
        else:
            print(f"gate failed ({exc.code}): {exc}")
        return 1
    if args.json:
        print(json.dumps(document(result), sort_keys=True))
    else:
        print("\n".join(lines(result)))
    return 1 if result["failures"] else UNDECIDED if result["unasked"] else 0


if __name__ == "__main__":
    sys.exit(main())
