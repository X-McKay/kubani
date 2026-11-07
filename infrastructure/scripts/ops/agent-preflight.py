#!/usr/bin/env python3
"""Check one agent's local candidate compatibility; no release qualification claim."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_preflight.core import run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
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
    result = run(args.root, args.source, args.agent, args.tag, live_scope=args.live)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
