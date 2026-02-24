# Nexus Capability Gaps — Future Roadmap

**Status:** Draft
**Created:** 2026-02-21
**Author:** Generated with Claude Code
**Context:** Remaining capabilities identified during the Nexus enhancement planning. These items are NOT part of Phases 1-3 but should be addressed in future iterations.

---

## Priority Tiers

### P1 — High Value, Address Soon

#### 1. Git/GitHub Integration
- **What:** Dedicated tools for PR creation, branch management, issue interaction, code review
- **Who has it:** Aider (deep git integration, auto-commits), Devin (full GitHub integration, issue-to-PR), SWE-Agent (issue-to-fix)
- **Why it matters:** Nexus can write code but can't create PRs, manage branches, or respond to GitHub issues. The complete issue-to-PR agentic loop is a core workflow for coding agents.
- **Approach:** MCP server wrapping `PyGithub` or `gh` CLI. Tools: `github_create_pr`, `github_list_issues`, `github_get_issue`, `github_create_branch`, `github_add_comment`
- **Dependencies:** GitHub personal access token, repository access
- **Effort:** LOW-MEDIUM (1-2 days)

#### 2. Document Ingestion / RAG Pipeline
- **What:** Ingest operational runbooks, architecture docs, PDFs, and codebase indexes into Qdrant for semantic search
- **Who has it:** OpenClaw (folder indexing, Obsidian integration), Windsurf (repo-scale comprehension), Devin (codebase-wide semantic search)
- **Why it matters:** The RAG infrastructure exists (Qdrant + embeddings at embeddings.almckay.io) but there's no pipeline to ingest documents
- **Approach:** Document ingestion pipeline: chunking (by section/paragraph) → embedding (via embeddings endpoint) → storage (Qdrant). Tools: `ingest_document(path)`, `ingest_url(url)`, `search_knowledge_base(query)`
- **Dependencies:** `pypdf` or `unstructured` for PDF parsing, `trafilatura` for URL content, existing Qdrant MCP
- **Effort:** MEDIUM (2-3 days)

#### 3. Database (SQL) Tools
- **What:** Read-only SQL queries against PostgreSQL (Nexus's own DB and potentially others)
- **Who has it:** Devin (schema exploration, query execution), OpenClaw (via MCP servers)
- **Why it matters:** Nexus has its own PostgreSQL but can't query it for debugging or data exploration
- **Approach:** MCP server wrapping `asyncpg` with read-only connection. Tools: `sql_query(query)`, `sql_list_tables()`, `sql_describe_table(name)`
- **Dependencies:** `asyncpg` (already a dependency), read-only DB user
- **Security:** Read-only connection, query timeout, blocked DDL/DML statements
- **Effort:** LOW (1 day)

#### 4. HTTP Request Tool
- **What:** Make arbitrary HTTP requests to test APIs, check service health, interact with webhooks
- **Who has it:** OpenClaw (web services integration), Devin (API testing), Cline (via terminal curl)
- **Why it matters:** `curl` is blocked by the bash security barrier. A typed tool with domain allowlisting is safer
- **Approach:** Strands @tool wrapping `httpx` with configurable domain allowlist. Tools: `http_request(method, url, headers, body)`
- **Security:** Domain allowlist (configurable), request size limits, timeout enforcement, no access to internal-only endpoints unless explicitly allowed
- **Effort:** LOW (0.5 day)

### P2 — Valuable, Address When Needed

#### 5. Browser Automation (Playwright)
- **What:** Headless browser for testing deployed web UIs, interacting with web-based admin panels (Grafana, Temporal UI, Argo)
- **Who has it:** OpenClaw (full CDP browser), Cline (headless click/type/screenshot), Devin (built-in browser)
- **Approach:** Playwright-based MCP server or Strands tools. Tools: `browser_navigate(url)`, `browser_screenshot()`, `browser_click(selector)`, `browser_type(selector, text)`
- **Dependencies:** `playwright` package, Chromium browser in container
- **Effort:** MEDIUM (2-3 days)

#### 6. CI/CD / Flux Status
- **What:** Check Flux reconciliation status, GitRepository sync state, HelmRelease health
- **Who has it:** Devin (CI/CD pipeline integration), Windsurf (build/test/deploy automation)
- **Approach:** Extend existing K8s tools to support Flux CRDs (Kustomization, GitRepository, HelmRelease). No new MCP server needed — add to k8s_client.py using CustomObjectsApi
- **Dependencies:** Flux CRDs installed in cluster (already present)
- **Effort:** LOW (0.5 day)

#### 7. Learning System Integration
- **What:** Wire Nexus execution events into the existing Critic/Reflection/Skill Synthesizer pipeline
- **Who has it:** OpenClaw Foundry ("agent that builds agents"), Live-SWE-Agent (self-evolving)
- **Why it matters:** The learning system infrastructure exists but Nexus doesn't emit events to it. Connecting them enables auto-generated skills from repeated patterns
- **Approach:** Emit events to Redis Streams after each agent turn: tool call success/failure, user corrections, task completion. The existing learning system syndicate picks these up automatically
- **Dependencies:** Redis Streams (already configured), learning system syndicate (already deployed)
- **Effort:** LOW (0.5 day)

#### 8. Scheduled Tasks (User-Facing)
- **What:** Users can schedule recurring tasks via chat: "Check pod health every morning and send me a Discord summary"
- **Who has it:** OpenClaw (built-in cron), NanoClaw (scheduled tasks), PicoClaw (recurring tasks)
- **Approach:** Expose a `schedule_task` Strands tool that creates Temporal scheduled workflows. The Temporal infrastructure already supports schedules natively
- **Dependencies:** Temporal schedules API
- **Effort:** LOW (1 day)

#### 9. Task/Project Management (GitHub Issues)
- **What:** Receive GitHub issues, plan work, create branches, write code, open PRs — the full agentic loop
- **Who has it:** Devin (Slack → GitHub issue → PR), SWE-Agent (issue → fix)
- **Approach:** Combine Git/GitHub tools (#1) with a GitHub webhook listener that creates Nexus tasks from new issues. Could be a new Temporal workflow triggered by webhook
- **Dependencies:** Git/GitHub integration (#1), GitHub webhook
- **Effort:** MEDIUM (2-3 days, after #1)

### P3 — Nice to Have

#### 10. Image/Vision Capabilities
- **What:** Screenshot analysis, diagram understanding, image-based debugging
- **Who has it:** OpenClaw (screenshot → vision model), Cline (screenshot analysis)
- **Approach:** Requires multimodal LLM support. If vLLM endpoint serves a vision model, add image input support to the agent
- **Dependencies:** Vision-capable model on vLLM
- **Effort:** LOW-MEDIUM (1-2 days, but depends on model availability)

#### 11. Additional Communication Channels
- **What:** Slack, Telegram, email notifications beyond Discord
- **Who has it:** OpenClaw (WhatsApp, Telegram, Slack, Signal, Teams, Matrix), NanoClaw (WhatsApp), PicoClaw (Telegram)
- **Approach:** Each channel is a new MCP server following the Discord MCP pattern. Start with Slack (most requested for team use)
- **Dependencies:** Per-channel API credentials
- **Effort:** LOW per channel (1 day each)

#### 12. User Context / Calendar / Preferences
- **What:** Calendar integration, personal preferences, location awareness
- **Who has it:** OpenClaw (Apple ecosystem, Notion, Obsidian, Things 3, WHOOP)
- **Approach:** Calendar MCP server (Google Calendar / CalDAV), preferences stored in memory system
- **Dependencies:** Calendar API credentials
- **Effort:** MEDIUM (2-3 days)

#### 13. Loki / Log Aggregation Queries
- **What:** Search aggregated logs across services using LogQL
- **Approach:** Similar to Prometheus tools — `httpx` calls to Loki HTTP API. Tools: `loki_query(logql)`, `loki_query_range(logql, start, end)`
- **Dependencies:** Loki endpoint URL
- **Effort:** LOW (0.5 day, same pattern as Prometheus)

#### 14. Voice / Audio
- **What:** Voice commands, speech-to-text, text-to-speech
- **Who has it:** OpenClaw (ElevenLabs voice), Aider (voice commands)
- **Approach:** STT/TTS pipeline, low ROI for a server-side infrastructure agent
- **Effort:** HIGH (1-2 weeks)

---

## Implementation Priority Matrix

| # | Capability | Priority | Effort | Dependencies | Phase |
|---|-----------|----------|--------|--------------|-------|
| 1 | Git/GitHub Integration | P1 | LOW-MEDIUM | GitHub PAT | Next sprint |
| 2 | Document Ingestion / RAG | P1 | MEDIUM | pypdf, Qdrant | Next sprint |
| 3 | Database (SQL) Tools | P1 | LOW | asyncpg, read-only user | Next sprint |
| 4 | HTTP Request Tool | P1 | LOW | httpx (already dep) | Next sprint |
| 5 | Browser Automation | P2 | MEDIUM | Playwright, Chromium | When needed |
| 6 | CI/CD / Flux Status | P2 | LOW | Flux CRDs | When needed |
| 7 | Learning System Wiring | P2 | LOW | Redis Streams | When needed |
| 8 | Scheduled Tasks | P2 | LOW | Temporal schedules | When needed |
| 9 | GitHub Issues Loop | P2 | MEDIUM | #1 Git/GitHub | After #1 |
| 10 | Image/Vision | P3 | LOW-MEDIUM | Vision model | When model available |
| 11 | Slack/Telegram/Email | P3 | LOW each | API credentials | On demand |
| 12 | User Context/Calendar | P3 | MEDIUM | Calendar API | On demand |
| 13 | Loki Log Queries | P3 | LOW | Loki endpoint | On demand |
| 14 | Voice/Audio | P3 | HIGH | STT/TTS pipeline | Low priority |

---

## Notes

- All P1 items can be implemented as Strands `@tool` functions following the same pattern established in Phase 1
- The Phase 2 MCP Gateway will provide centralized policy enforcement for all these tools once implemented
- Each tool should have its own file in `kubani/nexus/tools/` following the `create_*_tools()` factory pattern
- New pip dependencies should be added to `kubani/nexus/pyproject.toml` under optional `[tools]` extras
