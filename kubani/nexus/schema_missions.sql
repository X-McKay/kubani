-- Nexus Missions Schema
-- Additive migration: run after schema.sql
-- Adds the nexus_missions and nexus_mission_runs tables that power
-- the continuously-running proactive agent loop.

-- nexus_missions: one row per user-defined background mission
CREATE TABLE IF NOT EXISTS nexus_missions (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    title           TEXT NOT NULL,
    goal            TEXT NOT NULL,
    schedule        TEXT NOT NULL DEFAULT '0 * * * *',
    status          TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'paused', 'completed', 'failed')),
    mcp_policy      TEXT NOT NULL DEFAULT 'nexus',
    max_tool_calls  INT  NOT NULL DEFAULT 20 CHECK (max_tool_calls BETWEEN 1 AND 50),
    notify_on       JSONB NOT NULL DEFAULT '["anomaly","error"]',
    last_run_at     TIMESTAMPTZ,
    next_run_at     TIMESTAMPTZ,
    run_count       INT  NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_missions_user_status
    ON nexus_missions (user_id, status);

CREATE INDEX IF NOT EXISTS idx_missions_next_run
    ON nexus_missions (next_run_at)
    WHERE status = 'active';

-- nexus_mission_runs: one row per execution run
CREATE TABLE IF NOT EXISTS nexus_mission_runs (
    id                TEXT PRIMARY KEY,
    mission_id        TEXT NOT NULL REFERENCES nexus_missions(id) ON DELETE CASCADE,
    user_id           TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'running'
                          CHECK (status IN ('running', 'completed', 'failed', 'timed_out')),
    tool_calls_made   INT  NOT NULL DEFAULT 0,
    found_anomaly     BOOLEAN NOT NULL DEFAULT FALSE,
    notification_text TEXT NOT NULL DEFAULT '',
    error_message     TEXT NOT NULL DEFAULT '',
    started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at      TIMESTAMPTZ,
    duration_ms       INT  NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_mission_runs_mission
    ON nexus_mission_runs (mission_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_mission_runs_stale
    ON nexus_mission_runs (started_at)
    WHERE status = 'running';
