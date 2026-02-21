"""
Tests to verify that Nexus codebase does not import from legacy modules.

These tests ensure architectural isolation by verifying that the new Nexus
implementation does not depend on legacy code that is being replaced.

Requirements: 18.1-18.7
"""

import ast
import os
from pathlib import Path
from typing import Set

import pytest


def get_nexus_python_files() -> list[Path]:
    """Get all Python files in the kubani/nexus directory."""
    nexus_dir = Path("kubani/nexus")
    if not nexus_dir.exists():
        pytest.skip(f"Nexus directory not found: {nexus_dir}")
    
    python_files = []
    for root, dirs, files in os.walk(nexus_dir):
        # Skip __pycache__ directories
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        
        for file in files:
            if file.endswith(".py"):
                python_files.append(Path(root) / file)
    
    return python_files


def extract_imports_from_file(file_path: Path) -> Set[str]:
    """
    Extract all import statements from a Python file.
    
    Returns a set of module names that are imported.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        tree = ast.parse(content, filename=str(file_path))
        imports = set()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
        
        return imports
    except SyntaxError:
        # If file has syntax errors, skip it
        return set()


def check_no_imports_from_module(module_path: str) -> tuple[bool, list[tuple[Path, str]]]:
    """
    Check that no Nexus files import from the specified module.
    
    Args:
        module_path: The module path to check (e.g., "kubani.syndicates.k8s_monitor")
    
    Returns:
        Tuple of (all_clean, violations) where violations is a list of (file, import) tuples
    """
    nexus_files = get_nexus_python_files()
    violations = []
    
    for file_path in nexus_files:
        imports = extract_imports_from_file(file_path)
        
        for import_name in imports:
            # Check if this import is from the forbidden module
            if import_name.startswith(module_path):
                violations.append((file_path, import_name))
    
    return len(violations) == 0, violations


class TestLegacyCodeRemoval:
    """Tests to verify legacy code has been properly removed or isolated."""
    
    def test_no_k8s_monitor_imports(self):
        """
        Test that Nexus codebase does not import from kubani/syndicates/k8s_monitor.
        
        Requirements: 18.1
        """
        all_clean, violations = check_no_imports_from_module("kubani.syndicates.k8s_monitor")
        
        if not all_clean:
            violation_details = "\n".join(
                f"  - {file.relative_to('.')}: imports {import_name}"
                for file, import_name in violations
            )
            pytest.fail(
                f"Found {len(violations)} import(s) from kubani.syndicates.k8s_monitor:\n"
                f"{violation_details}"
            )
    
    def test_no_news_digest_imports(self):
        """
        Test that Nexus codebase does not import from kubani/syndicates/news_digest.
        
        Requirements: 18.2
        """
        all_clean, violations = check_no_imports_from_module("kubani.syndicates.news_digest")
        
        if not all_clean:
            violation_details = "\n".join(
                f"  - {file.relative_to('.')}: imports {import_name}"
                for file, import_name in violations
            )
            pytest.fail(
                f"Found {len(violations)} import(s) from kubani.syndicates.news_digest:\n"
                f"{violation_details}"
            )
    
    def test_no_agent_auto_imports(self):
        """
        Test that Nexus codebase does not import from kubani/workflows/agent_auto.
        
        Requirements: 18.3
        """
        all_clean, violations = check_no_imports_from_module("kubani.workflows.agent_auto")
        
        if not all_clean:
            violation_details = "\n".join(
                f"  - {file.relative_to('.')}: imports {import_name}"
                for file, import_name in violations
            )
            pytest.fail(
                f"Found {len(violations)} import(s) from kubani.workflows.agent_auto:\n"
                f"{violation_details}"
            )
    
    def test_no_skill_auto_imports(self):
        """
        Test that Nexus codebase does not import from kubani/workflows/skill_auto.
        
        Requirements: 18.4
        """
        all_clean, violations = check_no_imports_from_module("kubani.workflows.skill_auto")
        
        if not all_clean:
            violation_details = "\n".join(
                f"  - {file.relative_to('.')}: imports {import_name}"
                for file, import_name in violations
            )
            pytest.fail(
                f"Found {len(violations)} import(s) from kubani.workflows.skill_auto:\n"
                f"{violation_details}"
            )
    
    def test_no_framework_temporal_imports(self):
        """
        Test that Nexus orchestrator does not depend on kubani/framework/temporal.
        
        Requirements: 18.5
        """
        all_clean, violations = check_no_imports_from_module("kubani.framework.temporal")
        
        if not all_clean:
            violation_details = "\n".join(
                f"  - {file.relative_to('.')}: imports {import_name}"
                for file, import_name in violations
            )
            pytest.fail(
                f"Found {len(violations)} import(s) from kubani.framework.temporal:\n"
                f"{violation_details}"
            )
    
    def test_no_framework_temporal_memory_imports(self):
        """
        Test that Nexus memory client does not depend on kubani/framework/temporal/memory.py.
        
        Requirements: 18.6
        """
        # Check specifically for imports from kubani.framework.temporal.memory
        all_clean, violations = check_no_imports_from_module("kubani.framework.temporal.memory")
        
        if not all_clean:
            violation_details = "\n".join(
                f"  - {file.relative_to('.')}: imports {import_name}"
                for file, import_name in violations
            )
            pytest.fail(
                f"Found {len(violations)} import(s) from kubani.framework.temporal.memory:\n"
                f"{violation_details}"
            )
    
    def test_no_framework_events_imports(self):
        """
        Test that Nexus pubsub does not depend on kubani/framework/events.
        
        Requirements: 18.7
        """
        all_clean, violations = check_no_imports_from_module("kubani.framework.events")
        
        if not all_clean:
            violation_details = "\n".join(
                f"  - {file.relative_to('.')}: imports {import_name}"
                for file, import_name in violations
            )
            pytest.fail(
                f"Found {len(violations)} import(s) from kubani.framework.events:\n"
                f"{violation_details}"
            )


class TestLegacyCodeRemovalComprehensive:
    """Additional comprehensive tests for legacy code isolation."""
    
    def test_nexus_files_exist(self):
        """Verify that Nexus directory and files exist."""
        nexus_dir = Path("kubani/nexus")
        assert nexus_dir.exists(), "Nexus directory should exist"
        
        python_files = get_nexus_python_files()
        assert len(python_files) > 0, "Nexus directory should contain Python files"
    
    def test_all_legacy_modules_absent(self):
        """
        Comprehensive test that checks all legacy modules at once.
        
        This provides a single overview of all legacy dependencies.
        """
        legacy_modules = [
            "kubani.syndicates.k8s_monitor",
            "kubani.syndicates.news_digest",
            "kubani.workflows.agent_auto",
            "kubani.workflows.skill_auto",
            "kubani.framework.temporal",
            "kubani.framework.temporal.memory",
            "kubani.framework.events",
        ]
        
        all_violations = []
        
        for module in legacy_modules:
            all_clean, violations = check_no_imports_from_module(module)
            if not all_clean:
                all_violations.extend([(module, file, import_name) for file, import_name in violations])
        
        if all_violations:
            violation_summary = {}
            for module, file, import_name in all_violations:
                if module not in violation_summary:
                    violation_summary[module] = []
                violation_summary[module].append((file, import_name))
            
            details = []
            for module, violations in violation_summary.items():
                details.append(f"\n{module}:")
                for file, import_name in violations:
                    details.append(f"  - {file.relative_to('.')}: imports {import_name}")
            
            pytest.fail(
                f"Found {len(all_violations)} legacy import(s) in Nexus codebase:"
                f"{''.join(details)}"
            )
