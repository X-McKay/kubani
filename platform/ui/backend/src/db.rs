use duckdb::{Connection, Result};

/// Run all database migrations
pub fn run_migrations(db: &Connection) -> Result<()> {
    // DuckDB supports standard SQL with some enhanced features
    // Using JSON type natively instead of TEXT for metadata
    db.execute_batch(
        "
        -- Activity feed events
        CREATE TABLE IF NOT EXISTS activity_events (
            id VARCHAR PRIMARY KEY,
            source VARCHAR NOT NULL,
            event_type VARCHAR NOT NULL,
            title VARCHAR NOT NULL,
            content VARCHAR NOT NULL DEFAULT '',
            metadata JSON NOT NULL DEFAULT '{}',
            severity VARCHAR NOT NULL DEFAULT 'info',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            read BOOLEAN NOT NULL DEFAULT false
        );

        CREATE INDEX IF NOT EXISTS idx_activity_created_at ON activity_events(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_activity_source ON activity_events(source);
        CREATE INDEX IF NOT EXISTS idx_activity_type ON activity_events(event_type);
        CREATE INDEX IF NOT EXISTS idx_activity_read ON activity_events(read);

        -- Approval items
        CREATE TABLE IF NOT EXISTS approvals (
            id VARCHAR PRIMARY KEY,
            approval_type VARCHAR NOT NULL,
            source VARCHAR NOT NULL,
            title VARCHAR NOT NULL,
            summary VARCHAR NOT NULL,
            spec VARCHAR NOT NULL DEFAULT '',
            metadata JSON NOT NULL DEFAULT '{}',
            status VARCHAR NOT NULL DEFAULT 'pending',
            feedback VARCHAR,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
        CREATE INDEX IF NOT EXISTS idx_approvals_created ON approvals(created_at DESC);

        -- Agent sessions
        CREATE TABLE IF NOT EXISTS sessions (
            id VARCHAR PRIMARY KEY,
            title VARCHAR,
            agent_id VARCHAR,
            syndicate_id VARCHAR,
            status VARCHAR NOT NULL DEFAULT 'active',
            messages JSON NOT NULL DEFAULT '[]',
            metadata JSON NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
        CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
    ",
    )?;

    Ok(())
}

/// Activity event queries
pub mod activity {
    use duckdb::{params, Connection, Result};
    use serde_json::Value;

    #[derive(Debug, Clone)]
    pub struct ActivityEvent {
        pub id: String,
        pub source: String,
        pub event_type: String,
        pub title: String,
        pub content: String,
        pub metadata: Value,
        pub severity: String,
        pub created_at: String,
        pub read: bool,
    }

    /// Insert a new activity event
    pub fn insert(db: &Connection, event: &ActivityEvent) -> Result<()> {
        db.execute(
            "INSERT INTO activity_events (id, source, event_type, title, content, metadata, severity, created_at)
             VALUES ($1, $2, $3, $4, $5, $6::JSON, $7, $8::TIMESTAMPTZ)",
            params![
                event.id,
                event.source,
                event.event_type,
                event.title,
                event.content,
                event.metadata.to_string(),
                event.severity,
                event.created_at,
            ],
        )?;
        Ok(())
    }

    /// List activity events with filtering and pagination
    pub fn list(
        db: &Connection,
        source_filter: Option<&str>,
        event_type_filter: Option<&str>,
        limit: u32,
        offset: u32,
    ) -> Result<Vec<ActivityEvent>> {
        // Build query based on filters
        let mut conditions = vec!["1=1".to_string()];
        let mut param_values: Vec<Box<dyn duckdb::ToSql>> = Vec::new();

        if let Some(source) = source_filter {
            conditions.push(format!("source = ${}", param_values.len() + 1));
            param_values.push(Box::new(source.to_string()));
        }
        if let Some(event_type) = event_type_filter {
            conditions.push(format!("event_type = ${}", param_values.len() + 1));
            param_values.push(Box::new(event_type.to_string()));
        }

        let sql = format!(
            "SELECT id, source, event_type, title, content, metadata::VARCHAR, severity, created_at::VARCHAR, read
             FROM activity_events WHERE {}
             ORDER BY created_at DESC LIMIT {} OFFSET {}",
            conditions.join(" AND "),
            limit,
            offset
        );

        let mut stmt = db.prepare(&sql)?;
        let params_refs: Vec<&dyn duckdb::ToSql> =
            param_values.iter().map(|p| p.as_ref()).collect();

        let rows = stmt.query_map(params_refs.as_slice(), |row| {
            let metadata_str: String = row.get(5)?;
            Ok(ActivityEvent {
                id: row.get(0)?,
                source: row.get(1)?,
                event_type: row.get(2)?,
                title: row.get(3)?,
                content: row.get(4)?,
                metadata: serde_json::from_str(&metadata_str).unwrap_or_default(),
                severity: row.get(6)?,
                created_at: row.get(7)?,
                read: row.get(8)?,
            })
        })?;

        rows.collect()
    }

    /// Count unread events
    pub fn unread_count(db: &Connection) -> Result<u32> {
        db.query_row(
            "SELECT COUNT(*)::INTEGER FROM activity_events WHERE read = false",
            [],
            |row| row.get(0),
        )
    }

    /// Mark events as read
    pub fn mark_read(db: &Connection, ids: &[String]) -> Result<()> {
        if ids.is_empty() {
            return Ok(());
        }
        // DuckDB supports UPDATE with IN clause
        let placeholders: String = ids
            .iter()
            .map(|id| format!("'{}'", id.replace('\'', "''")))
            .collect::<Vec<_>>()
            .join(",");
        let sql = format!(
            "UPDATE activity_events SET read = true WHERE id IN ({})",
            placeholders
        );
        db.execute(&sql, [])?;
        Ok(())
    }
}

/// Approval queries
pub mod approvals {
    use duckdb::{params, Connection, Result};
    use serde_json::Value;

    #[derive(Debug, Clone)]
    pub struct Approval {
        pub id: String,
        pub approval_type: String,
        pub source: String,
        pub title: String,
        pub summary: String,
        pub spec: String,
        pub metadata: Value,
        pub status: String,
        pub feedback: Option<String>,
        pub created_at: String,
        pub updated_at: String,
    }

    pub fn insert(db: &Connection, approval: &Approval) -> Result<()> {
        db.execute(
            "INSERT INTO approvals (id, approval_type, source, title, summary, spec, metadata, status, created_at)
             VALUES ($1, $2, $3, $4, $5, $6, $7::JSON, $8, $9::TIMESTAMPTZ)",
            params![
                approval.id,
                approval.approval_type,
                approval.source,
                approval.title,
                approval.summary,
                approval.spec,
                approval.metadata.to_string(),
                approval.status,
                approval.created_at,
            ],
        )?;
        Ok(())
    }

    pub fn update_status(
        db: &Connection,
        id: &str,
        status: &str,
        feedback: Option<&str>,
    ) -> Result<()> {
        db.execute(
            "UPDATE approvals SET status = $1, feedback = $2, updated_at = now() WHERE id = $3",
            params![status, feedback.unwrap_or(""), id],
        )?;
        Ok(())
    }

    pub fn list_by_status(db: &Connection, status: &str, limit: u32) -> Result<Vec<Approval>> {
        let mut stmt = db.prepare(
            "SELECT id, approval_type, source, title, summary, spec, metadata::VARCHAR, status, feedback, created_at::VARCHAR, updated_at::VARCHAR
             FROM approvals WHERE status = $1 ORDER BY created_at DESC LIMIT $2",
        )?;

        let rows = stmt.query_map(params![status, limit], |row| {
            let metadata_str: String = row.get(6)?;
            Ok(Approval {
                id: row.get(0)?,
                approval_type: row.get(1)?,
                source: row.get(2)?,
                title: row.get(3)?,
                summary: row.get(4)?,
                spec: row.get(5)?,
                metadata: serde_json::from_str(&metadata_str).unwrap_or_default(),
                status: row.get(7)?,
                feedback: row.get(8)?,
                created_at: row.get(9)?,
                updated_at: row.get(10)?,
            })
        })?;

        rows.collect()
    }

    pub fn pending_count(db: &Connection) -> Result<u32> {
        db.query_row(
            "SELECT COUNT(*)::INTEGER FROM approvals WHERE status = 'pending'",
            [],
            |row| row.get(0),
        )
    }

    pub fn get_by_id(db: &Connection, id: &str) -> Result<Option<Approval>> {
        let mut stmt = db.prepare(
            "SELECT id, approval_type, source, title, summary, spec, metadata::VARCHAR, status, feedback, created_at::VARCHAR, updated_at::VARCHAR
             FROM approvals WHERE id = $1",
        )?;

        let mut rows = stmt.query_map(params![id], |row| {
            let metadata_str: String = row.get(6)?;
            Ok(Approval {
                id: row.get(0)?,
                approval_type: row.get(1)?,
                source: row.get(2)?,
                title: row.get(3)?,
                summary: row.get(4)?,
                spec: row.get(5)?,
                metadata: serde_json::from_str(&metadata_str).unwrap_or_default(),
                status: row.get(7)?,
                feedback: row.get(8)?,
                created_at: row.get(9)?,
                updated_at: row.get(10)?,
            })
        })?;

        Ok(rows.next().transpose()?)
    }
}

/// Session queries
pub mod sessions {
    use duckdb::{params, Connection, Result};
    use serde_json::Value;

    #[derive(Debug, Clone)]
    pub struct Session {
        pub id: String,
        pub title: Option<String>,
        pub agent_id: Option<String>,
        pub syndicate_id: Option<String>,
        pub status: String,
        pub messages: Value,
        pub metadata: Value,
        pub created_at: String,
        pub updated_at: String,
    }

    pub fn create(db: &Connection, session: &Session) -> Result<()> {
        db.execute(
            "INSERT INTO sessions (id, title, agent_id, syndicate_id, status, messages, metadata)
             VALUES ($1, $2, $3, $4, $5, $6::JSON, $7::JSON)",
            params![
                session.id,
                session.title.as_deref().unwrap_or(""),
                session.agent_id.as_deref().unwrap_or(""),
                session.syndicate_id.as_deref().unwrap_or(""),
                session.status,
                session.messages.to_string(),
                session.metadata.to_string(),
            ],
        )?;
        Ok(())
    }

    pub fn update_messages(db: &Connection, id: &str, messages: &Value) -> Result<()> {
        db.execute(
            "UPDATE sessions SET messages = $1::JSON, updated_at = now() WHERE id = $2",
            params![messages.to_string(), id],
        )?;
        Ok(())
    }

    pub fn update_status(db: &Connection, id: &str, status: &str) -> Result<()> {
        db.execute(
            "UPDATE sessions SET status = $1, updated_at = now() WHERE id = $2",
            params![status, id],
        )?;
        Ok(())
    }

    pub fn list_recent(db: &Connection, limit: u32) -> Result<Vec<Session>> {
        let mut stmt = db.prepare(
            "SELECT id, title, agent_id, syndicate_id, status, messages::VARCHAR, metadata::VARCHAR, created_at::VARCHAR, updated_at::VARCHAR
             FROM sessions ORDER BY updated_at DESC LIMIT $1",
        )?;

        let rows = stmt.query_map(params![limit], |row| {
            let messages_str: String = row.get(5)?;
            let metadata_str: String = row.get(6)?;
            let title: String = row.get(1)?;
            let agent_id: String = row.get(2)?;
            let syndicate_id: String = row.get(3)?;
            Ok(Session {
                id: row.get(0)?,
                title: if title.is_empty() {
                    None
                } else {
                    Some(title)
                },
                agent_id: if agent_id.is_empty() {
                    None
                } else {
                    Some(agent_id)
                },
                syndicate_id: if syndicate_id.is_empty() {
                    None
                } else {
                    Some(syndicate_id)
                },
                status: row.get(4)?,
                messages: serde_json::from_str(&messages_str).unwrap_or_default(),
                metadata: serde_json::from_str(&metadata_str).unwrap_or_default(),
                created_at: row.get(7)?,
                updated_at: row.get(8)?,
            })
        })?;

        rows.collect()
    }

    pub fn get_by_id(db: &Connection, id: &str) -> Result<Option<Session>> {
        let mut stmt = db.prepare(
            "SELECT id, title, agent_id, syndicate_id, status, messages::VARCHAR, metadata::VARCHAR, created_at::VARCHAR, updated_at::VARCHAR
             FROM sessions WHERE id = $1",
        )?;

        let mut rows = stmt.query_map(params![id], |row| {
            let messages_str: String = row.get(5)?;
            let metadata_str: String = row.get(6)?;
            let title: String = row.get(1)?;
            let agent_id: String = row.get(2)?;
            let syndicate_id: String = row.get(3)?;
            Ok(Session {
                id: row.get(0)?,
                title: if title.is_empty() {
                    None
                } else {
                    Some(title)
                },
                agent_id: if agent_id.is_empty() {
                    None
                } else {
                    Some(agent_id)
                },
                syndicate_id: if syndicate_id.is_empty() {
                    None
                } else {
                    Some(syndicate_id)
                },
                status: row.get(4)?,
                messages: serde_json::from_str(&messages_str).unwrap_or_default(),
                metadata: serde_json::from_str(&metadata_str).unwrap_or_default(),
                created_at: row.get(7)?,
                updated_at: row.get(8)?,
            })
        })?;

        Ok(rows.next().transpose()?)
    }

    pub fn active_count(db: &Connection) -> Result<u32> {
        db.query_row(
            "SELECT COUNT(*)::INTEGER FROM sessions WHERE status = 'active'",
            [],
            |row| row.get(0),
        )
    }
}
