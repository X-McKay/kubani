# MCP Infrastructure Review & Improvement Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a high-quality, scalable MCP infrastructure with shared base code, comprehensive tests, and consistent patterns across all servers.

**Architecture:** Add server utilities to `kubani/framework/mcp/server/`, fix inconsistencies across 5 existing servers (Discord, Memory, Qdrant, Skills, Temporal), create unified testing harness, and update registry to include all servers.

**Tech Stack:** Python 3.11+, FastMCP (mcp library), pytest + pytest-asyncio, pydantic, httpx

---

## Overview

This plan is divided into 4 phases:

1. **Phase 1: Server Base Module** (`2026-01-27-mcp-phase1-shared-base.md`)
   - Create `kubani/framework/mcp/server/` module
   - Add connection management, health checks, error handling
   - Define base classes and protocols

2. **Phase 2: Server Fixes & Standardization** (`2026-01-27-mcp-phase2-server-fixes.md`)
   - Fix entry point inconsistencies
   - Standardize error handling patterns
   - Update servers to use shared base
   - Fix registry gaps

3. **Phase 3: Unified Testing Harness** (`2026-01-27-mcp-phase3-testing.md`)
   - Create contract-based testing framework
   - Add tests for each server
   - Integration test suite

4. **Phase 4: Documentation & Validation** (`2026-01-27-mcp-phase4-validation.md`)
   - Update all READMEs
   - Run full validation
   - Document patterns for future servers

---

## Current State Analysis

### Servers Inventory

| Server | Version | Entry Point | Tests | In Registry |
|--------|---------|-------------|-------|-------------|
| Discord | 0.4.2 | `discord-mcp-server` → `discord_mcp:main` | Partial (models only) | Yes |
| Memory | 0.1.0 | `memory-mcp` → `memory_mcp.server:run` | None | No |
| Qdrant | 0.1.0 | `qdrant-mcp` → `qdrant_mcp.server:run` | None | No |
| Skills | 0.1.0 | `skills-mcp-server` → `skills_mcp:main` | Yes | No |
| Temporal | 0.1.0 | `temporal-mcp` → `temporal_mcp.server:run` | None | No |

### Issues Identified

1. **Entry point inconsistency**: Discord/Skills use `main()`, others use `run()`
2. **Registry incomplete**: Only 3 of 5+ servers registered
3. **Transport mode inconsistency**: Discord uses argparse, others use env vars
4. **No tests** for Memory, Qdrant, Temporal
5. **Duplicated patterns**: Connection management, health checks, error handling repeated
6. **Main function styles differ**: Discord wraps async properly, others use `asyncio.run()` directly

### Patterns to Extract

```python
# Common patterns found in all servers:
1. Global client connection (connect at startup, persist)
2. _get_client_or_error() pattern
3. lifespan context manager (empty in all cases)
4. create_server() factory
5. TransportSecuritySettings with allowed_hosts
6. Transport mode handling (stdio/sse/http)
```

---

## Success Criteria

- [ ] All 5 servers pass unified contract tests
- [ ] All 5 servers use `kubani.framework.mcp.server`
- [ ] All 5 servers registered in `registry.json`
- [ ] All servers have consistent entry points and transport handling
- [ ] Test coverage >80% for each server
- [ ] Documentation updated and accurate

---

## File Structure After Completion

```
kubani/framework/mcp/
├── __init__.py              # Updated exports
├── client.py                # MCP client (existing)
├── skills.py                # Skill filtering (existing)
└── server/                  # NEW: Server utilities
    ├── __init__.py
    ├── base.py              # MCPServerBase class
    ├── connection.py        # Connection management
    ├── errors.py            # Standardized errors
    ├── health.py            # Health check utilities
    ├── transport.py         # Transport mode handling
    └── testing/             # Testing utilities
        ├── __init__.py
        ├── harness.py       # MCPTestHarness
        ├── contracts.py     # Contract definitions
        └── mocks.py         # Mock backends

kubani/mcp/
├── registry/
│   ├── servers/             # Individual server definitions
│   │   ├── discord.json
│   │   ├── kubernetes.json
│   │   ├── cloudflare-docs.json
│   │   ├── temporal.json    # NEW
│   │   ├── qdrant.json      # NEW
│   │   ├── memory.json      # NEW
│   │   └── skills.json      # NEW
│   ├── policies/
│   └── registry.json        # Auto-generated combined
└── servers/
    ├── discord/             # Updated to use framework
    ├── memory/              # Updated to use framework
    ├── qdrant/              # Updated to use framework
    ├── skills/              # Updated to use framework
    └── temporal/            # Updated to use framework
```

---

## Execution Order

Start with Phase 1, which creates the foundation. Each subsequent phase depends on the previous:

```
Phase 1 (Server Base Module)
    ↓
Phase 2 (Server Fixes)
    ↓
Phase 3 (Testing)
    ↓
Phase 4 (Validation)
```

See individual phase documents for detailed implementation steps.
