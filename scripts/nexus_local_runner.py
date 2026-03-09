#!/usr/bin/env python3
"""Nexus Local Iterative Test Runner.

Runs the Nexus agent components locally against live cluster services
(*.almckay.io ingress) without building or pushing a container image.

This is the primary tool for iterating on prompts, activity logic, and
mission configuration before committing changes.

Usage
-----
# Interactive agent turn (reactive path):
python scripts/nexus_local_runner.py turn "What pods are unhealthy?"

# Single mission turn (proactive path):
python scripts/nexus_local_runner.py mission \\
    --goal "Check cluster health and report any pod failures" \\
    --policy nexus-proactive \\
    --max-tool-calls 10

# Health-check all cluster services:
python scripts/nexus_local_runner.py health

# Validate env and config only (no LLM calls):
python scripts/nexus_local_runner.py check

# Watch mode — re-run a mission turn on every file save:
python scripts/nexus_local_runner.py watch \\
    --goal "Summarise recent AI news" \\
    --watch-path kubani/nexus/orchestrator/activities.py

Environment
-----------
Loads .env.nexus-local by default, then overlays .env.nexus-local.override
(gitignored) for secrets. Override with --env-file.

All cluster URLs default to *.almckay.io. Override individual services with
environment variables (LLM_API_URL, MCP_MEMORY_URL, etc.) or in your
.env.nexus-local.override file.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Ensure the kubani package is importable from the repo root
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

logger = logging.getLogger("nexus_local_runner")


# ===========================================================================
# Environment loading
# ===========================================================================


def load_env(env_file: Path | None = None) -> None:
    """Load environment variables from .env.nexus-local and optional override.

    Load order (later values win):
    1. .env.nexus-local (committed template with cluster defaults)
    2. .env.nexus-local.override (gitignored, contains real secrets)
    3. Any extra --env-file passed on the command line

    Args:
        env_file: Optional additional env file to load last.
    """
    files_to_load: list[Path] = [
        REPO_ROOT / ".env.nexus-local",
        REPO_ROOT / ".env.nexus-local.override",
    ]
    if env_file:
        files_to_load.append(env_file)

    for path in files_to_load:
        if not path.exists():
            continue
        _parse_dotenv(path)
        logger.debug(f"Loaded env from {path}")


def _parse_dotenv(path: Path) -> None:
    """Parse a .env file and set environment variables (skip comments/blanks)."""
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            # Only set if not already set (allows shell env to override)
            if key and key not in os.environ:
                os.environ[key] = value


# ===========================================================================
# Service health checks
# ===========================================================================


async def check_service(name: str, url: str, timeout: float = 5.0) -> dict[str, Any]:
    """Perform an HTTP GET health check against a service URL.

    Args:
        name: Human-readable service name.
        url: URL to check (appends /health if no path given).
        timeout: Request timeout in seconds.

    Returns:
        Dict with name, url, ok (bool), status_code, latency_ms, error.
    """
    import urllib.error
    import urllib.request

    check_url = url.rstrip("/")
    if not any(check_url.endswith(p) for p in ("/health", "/v1/models", "/api/tags")):
        check_url += "/health"

    start = time.monotonic()
    try:
        req = urllib.request.Request(check_url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            latency_ms = int((time.monotonic() - start) * 1000)
            return {
                "name": name,
                "url": check_url,
                "ok": resp.status < 400,
                "status_code": resp.status,
                "latency_ms": latency_ms,
                "error": None,
            }
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "name": name,
            "url": check_url,
            "ok": False,
            "status_code": None,
            "latency_ms": latency_ms,
            "error": str(exc),
        }


async def run_health_checks() -> list[dict[str, Any]]:
    """Check all cluster services that the Nexus agent depends on.

    Returns:
        List of health check result dicts.
    """
    services = [
        ("LLM (vLLM)", os.environ.get("LLM_API_URL", "https://llm.almckay.io/v1") + "/models"),
        ("LLM Fast", "https://llm-fast.almckay.io/v1/models"),
        ("Memory MCP", os.environ.get("MCP_MEMORY_URL", "https://mcp-gateway.almckay.io/memory") + "/health"),
        ("Skills MCP", os.environ.get("MCP_SKILLS_URL", "https://skills-mcp.almckay.io") + "/health"),
        ("Discord MCP", os.environ.get("MCP_DISCORD_URL", "https://discord-mcp.almckay.io") + "/health"),
        ("Temporal MCP", os.environ.get("MCP_TEMPORAL_URL", "https://mcp-gateway.almckay.io/temporal") + "/health"),
        ("Qdrant", os.environ.get("QDRANT_URL", "https://qdrant.almckay.io") + "/healthz"),
        ("Nexus Gateway", "https://nexus.almckay.io/health"),
        ("Temporal UI", "https://temporal.almckay.io"),
        ("Grafana", "https://grafana.almckay.io/api/health"),
    ]

    tasks = [check_service(name, url) for name, url in services]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return list(results)


def print_health_results(results: list[dict[str, Any]]) -> bool:
    """Print health check results as a formatted table.

    Args:
        results: List of health check result dicts.

    Returns:
        True if all checks passed, False otherwise.
    """
    print("\n" + "=" * 65)
    print(f"{'Service':<25} {'Status':<10} {'Latency':>8}  URL")
    print("-" * 65)
    all_ok = True
    for r in results:
        icon = "✓" if r["ok"] else "✗"
        status = f"{r['status_code']}" if r["status_code"] else "ERR"
        latency = f"{r['latency_ms']}ms" if r["latency_ms"] is not None else "—"
        err = f"  ({r['error'][:40]})" if r["error"] else ""
        print(f"  {icon}  {r['name']:<22} {status:<10} {latency:>8}  {r['url']}{err}")
        if not r["ok"]:
            all_ok = False
    print("=" * 65)
    if all_ok:
        print("All services reachable.\n")
    else:
        print("Some services are unreachable. Check your VPN/Tailscale connection.\n")
    return all_ok


# ===========================================================================
# Config validation
# ===========================================================================


def run_config_check() -> bool:
    """Validate that required env vars are set and non-placeholder.

    Returns:
        True if all required vars are present and non-placeholder.
    """
    required = {
        "LLM_API_URL": "https://llm.almckay.io/v1",
        "TEMPORAL_HOST": "temporal.almckay.io:7233",
        "TEMPORAL_NAMESPACE": "nexus",
        "NEXUS_DATABASE_URL": None,  # must be set, no default
        "REDIS_URL": None,
    }
    placeholder_values = {"CHANGE_ME", "", "your-discord-bot-token-here"}

    print("\n=== Configuration Check ===\n")
    all_ok = True
    for var, default in required.items():
        val = os.environ.get(var, default)
        if not val or val in placeholder_values:
            print(f"  ✗  {var}: NOT SET or placeholder — update .env.nexus-local.override")
            all_ok = False
        else:
            # Mask secrets
            display = val if "password" not in var.lower() and "key" not in var.lower() else "***"
            print(f"  ✓  {var} = {display}")

    optional = {
        "MCP_MEMORY_URL": os.environ.get("MCP_MEMORY_URL", "https://mcp-gateway.almckay.io/memory"),
        "MCP_SKILLS_URL": os.environ.get("MCP_SKILLS_URL", "https://skills-mcp.almckay.io"),
        "MCP_DISCORD_URL": os.environ.get("MCP_DISCORD_URL", "https://discord-mcp.almckay.io"),
        "MCP_TEMPORAL_URL": os.environ.get("MCP_TEMPORAL_URL", "https://mcp-gateway.almckay.io/temporal"),
        "LLM_MODEL": os.environ.get("LLM_MODEL", "Qwen3.5-9B-NVFP4"),
    }
    print()
    for var, val in optional.items():
        print(f"  ·  {var} = {val}")

    print()
    if all_ok:
        print("Configuration looks good.\n")
    else:
        print("Fix the above issues before running agent turns.\n")
    return all_ok


# ===========================================================================
# Agent turn runner (reactive path)
# ===========================================================================


async def run_agent_turn_local(
    user_message: str,
    user_id: str = "local-dev",
    conversation_history: list[dict] | None = None,
    memories: list[str] | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """Run a single reactive agent turn locally against cluster services.

    This directly invokes the ``run_agent_turn`` Temporal activity function
    as a plain async function — no Temporal worker or cluster needed.
    The LLM and MCP servers are reached via the almckay.io ingress URLs
    configured in the environment.

    Args:
        user_message: The user's message to process.
        user_id: User identifier (used for workspace resolution).
        conversation_history: Optional list of prior conversation messages.
        memories: Optional list of relevant memory strings.
        verbose: Whether to print progress and results.

    Returns:
        Activity result dict with ``response_text`` and ``stop_reason``.
    """
    from kubani.nexus.orchestrator.activities import run_agent_turn

    input_data = {
        "user_message": user_message,
        "user_id": user_id,
        "conversation_history": conversation_history or [],
        "memories": memories or [],
    }

    if verbose:
        print(f"\n{'='*60}")
        print(f"  AGENT TURN (reactive)")
        print(f"  User:    {user_id}")
        print(f"  Message: {user_message[:120]}")
        print(f"  LLM:     {os.environ.get('LLM_API_URL', 'https://llm.almckay.io/v1')}")
        print(f"  Model:   {os.environ.get('LLM_MODEL', 'Qwen3.5-9B-NVFP4')}")
        print(f"{'='*60}\n")

    start = time.monotonic()

    # Patch activity.heartbeat so it works outside a Temporal worker
    _patch_temporal_activity()

    try:
        result = await run_agent_turn(input_data)
    except Exception as exc:
        elapsed = time.monotonic() - start
        logger.error(f"Agent turn failed after {elapsed:.1f}s: {exc}", exc_info=True)
        return {"response_text": f"ERROR: {exc}", "stop_reason": "error"}

    elapsed = time.monotonic() - start

    if verbose:
        print(f"\n{'─'*60}")
        print(f"  Response ({elapsed:.1f}s):\n")
        print(f"  {result.get('response_text', '(no response)')}")
        print(f"\n  stop_reason: {result.get('stop_reason', 'unknown')}")
        print(f"{'─'*60}\n")

    return result


# ===========================================================================
# Mission turn runner (proactive path)
# ===========================================================================


async def run_mission_turn_local(
    goal: str,
    mission_id: str = "local-dev-mission",
    mission_title: str = "Local Dev Mission",
    user_id: str = "local-dev",
    mcp_policy: str = "nexus",
    max_tool_calls: int = 10,
    notify_on: list[str] | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """Run a single proactive mission turn locally against cluster services.

    This directly invokes the ``run_mission_agent_turn`` Temporal activity
    function as a plain async function — no Temporal worker or cluster needed.
    The LLM and MCP servers are reached via the almckay.io ingress URLs.

    Args:
        goal: Natural language mission goal.
        mission_id: Mission identifier (arbitrary for local testing).
        mission_title: Human-readable mission title.
        user_id: User identifier.
        mcp_policy: MCP policy name (``nexus`` or ``nexus-proactive``).
        max_tool_calls: Hard cap on tool calls (1–50).
        notify_on: Notification conditions list.
        verbose: Whether to print progress and results.

    Returns:
        Activity result dict with should_notify, found_anomaly,
        notification_text, tool_calls_made, run_id, status.
    """
    from kubani.nexus.orchestrator.activities import run_mission_agent_turn

    input_data = {
        "mission_id": mission_id,
        "mission_title": mission_title,
        "mission_goal": goal,
        "user_id": user_id,
        "mcp_policy": mcp_policy,
        "max_tool_calls": max_tool_calls,
        "notify_on": notify_on or ["anomaly", "error"],
        "recent_history": [],
    }

    if verbose:
        print(f"\n{'='*60}")
        print(f"  MISSION TURN (proactive)")
        print(f"  Mission: {mission_title}")
        print(f"  Goal:    {goal[:120]}")
        print(f"  Policy:  {mcp_policy}")
        print(f"  Budget:  {max_tool_calls} tool calls")
        print(f"  LLM:     {os.environ.get('LLM_API_URL', 'https://llm.almckay.io/v1')}")
        print(f"  Model:   {os.environ.get('LLM_MODEL', 'Qwen3.5-9B-NVFP4')}")
        print(f"{'='*60}\n")

    start = time.monotonic()

    # Patch activity.heartbeat so it works outside a Temporal worker
    _patch_temporal_activity()

    try:
        result = await run_mission_agent_turn(input_data)
    except Exception as exc:
        elapsed = time.monotonic() - start
        logger.error(f"Mission turn failed after {elapsed:.1f}s: {exc}", exc_info=True)
        return {
            "should_notify": True,
            "found_anomaly": False,
            "notification_text": f"ERROR: {exc}",
            "tool_calls_made": 0,
            "run_id": "error",
            "status": "failed",
        }

    elapsed = time.monotonic() - start

    if verbose:
        print(f"\n{'─'*60}")
        print(f"  Result ({elapsed:.1f}s):")
        print(f"    status:           {result.get('status')}")
        print(f"    run_id:           {result.get('run_id')}")
        print(f"    tool_calls_made:  {result.get('tool_calls_made')}")
        print(f"    found_anomaly:    {result.get('found_anomaly')}")
        print(f"    should_notify:    {result.get('should_notify')}")
        if result.get("notification_text"):
            print(f"\n  Notification:\n    {result.get('notification_text')[:500]}")
        print(f"{'─'*60}\n")

    return result


# ===========================================================================
# Watch mode
# ===========================================================================


async def run_watch_mode(
    goal: str,
    watch_path: str,
    mcp_policy: str = "nexus",
    max_tool_calls: int = 10,
    verbose: bool = True,
) -> None:
    """Re-run a mission turn every time a watched file is saved.

    Useful for iterating on prompts or activity logic without restarting
    the runner manually.

    Args:
        goal: Mission goal to run on each file change.
        watch_path: File path to watch for changes (relative to repo root).
        mcp_policy: MCP policy to use.
        max_tool_calls: Tool call budget.
        verbose: Whether to print results.
    """
    watch_file = REPO_ROOT / watch_path
    if not watch_file.exists():
        print(f"Watch file not found: {watch_file}")
        sys.exit(1)

    print(f"\nWatch mode active. Watching: {watch_file}")
    print("Save the file to trigger a new mission turn. Ctrl+C to stop.\n")

    last_mtime = watch_file.stat().st_mtime
    run_count = 0

    # Run once immediately
    run_count += 1
    print(f"[Run #{run_count}] Initial run...")
    await run_mission_turn_local(
        goal=goal,
        mission_title=f"Watch Run #{run_count}",
        mcp_policy=mcp_policy,
        max_tool_calls=max_tool_calls,
        verbose=verbose,
    )

    while True:
        await asyncio.sleep(1)
        try:
            mtime = watch_file.stat().st_mtime
        except FileNotFoundError:
            continue
        if mtime != last_mtime:
            last_mtime = mtime
            run_count += 1
            print(f"\n[Run #{run_count}] File changed — reloading and re-running...")
            # Reload the module so code changes take effect
            _reload_activities()
            await run_mission_turn_local(
                goal=goal,
                mission_title=f"Watch Run #{run_count}",
                mcp_policy=mcp_policy,
                max_tool_calls=max_tool_calls,
                verbose=verbose,
            )


def _reload_activities() -> None:
    """Force-reload the activities module so prompt/code changes take effect."""
    import importlib
    mods_to_reload = [
        "kubani.nexus.orchestrator.activities",
        "kubani.nexus.tools.mcp_clients",
        "kubani.framework.config",
    ]
    for mod_name in mods_to_reload:
        if mod_name in sys.modules:
            try:
                importlib.reload(sys.modules[mod_name])
                logger.debug(f"Reloaded {mod_name}")
            except Exception as exc:
                logger.warning(f"Could not reload {mod_name}: {exc}")


# ===========================================================================
# Temporal activity heartbeat patch
# ===========================================================================


def _patch_temporal_activity() -> None:
    """Patch temporalio.activity.heartbeat to be a no-op outside a worker.

    The activity functions call ``activity.heartbeat()`` which raises
    RuntimeError when called outside a Temporal worker context. This patch
    replaces it with a logging call so the functions work as plain async
    functions during local testing.
    """
    import temporalio.activity as _ta

    if getattr(_ta, "_local_runner_patched", False):
        return

    _original_heartbeat = _ta.heartbeat

    def _noop_heartbeat(details: Any = None, *args: Any, **kwargs: Any) -> None:
        if details:
            logger.debug(f"[heartbeat] {details}")

    _ta.heartbeat = _noop_heartbeat
    _ta._local_runner_patched = True
    logger.debug("Patched activity.heartbeat for local runner")


# ===========================================================================
# CLI
# ===========================================================================


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Nexus local iterative test runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Additional .env file to load (loaded after .env.nexus-local.override)",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: from LOG_LEVEL env var or INFO)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON (useful for scripting)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # health
    sub.add_parser("health", help="Check all cluster service endpoints")

    # check
    sub.add_parser("check", help="Validate environment configuration")

    # turn
    turn_p = sub.add_parser("turn", help="Run a single reactive agent turn")
    turn_p.add_argument("message", help="User message to send to the agent")
    turn_p.add_argument("--user-id", default="local-dev", help="User ID")

    # mission
    mission_p = sub.add_parser("mission", help="Run a single proactive mission turn")
    mission_p.add_argument("--goal", required=True, help="Mission goal (natural language)")
    mission_p.add_argument("--title", default="Local Dev Mission", help="Mission title")
    mission_p.add_argument(
        "--policy",
        default="nexus",
        choices=["nexus", "nexus-proactive"],
        help="MCP policy (default: nexus)",
    )
    mission_p.add_argument(
        "--max-tool-calls",
        type=int,
        default=10,
        help="Hard tool call budget (1–50, default: 10)",
    )
    mission_p.add_argument("--user-id", default="local-dev", help="User ID")

    # watch
    watch_p = sub.add_parser(
        "watch",
        help="Re-run a mission turn on every file save (hot-reload for prompts)",
    )
    watch_p.add_argument("--goal", required=True, help="Mission goal")
    watch_p.add_argument(
        "--watch-path",
        default="kubani/nexus/orchestrator/activities.py",
        help="File to watch for changes (relative to repo root)",
    )
    watch_p.add_argument(
        "--policy",
        default="nexus",
        choices=["nexus", "nexus-proactive"],
        help="MCP policy",
    )
    watch_p.add_argument(
        "--max-tool-calls",
        type=int,
        default=10,
        help="Hard tool call budget",
    )

    return parser


async def _main(args: argparse.Namespace) -> int:
    """Main async entry point.

    Returns:
        Exit code (0 = success, 1 = failure).
    """
    load_env(args.env_file)

    log_level = args.log_level or os.environ.get("LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.command == "health":
        results = await run_health_checks()
        if args.json:
            print(json.dumps(results, indent=2))
            return 0 if all(r["ok"] for r in results) else 1
        ok = print_health_results(results)
        return 0 if ok else 1

    elif args.command == "check":
        ok = run_config_check()
        return 0 if ok else 1

    elif args.command == "turn":
        result = await run_agent_turn_local(
            user_message=args.message,
            user_id=args.user_id,
            verbose=not args.json,
        )
        if args.json:
            print(json.dumps(result, indent=2))
        return 0 if result.get("stop_reason") != "error" else 1

    elif args.command == "mission":
        result = await run_mission_turn_local(
            goal=args.goal,
            mission_title=args.title,
            user_id=args.user_id,
            mcp_policy=args.policy,
            max_tool_calls=args.max_tool_calls,
            verbose=not args.json,
        )
        if args.json:
            print(json.dumps(result, indent=2))
        return 0 if result.get("status") in ("completed", "timed_out") else 1

    elif args.command == "watch":
        await run_watch_mode(
            goal=args.goal,
            watch_path=args.watch_path,
            mcp_policy=args.policy,
            max_tool_calls=args.max_tool_calls,
            verbose=not args.json,
        )
        return 0

    return 0


def main() -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args()
    sys.exit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
