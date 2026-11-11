#!/usr/bin/env python3
"""Operate Kubani-applied agents: state, ls, run, status/wait/cancel, consent, register, sync, check-sync, stage, approve."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from agent_ops import approve, delegation, layout, live, register, run, stage, state, sync

ERRORS = (
    layout.LayoutError,
    live.LiveError,
    run.RunError,
    delegation.ConsentError,
    register.RegisterError,
    sync.SyncError,
    stage.StageError,
    approve.ApproveError,
)

# Subcommands that print exactly one JSON document on stdout however they end, once their arguments have parsed.
ONE_DOCUMENT = ("run", "consent")


def emit(payload) -> None:
    print(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False))


def positive_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number") from None
    if not 0 < value < float("inf"):
        raise argparse.ArgumentTypeError(f"must be above 0, not {text}")
    return value


def positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, not {text}")
    return value


def parse_task(args) -> object:
    given = [x for x in (args.task, args.task_json, args.task_file) if x is not None]
    if len(given) != 1:
        raise run.RunError("pass exactly one of --task, --task-json or --task-file")
    if args.task is not None:
        return {"request": args.task}
    raw = args.task_json if args.task_json is not None else Path(args.task_file).read_text(encoding="utf-8")
    return json.loads(raw)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--repo", help="source repository owner/name (default: the committed Agent's sync header)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ls", help="agents, their live readiness and the release `run` would use")
    p.add_argument("--json", action="store_true", help="print the rows as JSON instead of a table")

    p = sub.add_parser("state", help="read-only platform snapshot: Flux, platform pods, agents, releases, sandboxes, open PRs")
    p.add_argument("--json", action="store_true", help="print the snapshot as JSON instead of text")
    p.add_argument("--no-prs", action="store_true", help="skip the gh pull request listing")

    p = sub.add_parser("run", help="submit one ordinary session and, by default, wait for its report")
    p.add_argument("agent", help="agent name; `just agent ls` lists them")
    p.add_argument("--task", help="plain request text, sent as {\"request\": TEXT}")
    p.add_argument("--task-json", help="task as a JSON document")
    p.add_argument("--task-file", type=Path, help="read the task document (JSON) from this file")
    p.add_argument("--release", help="AgentRelease name to pin; `just agent ls` lists the names (default: the most recently approved runnable release, which the output records)")
    p.add_argument("--grant-handle", help="consented delegation handle for on-behalf-of agents; without one, a release that requires delegation asks for consent")
    p.add_argument("--consent-timeout", type=float, default=delegation.DEFAULT_TIMEOUT, help="seconds to wait for the sign-in or for the consent command; ignored when the run needs no consent")
    p.add_argument("--browser", action=argparse.BooleanOptionalAction, default=False, help="when signing in here, also hand the URL to the default browser (default: print it only); ignored when the run needs no consent")
    p.add_argument("--max-boundaries", type=positive_int, default=64, help="most boundaries (checkpoints) the session may cross; at least 1")
    p.add_argument("--no-wait", action="store_true", help="print the receipt as soon as the session is submitted, without following it")
    p.add_argument("--wait-timeout", type=positive_float, default=900, help="seconds to follow the session before giving up (exit 124); above 0")
    p.add_argument("--poll-interval", type=positive_float, default=10, help="seconds between status polls; above 0")
    p.add_argument("--cancel-on-timeout", action="store_true", help="when --wait-timeout passes, also ask the runner to cancel the session (default: leave it running)")
    p.add_argument("--out", type=Path, help="new private directory for receipt, status and report")

    for name, text in (("status", "read the exact run named by a receipt"), ("wait", "keep following a receipt's run"), ("cancel", "request cancellation of a receipt's run")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--receipt", type=Path, required=True, help="the receipt.json a `run` wrote")
        if name == "wait":
            p.add_argument("--wait-timeout", type=positive_float, default=900, help="seconds to follow the session before giving up (exit 124); above 0")
            p.add_argument("--poll-interval", type=positive_float, default=10, help="seconds between status polls; above 0")

    p = sub.add_parser("consent", help="a person consents to a waiting run's session (--session), or checks whether Keycloak would issue them a depositable token (--check)")
    p.add_argument("agent", help="agent name; `just agent ls` lists them")
    p.add_argument("--check", action="store_true", help="sign in afresh, report the token's metadata, discard it; nothing is deposited")
    p.add_argument("--session", help="the session id a waiting `run` printed: sign in, consent, and deposit the token for that session only")
    p.add_argument("--run-dir", type=Path, help="with --session: the waiting run's directory, when it was started with --out")
    p.add_argument("--timeout", type=float, default=delegation.DEFAULT_TIMEOUT, help="seconds to wait for the browser to return")
    p.add_argument("--browser", action=argparse.BooleanOptionalAction, default=False, help="also hand the URL to the default browser (default: print it only)")

    p = sub.add_parser("register", help="add a repository's agents to a tenant and regenerate the tenant signer pin")
    p.add_argument("tenant", help="tenant name, e.g. tenant-test")
    p.add_argument("repository", help="owner/name of the repository whose release workflow signs these agents")
    p.add_argument("agents", nargs="+", help="names of the agents to add to the tenant")
    p.add_argument("--source", type=Path, required=True, help="clean checkout of the repository")

    p = sub.add_parser("sync", help="copy deploy/agent.yaml from the source checkout with a provenance header")
    p.add_argument("agent", help="committed agent to refresh from the source checkout")
    p.add_argument("--source", type=Path, required=True, help="checkout of the source repository to copy deploy/agent.yaml from")
    p.add_argument("--allow-repo-change", action="store_true", help="let --repo differ from the repository the header records")

    p = sub.add_parser("check-sync", help="verify every committed Agent against its sync header and every tenant pin against the headers")
    p.add_argument("agents", nargs="*", help="limit the check to these committed agents (default: all)")
    p.add_argument("--source", type=Path, help="also compare with the recorded commit in this checkout")

    p = sub.add_parser("stage", help="download, verify and stage an unapproved AgentRelease")
    p.add_argument("agent", help="committed agent the release belongs to")
    p.add_argument("tag", help="release tag to download from the source repository")
    p.add_argument("--source", type=Path, help="verify manifest/lock hashes at buildRevision in this checkout")

    p = sub.add_parser("approve", help="record approval after the controller verified the staged release")
    p.add_argument("release", help="name of the staged AgentRelease to approve")
    p.add_argument("--by", help="who approves (default: the Agent's owner)")
    p.add_argument("--ticket", help="URL or id recorded with the approval")

    args = parser.parse_args(argv)
    root = args.root
    started: dict = {}  # the session id and directory of a `run`, once it has them
    try:
        if args.command == "ls":
            rows = live.listing(root, live.Kube())
            if args.json:
                emit(rows)
            else:
                print(live.format_listing(rows))
            return 0
        if args.command == "state":
            snap = state.snapshot(root, live.Kube(), prs=not args.no_prs)
            if args.json:
                emit(snap)
            else:
                print(state.format_snapshot(snap))
            return 0
        if args.command == "run":
            task = parse_task(args)
            code, envelope = run.submit(
                root,
                args.agent,
                task,
                release=args.release,
                grant_handle=args.grant_handle,
                max_boundaries=args.max_boundaries,
                wait=not args.no_wait,
                wait_timeout=args.wait_timeout,
                poll_interval=args.poll_interval,
                cancel_on_timeout=args.cancel_on_timeout,
                out=args.out,
                consent_timeout=args.consent_timeout,
                browser=args.browser,
                started=started,
            )
            emit(envelope)
            return code
        if args.command in ("status", "wait", "cancel"):
            code, envelope = run.resume(args.receipt, args.command, wait_timeout=args.wait_timeout, poll_interval=args.poll_interval)
            emit(envelope)
            return code
        if args.command == "consent":
            if args.check == (args.session is not None):
                raise delegation.ConsentError("pass exactly one of --session ID, to consent to the session a waiting `run` printed, or --check, to test the sign-in without depositing anything")
            if args.check:
                if args.run_dir is not None:
                    raise delegation.ConsentError("--run-dir applies only with --session")
                code, report = delegation.check(root, args.agent, timeout=args.timeout, browser=args.browser)
            else:
                code, report = run.consent(root, args.agent, args.session, run_dir=args.run_dir, timeout=args.timeout, browser=args.browser)
            emit(report)
            return code
        if args.command == "register":
            emit(register.register(root, args.tenant, args.repository, args.agents, args.source))
            return 0
        if args.command == "sync":
            emit(sync.sync(root, args.agent, args.source, repo=args.repo, allow_repo_change=args.allow_repo_change))
            return 0
        if args.command == "check-sync":
            result = sync.check(root, source=args.source, agents=args.agents or None)
            pins = register.check(root)
            result["pins"] = pins["tenants"]
            result["ok"] = result["ok"] and pins["ok"]
            emit(result)
            return 0 if result["ok"] else 1
        if args.command == "stage":
            emit(stage.stage(root, args.agent, args.tag, repo=args.repo, source=args.source))
            return 0
        if args.command == "approve":
            emit(approve.approve(root, args.release, by=args.by, ticket=args.ticket, repo=args.repo))
            return 0
    except KeyboardInterrupt:
        if args.command not in ONE_DOCUMENT:
            raise
        # `run` and `consent` end their own interrupts with what they know; this is one that arrived outside those places.
        print("interrupted", file=sys.stderr)
        emit({"status": "INTERRUPTED", "reason": "interrupted before the command finished; a run directory, when one was created, holds what was written by then", **started})
        return run.INTERRUPTED
    except ERRORS as exc:
        print(f"refused: {exc}", file=sys.stderr)
        if args.command in ONE_DOCUMENT:
            emit({"status": "REFUSED", "reason": str(exc)})
        return 2
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        if args.command in ONE_DOCUMENT:
            emit({"status": "ERROR", "reason": str(exc)})
        return 1
    except Exception as exc:
        if args.command not in ONE_DOCUMENT:
            raise
        # Anything unforeseen still ends as one document. Only the exception's type and place are named: its message is not
        # known to be free of what a remote answer or a token carried. A run that had a directory by then is named, because
        # a workflow may have been started and `receipt.json`, when it was written, is the only way back to it.
        frame = traceback.extract_tb(exc.__traceback__)[-1]
        reason = f"unexpected {type(exc).__name__} at {Path(frame.filename).name}:{frame.lineno}"
        print(f"error: {reason}", file=sys.stderr)
        emit({"status": "ERROR", "reason": reason, **started})
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
