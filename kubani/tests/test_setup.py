"""Verify test infrastructure is working."""


def test_pytest_working():
    """Basic test to verify pytest is functional."""
    assert True


def test_directory_structure_exists():
    """Verify test directory structure is in place."""
    from pathlib import Path

    tests_dir = Path(__file__).parent
    assert (tests_dir / "unit").exists()
    assert (tests_dir / "integration").exists()
    assert (tests_dir / "fixtures").exists()
    assert (tests_dir / "conftest.py").exists()
