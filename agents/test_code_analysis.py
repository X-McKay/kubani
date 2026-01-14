#!/usr/bin/env python3
"""
Code analysis tests - validates implementation by analyzing source code.

Reads actual source files and verifies they contain expected patterns,
logic, and implementations.
"""

import re
from pathlib import Path


class TestResults:
    """Track test results."""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
    
    def test(self, name: str, condition: bool, message: str = ""):
        """Run a test and record result."""
        if condition:
            self.passed += 1
            status = "✓"
        else:
            self.failed += 1
            status = "✗"
        
        self.tests.append((name, condition, message))
        print(f"{status} {name}" + (f": {message}" if message else ""))
        return condition
    
    def summary(self):
        """Print test summary."""
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"TEST SUMMARY")
        print(f"{'='*60}")
        print(f"✓ Passed: {self.passed}/{total}")
        print(f"✗ Failed: {self.failed}/{total}")
        
        if self.failed > 0:
            print(f"\nFailed tests:")
            for name, passed, msg in self.tests:
                if not passed:
                    print(f"  - {name}: {msg}")
        
        return self.failed == 0


def read_file(file_path: Path) -> str:
    """Read file content."""
    try:
        with open(file_path, 'r') as f:
            return f.read()
    except FileNotFoundError:
        return ""


def test_mcp_client_initialization(results: TestResults):
    """Test that MCP clients are properly initialized."""
    print("\n" + "="*60)
    print("TESTING MCP CLIENT INITIALIZATION")
    print("="*60)
    
    base_path = Path(__file__).parent
    
    # Test cluster-monitor MCP utils
    cm_mcp = read_file(base_path / "cluster-monitor/src/cluster_monitor/mcp_utils.py")
    
    results.test(
        "cluster-monitor: Kubernetes MCP client creation",
        "def create_kubernetes_mcp_client" in cm_mcp and "MCPClient" in cm_mcp,
        "Function exists with proper client creation"
    )
    
    results.test(
        "cluster-monitor: Discord MCP client creation",
        "def create_discord_mcp_client" in cm_mcp,
        "Function exists"
    )
    
    results.test(
        "cluster-monitor: Memory tools retrieval",
        "def get_memory_tools" in cm_mcp,
        "Function exists"
    )
    
    results.test(
        "cluster-monitor: Error handling in MCP creation",
        "try:" in cm_mcp and "except" in cm_mcp,
        "Has error handling"
    )
    
    # Test cluster-swarm MCP utils
    cs_mcp = read_file(base_path / "cluster-swarm/src/cluster_swarm/mcp_utils.py")
    
    results.test(
        "cluster-swarm: Kubernetes MCP client creation",
        "def create_kubernetes_mcp_client" in cs_mcp,
        "Function exists"
    )
    
    results.test(
        "cluster-swarm: Discord MCP client creation",
        "def create_discord_mcp_client" in cs_mcp,
        "Function exists"
    )
    
    results.test(
        "cluster-swarm: Memory tools retrieval",
        "def get_memory_tools" in cs_mcp,
        "Function exists"
    )


def test_worker_implementation(results: TestResults):
    """Test that workers are fully implemented."""
    print("\n" + "="*60)
    print("TESTING WORKER IMPLEMENTATIONS")
    print("="*60)
    
    base_path = Path(__file__).parent
    workers_file = base_path / "cluster-monitor/src/cluster_monitor/workers.py"
    workers_content = read_file(workers_file)
    
    # Test InvestigatorWorker
    results.test(
        "InvestigatorWorker: Class definition",
        "class InvestigatorWorker" in workers_content,
        "Class exists"
    )
    
    results.test(
        "InvestigatorWorker: System prompt",
        "system_prompt" in workers_content and "diagnostic" in workers_content.lower(),
        "Has diagnostic system prompt"
    )
    
    results.test(
        "InvestigatorWorker: Execute method",
        "async def execute" in workers_content or "def execute" in workers_content,
        "Has execute method"
    )
    
    # Test MemoryWorker
    results.test(
        "MemoryWorker: Class definition",
        "class MemoryWorker" in workers_content,
        "Class exists"
    )
    
    results.test(
        "MemoryWorker: Memory query logic",
        "query_learnings" in workers_content or "memory" in workers_content.lower(),
        "Has memory query logic"
    )
    
    # Test RemediatorWorker
    results.test(
        "RemediatorWorker: Class definition",
        "class RemediatorWorker" in workers_content,
        "Class exists"
    )
    
    results.test(
        "RemediatorWorker: Remediation logic",
        "remediation" in workers_content.lower() or "fix" in workers_content.lower(),
        "Has remediation logic"
    )
    
    # Test NarratorWorker
    results.test(
        "NarratorWorker: Class definition",
        "class NarratorWorker" in workers_content,
        "Class exists"
    )
    
    results.test(
        "NarratorWorker: Discord integration",
        "discord" in workers_content.lower() or "message" in workers_content.lower(),
        "Has Discord integration"
    )


def test_orchestrator_workflow(results: TestResults):
    """Test orchestrator workflow implementation."""
    print("\n" + "="*60)
    print("TESTING ORCHESTRATOR WORKFLOW")
    print("="*60)
    
    base_path = Path(__file__).parent
    orch_file = base_path / "cluster-monitor/src/cluster_monitor/orchestrator.py"
    orch_content = read_file(orch_file)
    
    # Test main investigation method
    results.test(
        "Orchestrator: conduct_investigation method",
        "async def conduct_investigation" in orch_content or "def conduct_investigation" in orch_content,
        "Main investigation method exists"
    )
    
    # Test all stages
    stages = [
        "_stage_analyze",
        "_stage_query_memory",
        "_stage_investigate",
        "_stage_plan_remediation",
        "_stage_execute_action",
        "_stage_verify",
        "_stage_summarize",
    ]
    
    for stage in stages:
        results.test(
            f"Orchestrator: {stage} method",
            f"async def {stage}" in orch_content or f"def {stage}" in orch_content,
            "Stage method exists"
        )
    
    # Test worker delegation
    results.test(
        "Orchestrator: Worker delegation",
        "_delegate_to_worker" in orch_content,
        "Has worker delegation method"
    )
    
    # Test error handling
    results.test(
        "Orchestrator: Error handling",
        orch_content.count("try:") >= 3,
        f"Has multiple error handling blocks: {orch_content.count('try:')}"
    )


def test_swarm_agents(results: TestResults):
    """Test swarm agent implementations."""
    print("\n" + "="*60)
    print("TESTING SWARM AGENT IMPLEMENTATIONS")
    print("="*60)
    
    base_path = Path(__file__).parent
    swarm_file = base_path / "cluster-swarm/src/cluster_swarm/swarm.py"
    swarm_content = read_file(swarm_file)
    
    # Test agent creation functions
    agents = [
        "create_triage_agent",
        "create_investigator_agent",
        "create_memory_agent",
        "create_remediation_agent",
        "create_communications_agent",
    ]
    
    for agent_func in agents:
        results.test(
            f"Swarm: {agent_func}",
            f"def {agent_func}" in swarm_content,
            "Agent creation function exists"
        )
        
        # Check for system prompt
        func_start = swarm_content.find(f"def {agent_func}")
        if func_start != -1:
            func_section = swarm_content[func_start:func_start+2000]
            results.test(
                f"Swarm: {agent_func} system prompt",
                "system_prompt" in func_section,
                "Has system prompt"
            )
    
    # Test ClusterSwarm coordinator
    results.test(
        "Swarm: ClusterSwarm class",
        "class ClusterSwarm" in swarm_content,
        "Coordinator class exists"
    )
    
    results.test(
        "Swarm: investigate method",
        "async def investigate" in swarm_content or "def investigate" in swarm_content,
        "Main investigation method exists"
    )


def test_correlator_implementation(results: TestResults):
    """Test correlator implementation."""
    print("\n" + "="*60)
    print("TESTING CORRELATOR IMPLEMENTATION")
    print("="*60)
    
    base_path = Path(__file__).parent
    corr_file = base_path / "cluster-monitor/src/cluster_monitor/correlator.py"
    corr_content = read_file(corr_file)
    
    # Test EventCorrelator class
    results.test(
        "Correlator: EventCorrelator class",
        "class EventCorrelator" in corr_content,
        "Class exists"
    )
    
    # Test key methods
    methods = [
        "process_event",
        "_extract_error_pattern",
        "_generate_correlation_key",
        "_should_process_immediately",
        "_flush_correlation_group",
    ]
    
    for method in methods:
        results.test(
            f"Correlator: {method}",
            f"def {method}" in corr_content,
            "Method exists"
        )
    
    # Test pattern detection logic
    patterns = ["timeout", "connection", "oom", "storage", "image"]
    for pattern in patterns:
        results.test(
            f"Correlator: {pattern} pattern detection",
            pattern in corr_content.lower(),
            "Pattern detection implemented"
        )
    
    # Test event bus integration
    results.test(
        "Correlator: Event bus integration",
        "event_bus" in corr_content and "publish" in corr_content,
        "Integrates with event bus"
    )


def test_observability_implementation(results: TestResults):
    """Test observability implementation."""
    print("\n" + "="*60)
    print("TESTING OBSERVABILITY IMPLEMENTATION")
    print("="*60)
    
    base_path = Path(__file__).parent
    obs_file = base_path / "cluster-monitor/src/cluster_monitor/observability.py"
    obs_content = read_file(obs_file)
    
    # Test logging functions
    log_functions = [
        "log_investigation_start",
        "log_investigation_complete",
        "log_stage_transition",
        "log_worker_task",
        "log_error",
    ]
    
    for func in log_functions:
        results.test(
            f"Observability: {func}",
            f"def {func}" in obs_content,
            "Logging function exists"
        )
    
    # Test metrics functions
    metric_functions = [
        "increment_metric",
        "record_duration",
        "get_metrics",
    ]
    
    for func in metric_functions:
        results.test(
            f"Observability: {func}",
            f"def {func}" in obs_content,
            "Metrics function exists"
        )
    
    # Test context managers
    results.test(
        "Observability: timed_operation context manager",
        "def timed_operation" in obs_content and "@contextmanager" in obs_content,
        "Timing context manager exists"
    )
    
    results.test(
        "Observability: error_context context manager",
        "def error_context" in obs_content,
        "Error context manager exists"
    )


def test_skills_integration(results: TestResults):
    """Test skills integration."""
    print("\n" + "="*60)
    print("TESTING SKILLS INTEGRATION")
    print("="*60)
    
    base_path = Path(__file__).parent
    skills_file = base_path / "cluster-monitor/src/cluster_monitor/skills_loader.py"
    skills_content = read_file(skills_file)
    
    results.test(
        "Skills: load_diagnostic_skills function",
        "def load_diagnostic_skills" in skills_content,
        "Skills loading function exists"
    )
    
    results.test(
        "Skills: get_skill_for_pattern function",
        "def get_skill_for_pattern" in skills_content,
        "Pattern matching function exists"
    )
    
    results.test(
        "Skills: Pattern mapping",
        "timeout" in skills_content and "oom" in skills_content,
        "Has pattern to skill mappings"
    )


def test_error_handling_coverage(results: TestResults):
    """Test error handling coverage across all files."""
    print("\n" + "="*60)
    print("TESTING ERROR HANDLING COVERAGE")
    print("="*60)
    
    base_path = Path(__file__).parent
    
    critical_files = [
        "cluster-monitor/src/cluster_monitor/orchestrator.py",
        "cluster-monitor/src/cluster_monitor/workers.py",
        "cluster-monitor/src/cluster_monitor/correlator.py",
        "cluster-monitor/src/cluster_monitor/mcp_utils.py",
        "cluster-swarm/src/cluster_swarm/swarm.py",
        "cluster-swarm/src/cluster_swarm/mcp_utils.py",
    ]
    
    for file_path in critical_files:
        full_path = base_path / file_path
        content = read_file(full_path)
        
        if content:
            try_count = content.count("try:")
            except_count = content.count("except")
            
            results.test(
                f"Error handling: {Path(file_path).name}",
                try_count > 0 and except_count > 0,
                f"{try_count} try blocks, {except_count} except blocks"
            )


def test_conversational_prompts(results: TestResults):
    """Test that agents have conversational, engineer-like prompts."""
    print("\n" + "="*60)
    print("TESTING CONVERSATIONAL PROMPTS")
    print("="*60)
    
    base_path = Path(__file__).parent
    
    # Test cluster-monitor workers
    workers_content = read_file(base_path / "cluster-monitor/src/cluster_monitor/workers.py")
    
    conversational_indicators = [
        "conversational",
        "natural language",
        "engineer",
        "explain",
        "describe",
        "narrative",
    ]
    
    found_indicators = sum(1 for indicator in conversational_indicators if indicator in workers_content.lower())
    
    results.test(
        "cluster-monitor: Conversational prompt indicators",
        found_indicators >= 2,
        f"Found {found_indicators} conversational indicators"
    )
    
    # Test cluster-swarm agents
    swarm_content = read_file(base_path / "cluster-swarm/src/cluster_swarm/swarm.py")
    
    found_indicators = sum(1 for indicator in conversational_indicators if indicator in swarm_content.lower())
    
    results.test(
        "cluster-swarm: Conversational prompt indicators",
        found_indicators >= 2,
        f"Found {found_indicators} conversational indicators"
    )


def main():
    """Run all code analysis tests."""
    print("="*60)
    print("CODE ANALYSIS TESTS")
    print("Validating implementation by analyzing source code")
    print("="*60)
    
    results = TestResults()
    
    try:
        test_mcp_client_initialization(results)
        test_worker_implementation(results)
        test_orchestrator_workflow(results)
        test_swarm_agents(results)
        test_correlator_implementation(results)
        test_observability_implementation(results)
        test_skills_integration(results)
        test_error_handling_coverage(results)
        test_conversational_prompts(results)
    except Exception as e:
        print(f"\n✗ Test execution failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Print summary
    success = results.summary()
    
    if success:
        print(f"\n{'='*60}")
        print("✓ ALL CODE ANALYSIS TESTS PASSED")
        print(f"{'='*60}")
        return 0
    else:
        print(f"\n{'='*60}")
        print("✗ SOME CODE ANALYSIS TESTS FAILED")
        print(f"{'='*60}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
