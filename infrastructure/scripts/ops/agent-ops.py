#!/usr/bin/env python3
"""Operate Kubani-applied agents: state, ls, run, status/wait/cancel, consent, register, sync, check-sync, stage, approve."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import outcome
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


class Parser(argparse.ArgumentParser):
    """argparse, which still prints usage and the message to stderr and exits 2, plus the `invalid-arguments` document on stdout."""

    def error(self, message):
        emit(outcome.document({}, outcome.error("invalid-arguments", outcome.usage_message(message))))
        super().error(message)


def not_confirmed(reason: str, doc: dict) -> str:
    """`reason` and what the caller does instead of repeating the command: the work was, or may have been, started."""
    follow = doc.get("next")
    if follow:
        return f"{reason}; its result is not confirmed: do not repeat this command, follow up with `{follow}`"
    return f"{reason}; its result is not confirmed: do not repeat this command" + (", the document's sessionId and dir name the run" if doc.get("sessionId") else "")


def ended_on_exception(args, started, status: str, reason: str, code: str) -> tuple[dict, dict]:
    """The document and `error` of a `run` or `consent` that ended on an exception its own code did not handle.

    A `run` that had attempted its submission may have started a session whatever the exception was, so it ends
    `not-confirmed` and carries the session id, the directory and, once there is one, the receipt and the command that reads
    it; every other ending keeps the code its exception chose.
    """
    doc = {"status": status, "reason": reason, **started}
    if args.command == "run" and getattr(started, "attempted", False):
        doc["status"] = "FOLLOW_FAILED" if "receiptPath" in started else "SUBMIT_UNCONFIRMED"
        return doc, outcome.error("not-confirmed", not_confirmed(reason, doc))
    return doc, outcome.error(code, reason)


def failure_for(command: str, args, code: int, doc: dict) -> dict:
    """The `error` object of a command that ended with a non-zero exit code and printed `doc`. The message is the
    document's own `reason` where it has one, else a fixed sentence: nothing here shows what `reason` does not."""
    kind = getattr(doc, "kind", None)
    reason = doc.get("reason") if isinstance(doc.get("reason"), str) else None
    if command == "check-sync":
        rows = [{"check": "agent-sync", **row} for row in doc.get("agents", [])] + [{"check": "tenant-pin", **row} for row in doc.get("pins", [])]
        failed = sum(1 for row in rows if row.get("state") != "ok")
        return outcome.error("check-failed", f"{failed} of {len(rows)} checks did not hold; see proofs", proofs=rows)
    if command == "consent" and args.check and code == 1:
        proofs = [
            {"check": f"the audience includes {delegation.POLICY_AUDIENCE}", "ok": doc.get("hasPolicyServiceAudience") is True},
            {"check": "the token is a person's, not an agent's", "ok": doc.get("clientType") != "agent"},
            {"check": f"the scope includes {doc.get('requiredScope')}", "ok": doc.get("hasDelegationScope") is True},
            {"check": "the token carries may_act.sub", "ok": doc.get("mayActSubPresent") is True},
            {"check": "every claim has the JSON type the policy service decodes", "ok": not doc.get("undecodableClaims")},
        ]
        return outcome.error("check-failed", "the token Keycloak issued would not be accepted for deposit; see proofs and missing", proofs=proofs)
    if kind is None:
        kind = {124: "timeout", run.INTERRUPTED: "interrupted", run.NO_CONSENT: "no-consent"}.get(code, "failed")
        if command == "consent" and code == 124:
            kind = "no-consent"
    if reason is None:
        status = doc.get("status")
        if kind == "timeout":
            shown = status if status in run.TERMINAL or status == "RUNNING" else None
            reason = f"the wait ended before the session did (status {shown})" if shown else "the wait ended before the work did"
        elif kind == "no-consent":
            reason = "nobody signed in before the timeout; nothing was deposited"
        elif kind == "refused" and "missing" in doc:
            reason = "the token Keycloak issued would not be accepted for deposit; see missing"
        elif command == "cancel":
            reason = "the runner did not accept the cancel request; see cancel"
        elif status in run.TERMINAL:
            reason = f"the session ended {status}" + ("" if doc.get("confirmed") else " and its cleanup was not confirmed")
        else:
            reason = "the command ended unsuccessfully"
    return outcome.error(kind, not_confirmed(reason, doc) if kind == "not-confirmed" else reason)


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
        raise run.RunError("pass exactly one of --task, --task-json or --task-file", "invalid-arguments")
    if args.task is not None:
        return {"request": args.task}
    raw = args.task_json if args.task_json is not None else Path(args.task_file).read_text(encoding="utf-8")
    return json.loads(raw)


def conclude(args, code: int, doc: dict) -> int:
    """Print `doc` with `ok` (and, when `code` is not 0, `error`) added, and give back the exit code unchanged."""
    emit(outcome.document(doc, None if code == 0 else failure_for(args.command, args, code, doc)))
    return code


def main(argv=None) -> int:
    parser = Parser(description=__doc__)
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
    started = run.Started()  # the session id, directory and receipt of a `run`, once it has them
    try:
        if args.command == "ls":
            rows = live.listing(root, live.Kube())
            if args.json:
                emit(outcome.document({"agents": rows}))
            else:
                print(live.format_listing(rows))
            return 0
        if args.command == "state":
            snap = state.snapshot(root, live.Kube(), prs=not args.no_prs)
            if args.json:
                emit(outcome.document(snap))
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
            return conclude(args, code, envelope)
        if args.command in ("status", "wait", "cancel"):
            code, envelope = run.resume(args.receipt, args.command, wait_timeout=getattr(args, "wait_timeout", 900), poll_interval=getattr(args, "poll_interval", 10))
            return conclude(args, code, envelope)
        if args.command == "consent":
            if args.check == (args.session is not None):
                raise delegation.ConsentError("pass exactly one of --session ID, to consent to the session a waiting `run` printed, or --check, to test the sign-in without depositing anything", "invalid-arguments")
            if args.check:
                if args.run_dir is not None:
                    raise delegation.ConsentError("--run-dir applies only with --session", "invalid-arguments")
                code, report = delegation.check(root, args.agent, timeout=args.timeout, browser=args.browser)
            else:
                code, report = run.consent(root, args.agent, args.session, run_dir=args.run_dir, timeout=args.timeout, browser=args.browser)
            return conclude(args, code, report)
        if args.command == "register":
            return conclude(args, 0, register.register(root, args.tenant, args.repository, args.agents, args.source))
        if args.command == "sync":
            return conclude(args, 0, sync.sync(root, args.agent, args.source, repo=args.repo, allow_repo_change=args.allow_repo_change))
        if args.command == "check-sync":
            result = sync.check(root, source=args.source, agents=args.agents or None)
            pins = register.check(root)
            result["pins"] = pins["tenants"]
            result["ok"] = result["ok"] and pins["ok"]
            return conclude(args, 0 if result["ok"] else 1, result)
        if args.command == "stage":
            return conclude(args, 0, stage.stage(root, args.agent, args.tag, repo=args.repo, source=args.source))
        if args.command == "approve":
            return conclude(args, 0, approve.approve(root, args.release, by=args.by, ticket=args.ticket, repo=args.repo))
    except KeyboardInterrupt:
        message = "interrupted before the command finished; a run directory, when one was created, holds what was written by then"
        if args.command not in ONE_DOCUMENT:
            emit(outcome.document({}, outcome.error("interrupted", message)))
            raise
        # `run` and `consent` end their own interrupts with what they know; this is one that arrived outside those places.
        print("interrupted", file=sys.stderr)
        doc, failure = ended_on_exception(args, started, "INTERRUPTED", message, "interrupted")
        emit(outcome.document(doc, failure))
        return run.INTERRUPTED
    except ERRORS as exc:
        print(f"refused: {exc}", file=sys.stderr)
        reason = str(exc) or type(exc).__name__
        if args.command in ONE_DOCUMENT:
            doc, failure = ended_on_exception(args, started, "REFUSED", reason, outcome.code_of(exc, "refused"))
        else:
            doc, failure = {}, outcome.error(outcome.code_of(exc, "refused"), reason)
        emit(outcome.document(doc, failure))
        return 2
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        code = "not-found" if isinstance(exc, FileNotFoundError) else "validation-failed" if isinstance(exc, ValueError) else "failed"
        reason = str(exc) or type(exc).__name__
        if args.command in ONE_DOCUMENT:
            doc, failure = ended_on_exception(args, started, "ERROR", reason, code)
        else:
            doc, failure = {}, outcome.error(code, reason)
        emit(outcome.document(doc, failure))
        return 1
    except Exception as exc:
        # Anything unforeseen still ends as one document. Only the exception's type and place are named: its message is not
        # known to be free of what a remote answer or a token carried. A run that had a directory by then is named, because
        # a workflow may have been started and `receipt.json`, when it was written, is the only way back to it.
        reason = outcome.unexpected(exc)
        if args.command not in ONE_DOCUMENT:
            traceback.print_exc()  # what the uncaught exception printed before this document existed
            emit(outcome.document({}, outcome.error("internal", reason)))
            return 1
        print(f"error: {reason}", file=sys.stderr)
        doc, failure = ended_on_exception(args, started, "ERROR", reason, "internal")
        emit(outcome.document(doc, failure))
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
