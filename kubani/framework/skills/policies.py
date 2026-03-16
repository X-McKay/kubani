"""Policy-based skill filtering.

Skills are filtered before catalog generation, not at query time.
This means the agent literally cannot see skills outside its policy
because they never enter the system prompt.

Policy names match the MCP connection policies in
``kubani/nexus/tools/mcp_clients.py`` (lines 48-73) so that the
``mcp_policy`` parameter controls both MCP server access and skill
visibility in a single knob.
"""

from __future__ import annotations

import logging
from fnmatch import fnmatch

logger = logging.getLogger(__name__)

# Each policy defines which skill name patterns are allowed/denied.
# ``allowed`` patterns are checked with fnmatch — a skill must match
# at least one allowed pattern to be included.
# ``denied`` patterns are checked first — a matching skill is excluded
# even if it also matches an allowed pattern.
SKILL_POLICIES: dict[str, dict[str, list[str]]] = {
    "nexus": {
        "allowed": ["*"],
        "denied": ["_development/*"],
    },
    "nexus-proactive": {
        "allowed": [
            "k8s/*",
            "general/missions/*",
            "general/notifications/*",
            "general/analytics/*",
        ],
        "denied": ["_development/*"],
    },
    "nexus-computer": {
        "allowed": ["*"],
        "denied": ["_development/*"],
    },
}


def filter_skills(skills: list[dict], policy: str) -> list[dict]:
    """Filter skill dicts by a named policy.

    Args:
        skills: List of skill dicts. Each must have a ``name`` key.
        policy: Policy name (e.g. ``"nexus"``, ``"nexus-proactive"``).
                Falls back to ``"nexus"`` if the name is unknown.

    Returns:
        New list containing only skills permitted by the policy.
    """
    rules = SKILL_POLICIES.get(policy)
    if rules is None:
        logger.warning("Unknown skill policy '%s', falling back to 'nexus'", policy)
        rules = SKILL_POLICIES["nexus"]

    allowed_patterns = rules["allowed"]
    denied_patterns = rules["denied"]

    filtered = []
    for skill in skills:
        # Match against skill_key (relative path like "k8s/collection/check-pods")
        # which supports hierarchical policy patterns like "k8s/*".
        # Falls back to name for skills without a skill_key (e.g. OCI-sourced).
        key = skill.get("skill_key", skill["name"])

        # Denied patterns checked first — takes priority
        if any(fnmatch(key, p) for p in denied_patterns):
            continue

        # Must match at least one allowed pattern
        if any(fnmatch(key, p) for p in allowed_patterns):
            filtered.append(skill)

    logger.info(
        "Policy '%s': %d/%d skills passed filter",
        policy,
        len(filtered),
        len(skills),
    )
    return filtered
