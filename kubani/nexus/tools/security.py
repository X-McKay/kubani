"""Bash command security barrier — 3-tier analysis.

Analyzes shell commands before execution and classifies them into:
- Low risk (auto-execute): safe read-only or common dev commands
- Medium risk (HITL approval): commands with side effects that need human review
- High risk (hard-blocked): dangerous system commands that are never allowed

This is the "Shell Structure Barrier" inspired by OpenClaw's AST-based
blocking, adapted for the Kubani security model with HITL approval.
"""

from __future__ import annotations

import re
from typing import Any

# =========================================================================
# High risk — hard-blocked, never allowed
# =========================================================================

HIGH_RISK_PATTERNS: list[tuple[str, str]] = [
    (r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/(?!tmp)", "rm targeting root filesystem"),
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*\s+-[a-zA-Z]*f[a-zA-Z]*\s+/", "recursive force delete from root"),
    (r"\bsudo\b", "privilege escalation via sudo"),
    (r"\bsu\b\s", "privilege escalation via su"),
    (r"\bdd\b.*\bof=/dev/", "raw device write"),
    (r"\bmkfs\b", "filesystem format"),
    (r"\bchmod\s+.*777", "world-writable permissions"),
    (r"\bchmod\s+.*\+s", "setuid/setgid bit"),
    (r"\bchown\s+root", "change ownership to root"),
    (r">\s*/etc/", "write to /etc/"),
    (r">\s*/usr/", "write to /usr/"),
    (r">\s*/bin/", "write to /bin/"),
    (r">\s*/sbin/", "write to /sbin/"),
    (r">\s*/boot/", "write to /boot/"),
    (r">\s*/sys/", "write to /sys/"),
    (r">\s*/proc/", "write to /proc/"),
    (r"\b(curl|wget)\b.*\|\s*(ba)?sh", "pipe remote content to shell"),
    (r"\beval\b.*\$\(", "eval with command substitution"),
    (r":\(\)\s*\{", "fork bomb"),
    (r"\bshutdown\b", "system shutdown"),
    (r"\breboot\b", "system reboot"),
    (r"\binit\s+0", "system halt"),
    (r"\bkill\s+-9\s+-1", "kill all processes"),
    (r"\biptables\b", "firewall modification"),
    (r"\bufw\b", "firewall modification"),
    (r"\bsystemctl\s+(stop|disable|mask)", "stopping system services"),
    (r"\bpasswd\b", "password change"),
    (r"\buseradd\b", "user creation"),
    (r"\buserdel\b", "user deletion"),
    (r"\bcrontab\s+-r", "remove all cron jobs"),
]

# =========================================================================
# Medium risk — requires HITL approval
# =========================================================================

MEDIUM_RISK_PATTERNS: list[tuple[str, str]] = [
    (r"\brm\b", "file deletion"),
    (r"\brmdir\b", "directory removal"),
    (r"\bgit\s+push\b", "git push (modifies remote)"),
    (r"\bgit\s+reset\s+--hard", "git hard reset"),
    (r"\bgit\s+clean\s+-[a-zA-Z]*f", "git clean force"),
    (r"\bgit\s+checkout\s+\.", "git discard changes"),
    (r"\bcurl\b", "network request"),
    (r"\bwget\b", "network download"),
    (r"\bpip\s+install\b", "package installation"),
    (r"\bnpm\s+install\b", "package installation"),
    (r"\bapt\b", "system package manager"),
    (r"\bbrew\b", "package manager"),
    (r"\bdocker\b", "container operations"),
    (r"\bkubectl\b", "kubernetes operations"),
    (r"\bchmod\b", "permission change"),
    (r"\bchown\b", "ownership change"),
    (r"\bmv\s+/", "move from root"),
    (r"\bscp\b", "secure copy"),
    (r"\brsync\b", "remote sync"),
    (r"\bssh\b", "remote shell"),
    (r"\bnc\b", "netcat"),
    (r"\bpython.*-c\b", "inline python execution"),
]

# =========================================================================
# Low risk — auto-execute (whitelist approach)
# =========================================================================

LOW_RISK_PREFIXES: list[str] = [
    "ls", "dir", "pwd", "echo", "printf",
    "cat", "head", "tail", "less", "more",
    "grep", "rg", "ag", "ack",
    "find", "locate", "which", "whereis", "type",
    "wc", "sort", "uniq", "cut", "tr", "sed", "awk",
    "diff", "cmp", "comm",
    "date", "cal", "uptime", "whoami", "hostname",
    "env", "printenv", "set",
    "file", "stat", "du", "df",
    "tree", "realpath", "dirname", "basename",
    "git status", "git log", "git diff", "git show",
    "git branch", "git remote", "git tag", "git stash list",
    "python --version", "python3 --version",
    "pip list", "pip show", "pip freeze",
    "node --version", "npm list", "npm ls",
    "uv --version", "uv pip list",
    "just --list", "just --summary",
    "make --dry-run", "make -n",
    "test ", "[",
    "true", "false",
]


def analyze_bash_command(command: str) -> dict[str, Any]:
    """Analyze a bash command and classify its risk level.

    Returns:
        Dict with:
            action: "allow" | "approve" | "block"
            reason: Human-readable explanation
            risk_score: 0.0-10.0
    """
    command = command.strip()

    if not command:
        return {"action": "block", "reason": "Empty command", "risk_score": 0.0}

    # Check high risk first (hard block)
    for pattern, reason in HIGH_RISK_PATTERNS:
        if re.search(pattern, command):
            return {
                "action": "block",
                "reason": f"Blocked: {reason}",
                "risk_score": 9.0,
            }

    # Check if it's a known low-risk command
    first_part = command.split("|")[0].strip()  # Check first command in pipe
    for prefix in LOW_RISK_PREFIXES:
        if first_part.startswith(prefix):
            return {
                "action": "allow",
                "reason": "Low-risk command",
                "risk_score": 1.0,
            }

    # Check medium risk patterns (HITL approval)
    for pattern, reason in MEDIUM_RISK_PATTERNS:
        if re.search(pattern, command):
            return {
                "action": "approve",
                "reason": f"Needs approval: {reason}",
                "risk_score": 5.0,
            }

    # Unknown commands — default to approval for safety
    return {
        "action": "approve",
        "reason": "Unknown command pattern — requires approval",
        "risk_score": 4.0,
    }
