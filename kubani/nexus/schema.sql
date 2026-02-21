-- Kubani Nexus Database Schema
-- Run against the kubani_nexus database

-- conversations table
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    source TEXT DEFAULT 'kubani-ui',
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- conversation_messages table
CREATE TABLE IF NOT EXISTS conversation_messages (
    id SERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT DEFAULT 'kubani-ui',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON conversation_messages(conversation_id, created_at);

-- agent_actions table
CREATE TABLE IF NOT EXISTS agent_actions (
    id SERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'started',
    input_summary TEXT DEFAULT '',
    output_summary TEXT DEFAULT '',
    error_message TEXT,
    duration_ms INT DEFAULT 0,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_actions_conversation ON agent_actions(conversation_id, started_at);

-- skills table
CREATE TABLE IF NOT EXISTS skills (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    oci_url TEXT DEFAULT '',
    description TEXT DEFAULT '',
    category TEXT DEFAULT 'general',
    author TEXT DEFAULT 'nexus-synthesizer',
    requires_network BOOLEAN DEFAULT FALSE,
    requires_filesystem BOOLEAN DEFAULT FALSE,
    status TEXT DEFAULT 'pending',
    risk_score FLOAT,
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    rejection_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(name, version)
);

-- approval_requests table
CREATE TABLE IF NOT EXISTS approval_requests (
    id SERIAL PRIMARY KEY,
    request_type TEXT NOT NULL,
    reference_id INT NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    risk_score FLOAT DEFAULT 0.0,
    status TEXT DEFAULT 'pending',
    decided_by TEXT,
    decided_at TIMESTAMPTZ,
    decision_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
