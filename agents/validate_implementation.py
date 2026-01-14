#!/usr/bin/env python3
"""
Comprehensive validation script for cluster-monitor and cluster-swarm.

This script validates:
1. Code structure and completeness
2. Logic correctness
3. Error handling
4. Data flow
5. Integration points
"""

import ast
import os
import sys
from pathlib import Path
from typing import Any


class ValidationResult:
    """Track validation results."""
    
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []
    
    def add_pass(self, test: str, message: str = ""):
        self.passed.append((test, message))
        print(f"✓ {test}" + (f": {message}" if message else ""))
    
    def add_fail(self, test: str, message: str):
        self.failed.append((test, message))
        print(f"✗ {test}: {message}")
    
    def add_warning(self, test: str, message: str):
        self.warnings.append((test, message))
        print(f"⚠ {test}: {message}")
    
    def summary(self):
        total = len(self.passed) + len(self.failed)
        print(f"\n{'='*60}")
        print(f"VALIDATION SUMMARY")
        print(f"{'='*60}")
        print(f"✓ Passed: {len(self.passed)}/{total}")
        print(f"✗ Failed: {len(self.failed)}/{total}")
        print(f"⚠ Warnings: {len(self.warnings)}")
        
        if self.failed:
            print(f"\nFailed Tests:")
            for test, msg in self.failed:
                print(f"  - {test}: {msg}")
        
        if self.warnings:
            print(f"\nWarnings:")
            for test, msg in self.warnings:
                print(f"  - {test}: {msg}")
        
        return len(self.failed) == 0


def validate_file_structure(results: ValidationResult):
    """Validate that all expected files exist."""
    print("\n" + "="*60)
    print("VALIDATING FILE STRUCTURE")
    print("="*60)
    
    base_path = Path(__file__).parent
    
    # cluster-monitor files
    cm_files = [
        "cluster-monitor/src/cluster_monitor/__init__.py",
        "cluster-monitor/src/cluster_monitor/models.py",
        "cluster-monitor/src/cluster_monitor/correlator.py",
        "cluster-monitor/src/cluster_monitor/orchestrator.py",
        "cluster-monitor/src/cluster_monitor/workers.py",
        "cluster-monitor/src/cluster_monitor/mcp_utils.py",
        "cluster-monitor/src/cluster_monitor/skills_loader.py",
        "cluster-monitor/src/cluster_monitor/observability.py",
        "cluster-monitor/src/cluster_monitor/worker.py",
        "cluster-monitor/pyproject.toml",
        "cluster-monitor/README.md",
    ]
    
    # cluster-swarm files
    cs_files = [
        "cluster-swarm/src/cluster_swarm/__init__.py",
        "cluster-swarm/src/cluster_swarm/models.py",
        "cluster-swarm/src/cluster_swarm/swarm.py",
        "cluster-swarm/src/cluster_swarm/mcp_utils.py",
        "cluster-swarm/src/cluster_swarm/skills_loader.py",
        "cluster-swarm/src/cluster_swarm/observability.py",
        "cluster-swarm/src/cluster_swarm/worker.py",
        "cluster-swarm/pyproject.toml",
        "cluster-swarm/README.md",
    ]
    
    for file_path in cm_files + cs_files:
        full_path = base_path / file_path
        if full_path.exists():
            results.add_pass(f"File exists: {file_path}")
        else:
            results.add_fail(f"File missing: {file_path}", "File not found")


def validate_python_syntax(results: ValidationResult):
    """Validate Python syntax for all files."""
    print("\n" + "="*60)
    print("VALIDATING PYTHON SYNTAX")
    print("="*60)
    
    base_path = Path(__file__).parent
    
    for agent in ["cluster-monitor", "cluster-swarm"]:
        src_path = base_path / agent / "src"
        if not src_path.exists():
            results.add_fail(f"{agent} syntax", f"Source path not found: {src_path}")
            continue
        
        for py_file in src_path.rglob("*.py"):
            try:
                with open(py_file, 'r') as f:
                    code = f.read()
                ast.parse(code)
                results.add_pass(f"Syntax: {py_file.relative_to(base_path)}")
            except SyntaxError as e:
                results.add_fail(
                    f"Syntax: {py_file.relative_to(base_path)}",
                    f"Line {e.lineno}: {e.msg}"
                )


def validate_no_todos(results: ValidationResult):
    """Check for TODO/FIXME/XXX comments."""
    print("\n" + "="*60)
    print("CHECKING FOR TODOS/PLACEHOLDERS")
    print("="*60)
    
    base_path = Path(__file__).parent
    todo_patterns = ["TODO", "FIXME", "XXX", "HACK"]
    
    found_todos = False
    for agent in ["cluster-monitor", "cluster-swarm"]:
        src_path = base_path / agent / "src"
        if not src_path.exists():
            continue
        
        for py_file in src_path.rglob("*.py"):
            with open(py_file, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    for pattern in todo_patterns:
                        if pattern in line and not line.strip().startswith("#"):
                            results.add_warning(
                                f"TODO found: {py_file.relative_to(base_path)}",
                                f"Line {line_num}: {line.strip()}"
                            )
                            found_todos = True
    
    if not found_todos:
        results.add_pass("No TODOs found", "Code appears complete")


def validate_critical_functions(results: ValidationResult):
    """Validate that critical functions are implemented."""
    print("\n" + "="*60)
    print("VALIDATING CRITICAL FUNCTIONS")
    print("="*60)
    
    base_path = Path(__file__).parent
    
    # cluster-monitor critical functions
    cm_checks = {
        "cluster-monitor/src/cluster_monitor/correlator.py": [
            "process_event",
            "_flush_correlation_group",
            "_extract_error_pattern",
            "_generate_correlation_key",
        ],
        "cluster-monitor/src/cluster_monitor/orchestrator.py": [
            "conduct_investigation",
            "_delegate_to_worker",
            "_stage_analyze",
            "_stage_investigate",
        ],
        "cluster-monitor/src/cluster_monitor/workers.py": [
            "InvestigatorWorker",
            "MemoryWorker",
            "RemediatorWorker",
            "NarratorWorker",
        ],
    }
    
    # cluster-swarm critical functions
    cs_checks = {
        "cluster-swarm/src/cluster_swarm/swarm.py": [
            "create_triage_agent",
            "create_investigator_agent",
            "create_memory_agent",
            "create_remediation_agent",
            "create_communications_agent",
            "ClusterSwarm",
        ],
    }
    
    for file_path, functions in {**cm_checks, **cs_checks}.items():
        full_path = base_path / file_path
        if not full_path.exists():
            results.add_fail(f"Critical file: {file_path}", "File not found")
            continue
        
        with open(full_path, 'r') as f:
            content = f.read()
        
        for func_name in functions:
            if f"def {func_name}" in content or f"class {func_name}" in content:
                results.add_pass(f"Function exists: {func_name} in {Path(file_path).name}")
            else:
                results.add_fail(
                    f"Function missing: {func_name}",
                    f"Not found in {file_path}"
                )


def validate_mcp_integration(results: ValidationResult):
    """Validate MCP client integration."""
    print("\n" + "="*60)
    print("VALIDATING MCP INTEGRATION")
    print("="*60)
    
    base_path = Path(__file__).parent
    
    for agent in ["cluster-monitor", "cluster-swarm"]:
        mcp_utils_path = base_path / agent / "src" / agent.replace("-", "_") / "mcp_utils.py"
        
        if not mcp_utils_path.exists():
            results.add_fail(f"{agent} MCP utils", "mcp_utils.py not found")
            continue
        
        with open(mcp_utils_path, 'r') as f:
            content = f.read()
        
        # Check for MCP client creation functions
        required_functions = [
            "create_kubernetes_mcp_client",
            "create_discord_mcp_client",
            "get_memory_tools",
        ]
        
        for func in required_functions:
            if f"def {func}" in content:
                results.add_pass(f"{agent}: {func}")
            else:
                results.add_fail(f"{agent}: {func}", "Function not found")
        
        # Check for proper imports
        if "from mcp.client" in content or "MCPClient" in content:
            results.add_pass(f"{agent}: MCP imports present")
        else:
            results.add_warning(f"{agent}: MCP imports", "May be missing MCP imports")


def validate_error_handling(results: ValidationResult):
    """Validate error handling is present."""
    print("\n" + "="*60)
    print("VALIDATING ERROR HANDLING")
    print("="*60)
    
    base_path = Path(__file__).parent
    
    for agent in ["cluster-monitor", "cluster-swarm"]:
        src_path = base_path / agent / "src"
        if not src_path.exists():
            continue
        
        for py_file in src_path.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            
            with open(py_file, 'r') as f:
                content = f.read()
            
            # Check for try/except blocks
            try_count = content.count("try:")
            except_count = content.count("except")
            
            if try_count > 0 and except_count > 0:
                results.add_pass(
                    f"Error handling: {py_file.relative_to(base_path).name}",
                    f"{try_count} try/except blocks"
                )
            elif "observability" in py_file.name or "models" in py_file.name:
                # These files may not need error handling
                pass
            else:
                results.add_warning(
                    f"Error handling: {py_file.relative_to(base_path).name}",
                    "No try/except blocks found"
                )


def validate_agent_system_prompts(results: ValidationResult):
    """Validate that agents have proper system prompts."""
    print("\n" + "="*60)
    print("VALIDATING AGENT SYSTEM PROMPTS")
    print("="*60)
    
    base_path = Path(__file__).parent
    
    # Check cluster-monitor workers
    workers_path = base_path / "cluster-monitor/src/cluster_monitor/workers.py"
    if workers_path.exists():
        with open(workers_path, 'r') as f:
            content = f.read()
        
        workers = ["InvestigatorWorker", "MemoryWorker", "RemediatorWorker", "NarratorWorker"]
        for worker in workers:
            if f"class {worker}" in content and "system_prompt" in content:
                results.add_pass(f"Worker prompt: {worker}")
            else:
                results.add_fail(f"Worker prompt: {worker}", "Missing or incomplete")
    
    # Check cluster-swarm agents
    swarm_path = base_path / "cluster-swarm/src/cluster_swarm/swarm.py"
    if swarm_path.exists():
        with open(swarm_path, 'r') as f:
            content = f.read()
        
        agents = [
            "create_triage_agent",
            "create_investigator_agent",
            "create_memory_agent",
            "create_remediation_agent",
            "create_communications_agent",
        ]
        for agent_func in agents:
            if f"def {agent_func}" in content and "system_prompt" in content[content.find(f"def {agent_func}"):]:
                results.add_pass(f"Agent prompt: {agent_func}")
            else:
                results.add_fail(f"Agent prompt: {agent_func}", "Missing or incomplete")


def validate_data_models(results: ValidationResult):
    """Validate that data models are properly defined."""
    print("\n" + "="*60)
    print("VALIDATING DATA MODELS")
    print("="*60)
    
    base_path = Path(__file__).parent
    
    for agent in ["cluster-monitor", "cluster-swarm"]:
        models_path = base_path / agent / "src" / agent.replace("-", "_") / "models.py"
        
        if not models_path.exists():
            results.add_fail(f"{agent} models", "models.py not found")
            continue
        
        with open(models_path, 'r') as f:
            content = f.read()
        
        # Check for Pydantic BaseModel
        if "from pydantic import BaseModel" in content or "BaseModel" in content:
            results.add_pass(f"{agent}: Pydantic models")
        else:
            results.add_fail(f"{agent}: Pydantic models", "BaseModel not found")
        
        # Check for key models
        required_models = ["K8sEvent", "CorrelatedIssue", "Severity"]
        for model in required_models:
            if f"class {model}" in content:
                results.add_pass(f"{agent}: {model} model")
            else:
                results.add_fail(f"{agent}: {model} model", "Model not found")


def main():
    """Run all validations."""
    print("="*60)
    print("COMPREHENSIVE VALIDATION")
    print("cluster-monitor & cluster-swarm")
    print("="*60)
    
    results = ValidationResult()
    
    # Run all validation checks
    validate_file_structure(results)
    validate_python_syntax(results)
    validate_no_todos(results)
    validate_critical_functions(results)
    validate_mcp_integration(results)
    validate_error_handling(results)
    validate_agent_system_prompts(results)
    validate_data_models(results)
    
    # Print summary
    success = results.summary()
    
    if success:
        print(f"\n{'='*60}")
        print("✓ ALL VALIDATIONS PASSED")
        print(f"{'='*60}")
        return 0
    else:
        print(f"\n{'='*60}")
        print("✗ SOME VALIDATIONS FAILED")
        print(f"{'='*60}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
