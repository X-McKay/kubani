#!/usr/bin/env python3
"""Operate Kubani-applied agents: state, ls, run, status/wait/cancel, consent, register, sync, check-sync, stage, approve, authority, alias, rollback, pin, unpin, disable, enable, evaluate, revoke."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import outcome
from agent_ops import alias, approve, authority, delegation, delivery, layout, live, register, registry_client, run, stage, state, sync

ERRORS = (
    layout.LayoutError,
    live.LiveError,
    run.RunError,
    delegation.ConsentError,
    register.RegisterError,
    sync.SyncError,
    stage.StageError,
    approve.ApproveError,
    authority.AuthorityError,
    delivery.DeliveryError,
    registry_client.RegistryError,
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


# The values of the session lifecycle's enumerations (agent runtime platform spec, session lifecycle); a value outside them is never printed.
SESSION_OUTCOMES = frozenset({"COMPLETED", "FAILED", "TIMED_OUT", "CANCELLED", "CANCELED", "NOT_CONFIRMED"})
SESSION_STATES = frozenset({"SUBMITTED", "PROVISIONING", "READY", "RUNNING", "COMPLETED", "FAILED", "TIMED_OUT", "CANCELLED", "CLEANING", "CLEANED", "NOT_CONFIRMED"})
CLEANUP_VALUES = frozenset({"CONFIRMED", "NOT_CONFIRMED"})
CLEANUP_STEPS = frozenset({"stop", "delete", "grant"})
CLEANUP_DONE = frozenset({"OK", "DELETED"})
STDERR_SHOWN = 5


def enum_value(value, allowed: frozenset) -> str | None:
    """`value` as one of the fixed names in `allowed` (case and hyphens aside), else None: nothing else is ever printed."""
    name = value.upper().replace("-", "_") if isinstance(value, str) else None
    return name if name in allowed else None


def ended_reason(status: str, doc: dict) -> str:
    """Why a session that ended did not succeed, from the fields of the result that are fixed enumerations.

    The workflow status says only that the workflow stopped; the session's own outcome and its cleanup are in the result and
    the query. Free text (a task, a report, an error) is never copied: the record directory holds it for the operator."""
    result = doc.get("result") if isinstance(doc.get("result"), dict) else {}
    query = doc.get("query") if isinstance(doc.get("query"), dict) else {}
    ended = enum_value(result.get("outcome"), SESSION_OUTCOMES)
    parts = [f"the session's outcome was {ended}" if ended else f"the session ended {status}"]
    if not doc.get("confirmed"):
        cleanup = result.get("cleanup")
        shown = []
        if isinstance(cleanup, dict):
            open_steps = sorted(k for k, v in cleanup.items() if k in CLEANUP_STEPS and v not in CLEANUP_DONE)
            if open_steps:
                shown.append("cleanup steps not done: " + ", ".join(open_steps))
        elif enum_value(cleanup, CLEANUP_VALUES):
            shown.append(f"cleanup {enum_value(cleanup, CLEANUP_VALUES)}")
        state = enum_value(query.get("state"), SESSION_STATES)
        if state:
            shown.append(f"state {state}")
        parts.append("its cleanup was not confirmed" + (f" ({', '.join(shown)})" if shown else ""))
    if ended and status != "COMPLETED":
        parts.append(f"the workflow status was {status}")
    receipt = doc.get("receipt") if isinstance(doc.get("receipt"), dict) else {}
    where = doc.get("dir") or receipt.get("dir")
    if isinstance(where, str) and where:
        saved = sorted(p.name for p in Path(where).glob("exec-*.stderr")) if Path(where).is_dir() else []
        files = ", ".join(saved[:STDERR_SHOWN]) + (f" and {len(saved) - STDERR_SHOWN} more" if len(saved) > STDERR_SHOWN else "")
        parts.append(f"open {where}/status.json" + (f" and {files}" if saved else "") + " for the detail")
    return "; ".join(parts)


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
            reason = ended_reason(status, doc)
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


def alias_seconds(text: str) -> int:
    value = positive_int(text)
    if not alias.MIN_SECONDS <= value <= alias.MAX_SECONDS:
        raise argparse.ArgumentTypeError(f"must be between {alias.MIN_SECONDS} and {alias.MAX_SECONDS}, not {text}")
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


SOURCE_HELP_REGISTER = f"clean checkout of the repository (default: ${sync.SOURCE_ENV}); its origin must be that repository"
SOURCE_HELP_SYNC = f"checkout of the source repository to copy deploy/agent.yaml from (default: ${sync.SOURCE_ENV}); its origin must be the repository the header records"


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

    for name, text in (("status", "the registry's view of every agent, tool server and model; with --receipt, the exact run a receipt names"), ("wait", "keep following a receipt's run"), ("cancel", "request cancellation of a receipt's run")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--receipt", type=Path, required=name != "status", help="the receipt.json a `run` wrote" + ("; without it, the registry's view of every agent, tool server and model" if name == "status" else ""))
        if name == "status":
            p.add_argument("--json", action="store_true", help="without --receipt: print the registry's view as JSON instead of text")
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
    p.add_argument("--source", type=Path, help=SOURCE_HELP_REGISTER)

    p = sub.add_parser("sync", help="copy deploy/agent.yaml from the source checkout with a provenance header")
    p.add_argument("agent", help="committed agent to refresh from the source checkout")
    p.add_argument("--source", type=Path, help=SOURCE_HELP_SYNC)
    p.add_argument("--allow-repo-change", action="store_true", help="let --repo differ from the repository the header records")

    p = sub.add_parser("check-sync", help="verify every committed Agent against its sync header and every tenant pin against the headers")
    p.add_argument("agents", nargs="*", help="limit the check to these committed agents (default: all)")
    p.add_argument("--source", type=Path, help="also compare with the recorded commit in this checkout, whose origin must be the repository the header names")

    p = sub.add_parser("stage", help="download, verify and stage an unapproved AgentRelease")
    p.add_argument("agent", help="committed agent the release belongs to")
    p.add_argument("tag", help="release tag to download from the source repository")
    p.add_argument("--source", type=Path, help="verify manifest/lock hashes at buildRevision in this checkout, whose origin must be the repository the release comes from")

    p = sub.add_parser("approve", help="record approval after the controller verified the staged release")
    p.add_argument("release", help="name of the staged AgentRelease to approve, or an agent the registry owns")
    p.add_argument("--by", help="who approves (default: the Agent's owner)")
    p.add_argument("--ticket", help="URL or id recorded with the approval")

    p = sub.add_parser("authority", help="hand an agent to the registry (take) or back to the pull request path (return)")
    p.add_argument("action", choices=("take", "return"), help="take: the registry owns the agent; return: git owns it again")
    p.add_argument("agent", help="committed agent whose authority moves")

    for name, text in (("rollback", "return a registry-owned agent to an earlier activated release (default: the one before the current)"), ("pin", "keep a registry-owned agent on one release while newer ones activate (default: the current one)"), ("unpin", "let a registry-owned agent follow the newest activated release again"), ("disable", "stop a registry-owned agent from starting sessions"), ("enable", "let a registry-owned agent start sessions again"), ("evaluate", "ask for another evaluation of the newest revision after a refusal")):
        p = sub.add_parser(name, help=text)
        p.add_argument("agent", help="agent the registry owns")
        if name == "rollback":
            p.add_argument("--to", metavar="RELEASE", help="the release to return to (default: the newest activated release below the current one)")
        if name == "pin":
            p.add_argument("--release", help="the release to pin (default: the current release)")
        if name in ("rollback", "disable", "enable", "evaluate"):
            p.add_argument("--reason", help="why, recorded with the change")

    p = sub.add_parser("alias", help="move a model alias: plan (assess), move, status, evaluate, cancel")
    actions = p.add_subparsers(dest="action", required=True, help="what to do with the alias")
    q = actions.add_parser("plan", help="assess a candidate pair for an alias: who depends on it, who is held, who is evaluated")
    q.add_argument("alias", help="the alias, e.g. fast")
    q.add_argument("--engine", required=True, help="the candidate's engine")
    q.add_argument("--release", required=True, help="the candidate's model release (its manifest is merged first)")
    q = actions.add_parser("move", help="start a move for an assessment that is not stale and not blocked")
    q.add_argument("assessment", help="the assessment id `alias plan` printed")
    q.add_argument("--sessions", choices=("finish", "cancel"), default="finish", help="what happens to running sessions of held agents (default: finish)")
    q.add_argument("--evaluation-seconds", type=alias_seconds, help=f"how long the evaluation may take, {alias.MIN_SECONDS} to {alias.MAX_SECONDS} (default: the registry's)")
    q = actions.add_parser("status", help="one move, or the open moves (of one alias)")
    q.add_argument("move", nargs="?", help="a move id; without it the open moves are listed")
    q.add_argument("--alias", help="only the open moves of this alias")
    q = actions.add_parser("evaluate", help="say the engine is serving the candidate, so the evaluation starts")
    q.add_argument("move", help="the move id")
    q = actions.add_parser("cancel", help="cancel a move that is holding or held")
    q.add_argument("move", help="the move id")
    q.add_argument("--reason", required=True, help="why, recorded with the cancellation")
    for q in actions.choices.values():
        q.add_argument("--json", action="store_true", help="print the registry's document as JSON instead of text")

    p = sub.add_parser("revoke", help="prepare the reviewed revocation file for a release and regenerate the feed; commits and sends nothing")
    p.add_argument("agent", help="agent name")
    p.add_argument("release", help="the release to revoke")
    p.add_argument("--reason", choices=("security", "quality"), required=True, help="security cancels the release's running sessions unless --sessions finish; quality lets them finish")
    p.add_argument("--summary", required=True, help="one sentence for the record")
    p.add_argument("--sessions", choices=("cancel", "finish"), help="what happens to running sessions (default: cancel for security, finish for quality)")
    p.add_argument("--by", required=True, help="who decided")

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
            kube = live.Kube()
            owned = delivery.new_path(root, kube, args.agent)
            if owned is not None:
                code, envelope = delivery.submit(
                    *owned,
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
                kube=kube,
            )
            return conclude(args, code, envelope)
        if args.command == "status" and args.receipt is None:
            doc = registry_client.status()
            if args.json:
                emit(outcome.document(doc))
            else:
                print(registry_client.format_status(doc))
            return 0
        if args.command in ("status", "wait", "cancel") and delivery.is_session_receipt(args.receipt):
            code, envelope = delivery.resume(args.receipt, args.command, wait_timeout=getattr(args, "wait_timeout", 900), poll_interval=getattr(args, "poll_interval", 10))
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
            return conclude(args, 0, register.register(root, args.tenant, args.repository, args.agents, sync.source_path(args.source)))
        if args.command == "sync":
            return conclude(args, 0, sync.sync(root, args.agent, sync.source_path(args.source), repo=args.repo, allow_repo_change=args.allow_repo_change))
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
        if args.command == "authority":
            return conclude(args, 0, authority.take(root, args.agent) if args.action == "take" else authority.give_back(root, args.agent))
        if args.command == "alias":
            return alias.run(args)
        if args.command == "rollback":
            return conclude(args, 0, delivery.rollback(root, args.agent, to=args.to, reason=args.reason))
        if args.command == "pin":
            return conclude(args, 0, delivery.pin(root, args.agent, release=args.release))
        if args.command == "unpin":
            return conclude(args, 0, delivery.unpin(root, args.agent))
        if args.command in ("disable", "enable"):
            return conclude(args, 0, delivery.set_enabled(root, args.agent, args.command == "enable", reason=args.reason))
        if args.command == "evaluate":
            return conclude(args, 0, delivery.evaluate(root, args.agent, reason=args.reason))
        if args.command == "revoke":
            return conclude(args, 0, delivery.revoke(root, args.agent, args.release, reason=args.reason, summary=args.summary, by=args.by, sessions=args.sessions))
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
