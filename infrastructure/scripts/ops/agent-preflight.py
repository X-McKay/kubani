#!/usr/bin/env python3
"""Check one agent's local candidate compatibility; no release qualification claim."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import outcome
from agent_preflight.core import run

BLOCKING = ("fail", "not_checked", "unavailable")


class Parser(argparse.ArgumentParser):
    """argparse, which still prints usage and the message to stderr and exits 2, plus the `invalid-arguments` document on stdout."""

    def error(self, message):
        emit(outcome.document({}, outcome.error("invalid-arguments", message)))
        super().error(message)


def emit(document):
    print(json.dumps(document, sort_keys=True, allow_nan=False))


def failure_for(result):
    """Why a receipt with `ok` false failed: a check that did not hold, or only checks whose evidence could not be had."""
    blocking = [c for c in result.get("checks", []) if c.get("required") and c.get("state") in BLOCKING]
    if blocking and all(c["state"] == "unavailable" for c in blocking):
        return outcome.error("unavailable", f"{len(blocking)} required checks could not be evaluated; their evidence was unavailable (see checks)")
    return outcome.error("check-failed", f"{len(blocking)} required checks did not hold; see proofs", proofs=list(result.get("checks", [])))


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument("agent")
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="explicit trusted executable source checkout",
    )
    parser.add_argument("--tag", required=True, help="prospective AGENT/vVERSION tag")
    parser.add_argument(
        "--live",
        action="store_true",
        help="GET-only MCP registration evidence; may decrypt existing SOPS operator credential",
    )
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[3]
    )
    args = parser.parse_args(argv)
    try:
        result = run(args.root, args.source, args.agent, args.tag, live_scope=args.live)
    except KeyboardInterrupt:
        emit(outcome.document({}, outcome.error("interrupted", "interrupted before the preflight finished")))
        raise
    except Exception as exc:  # noqa: BLE001 - one document however it ends; the message names the type and place only
        traceback.print_exc(file=sys.stderr)  # what the uncaught exception printed before this document existed
        emit(outcome.document({}, outcome.error("internal", outcome.unexpected(exc))))
        return 1
    emit(outcome.document(result, None if result["ok"] else failure_for(result)))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
