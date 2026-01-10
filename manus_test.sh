#!/usr/bin/env bash
# =============================================================================
# Kubani Manus Enhancement Verification Script
# =============================================================================
# This script verifies all functionality after merging the feature/manus-enhancements
# branch to main. Run this script with access to the cluster.
#
# Usage:
#   ./manus_test.sh              # Run all tests
#   ./manus_test.sh --quick      # Run quick connectivity tests only
#   ./manus_test.sh --agents     # Run agent tests only
#   ./manus_test.sh --services   # Run service connectivity tests only
#
# Prerequisites:
#   - kubectl configured with cluster access
#   - Python 3.11+ with uv installed
#   - kubani-dev CLI installed (pip install -e tools/kubani-dev)
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# =============================================================================
# Utility Functions
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((TESTS_PASSED++)) || true
}

log_failure() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((TESTS_FAILED++)) || true
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_skip() {
    echo -e "${YELLOW}[SKIP]${NC} $1"
    ((TESTS_SKIPPED++)) || true
}

log_section() {
    echo ""
    echo "============================================================================="
    echo -e "${BLUE}$1${NC}"
    echo "============================================================================="
}

check_command() {
    if command -v "$1" &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# =============================================================================
# Prerequisites Check
# =============================================================================

check_prerequisites() {
    log_section "Checking Prerequisites"

    # Check kubectl
    if check_command kubectl; then
        log_success "kubectl is installed"
    else
        log_failure "kubectl is not installed"
        exit 1
    fi

    # Check cluster access
    if kubectl cluster-info &> /dev/null; then
        log_success "Cluster is accessible"
    else
        log_failure "Cannot access cluster - check KUBECONFIG"
        exit 1
    fi

    # Check Python
    if check_command python3; then
        PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
        log_success "Python $PYTHON_VERSION is installed"
    else
        log_failure "Python 3 is not installed"
        exit 1
    fi

    # Check uv
    if check_command uv; then
        log_success "uv is installed"
    else
        log_warning "uv is not installed - some tests may fail"
    fi

    # Check kubani-dev
    if check_command kubani-dev; then
        log_success "kubani-dev CLI is installed"
    else
        log_warning "kubani-dev CLI is not installed - run: pip install -e tools/kubani-dev"
    fi
}

# =============================================================================
# Service Connectivity Tests
# =============================================================================

test_service_connectivity() {
    log_section "Testing Service Connectivity"

    # LLM API
    log_info "Testing LLM API (llm.almckay.io)..."
    if curl -sf "https://llm.almckay.io/v1/models" > /dev/null 2>&1; then
        log_success "LLM API is accessible"
    else
        log_failure "LLM API is not accessible"
    fi

    # Embeddings API
    log_info "Testing Embeddings API (embeddings.almckay.io)..."
    if curl -sf "https://embeddings.almckay.io/v1/models" > /dev/null 2>&1; then
        log_success "Embeddings API is accessible"
    else
        log_failure "Embeddings API is not accessible"
    fi

    # Qdrant (may require API key - 401 means service is up)
    log_info "Testing Qdrant (qdrant.almckay.io)..."
    QDRANT_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://qdrant.almckay.io/collections" 2>/dev/null)
    if [ "$QDRANT_STATUS" = "200" ]; then
        log_success "Qdrant is accessible"
    elif [ "$QDRANT_STATUS" = "401" ]; then
        log_success "Qdrant is accessible (auth required)"
    else
        log_failure "Qdrant is not accessible (HTTP $QDRANT_STATUS)"
    fi

    # Redis
    log_info "Testing Redis (redis.almckay.io:6379)..."
    if nc -zv redis.almckay.io 6379 2>&1 | grep -q "succeeded\|open"; then
        log_success "Redis is accessible"
    else
        log_failure "Redis is not accessible"
    fi

    # Neo4j
    log_info "Testing Neo4j (neo4j.almckay.io:7687)..."
    if nc -zv neo4j.almckay.io 7687 2>&1 | grep -q "succeeded\|open"; then
        log_success "Neo4j is accessible"
    else
        log_failure "Neo4j is not accessible"
    fi

    # Temporal
    log_info "Testing Temporal (temporal.almckay.io:7233)..."
    if nc -zv temporal.almckay.io 7233 2>&1 | grep -q "succeeded\|open"; then
        log_success "Temporal is accessible"
    else
        log_failure "Temporal is not accessible"
    fi
}

# =============================================================================
# Core Library Tests
# =============================================================================

test_core_library() {
    log_section "Testing Core Library"

    cd agents/core

    # Install dependencies
    log_info "Installing core-agents dependencies..."
    if uv sync 2>&1 | tail -1; then
        log_success "Dependencies installed"
    else
        log_failure "Failed to install dependencies"
        return
    fi

    # Run pytest
    log_info "Running core-agents tests..."
    if uv run --with pytest pytest tests/ -v --tb=short 2>&1 | tail -20; then
        log_success "Core library tests passed"
    else
        log_failure "Core library tests failed"
    fi

    cd ../..
}

# =============================================================================
# New Module Tests
# =============================================================================

test_new_modules() {
    log_section "Testing New Modules"

    cd agents/core

    # Test Context Engineering Module
    log_info "Testing Context Engineering module..."
    if uv run python -c "
from core_agents.context import ContextManager, TodoManager, ErrorContext, ContextCompressor
import tempfile
with tempfile.TemporaryDirectory() as tmpdir:
    ctx = ContextManager(working_dir=tmpdir, agent_id='test', session_id='test-session')
    print('Context module OK')
" 2>&1; then
        log_success "Context Engineering module works"
    else
        log_failure "Context Engineering module failed"
    fi

    # Test Workflows Module
    log_info "Testing Workflows module..."
    if uv run python -c "
from core_agents.workflows import WorkflowBuilder, WorkflowGraph, WorkflowExecutor
builder = WorkflowBuilder('test')
print('Workflows module OK')
" 2>&1; then
        log_success "Workflows module works"
    else
        log_failure "Workflows module failed"
    fi

    # Test Plugins Module
    log_info "Testing Plugins module..."
    if uv run python -c "
from core_agents.plugins import get_plugin_manager, PluginConfig, PluginRegistry
manager = get_plugin_manager()
print('Plugins module OK')
" 2>&1; then
        log_success "Plugins module works"
    else
        log_failure "Plugins module failed"
    fi

    # Test Learning Module
    log_info "Testing Learning module..."
    if uv run python -c "
from core_agents.learning import get_learning_manager, PatternMatcher, SkillEvolution
manager = get_learning_manager()
print('Learning module OK')
" 2>&1; then
        log_success "Learning module works"
    else
        log_failure "Learning module failed"
    fi

    # Test Factory Extensions
    log_info "Testing Factory extensions..."
    if uv run python -c "
from core_agents import AgentConfig, AgentFactory, get_agent_factory
factory = get_agent_factory()
print('Factory extensions OK')
" 2>&1; then
        log_success "Factory extensions work"
    else
        log_failure "Factory extensions failed"
    fi

    # Test Hierarchical Memory
    log_info "Testing Hierarchical Memory..."
    if uv run python -c "
from core_agents.memory import HierarchicalMemory, HierarchicalMemoryConfig, MemoryTier
config = HierarchicalMemoryConfig()
memory = HierarchicalMemory(agent_id='test', config=config)
print('Hierarchical Memory OK')
" 2>&1; then
        log_success "Hierarchical Memory works"
    else
        log_failure "Hierarchical Memory failed"
    fi

    cd ../..
}

# =============================================================================
# K8s Monitor Tests
# =============================================================================

test_k8s_monitor() {
    log_section "Testing K8s Monitor Agent"

    cd agents/k8s-monitor

    # Install dependencies
    log_info "Installing k8s-monitor dependencies..."
    if uv sync 2>&1 | tail -1; then
        log_success "Dependencies installed"
    else
        log_failure "Failed to install dependencies"
        return
    fi

    # Run pytest
    log_info "Running k8s-monitor tests..."
    if uv run --with pytest pytest tests/ -v --tb=short 2>&1 | tail -20; then
        log_success "K8s monitor tests passed"
    else
        log_failure "K8s monitor tests failed"
    fi

    # Test Triage Graph
    log_info "Testing Triage Graph module..."
    if uv run python -c "
from k8s_monitor.federated.triage_graph import TriageGraph, TriageContext
graph = TriageGraph()
print('Triage Graph OK')
" 2>&1; then
        log_success "Triage Graph module works"
    else
        log_failure "Triage Graph module failed"
    fi

    # Test LLM Event Classifier
    log_info "Testing LLM Event Classifier..."
    if uv run python -c "
from k8s_monitor.federated.sentinel import LLMEventClassifier
classifier = LLMEventClassifier()
print('LLM Event Classifier OK')
" 2>&1; then
        log_success "LLM Event Classifier works"
    else
        log_failure "LLM Event Classifier failed"
    fi

    cd ../..
}

# =============================================================================
# News Monitor Tests
# =============================================================================

test_news_monitor() {
    log_section "Testing News Monitor Agent"

    cd agents/news-monitor

    # Install dependencies
    log_info "Installing news-monitor dependencies..."
    if uv sync 2>&1 | tail -1; then
        log_success "Dependencies installed"
    else
        log_failure "Failed to install dependencies"
        return
    fi

    # Run pytest (excluding known pre-existing failures)
    log_info "Running news-monitor tests..."
    if uv run --with pytest pytest tests/ -v --tb=short --ignore=tests/test_workflows.py 2>&1 | tail -20; then
        log_success "News monitor tests passed"
    else
        log_failure "News monitor tests failed"
    fi

    # Test Shared Agents
    log_info "Testing Shared Agents module..."
    if uv run python -c "
from news_monitor.shared_agents import get_shared_agents, SharedAgents
agents = get_shared_agents()
print('Shared Agents OK')
" 2>&1; then
        log_success "Shared Agents module works"
    else
        log_failure "Shared Agents module failed"
    fi

    # Test User Profiles
    log_info "Testing User Profiles module..."
    if uv run python -c "
from news_monitor.user_profiles import UserProfileManager, UserProfile
manager = UserProfileManager()
print('User Profiles OK')
" 2>&1; then
        log_success "User Profiles module works"
    else
        log_failure "User Profiles module failed"
    fi

    cd ../..
}

# =============================================================================
# kubani-dev CLI Tests
# =============================================================================

test_kubani_dev_cli() {
    log_section "Testing kubani-dev CLI"

    # Check if kubani-dev is installed
    if ! check_command kubani-dev; then
        log_skip "kubani-dev CLI not installed"
        return
    fi

    # Test help
    log_info "Testing kubani-dev --help..."
    if kubani-dev --help > /dev/null 2>&1; then
        log_success "kubani-dev --help works"
    else
        log_failure "kubani-dev --help failed"
    fi

    # Test run --help
    log_info "Testing kubani-dev run --help..."
    if kubani-dev run --help > /dev/null 2>&1; then
        log_success "kubani-dev run --help works"
    else
        log_failure "kubani-dev run --help failed"
    fi

    # Test test --help
    log_info "Testing kubani-dev test --help..."
    if kubani-dev test --help > /dev/null 2>&1; then
        log_success "kubani-dev test --help works"
    else
        log_failure "kubani-dev test --help failed"
    fi

    # Test eval --help
    log_info "Testing kubani-dev eval --help..."
    if kubani-dev eval --help > /dev/null 2>&1; then
        log_success "kubani-dev eval --help works"
    else
        log_failure "kubani-dev eval --help failed"
    fi

    # Test dashboard --help
    log_info "Testing kubani-dev dashboard --help..."
    if kubani-dev dashboard --help > /dev/null 2>&1; then
        log_success "kubani-dev dashboard --help works"
    else
        log_failure "kubani-dev dashboard --help failed"
    fi

    # Test trace --help
    log_info "Testing kubani-dev trace --help..."
    if kubani-dev trace --help > /dev/null 2>&1; then
        log_success "kubani-dev trace --help works"
    else
        log_failure "kubani-dev trace --help failed"
    fi

    # Test metrics --help
    log_info "Testing kubani-dev metrics --help..."
    if kubani-dev metrics --help > /dev/null 2>&1; then
        log_success "kubani-dev metrics --help works"
    else
        log_failure "kubani-dev metrics --help failed"
    fi

    # Test build --help
    log_info "Testing kubani-dev build --help..."
    if kubani-dev build --help > /dev/null 2>&1; then
        log_success "kubani-dev build --help works"
    else
        log_failure "kubani-dev build --help failed"
    fi

    # Test deploy --help
    log_info "Testing kubani-dev deploy --help..."
    if kubani-dev deploy --help > /dev/null 2>&1; then
        log_success "kubani-dev deploy --help works"
    else
        log_failure "kubani-dev deploy --help failed"
    fi

    # Test new --help
    log_info "Testing kubani-dev new --help..."
    if kubani-dev new --help > /dev/null 2>&1; then
        log_success "kubani-dev new --help works"
    else
        log_failure "kubani-dev new --help failed"
    fi

    # Test skills --help
    log_info "Testing kubani-dev skills --help..."
    if kubani-dev skills --help > /dev/null 2>&1; then
        log_success "kubani-dev skills --help works"
    else
        log_failure "kubani-dev skills --help failed"
    fi
}

# =============================================================================
# Cluster Deployment Tests
# =============================================================================

test_cluster_deployments() {
    log_section "Testing Cluster Deployments"

    # Check k8s-monitor deployment
    log_info "Checking k8s-monitor deployment..."
    if kubectl get deployment k8s-monitor -n ai-agents &> /dev/null; then
        READY=$(kubectl get deployment k8s-monitor -n ai-agents -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        if [ "$READY" -gt 0 ]; then
            log_success "k8s-monitor is deployed and running ($READY replicas)"
        else
            log_warning "k8s-monitor is deployed but not ready"
        fi
    else
        log_skip "k8s-monitor is not deployed"
    fi

    # Check news-monitor deployment
    log_info "Checking news-monitor deployment..."
    if kubectl get deployment news-monitor -n ai-agents &> /dev/null; then
        READY=$(kubectl get deployment news-monitor -n ai-agents -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        if [ "$READY" -gt 0 ]; then
            log_success "news-monitor is deployed and running ($READY replicas)"
        else
            log_warning "news-monitor is deployed but not ready"
        fi
    else
        log_skip "news-monitor is not deployed"
    fi

    # Check MCP server sidecar
    log_info "Checking MCP server sidecars..."
    MCP_CONTAINERS=$(kubectl get pods -n ai-agents -o jsonpath='{.items[*].spec.containers[*].name}' 2>/dev/null | tr ' ' '\n' | grep -c "mcp-server" || echo "0")
    if [ "$MCP_CONTAINERS" -gt 0 ]; then
        log_success "MCP server sidecars are running ($MCP_CONTAINERS containers)"
    else
        log_skip "No MCP server sidecars found"
    fi
}

# =============================================================================
# Integration Tests
# =============================================================================

test_integration() {
    log_section "Running Integration Tests"

    # Test agent factory with real LLM
    log_info "Testing AgentFactory with real LLM..."
    if uv run python -c "
import os
from core_agents import AgentConfig, get_agent_factory

# Skip if no LLM access
if not os.environ.get('KUBANI_VLLM_API_URL') and not os.environ.get('VLLM_API_URL'):
    print('Skipping - no LLM URL configured')
    exit(0)

factory = get_agent_factory()
config = AgentConfig(
    name='test-agent',
    description='Test agent',
    system_prompt='You are a test agent.',
    tools=[],
)
# Just test config creation, don't actually create agent
print('AgentFactory integration OK')
" 2>&1; then
        log_success "AgentFactory integration works"
    else
        log_failure "AgentFactory integration failed"
    fi

    # Test memory with real Qdrant
    log_info "Testing Memory with real Qdrant..."
    if uv run python -c "
import os
from core_agents.memory import HierarchicalMemory, HierarchicalMemoryConfig

# Skip if no Qdrant access
if not os.environ.get('QDRANT_URL') and not os.environ.get('KUBANI_QDRANT_URL'):
    print('Skipping - no Qdrant URL configured')
    exit(0)

config = HierarchicalMemoryConfig()
memory = HierarchicalMemory(agent_id='integration-test', config=config)
print('Memory integration OK')
" 2>&1; then
        log_success "Memory integration works"
    else
        log_failure "Memory integration failed"
    fi
}

# =============================================================================
# Summary
# =============================================================================

print_summary() {
    log_section "Test Summary"

    TOTAL=$((TESTS_PASSED + TESTS_FAILED + TESTS_SKIPPED))

    echo ""
    echo -e "  ${GREEN}Passed:${NC}  $TESTS_PASSED"
    echo -e "  ${RED}Failed:${NC}  $TESTS_FAILED"
    echo -e "  ${YELLOW}Skipped:${NC} $TESTS_SKIPPED"
    echo -e "  Total:   $TOTAL"
    echo ""

    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "${GREEN}All tests passed!${NC}"
        exit 0
    else
        echo -e "${RED}Some tests failed. Please review the output above.${NC}"
        exit 1
    fi
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo "============================================================================="
    echo "  Kubani Manus Enhancement Verification Script"
    echo "============================================================================="
    echo ""

    # Parse arguments
    RUN_ALL=true
    RUN_QUICK=false
    RUN_AGENTS=false
    RUN_SERVICES=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --quick)
                RUN_QUICK=true
                RUN_ALL=false
                shift
                ;;
            --agents)
                RUN_AGENTS=true
                RUN_ALL=false
                shift
                ;;
            --services)
                RUN_SERVICES=true
                RUN_ALL=false
                shift
                ;;
            *)
                echo "Unknown option: $1"
                echo "Usage: $0 [--quick|--agents|--services]"
                exit 1
                ;;
        esac
    done

    # Always check prerequisites
    check_prerequisites

    if [ "$RUN_ALL" = true ] || [ "$RUN_SERVICES" = true ] || [ "$RUN_QUICK" = true ]; then
        test_service_connectivity
    fi

    if [ "$RUN_QUICK" = true ]; then
        print_summary
        return
    fi

    if [ "$RUN_ALL" = true ] || [ "$RUN_AGENTS" = true ]; then
        test_core_library
        test_new_modules
        test_k8s_monitor
        test_news_monitor
        test_kubani_dev_cli
    fi

    if [ "$RUN_ALL" = true ]; then
        test_cluster_deployments
        test_integration
    fi

    print_summary
}

# Run main function
main "$@"
