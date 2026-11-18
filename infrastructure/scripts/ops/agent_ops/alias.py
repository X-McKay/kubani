"""Move a model alias: assess who depends on it, hold them, say the engine is serving, read the result.

`plan` asks the registry for an assessment of a candidate pair; `move` starts a move for an assessment; `status` reads moves;
`evaluate` says the engine is serving; `cancel` ends a move that has not moved yet. Writes are made as a signed-in person,
reads with the reader token. The registry decides everything and these commands only ask and print; none of them restarts an
engine. See platform/registry/contract/dependencies.md sections 5, 6 and 9 in the zetra repository.
"""

from __future__ import annotations

import json
import sys
import urllib.parse

import outcome

from . import registry_client

MIN_SECONDS, MAX_SECONDS = 60, 86400


def _list(value) -> list:
    return value if isinstance(value, list) else []


def _pair(pair) -> str:
    pair = pair if isinstance(pair, dict) else {}
    return f"{pair.get('engine')} / {pair.get('release')}"


def _met(need: dict) -> str:
    return {True: "met", False: "NOT MET"}.get(need.get("met"), "not recorded")


def _blockers(assessment: dict) -> list[str]:
    """Each need of an enabled dependant that the candidate does not meet."""
    return [f"{d.get('agent')} ({d.get('tenant')}) needs {n.get('need')}: the candidate does not offer it" for d in _list(assessment.get("dependants")) if isinstance(d, dict) and d.get("enabled") for n in _list(d.get("needs")) if isinstance(n, dict) and n.get("met") is False]


def format_assessment(a: dict) -> str:
    lines = [f"alias {a.get('alias')} on cluster {a.get('cluster')}", f"  now:       {_pair(a.get('from'))}", f"  candidate: {_pair(a.get('candidate'))}", "", "Dependants"]
    dependants = [d for d in _list(a.get("dependants")) if isinstance(d, dict)]
    for d in dependants:
        needs = ", ".join(f"{n.get('need')} {_met(n)}" for n in _list(d.get("needs"))) or "none"
        lines.append(
            f"  {d.get('agent')} ({d.get('tenant')})  authority {d.get('authority')}  {'enabled' if d.get('enabled') else 'disabled'}  release {d.get('release') or '-'}"
            f"  {'will be held' if d.get('held') else 'will not be held'}  evaluation {'will run' if d.get('evaluation') == 'required' else 'will not run'}  needs: {needs}"
        )
    if not dependants:
        lines.append("  none")
    loose = [d for d in dependants if not d.get("held")]
    if loose:
        lines += ["", "Not held (the pull request path): these agents' sessions use the new model with no hold and no evaluation; decide whether that is acceptable"]
        lines += [f"  {d.get('agent')} ({d.get('tenant')})" for d in loose]
    lines.append("")
    if a.get("blocked"):
        reasons = _blockers(a)
        lines.append("BLOCKED: " + ("; ".join(reasons) if reasons else "the registry marks this assessment blocked"))
    else:
        lines.append("not blocked")
    lines.append(f"assessment {a.get('id')}")
    if not a.get("blocked"):
        lines.append(f"next: just agent alias move {a.get('id')}")
    return "\n".join(lines)


def format_move(move: dict) -> str:
    candidate = move.get("candidate")
    lines = [f"move {move.get('id')}  alias {move.get('alias')}  state {move.get('state')}" + (f"  candidate {_pair(candidate)}" if isinstance(candidate, dict) else "")]
    if move.get("deadline"):
        lines.append(f"  deadline: {move['deadline']}")
    holds = [h for h in _list(move.get("holds")) if isinstance(h, dict)]
    for h in holds:
        running = h.get("running")
        lines.append(f"  hold {h.get('agent')}: {h.get('state')}  running sessions {'not reported' if running is None else running}" + (f"  reason: {h['reason']}" if h.get("reason") else ""))
    lines.append(f"  next: {move.get('next') or '-'}")
    return "\n".join(lines)


def format_moves(doc: dict) -> str:
    moves = [m for m in _list(doc.get("moves", doc.get("items"))) if isinstance(m, dict)]
    return "\n".join(format_move(m) for m in moves) if moves else "no open alias moves"


def _path(move: str) -> str:
    return "/v1/alias-moves/" + registry_client.segment(move)


def _show(doc: dict, text: str, as_json: bool) -> int:
    if as_json:
        print(json.dumps(outcome.document(doc), sort_keys=True, indent=2, allow_nan=False))
    else:
        print(text)
    return 0


def plan(cfg, client, args) -> int:
    body = {"cluster": cfg.cluster, "alias": args.alias, "candidate": {"engine": args.engine, "release": args.release}}
    doc = client.post("/v1/assessments", body)
    if not doc.get("blocked"):
        return _show(doc, format_assessment(doc), args.json)
    reasons = _blockers(doc)
    message = "the assessment is blocked: " + ("; ".join(reasons) if reasons else "the registry marks it blocked") + f"; assessment {doc.get('id')} cannot be moved"
    if not args.json:
        print(format_assessment(doc), file=sys.stderr)
    print(json.dumps(outcome.document(doc, outcome.error("refused", message)), sort_keys=True, indent=2, allow_nan=False))
    return 2


def move(cfg, client, args) -> int:
    body = {"assessment": args.assessment, "sessions": args.sessions}
    if args.evaluation_seconds is not None:
        body["evaluationSeconds"] = args.evaluation_seconds
    doc = client.post("/v1/alias-moves", body)
    return _show(doc, format_move(doc), args.json)


def status(cfg, client, args) -> int:
    if args.move and args.alias:
        raise registry_client.RegistryError("pass a move id or --alias, not both", "invalid-arguments")
    if args.move:
        doc = client.get(_path(args.move))
        return _show(doc, format_move(doc), args.json)
    query = {"cluster": cfg.cluster}
    if args.alias:
        query["alias"] = args.alias
    query["open"] = "true"
    doc = client.get("/v1/alias-moves?" + urllib.parse.urlencode(query))
    return _show(doc, format_moves(doc), args.json)


def evaluate(cfg, client, args) -> int:
    doc = client.post(_path(args.move) + "/evaluate", {})
    return _show(doc, format_move(doc), args.json)


def cancel(cfg, client, args) -> int:
    doc = client.post(_path(args.move) + "/cancel", {"reason": args.reason})
    return _show(doc, format_move(doc), args.json)


COMMANDS = {"plan": plan, "move": move, "status": status, "evaluate": evaluate, "cancel": cancel}


def run(args) -> int:
    """Run `just agent alias <action>`: reads as the reader, writes as the signed-in person. The registry's refusals are raised as RegistryError."""
    cfg = registry_client.settings()
    client = registry_client.read_client(cfg) if args.action == "status" else registry_client.write_client(cfg)
    return COMMANDS[args.action](cfg, client, args)
