"""Bounded offline registry and complete Kustomize validation."""

from pathlib import Path
from . import model, render


def check(root: Path) -> list[str]:
    try:
        entries = model.load_registry(root)
        expected = render.render(root, entries)
        findings = []
        for p, data in expected.items():
            path = model.safe_path(root, p)
            if not path.is_file() or path.read_bytes() != data:
                findings.append("stale or missing generated output: " + p)
        if findings:
            return findings[:20]
        render.validate_effective(root, entries, render.build(root))
        return []
    except (ValueError, OSError, KeyError, TypeError, StopIteration) as exc:
        return ["registry validation failed: " + str(exc)[:1000]]
