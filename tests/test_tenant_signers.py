"""Kyverno's tenant signer pins agree with the Namespace annotations and are sound.

Kyverno Rule 1 reads ConfigMap kyverno/tenant-signers (GitOps only). The Registry
Controller reads the tenant Namespace's agentplatform.io/signer-* annotations. Both
must hold the same declaration, and neither may be empty or unanchored: Kyverno
skips the subject check entirely when subjectRegExp is "".
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
GITOPS = ROOT / "infrastructure/gitops/infrastructure"
SIGNERS = GITOPS / "kyverno/tenant-signers.yaml"
NAMESPACES = GITOPS / "namespace-policy/agent-platform-namespaces.yaml"

ISSUER = "agentplatform.io/signer-issuer"
SUBJECT = "agentplatform.io/signer-subject-regexp"
EXCEPTIONS = "agentplatform.io/vuln-exceptions"
TENANT_LABEL = "agentplatform.io/tenant"
CVE_ID = re.compile(r"^[A-Za-z0-9.:_-]+$")


def tenant_namespaces() -> dict[str, dict]:
    docs = [d for d in yaml.safe_load_all(NAMESPACES.read_text()) if d]
    return {
        d["metadata"]["name"]: d["metadata"]
        for d in docs
        if d.get("kind") == "Namespace" and TENANT_LABEL in (d["metadata"].get("labels") or {})
    }


def signer_pins() -> dict[str, dict]:
    data = yaml.safe_load(SIGNERS.read_text())["data"] or {}
    return {name: json.loads(value) for name, value in data.items()}


def anchored(pattern: str) -> bool:
    body = pattern[:-1]
    backslashes = len(body) - len(body.rstrip("\\"))
    return pattern.startswith("^") and pattern.endswith("$") and backslashes % 2 == 0


def top_level_alternation(pattern: str) -> bool:
    depth, in_class, i = 0, False, 0
    while i < len(pattern):
        c = pattern[i]
        if c == "\\":
            i += 2
            continue
        if in_class:
            in_class = c != "]"
        elif c == "[":
            in_class = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "|" and depth == 0:
            return True
        i += 1
    return False


class TenantSignersTest(unittest.TestCase):
    def test_every_tenant_has_exactly_one_pin(self) -> None:
        self.assertEqual(sorted(signer_pins()), sorted(tenant_namespaces()))

    def test_pins_are_sound(self) -> None:
        for name, pin in signer_pins().items():
            with self.subTest(tenant=name):
                self.assertEqual(set(pin), {"issuer", "subjectRegExp", "vulnExceptions"})
                self.assertTrue(pin["issuer"].startswith("https://"))
                subject = pin["subjectRegExp"]
                self.assertTrue(anchored(subject), subject)
                self.assertFalse(top_level_alternation(subject[1:-1]), subject)
                re.compile(subject)
                self.assertIsInstance(pin["vulnExceptions"], list)
                for vid in pin["vulnExceptions"]:
                    self.assertRegex(vid, CVE_ID)

    def test_pins_equal_namespace_annotations(self) -> None:
        pins = signer_pins()
        for name, meta in tenant_namespaces().items():
            with self.subTest(tenant=name):
                annotations = meta.get("annotations") or {}
                pin = pins.get(name, {})
                self.assertEqual(annotations.get(ISSUER), pin.get("issuer"))
                self.assertEqual(annotations.get(SUBJECT), pin.get("subjectRegExp"))
                exceptions = [
                    v.strip() for v in (annotations.get(EXCEPTIONS) or "").split(",") if v.strip()
                ]
                self.assertEqual(exceptions, pin.get("vulnExceptions"))

    def test_checks_reject_unsafe_patterns(self) -> None:
        self.assertFalse(anchored(".*"))
        self.assertFalse(anchored(""))
        self.assertFalse(anchored(r"^a\$"))
        self.assertTrue(anchored(r"^a\\$"))
        self.assertTrue(top_level_alternation("a|.*"))
        self.assertFalse(top_level_alternation("(?:a|b)"))


if __name__ == "__main__":
    unittest.main()
