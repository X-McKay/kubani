"""Fail the run when a test file that pytest collected yields no tests.

A file that is collected but yields nothing (a misspelt class name, a body of
bare helpers) would otherwise pass unnoticed. Only files pytest actually
collected are judged, and they are judged at collection, before `-k`, `-m` or
`--deselect` remove anything, so narrowing a run never trips the guard. A file
that was not collected (`--ignore`, or simply not named) is not a file that
came up empty, and a module skipped whole (`importorskip`) shows as a skip.

`--lf` is the one exception: pytest reports the files it passes over as
collected and empty, which is indistinguishable from a truly empty file, so the
guard stands down for that run.
"""

import pytest

_modules: set[str] = set()  # test modules collected without an error or a skip
_with_tests: set[str] = set()  # the ones that yielded at least one test


def pytest_collectreport(report):
    nodeid = report.nodeid
    if report.passed and "::" not in nodeid and nodeid.endswith(".py"):
        if nodeid.rsplit("/", 1)[-1].startswith("test_"):
            _modules.add(nodeid)


def pytest_itemcollected(item):
    _with_tests.add(item.nodeid.split("::", 1)[0])


def pytest_sessionfinish(session, exitstatus):
    if session.config.getoption("lf", False):
        return
    empty = sorted(_modules - _with_tests)
    judged = (pytest.ExitCode.OK, pytest.ExitCode.TESTS_FAILED, pytest.ExitCode.NO_TESTS_COLLECTED)
    if empty and exitstatus in judged:
        print(f"\nERROR: test files that contributed zero tests: {', '.join(empty)}")
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
