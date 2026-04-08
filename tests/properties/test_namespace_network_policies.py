"""Property-based tests for namespace-level network policies.

Feature: cluster-stability, Property 4: Every operational namespace has a default-deny ingress policy
Validates: Requirements 5.1
"""

from pathlib import Path

import yaml

NETWORKING_DIR = Path("infrastructure/gitops/infrastructure/networking")

# All operational namespaces that must have a default-deny ingress NetworkPolicy
OPERATIONAL_NAMESPACES = [
    "monitoring",
    "vllm",
    "database",
    "cache",
    "temporal",
    "nexus",
    "ai-agents",
]


def load_all_network_policies() -> list[dict]:
    """Load all NetworkPolicy objects from all YAML files in the networking directory."""
    policies = []
    for yaml_file in NETWORKING_DIR.glob("*.yaml"):
        if yaml_file.name == "kustomization.yaml":
            continue
        with open(yaml_file) as f:
            # Files may contain multiple documents separated by ---
            for doc in yaml.safe_load_all(f):
                if doc and doc.get("kind") == "NetworkPolicy":
                    policies.append(doc)
    return policies


def is_default_deny_ingress(policy: dict) -> bool:
    """
    Return True if this NetworkPolicy is a default-deny ingress policy.

    A default-deny ingress policy has:
    - podSelector: {} (matches all pods)
    - policyTypes includes Ingress
    - no ingress rules (or ingress key is absent/empty)
    """
    spec = policy.get("spec", {})

    # podSelector must be empty (matches all pods)
    pod_selector = spec.get("podSelector", None)
    if pod_selector != {}:
        return False

    # policyTypes must include Ingress
    policy_types = spec.get("policyTypes", [])
    if "Ingress" not in policy_types:
        return False

    # Must have no ingress rules
    ingress_rules = spec.get("ingress", [])
    if ingress_rules:
        return False

    return True


def test_property_4_all_operational_namespaces_have_default_deny_ingress():
    """
    Feature: cluster-stability, Property 4: Every operational namespace has a default-deny ingress policy

    For any operational namespace, a NetworkPolicy with podSelector: {} and
    policyTypes: [Ingress] with no ingress rules must exist.

    Validates: Requirements 5.1
    """
    assert NETWORKING_DIR.exists(), (
        f"Networking directory not found at {NETWORKING_DIR}"
    )

    all_policies = load_all_network_policies()
    assert all_policies, "No NetworkPolicy objects found in networking directory"

    # Build a set of namespaces that have a default-deny ingress policy
    namespaces_with_deny = {
        policy["metadata"]["namespace"]
        for policy in all_policies
        if is_default_deny_ingress(policy)
    }

    missing = [ns for ns in OPERATIONAL_NAMESPACES if ns not in namespaces_with_deny]

    assert not missing, (
        "The following operational namespaces are missing a default-deny ingress NetworkPolicy:\n"
        + "\n".join(f"  - {ns}" for ns in missing)
        + "\n\nEach namespace needs a policy with:\n"
        + "  podSelector: {}\n"
        + "  policyTypes: [Ingress]\n"
        + "  (no ingress rules)"
    )


def test_property_4_default_deny_policies_have_correct_structure():
    """
    Verify that each default-deny ingress policy has the exact required structure:
    - podSelector must be {} (not missing, not with matchLabels)
    - policyTypes must contain Ingress
    - ingress field must be absent or empty

    Validates: Requirements 5.1
    """
    all_policies = load_all_network_policies()

    deny_policies = [p for p in all_policies if is_default_deny_ingress(p)]
    assert deny_policies, "No default-deny ingress policies found"

    # Verify each deny policy covers an operational namespace
    deny_namespaces = {p["metadata"]["namespace"] for p in deny_policies}
    operational_covered = deny_namespaces & set(OPERATIONAL_NAMESPACES)

    assert operational_covered == set(OPERATIONAL_NAMESPACES), (
        f"Not all operational namespaces are covered. "
        f"Missing: {set(OPERATIONAL_NAMESPACES) - operational_covered}"
    )
