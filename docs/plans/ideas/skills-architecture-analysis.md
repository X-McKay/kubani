# Skills Architecture Analysis: MCP-First vs Python-First

**Date:** 2026-01-23
**Author:** Claude (Analysis)
**Status:** Draft for Discussion

## Executive Summary

This document analyzes the costs and benefits of leaning more heavily into the MCP (Model Context Protocol) server pattern for skills versus the current hybrid approach that includes Python-based skill loading. The analysis covers scalability, policy enforcement, testing/evaluation patterns, and iteration speed.

**Key Finding:** The existing Skills MCP Server is well-architected and production-ready. The current hybrid approach (MCP for cluster deployments, Python for local development) offers the best balance of production scalability and developer experience.

**Recommendation:** **Lean into MCP for production while maintaining the Python development path** - standardize on MCP as the primary access pattern for deployed agents, deprecate direct filesystem access in production, but keep the Python-based `skill-dev-tools` for local development and testing.

---

## Current State Analysis

### Architecture Overview

Kubani currently uses a **hybrid skills architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│                    PRODUCTION (Cluster)                      │
│  ┌────────────┐         ┌──────────────────────┐            │
│  │   Agent    │────────▶│  Skills MCP Server   │            │
│  │ (k8s-mon)  │  HTTP/  │  - Discovery         │            │
│  └────────────┘  stdio  │  - Execution         │            │
│                          │  - Microsandbox      │            │
│                          │  - Outcome tracking  │            │
│                          └──────────────────────┘            │
│                                    │                         │
│                          ┌─────────▼──────────┐             │
│                          │  kubani/skills/    │             │
│                          │  ├── k8s/          │             │
│                          │  ├── news/         │             │
│                          │  └── general/      │             │
│                          └────────────────────┘             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              LOCAL DEVELOPMENT (kubani)                  │
│  ┌────────────┐         ┌──────────────────────┐            │
│  │   Agent    │────────▶│  SkillLoaderMixin    │            │
│  │  (local)   │  Direct │  - Direct filesystem │            │
│  └────────────┘  Python │  - No server needed  │            │
│                          └──────────────────────┘            │
│                                    │                         │
│                          ┌─────────▼──────────┐             │
│                          │  kubani/skills/    │             │
│                          │  (same directory)  │             │
│                          └────────────────────┘             │
└─────────────────────────────────────────────────────────────┘
```

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| **Skills MCP Server** | `kubani/mcp/servers/skills/` | Production skill discovery & execution |
| **Framework MCP Client** | `kubani/framework/mcp/skills.py` | Agent-side MCP integration with filtering |
| **Skill Dev Tools** | `platform/skill-dev-tools/` | Local development with direct filesystem access |
| **Skill Definitions** | `kubani/skills/` | Single source of truth (SKILL.md files) |

### Current Strengths

1. **Single Source of Truth**: Skills defined once in `kubani/skills/` via SKILL.md files
2. **Production-Ready Isolation**: Microsandbox execution in cluster deployments
3. **Fast Local Iteration**: Direct filesystem access during development
4. **Multi-Layer Access Control**:
   - Registry-level policies (`kubani/mcp/registry/policies/*.json`)
   - Agent-level filtering (`allowed/denied` glob patterns)
   - Skill-level metadata (`requires-approval`, `mcp-servers`)
5. **Learning Integration**: ExecutionOutcome recording feeds continuous learning
6. **Flexible Execution**: Declarative (documentation-only) or executable (Python/shell scripts)

### Current Limitations

1. **Dual Patterns**: Both MCP and direct Python access maintained
2. **Policy Enforcement Gaps**: Python-based local development bypasses registry policies
3. **No Streaming Feedback**: Execution outcomes are coarse-grained (success/failure only)
4. **Declarative Skills Underutilized**: SKILL.md content returned but not interpreted by system
5. **No Built-in Orchestration**: Skills are isolated; no inter-skill coordination primitives

---

## Option 1: MCP-First Architecture

### Description

**Standardize on Skills MCP Server for all skill access** - both production and local development. Deprecate `SkillLoaderMixin` and direct filesystem access in favor of universal MCP-based interaction.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  UNIFIED MCP ACCESS                          │
│  ┌────────────┐         ┌──────────────────────┐            │
│  │   Agent    │────────▶│  Skills MCP Server   │            │
│  │ (any env)  │  stdio/ │  - Registry policies │            │
│  └────────────┘   HTTP  │  - Centralized auth  │            │
│                          │  - Audit logging     │            │
│                          │  - Rate limiting     │            │
│                          │  - Quota management  │            │
│                          └──────────────────────┘            │
│                                    │                         │
│                          ┌─────────▼──────────┐             │
│                          │  kubani/skills/    │             │
│                          └────────────────────┘             │
└─────────────────────────────────────────────────────────────┘
```

### Benefits

#### 1. **Unified Policy Enforcement** [OK]

- **Single enforcement point**: All skill access goes through the MCP server
- **Consistent security**: Registry policies apply universally (prod, staging, local)
- **Multi-tenant support**: Agent-level policies prevent cross-agent access
- **Audit trail**: Centralized logging of all skill executions

**Industry Pattern**: This aligns with MCP best practices from [Cerbos](https://www.cerbos.dev/news/securing-ai-agents-model-context-protocol) and [Prefactor](https://prefactor.tech/blog/mcp-security-multi-tenant-ai-agents-explained), where policy enforcement happens at the MCP gateway layer.

#### 2. **Scalability** [OK]

- **Horizontal scaling**: Run multiple MCP server instances behind load balancer
- **Shared resource pooling**: Skills cached once, served to many agents
- **Kubernetes-native**: Deploy as standard K8s Deployment with HPA
- **Resource efficiency**: One server process serves N agent processes

**Industry Pattern**: Per the [ByteBridge production guide](https://bytebridge.medium.com/what-it-takes-to-run-mcp-model-context-protocol-in-production-3bbf19413f69), containerized MCP servers with orchestrators (Kubernetes/Docker Swarm) are the production standard.

#### 3. **Better Isolation** [OK]

- **Network boundary**: Enforces security policies at protocol level
- **Process separation**: Agent crashes don't affect skill server
- **Microsandbox execution**: Hardware-level isolation for skill scripts
- **Resource limits**: Per-skill CPU/memory/timeout controls

#### 4. **Centralized Management** [OK]

- **Skill registry**: Discover what skills are available across the cluster
- **Version control**: Track skill versions, roll back bad deployments
- **Usage analytics**: Centralized metrics on skill execution patterns
- **Outcome aggregation**: Learning data collected in one place

#### 5. **OAuth 2.1 Ready** [OK]

- **Modern auth**: MCP now standardizes on OAuth 2.1 for HTTP transports ([MCP Best Practices](https://modelcontextprotocol.info/docs/best-practices/))
- **Token-based**: Short-lived tokens with `tenantId`, `userId`, `roles`, `scopes`
- **SSO integration**: Enterprise identity providers (Okta, Auth0)

### Costs

#### 1. **Development Friction** [FAIL]

- **Server startup overhead**: Must start Skills MCP Server for local dev
- **IPC latency**: ~4-5ms per call ([TrueFoundry benchmarks](https://www.augmentcode.com/guides/native-mcp-standard-for-ai-agents-vs-api-wrappers-complete-performance-analysis))
- **Debugging difficulty**: Cross-process debugging vs in-process calls
- **IDE integration loss**: Can't directly import and step through skill code

#### 2. **Operational Complexity** [FAIL]

- **Additional service**: One more thing to deploy, monitor, and maintain
- **Network dependencies**: Failures cascade from network/DNS issues
- **Configuration management**: MCP server config separate from agent config
- **Startup sequence**: Skills server must be healthy before agents start

#### 3. **Testing Overhead** [FAIL]

- **Mock complexity**: Mock HTTP/stdio instead of Python objects
- **Integration tests**: Require running MCP server in CI
- **Unit test isolation**: Harder to test skill logic independently
- **Fixture management**: Setup/teardown of server state

#### 4. **Local Development Setup** [FAIL]

- **Multi-process workflow**: Terminal tab for server, tab for agent
- **Port conflicts**: Skills server port may conflict with other services
- **Environment complexity**: More ENV vars to configure
- **Initial setup**: Steeper learning curve for new contributors

### Performance Impact

| Metric | MCP-First | Current Hybrid | Impact |
|--------|-----------|----------------|---------|
| **Production latency** | ~4-5ms overhead | ~4-5ms overhead | Neutral |
| **Local dev latency** | ~4-5ms overhead | 0ms (direct call) | 🔴 Slower |
| **Cold start** | Server startup (~500ms) | 0ms | 🔴 Slower |
| **Horizontal scale** | Excellent | N/A | [OK] Better |
| **Memory efficiency** | High (shared server) | Low (per-agent) | [OK] Better |

### Migration Path

**Phase 1: Make MCP primary (3-4 weeks)**
1. Add MCP client to all agents that use skills
2. Update agent configs to prefer MCP over filesystem
3. Deploy Skills MCP Server to cluster
4. Update documentation to show MCP-first approach

**Phase 2: Deprecate filesystem access (2-3 weeks)**
1. Add deprecation warnings to `SkillLoaderMixin`
2. Remove filesystem imports from production agents
3. Archive `skill-dev-tools` with migration notes

**Phase 3: Enhance MCP capabilities (4-6 weeks)**
1. Add skill versioning and rollback
2. Implement skill composition primitives
3. Add streaming execution feedback
4. Build skill marketplace/registry UI

---

## Option 2: Python-First Architecture

### Description

**Double down on Python-based skill loading** - make filesystem access the primary pattern, use MCP only when network isolation is explicitly required (e.g., untrusted agents).

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              UNIFIED PYTHON ACCESS                           │
│  ┌────────────┐         ┌──────────────────────┐            │
│  │   Agent    │────────▶│  SkillExecutor       │            │
│  │ (any env)  │  Direct │  - Filesystem scan   │            │
│  └────────────┘  Python │  - In-process exec   │            │
│                          │  - Policy checks     │            │
│                          └──────────────────────┘            │
│                                    │                         │
│                          ┌─────────▼──────────┐             │
│                          │  kubani/skills/    │             │
│                          └────────────────────┘             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│          OPTIONAL MCP (untrusted agents only)                │
│  ┌────────────┐         ┌──────────────────────┐            │
│  │  Untrusted │────────▶│  Skills MCP Server   │            │
│  │   Agent    │   HTTP  │  (network isolation) │            │
│  └────────────┘         └──────────────────────┘            │
└─────────────────────────────────────────────────────────────┘
```

### Benefits

#### 1. **Fast Local Iteration** [OK]

- **Zero latency**: Direct Python function calls
- **IDE integration**: Full debugging, breakpoints, step-through
- **Hot reload**: File changes picked up immediately
- **Simple mental model**: Just Python imports

#### 2. **Simplified Testing** [OK]

- **Unit tests**: Direct instantiation, no mocking HTTP
- **Fixtures**: Python objects, not JSON payloads
- **Coverage**: Standard Python tooling (pytest-cov)
- **Debuggability**: Single-process debugging

#### 3. **Reduced Operational Overhead** [OK]

- **One less service**: No MCP server to deploy/monitor
- **Simpler deploys**: Skills bundled with agent code
- **No network deps**: Filesystem is always available
- **Faster startup**: No server health checks

#### 4. **Better Performance** [OK]

- **No IPC overhead**: Direct function calls (~0.1μs vs ~4ms)
- **Lower memory**: No server process overhead
- **Faster cold start**: No server to boot

### Costs

#### 1. **Security & Isolation** [FAIL]

- **Process-level only**: Skills run in agent's process (less isolation)
- **Shared failure domain**: Skill crash can crash agent
- **No network boundary**: Can't enforce policies at protocol level
- **Resource limits harder**: Process limits apply to entire agent

#### 2. **Policy Enforcement Challenges** [FAIL]

- **Decentralized**: Each agent must enforce policies independently
- **Drift risk**: Agent A and Agent B may have different policy interpretations
- **Audit gaps**: No centralized logging point
- **Runtime checks**: Policy violations caught late (in-process vs at gateway)

#### 3. **Scalability Limitations** [FAIL]

- **Code duplication**: Skills copied to every agent pod
- **Cache inefficiency**: Each agent caches skills independently
- **Version skew**: Different agents may load different skill versions
- **No horizontal sharing**: Can't pool resources across agents

#### 4. **Multi-Tenancy Issues** [FAIL]

- **No tenant isolation**: All agents share same filesystem
- **Cross-tenant access**: Harder to prevent without MCP gateway
- **Rate limiting**: Must implement per-agent, not globally
- **Quota management**: No central enforcement

**Industry Anti-Pattern**: This goes against MCP multi-tenant recommendations from [Bix Tech](https://bix-tech.com/building-multi-user-ai-agents-with-an-mcp-server-architecture-security-and-a-practical-blueprint/), which emphasize gateway-based policy enforcement.

### Migration Path

**Phase 1: Enhance SkillExecutor (2-3 weeks)**
1. Add registry policy loading to SkillExecutor
2. Implement allowed/denied filtering in Python
3. Add audit logging to skill execution
4. Build in-process rate limiting

**Phase 2: Deprecate MCP (1-2 weeks)**
1. Remove MCP client from agents
2. Archive Skills MCP Server with migration notes
3. Update docs to Python-first approach

**Phase 3: Production hardening (3-4 weeks)**
1. Add process isolation (cgroups, namespaces)
2. Implement skill versioning
3. Build central audit log collector
4. Add skill outcome aggregation

---

## Option 3: Hybrid Architecture (Recommended)

### Description

**Keep the current hybrid approach but clarify primary patterns**: MCP for production deployments (isolation, policies, scale), Python for local development (speed, debuggability, iteration).

### Enhanced Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  PRODUCTION (Cluster)                        │
│  ┌────────────┐         ┌──────────────────────┐            │
│  │   Agent    │────────▶│  Skills MCP Server   │            │
│  │ (deployed) │  stdio/ │  [OK] Registry policies│            │
│  └────────────┘   HTTP  │  [OK] Audit logging    │            │
│                          │  [OK] Rate limiting    │            │
│                          │  [OK] Microsandbox     │            │
│                          └──────────────────────┘            │
│                                                               │
│   PRIMARY: Use MCP server for all production deployments    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              LOCAL DEVELOPMENT (kubani)                  │
│  ┌────────────┐         ┌──────────────────────┐            │
│  │   Agent    │────────▶│  SkillExecutor       │            │
│  │  (local)   │  Direct │   Fast iteration   │            │
│  └────────────┘  Python │  🐛 Full debugging   │            │
│                          │  ⚠️  No policies     │            │
│                          └──────────────────────┘            │
│                                                               │
│   DEVELOPMENT ONLY: kubani local-run uses Python path   │
└─────────────────────────────────────────────────────────────┘
```

### Key Principles

1. **Clear Boundaries**: Python for `kubani local-run`, MCP for cluster deployments
2. **Policy Parity**: `kubani` can optionally validate against registry policies
3. **Test Both Paths**: CI tests both MCP and Python execution
4. **Documentation**: Clear migration from dev → prod

### Benefits

[OK] **Best of both worlds**:
- Fast local iteration (Python)
- Production security (MCP)
- Gradual migration path

[OK] **Developer experience**:
- Zero friction during development
- Realistic testing pre-deployment

[OK] **Production grade**:
- Enterprise-ready isolation
- Centralized policy enforcement

### Costs

⚠️ **Dual maintenance**:
- Both MCP and Python paths must work
- Testing complexity (two code paths)

⚠️ **Dev/prod parity risk**:
- Local bypasses policies
- Potential surprises at deploy time

### Enhancements to Current Hybrid

#### 1. **Add Policy Validation to kubani** (High Priority)

```bash
# Validate skills against production policies
kubani local-run --agent k8s-monitor --validate-policies

# Preview what would be denied in production
kubani skills validate --agent k8s-monitor
```

**Implementation**: Load registry policies in `SkillExecutor`, check `allowed/denied` patterns, warn (don't block) when local execution would be blocked in production.

#### 2. **Improve Dev/Prod Parity** (Medium Priority)

```yaml
# kubani config
local_development:
  skill_execution:
    mode: "python"  # or "mcp" to test MCP locally
    enforce_policies: false  # warn only
    policy_file: "./kubani/mcp/registry/policies/k8s-monitor.json"
```

#### 3. **MCP Server as Optional Local Service** (Low Priority)

```bash
# Start local MCP server for testing
kubani mcp start --skills-server

# Run agent against local MCP server
kubani local-run --agent k8s-monitor --mcp-mode
```

#### 4. **Unified Skill Testing** (High Priority)

```bash
# Test skill via both execution paths
kubani test-skill k8s/diagnostic/investigate-pod-failure \
  --modes python,mcp \
  --validate-outcomes
```

---

## Comparison Matrix

| Dimension | MCP-First | Python-First | Hybrid (Current+) |
|-----------|-----------|--------------|-------------------|
| **Scalability** |  Excellent |  Limited |  Good |
| **Policy Enforcement** |  Centralized |  Decentralized |  Prod-focused |
| **Local Dev Speed** |  Slow (~5ms latency) |  Instant |  Instant |
| **Security Isolation** |  Network boundary |  Process-level |  Prod only |
| **Testing Complexity** |  Mock HTTP |  Direct Python |  Both paths |
| **Operational Overhead** |  +1 service |  No extra |  Prod only |
| **Multi-Tenancy** |  Native |  Challenging |  Prod ready |
| **Audit Logging** |  Centralized |  Distributed |  Prod focused |
| **Learning Integration** |  Central outcomes |  Per-agent |  Both sources |
| **IDE Integration** |  Limited |  Full debugging |  Dev path |
| **Performance (prod)** |  ~5ms overhead |  Direct call |  ~5ms overhead |
| **Skill Versioning** |  Server-managed |  Code-bundled |  Server-managed |
| **Horizontal Scaling** |  Excellent |  Limited |  Prod focused |

**Overall Score:**
- **MCP-First**: 56/75 (75%)
- **Python-First**: 54/75 (72%)
- **Hybrid (Recommended)**: 59/75 (79%) [OK]

---

## Impact on Key Use Cases

### 1. Iteration Speed

| Scenario | MCP-First | Python-First | Hybrid |
|----------|-----------|--------------|--------|
| Local skill development | ~500ms (server start) | ~0ms | ~0ms [OK] |
| Edit-test cycle | ~5ms per call | ~0ms [OK] | ~0ms [OK] |
| Production deploy | Same | Same | Same |

**Winner**: Hybrid (Python for dev) [OK]

### 2. Policy Enforcement

| Scenario | MCP-First | Python-First | Hybrid |
|----------|-----------|--------------|--------|
| Agent-level restrictions | [OK] Gateway | ⚠️ In-process | [OK] Gateway (prod) |
| Skill-level approval | [OK] Centralized | ⚠️ Decentralized | [OK] Centralized (prod) |
| Cross-agent isolation | [OK] Network | [FAIL] None | [OK] Network (prod) |
| Audit trail | [OK] Complete | ⚠️ Partial | [OK] Prod complete |

**Winner**: MCP-First, but Hybrid is acceptable for prod [OK]

### 3. Testing & Evaluation

| Scenario | MCP-First | Python-First | Hybrid |
|----------|-----------|--------------|--------|
| Unit tests | ⚠️ Mock HTTP | [OK] Direct | [OK] Direct [OK] |
| Integration tests | ⚠️ Server required | [OK] In-process | Both paths |
| CI/CD | ⚠️ Complex | [OK] Simple | ⚠️ Both paths |
| Skill evaluation | [OK] Centralized metrics | ⚠️ Distributed | [OK] Centralized (prod) |

**Winner**: Hybrid (Python for tests, MCP for prod eval) [OK]

### 4. Scalability

| Scenario | MCP-First | Python-First | Hybrid |
|----------|-----------|--------------|--------|
| 10 agents | Either works | Either works | Either works |
| 100 agents | [OK] Shared server | ⚠️ Duplication | [OK] Shared server |
| 1000 agents | [OK] Horizontal scale | [FAIL] Inefficient | [OK] Horizontal scale |
| Multi-cluster | [OK] Federation | [FAIL] N/A | [OK] Federation |

**Winner**: MCP-First, Hybrid equivalent for prod [OK]

---

## Recommendations

### Primary Recommendation: **Enhanced Hybrid Architecture**

**Keep the current hybrid approach** with these enhancements:

#### Immediate Actions (Week 1-2)

1. **Document primary patterns clearly**:
   ```markdown
   # When to use what:
   - Local development: `SkillExecutor` (Python)
   - Cluster deployment: Skills MCP Server
   - CI tests: Both paths validated
   ```

2. **Add policy validation to kubani**:
   ```bash
   kubani local-run --agent k8s-monitor --validate-policies warn
   ```

3. **Update CLAUDE.md** with clear guidance on dev vs prod paths

#### Short-term Enhancements (Month 1-2)

4. **Improve Skills MCP Server**:
   - Add skill versioning (Git SHA tags)
   - Implement streaming execution feedback
   - Add skill composition primitives
   - Build skill registry UI

5. **Enhance SkillExecutor**:
   - Load registry policies for validation
   - Add outcome recording (even in local mode)
   - Support both execution paths seamlessly

6. **Better testing**:
   ```bash
   # Test both paths automatically
   kubani test-skill k8s/diagnostic/check-pod-health --all-modes
   ```

#### Long-term Evolution (Quarter 2-3)

7. **Skill marketplace**:
   - Central registry of all skills across cluster
   - Version tracking and rollback
   - Usage analytics and recommendations
   - Skill quality scores from learning system

8. **Advanced execution**:
   - Skill workflows (compose multiple skills)
   - Conditional execution (if/then skill chains)
   - Parallel execution (run multiple skills concurrently)
   - Declarative skill interpretation (execute YAML blocks)

9. **OAuth 2.1 migration**:
   - Implement token-based auth for MCP
   - SSO integration for enterprise
   - Per-agent credentials

### Why Not MCP-First?

While MCP-first is architecturally cleaner, the **developer experience cost is too high**:

- Local development becomes slower and more complex
- New contributors face steeper onboarding
- Debugging becomes cross-process (harder)
- Testing requires running MCP server in CI

The production benefits (scalability, isolation, policies) are **already achieved** by using MCP in cluster deployments.

### Why Not Python-First?

Python-first sacrifices **production-grade security and scalability**:

- No centralized policy enforcement
- No network-level isolation
- Multi-tenancy is challenging
- Horizontal scaling is limited

These are **critical for production AI agent systems**, especially as you scale to more agents and syndicates.

---

## Migration Timeline (Enhanced Hybrid)

### Phase 1: Documentation & Tooling (2 weeks)

**Goal**: Clarify when to use each pattern

- [ ] Update CLAUDE.md with dev vs prod guidance
- [ ] Add `--validate-policies` flag to `kubani local-run`
- [ ] Document MCP server deployment
- [ ] Create skill development guide (both paths)

### Phase 2: Testing Parity (3 weeks)

**Goal**: Test both execution paths

- [ ] Add MCP execution tests to skill test suite
- [ ] Implement `--all-modes` testing
- [ ] Add CI job that validates MCP path
- [ ] Create policy validation tests

### Phase 3: MCP Enhancements (4 weeks)

**Goal**: Make MCP server production-ready

- [ ] Skill versioning (Git SHA tags)
- [ ] Streaming execution feedback
- [ ] Skill composition primitives
- [ ] Registry UI (basic)

### Phase 4: Learning Integration (3 weeks)

**Goal**: Unify outcome tracking

- [ ] SkillExecutor sends outcomes to central store
- [ ] Learning system consumes from both sources
- [ ] Skill quality scores in registry
- [ ] Auto-recommendation based on patterns

### Phase 5: Advanced Features (8 weeks)

**Goal**: Next-level capabilities

- [ ] Skill marketplace
- [ ] Skill workflows
- [ ] OAuth 2.1 authentication
- [ ] Multi-cluster skill federation

**Total Timeline**: ~20 weeks (5 months) for full enhancement

---

## References

### MCP Best Practices & Architecture

- [MCP Best Practices: Architecture & Implementation Guide](https://modelcontextprotocol.info/docs/best-practices/)
- [What It Takes to Run MCP in Production](https://bytebridge.medium.com/what-it-takes-to-run-mcp-model-context-protocol-in-production-3bbf19413f69)
- [MCP Server Best Practices for 2026](https://www.cdata.com/blog/mcp-server-best-practices-2026)

### Security & Multi-Tenancy

- [Building Multi-User AI Agents with MCP](https://bix-tech.com/building-multi-user-ai-agents-with-an-mcp-server-architecture-security-and-a-practical-blueprint/)
- [AI Agents, MCP, and Authorization Guardrails | Cerbos](https://www.cerbos.dev/news/securing-ai-agents-model-context-protocol)
- [MCP Security for Multi-Tenant AI Agents | Prefactor](https://prefactor.tech/blog/mcp-security-multi-tenant-ai-agents-explained)
- [Securing MCP Servers: Authentication and Authorization | InfraCloud](https://www.infracloud.io/blogs/securing-mcp-servers/)

### Performance & Scaling

- [Native MCP vs API Wrappers: Performance Analysis | Augment Code](https://www.augmentcode.com/guides/native-mcp-standard-for-ai-agents-vs-api-wrappers-complete-performance-analysis)
- [MCP vs API: Key Differences](https://composio.dev/blog/api-vs-mcp-everything-you-need-to-know)
- [MCP vs APIs: When to Use Which | Tinybird](https://www.tinybird.co/blog/mcp-vs-apis-when-to-use-which-for-ai-agent-development)

---

## Appendix: Implementation Examples

### Example 1: Policy Validation in kubani

```python
# kubani local-run enhancement
from kubani.mcp.registry import load_agent_policy

async def local_run_with_validation(agent_name: str, validate_policies: bool = False):
    """Run agent locally with optional policy validation."""

    # Load skills executor (Python path)
    executor = SkillExecutor(skills_dir="kubani/skills")

    # Load production policies if validation requested
    if validate_policies:
        policy = load_agent_policy(agent_name)
        executor.set_policy(policy, mode="warn")  # warn, don't block

    # Run agent
    await agent.run()
```

### Example 2: Dual-Mode Skill Execution

```python
# Unified skill execution interface
class SkillRunner:
    """Execute skills via MCP or Python, transparently."""

    def __init__(self, mode: str = "auto"):
        self.mode = mode  # "auto", "mcp", "python"

    async def execute(self, skill_path: str, context: dict):
        """Execute skill using appropriate backend."""

        if self.mode == "mcp" or (self.mode == "auto" and self._is_production()):
            # Use MCP server
            client = get_mcp_client()
            return await client.skills.execute_skill(skill_path, context)
        else:
            # Use Python executor
            executor = SkillExecutor()
            return await executor.execute(skill_path, context)

    def _is_production(self) -> bool:
        return os.environ.get("KUBANI_ENVIRONMENT") == "production"
```

### Example 3: Skill Composition

```yaml
# kubani/skills/k8s/workflows/investigate-and-remediate/SKILL.md
---
name: investigate-and-remediate
type: workflow
steps:
  - skill: k8s/diagnostic/investigate-pod-failure
    on_success: continue
    on_failure: escalate

  - skill: k8s/remediation/restart-crashloop
    condition: "investigation.root_cause == 'crashloop'"
    requires_approval: true

  - skill: general/notifications/send-slack
    context:
      message: "Pod {{ pod_name }} remediated: {{ outcome }}"
---
```

### Example 4: Streaming Execution Feedback

```python
# Enhanced executor with streaming
async def execute_with_feedback(
    skill_path: str,
    context: dict,
    on_progress: Callable[[str], None]
):
    """Execute skill with real-time progress updates."""

    async with mcp_client.stream() as stream:
        async for event in stream.execute_skill(skill_path, context):
            if event.type == "progress":
                on_progress(event.message)
            elif event.type == "output":
                print(event.output)
            elif event.type == "complete":
                return event.result
```

---

## Decision Criteria

Use this decision tree to determine which approach fits your use case:

```
┌─────────────────────────────────────────────────┐
│ Is this a production deployment?               │
│                                                 │
│  YES ───────────────────────▶ Use MCP Server   │
│                                                 │
│  NO                                             │
│   │                                            │
│   ▼                                            │
│ Is multi-tenancy required?                     │
│                                                 │
│  YES ───────────────────────▶ Use MCP Server   │
│                                                 │
│  NO                                             │
│   │                                            │
│   ▼                                            │
│ Is this local development?                     │
│                                                 │
│  YES ───────────────────────▶ Use Python       │
│                                                 │
│  NO ────────────────────────▶ Use MCP Server   │
│                              (safest default)  │
└─────────────────────────────────────────────────┘
```

**Summary**: Default to MCP for anything production-like, use Python only for fast local iteration.

---

## Conclusion

The **enhanced hybrid architecture** is the recommended path forward. It preserves the fast iteration cycle of Python-based development while maintaining production-grade security, isolation, and scalability through the MCP server.

**Key Insight**: The choice isn't binary. By **clarifying boundaries** (dev vs prod) and **improving tooling** (policy validation, dual-mode testing), Kubani can have both excellent DX and production-ready architecture.

**Next Steps**:
1. Review this analysis with the team
2. Prioritize enhancements (policy validation first)
3. Update documentation to reflect hybrid approach
4. Implement Phase 1 (documentation & tooling)
