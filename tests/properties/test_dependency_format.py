"""Property-based tests for dependency format compliance.

Feature: tailscale-k8s-cluster, Property 15: Dependency format compliance
Validates: Requirements 6.4
"""

import re
from pathlib import Path

import tomli
from hypothesis import given
from hypothesis import strategies as st


def load_pyproject_toml():
    """Load the pyproject.toml file."""
    pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        return tomli.load(f)


def is_valid_uv_dependency_format(dep: str) -> bool:
    """
    Check if a dependency string is in valid UV-compatible format.

    Valid formats include:
    - package-name>=1.0.0
    - package-name==1.0.0
    - package-name~=1.0.0
    - package-name>=1.0.0,<2.0.0
    - package-name[extra]>=1.0.0
    - package-name
    """
    # UV supports standard PEP 508 dependency specifiers
    # Basic pattern: package-name[extras](version-spec)
    pattern = re.compile(
        r"^[a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?"  # package name
        r"(\[[a-zA-Z0-9,_-]+\])?"  # optional extras
        r"(([><=!~]+[0-9][a-zA-Z0-9.*+-]*(,[><=!~]+[0-9][a-zA-Z0-9.*+-]*)*)?)?$"  # version specs
    )
    return bool(pattern.match(dep.strip()))


def test_property_15_dependency_format_compliance():
    """
    Feature: tailscale-k8s-cluster, Property 15: Dependency format compliance

    For any Python dependency added to the project, it should be documented in
    UV-compatible format (pyproject.toml) to ensure reproducible installations.

    Validates: Requirements 6.4
    """
    pyproject = load_pyproject_toml()

    # Check main dependencies
    dependencies = pyproject.get("project", {}).get("dependencies", [])
    assert len(dependencies) > 0, "Project should have dependencies defined"

    for dep in dependencies:
        assert is_valid_uv_dependency_format(dep), (
            f"Dependency '{dep}' is not in valid UV-compatible format. "
            "Dependencies must follow PEP 508 format (e.g., 'package>=1.0.0')"
        )

    # Check optional dependencies
    optional_deps = pyproject.get("project", {}).get("optional-dependencies", {})
    for group_name, group_deps in optional_deps.items():
        for dep in group_deps:
            assert is_valid_uv_dependency_format(dep), (
                f"Optional dependency '{dep}' in group '{group_name}' is not in "
                "valid UV-compatible format"
            )


@given(
    package_name=st.from_regex(
        r"^[a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?$", fullmatch=True
    ).filter(lambda x: x.isascii()),
    version=st.from_regex(r"^[0-9]+\.[0-9]+\.[0-9]+$", fullmatch=True).filter(
        lambda x: x.isascii()
    ),
    operator=st.sampled_from([">=", "==", "~=", ">", "<", "!="]),
)
def test_valid_dependency_formats_accepted(package_name, version, operator):
    """
    Property test: Valid dependency format strings should be recognized.

    For any valid package name, version, and operator, the combined dependency
    string should be recognized as valid UV format.
    """
    dep = f"{package_name}{operator}{version}"
    assert is_valid_uv_dependency_format(dep), f"Valid dependency format '{dep}' should be accepted"


@given(
    invalid_dep=st.one_of(
        st.just(""),  # empty string
        st.just("   "),  # whitespace only
        st.just("-invalid"),  # starts with hyphen
        st.just("invalid-"),  # ends with hyphen
        st.just("invalid package"),  # contains space
        st.just("package@1.0.0"),  # wrong version separator
    )
)
def test_invalid_dependency_formats_rejected(invalid_dep):
    """
    Property test: Invalid dependency formats should be rejected.

    For any invalid dependency format, the validation should return False.
    """
    assert not is_valid_uv_dependency_format(
        invalid_dep
    ), f"Invalid dependency format '{invalid_dep}' should be rejected"


def test_pyproject_toml_has_required_sections():
    """
    Verify that pyproject.toml has all required sections for UV compatibility.
    """
    pyproject = load_pyproject_toml()

    # Required sections for UV
    assert "project" in pyproject, "pyproject.toml must have [project] section"
    assert "name" in pyproject["project"], "[project] must have 'name' field"
    assert "version" in pyproject["project"], "[project] must have 'version' field"
    assert "dependencies" in pyproject["project"], "[project] must have 'dependencies' field"

    # Build system should be defined
    assert "build-system" in pyproject, "pyproject.toml must have [build-system] section"
    assert "requires" in pyproject["build-system"], "[build-system] must have 'requires' field"
    assert (
        "build-backend" in pyproject["build-system"]
    ), "[build-system] must have 'build-backend' field"


def test_dependencies_are_pinned_or_constrained():
    """
    Verify that dependencies have version constraints for reproducibility.

    This ensures that 'uv sync' will produce reproducible installations.
    """
    pyproject = load_pyproject_toml()
    dependencies = pyproject.get("project", {}).get("dependencies", [])

    for dep in dependencies:
        # Extract package name (before any version specifier or bracket)
        package_name = re.split(r"[><=!~\[]", dep)[0].strip()

        # Check if it has a version constraint
        has_version = any(op in dep for op in [">=", "==", "~=", ">", "<", "!="])

        # For production dependencies, we should have version constraints
        # (This is a best practice for reproducibility)
        assert has_version or "[" in dep, (
            f"Dependency '{package_name}' should have a version constraint "
            "for reproducible installations (e.g., '{package_name}>=1.0.0')"
        )
