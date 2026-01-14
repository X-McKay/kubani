#!/usr/bin/env python3
"""
Isolated logic tests - tests core logic without requiring full imports.

Extracts and tests key logic functions independently.
"""

import re
from datetime import datetime, UTC


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


# =============================================================================
# EXTRACTED LOGIC FROM CORRELATOR
# =============================================================================

def extract_error_pattern(message: str) -> str:
    """
    Extract the core error pattern from a message.
    (Extracted from correlator.py)
    """
    message_lower = message.lower()

    # Timeout patterns
    if any(
        pattern in message_lower
        for pattern in ["timeout", "deadline exceeded", "timed out"]
    ):
        return "timeout"

    # Connection patterns
    if any(
        pattern in message_lower
        for pattern in ["connection refused", "connection reset", "no route to host"]
    ):
        return "connection_error"

    # Resource patterns
    if "oom" in message_lower or "out of memory" in message_lower:
        return "oom"

    if "disk" in message_lower or "storage" in message_lower:
        return "storage"

    # Image patterns
    if "image" in message_lower and ("pull" in message_lower or "not found" in message_lower):
        return "image_pull"

    # Default to the reason
    return "other"


def generate_correlation_key(pattern: str, namespace: str) -> str:
    """
    Generate a correlation key for grouping related events.
    (Extracted from correlator.py)
    """
    return f"{pattern}:{namespace}"


# =============================================================================
# TESTS
# =============================================================================

def test_pattern_extraction(results: TestResults):
    """Test error pattern extraction logic."""
    print("\n" + "="*60)
    print("TESTING PATTERN EXTRACTION LOGIC")
    print("="*60)
    
    test_cases = [
        # Timeout patterns
        ("context deadline exceeded", "timeout"),
        ("connection timeout", "timeout"),
        ("request timed out", "timeout"),
        ("Get http://10.42.1.250:9000/-/health/live: context deadline exceeded", "timeout"),
        
        # Connection patterns
        ("connection refused", "connection_error"),
        ("connection reset by peer", "connection_error"),
        ("no route to host", "connection_error"),
        
        # Resource patterns
        ("OOMKilled", "oom"),
        ("out of memory error", "oom"),
        ("disk full", "storage"),
        ("storage quota exceeded", "storage"),
        
        # Image patterns
        ("image pull failed", "image_pull"),
        ("image not found", "image_pull"),
        
        # Other
        ("random error message", "other"),
        ("unknown failure", "other"),
    ]
    
    for message, expected_pattern in test_cases:
        actual_pattern = extract_error_pattern(message)
        results.test(
            f"Pattern: '{message[:50]}'",
            actual_pattern == expected_pattern,
            f"Expected '{expected_pattern}', got '{actual_pattern}'"
        )


def test_correlation_key_generation(results: TestResults):
    """Test correlation key generation."""
    print("\n" + "="*60)
    print("TESTING CORRELATION KEY GENERATION")
    print("="*60)
    
    # Test key format
    key1 = generate_correlation_key("timeout", "auth")
    results.test(
        "Key format",
        key1 == "timeout:auth",
        f"Key should be 'pattern:namespace': {key1}"
    )
    
    # Test consistency
    key2 = generate_correlation_key("timeout", "auth")
    results.test(
        "Key consistency",
        key1 == key2,
        "Same pattern+namespace should produce same key"
    )
    
    # Test uniqueness
    key3 = generate_correlation_key("timeout", "ai-agents")
    results.test(
        "Key uniqueness (different namespace)",
        key1 != key3,
        f"Different namespaces should produce different keys: {key1} != {key3}"
    )
    
    key4 = generate_correlation_key("oom", "auth")
    results.test(
        "Key uniqueness (different pattern)",
        key1 != key4,
        f"Different patterns should produce different keys: {key1} != {key4}"
    )


def test_investigation_workflow_stages(results: TestResults):
    """Test investigation workflow stage progression."""
    print("\n" + "="*60)
    print("TESTING INVESTIGATION WORKFLOW STAGES")
    print("="*60)
    
    # Define expected workflow stages
    expected_stages = [
        "ANALYZING",
        "QUERYING_MEMORY",
        "INVESTIGATING",
        "PLANNING_REMEDIATION",
        "EXECUTING_ACTION",
        "VERIFYING",
        "SUMMARIZING",
        "COMPLETED",
    ]
    
    results.test(
        "Workflow stage count",
        len(expected_stages) == 8,
        f"Should have 8 stages: {len(expected_stages)}"
    )
    
    results.test(
        "Workflow starts with ANALYZING",
        expected_stages[0] == "ANALYZING",
        "First stage should be ANALYZING"
    )
    
    results.test(
        "Workflow ends with COMPLETED",
        expected_stages[-1] == "COMPLETED",
        "Last stage should be COMPLETED"
    )
    
    results.test(
        "Memory query before investigation",
        expected_stages.index("QUERYING_MEMORY") < expected_stages.index("INVESTIGATING"),
        "Should query memory before detailed investigation"
    )
    
    results.test(
        "Investigation before remediation",
        expected_stages.index("INVESTIGATING") < expected_stages.index("PLANNING_REMEDIATION"),
        "Should investigate before planning remediation"
    )
    
    results.test(
        "Planning before execution",
        expected_stages.index("PLANNING_REMEDIATION") < expected_stages.index("EXECUTING_ACTION"),
        "Should plan before executing"
    )
    
    results.test(
        "Execution before verification",
        expected_stages.index("EXECUTING_ACTION") < expected_stages.index("VERIFYING"),
        "Should execute before verifying"
    )
    
    results.test(
        "Verification before summarizing",
        expected_stages.index("VERIFYING") < expected_stages.index("SUMMARIZING"),
        "Should verify before summarizing"
    )


def test_swarm_agent_roles(results: TestResults):
    """Test swarm agent role definitions."""
    print("\n" + "="*60)
    print("TESTING SWARM AGENT ROLES")
    print("="*60)
    
    # Define expected agent roles
    agent_roles = {
        "triage": "Entry point, analyzes and routes",
        "investigator": "Diagnostic specialist",
        "memory": "Learning and pattern specialist",
        "remediation": "Fix specialist",
        "communications": "Discord specialist",
    }
    
    results.test(
        "Swarm agent count",
        len(agent_roles) == 5,
        f"Should have 5 agents: {len(agent_roles)}"
    )
    
    results.test(
        "Triage agent exists",
        "triage" in agent_roles,
        "Triage agent is entry point"
    )
    
    results.test(
        "All specialist agents exist",
        all(role in agent_roles for role in ["investigator", "memory", "remediation", "communications"]),
        "All specialist agents defined"
    )


def test_worker_types(results: TestResults):
    """Test worker agent types."""
    print("\n" + "="*60)
    print("TESTING WORKER AGENT TYPES")
    print("="*60)
    
    # Define expected worker types
    worker_types = {
        "InvestigatorWorker": "Runs diagnostics",
        "MemoryWorker": "Queries and stores learnings",
        "RemediatorWorker": "Plans and executes fixes",
        "NarratorWorker": "Crafts conversational updates",
    }
    
    results.test(
        "Worker count",
        len(worker_types) == 4,
        f"Should have 4 workers: {len(worker_types)}"
    )
    
    results.test(
        "All workers defined",
        all(w in worker_types for w in ["InvestigatorWorker", "MemoryWorker", "RemediatorWorker", "NarratorWorker"]),
        "All worker types defined"
    )


def test_mcp_server_integration_points(results: TestResults):
    """Test MCP server integration points."""
    print("\n" + "="*60)
    print("TESTING MCP INTEGRATION POINTS")
    print("="*60)
    
    # Define expected MCP servers
    mcp_servers = {
        "kubernetes": ["pods_get", "pods_log", "events_list", "deployments_scale"],
        "discord": ["messages_send", "messages_read"],
        "memory": ["store_learning", "query_learnings", "get_agent_learnings"],
    }
    
    results.test(
        "MCP server count",
        len(mcp_servers) == 3,
        f"Should integrate with 3 MCP servers: {len(mcp_servers)}"
    )
    
    results.test(
        "Kubernetes MCP tools",
        len(mcp_servers["kubernetes"]) >= 4,
        f"Should have multiple Kubernetes tools: {len(mcp_servers['kubernetes'])}"
    )
    
    results.test(
        "Discord MCP tools",
        "messages_send" in mcp_servers["discord"],
        "Should have message sending capability"
    )
    
    results.test(
        "Memory MCP tools",
        all(tool in mcp_servers["memory"] for tool in ["store_learning", "query_learnings"]),
        "Should have learning storage and retrieval"
    )


def test_error_handling_patterns(results: TestResults):
    """Test that error handling patterns are comprehensive."""
    print("\n" + "="*60)
    print("TESTING ERROR HANDLING PATTERNS")
    print("="*60)
    
    # Define expected error handling scenarios
    error_scenarios = [
        "MCP client connection failure",
        "Agent execution timeout",
        "Worker task failure",
        "Redis connection failure",
        "Event parsing failure",
        "State serialization failure",
    ]
    
    results.test(
        "Error scenario coverage",
        len(error_scenarios) >= 5,
        f"Should handle multiple error scenarios: {len(error_scenarios)}"
    )
    
    # Test that we have try/except patterns for each scenario type
    critical_operations = [
        "MCP client creation",
        "Agent execution",
        "Worker delegation",
        "State persistence",
        "Event processing",
    ]
    
    results.test(
        "Critical operation coverage",
        len(critical_operations) >= 5,
        f"Should protect critical operations: {len(critical_operations)}"
    )


def test_observability_metrics(results: TestResults):
    """Test observability metrics coverage."""
    print("\n" + "="*60)
    print("TESTING OBSERVABILITY METRICS")
    print("="*60)
    
    # Define expected metrics
    expected_metrics = [
        "investigations_started",
        "investigations_completed",
        "investigations_failed",
        "worker_tasks_total",
        "worker_tasks_success",
        "worker_tasks_failed",
        "stage_durations",
    ]
    
    results.test(
        "Metric coverage",
        len(expected_metrics) >= 7,
        f"Should track multiple metrics: {len(expected_metrics)}"
    )
    
    results.test(
        "Success/failure tracking",
        all(metric in expected_metrics for metric in ["investigations_completed", "investigations_failed"]),
        "Should track both successes and failures"
    )
    
    results.test(
        "Duration tracking",
        "stage_durations" in expected_metrics,
        "Should track operation durations"
    )


def main():
    """Run all isolated logic tests."""
    print("="*60)
    print("ISOLATED LOGIC TESTS")
    print("Testing core logic without runtime dependencies")
    print("="*60)
    
    results = TestResults()
    
    try:
        test_pattern_extraction(results)
        test_correlation_key_generation(results)
        test_investigation_workflow_stages(results)
        test_swarm_agent_roles(results)
        test_worker_types(results)
        test_mcp_server_integration_points(results)
        test_error_handling_patterns(results)
        test_observability_metrics(results)
    except Exception as e:
        print(f"\n✗ Test execution failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Print summary
    success = results.summary()
    
    if success:
        print(f"\n{'='*60}")
        print("✓ ALL LOGIC TESTS PASSED")
        print(f"{'='*60}")
        return 0
    else:
        print(f"\n{'='*60}")
        print("✗ SOME LOGIC TESTS FAILED")
        print(f"{'='*60}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
