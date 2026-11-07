# DB Admin agent

The user approved adding an advisory DB Admin through agentgateway after discussing a dedicated monitoring MCP connection, explicit tool permissions, and read-only diagnostics. This document records that scope; corrective database actions and the paused platform qualification campaign are separate work.

## Approach

Reuse Crystal DBA postgres-mcp 0.3.0 as a dedicated `postgres-admin` backend, keeping the existing Starbase2-scoped `postgres` backend unchanged. Reusing the old login would mix application-data and monitoring permissions; building a new MCP server would duplicate transport and SQL execution already available. Fixed agent tools call only `execute_sql` through `ctx.mcp`. Four read-only views over fixed SECURITY DEFINER functions in the postgres database return operational summaries without application rows, raw query text, client addresses, or credentials. Restricted MCP mode and database grants provide separate controls. The gateway authorizes execute_sql, not its SQL argument; the signed agent exposes only four fixed queries. The MCP login does not inherit the function owner’s pg_read_all_stats role.

## Initial behavior

On-demand `db-admin` sessions gather instance health, database statistics/sizes, connection utilization and blocking summaries, then write a timestamped evidence-backed advisory report into the session workspace. Missing permissions, unavailable metrics and truncated observations are errors or explicitly unknown, never healthy results. No scheduled monitoring, SQL supplied by the model/user, query cancellation, maintenance writes, query-plan execution, backup-success claims, or automatic remediation.

The first live attempt exposed an unsupported narrative claim after the model skipped a check. Report generation therefore requires all four diagnostic attempts and accepts no model-written findings or advice. It derives facts, limitations and conditional follow-ups from the latest validated evidence for each check; failed or stale observations never fall back to earlier successes. Missing attempts prevent report creation. An unavailable observation can produce an explicitly incomplete report, but does not satisfy the deployment smoke check.

The initial scope is deliberately instance diagnostics. Per-database table/index maintenance, query fingerprints and backup/restore evidence require separately scoped follow-up capabilities. Cumulative PostgreSQL statistics are labeled cumulative; one snapshot does not establish growth or incident rates.

## Deployment

Use existing tenant-test and agent identity mode, avoiding the unresolved human-delegation qualification path. Model is the existing llm-main Qwen3.6-35B-A3B-NVFP4. The agent has no database credentials or direct network access. Dedicated MCP credentials are SOPS-encrypted; the role/bootstrap runs via the existing normal Job pattern. No existing database workload restart is required.

Root owns live operations, merges, serial release tags, unapproved staging, verification of signature/all five attestations/NoDrift, and separate release approval. Existing worktrees and unfinished work remain intact. Test the actual packaged agent and one real gateway-backed session; preserve failed attempts and describe limits honestly.

## Deployment observations

Keep errors and streamlining opportunities in `docs/infrastructure/configuration/db-admin-deployment-notes.md`. Address blockers required for this agent; defer broader workflow redesign for discussion.
