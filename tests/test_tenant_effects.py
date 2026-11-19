"""The effects each tenant grants are exactly the ones listed here.

A grant is the Namespace annotation agentplatform.io/granted-effects (zetra skills
contract, section 7): the Registry Controller makes a release Ready only when the
tenant grants every effect the release asks for. A new grant, or a grant in another
tenant, is therefore a change to GRANTS below as well as to the manifest, and both
are read in one pull request.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GITOPS = ROOT / "infrastructure/gitops"
OPS = ROOT / "infrastructure/scripts/ops"
sys.path.insert(0, str(OPS))
from agent_ops import approve  # noqa: E402

ANNOTATION = "agentplatform.io/granted-effects"
TENANT_LABEL = "agentplatform.io/tenant"

# Tenant Namespace -> the effects it grants. Nothing else may grant anything.
GRANTS = {"tenant-test": ["sandbox_execute"]}


def namespaces() -> list[tuple[Path, dict]]:
    found = []
    for path in sorted(GITOPS.rglob("*.yaml")):
        if path.name.endswith(".enc.yaml"):
            continue
        text = path.read_text(encoding="utf-8")
        if "kind: Namespace" not in text:
            continue
        for doc in yaml.safe_load_all(text):
            if isinstance(doc, dict) and doc.get("kind") == "Namespace":
                found.append((path, doc))
    return found


def granted(doc: dict) -> list[str] | None:
    value = (doc.get("metadata", {}).get("annotations") or {}).get(ANNOTATION)
    if value is None:
        return None
    return sorted(name.strip() for name in str(value).split(",") if name.strip())


class TenantEffects(unittest.TestCase):
    def test_the_committed_grants_are_the_listed_ones(self):
        seen = {doc["metadata"]["name"]: granted(doc) for _, doc in namespaces() if granted(doc) is not None}
        self.assertEqual(seen, GRANTS)

    def test_only_a_tenant_namespace_carries_a_grant(self):
        for path, doc in namespaces():
            if granted(doc) is not None:
                labels = doc["metadata"].get("labels") or {}
                self.assertEqual(labels.get(TENANT_LABEL), doc["metadata"]["name"], path)

    def test_a_grant_is_written_once_in_the_form_the_controller_reads(self):
        for path, doc in namespaces():
            value = (doc["metadata"].get("annotations") or {}).get(ANNOTATION)
            if value is not None:
                self.assertIsInstance(value, str, path)
                self.assertEqual(value, ",".join(granted(doc)), path)
                self.assertEqual(len(set(granted(doc))), len(granted(doc)), path)

    def test_every_granted_effect_is_one_an_approval_can_describe(self):
        for effects in GRANTS.values():
            for effect in effects:
                self.assertIn(effect, approve.EFFECT_STATEMENTS)


if __name__ == "__main__":
    unittest.main()
