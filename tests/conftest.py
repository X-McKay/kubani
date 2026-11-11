"""Fail the run when a tests/test_*.py file contributes no tests.

A file that pytest collects but that yields nothing (a misspelt class name, a
body of bare helpers, an import guarded away) would otherwise pass unnoticed.
Only meaningful for runs that select whole files, so it skips when `-k` or `-m`
deselects tests or when the run is limited to specific tests.
"""

from pathlib import Path

import pytest

_HERE = Path(__file__).parent
_collected: set[Path] = set()


def pytest_collection_modifyitems(config, items):
    for item in items:
        _collected.add(Path(str(item.path)).resolve())


def pytest_collectreport(report):
    # A module skipped wholesale (importorskip) is visible as a skip, not silent.
    if report.skipped and report.nodeid.startswith("tests/"):
        _collected.add((_HERE.parent / report.nodeid).resolve())


def pytest_sessionfinish(session, exitstatus):
    config = session.config
    if config.getoption("keyword") or config.getoption("markexpr"):
        return
    if any("::" in str(a) for a in config.args):
        return
    selected = []
    for arg in config.args or [str(_HERE)]:
        path = Path(str(arg).split("::")[0]).resolve()
        if path.is_dir():
            selected += sorted(path.glob("test_*.py")) if path == _HERE else []
        elif path.name.startswith("test_") and path.parent == _HERE:
            selected.append(path)
    empty = [p.name for p in selected if p.resolve() not in _collected]
    if empty and exitstatus in (0, 1):
        print(f"\nERROR: test files that contributed zero tests: {', '.join(empty)}")
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
