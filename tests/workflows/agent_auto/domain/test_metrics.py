# tests/workflows/agent_auto/domain/test_metrics.py
"""Unit tests for the metrics functions."""

import pytest

from kubani.workflows.agent_auto.domain.metrics import (
    calculate_skill_precision,
    calculate_skill_recall,
)


@pytest.mark.parametrize(
    "invoked, required, expected_precision, expected_recall",
    [
        ({"a", "b"}, {"a", "b"}, 1.0, 1.0),  # Perfect match
        ({"a"}, {"a", "b"}, 1.0, 0.5),  # Missed one (low recall)
        ({"a", "b"}, {"a"}, 0.5, 1.0),  # Invoked extra (low precision)
        ({"c"}, {"a", "b"}, 0.0, 0.0),  # Completely wrong
        (set(), {"a"}, 1.0, 0.0),  # Invoked none, required some
        ({"a"}, set(), 0.0, 1.0),  # Invoked some, required none
        (set(), set(), 1.0, 1.0),  # Invoked none, required none
    ],
)
def test_skill_metrics(invoked, required, expected_precision, expected_recall):
    """Test skill precision and recall calculations with various inputs."""
    precision = calculate_skill_precision(invoked, required)
    recall = calculate_skill_recall(invoked, required)
    assert precision == pytest.approx(expected_precision)
    assert recall == pytest.approx(expected_recall)


def test_skill_precision_with_partial_overlap():
    """Test precision when some invoked skills are correct and some are not."""
    invoked = {"a", "b", "c"}
    required = {"a", "b", "d"}  # c is wrong, d is missing

    precision = calculate_skill_precision(invoked, required)

    # 2 correct out of 3 invoked
    assert precision == pytest.approx(2 / 3)


def test_skill_recall_with_partial_overlap():
    """Test recall when some required skills are invoked and some are not."""
    invoked = {"a", "b", "c"}
    required = {"a", "b", "d"}  # c is extra, d is missing

    recall = calculate_skill_recall(invoked, required)

    # 2 correct out of 3 required
    assert recall == pytest.approx(2 / 3)
