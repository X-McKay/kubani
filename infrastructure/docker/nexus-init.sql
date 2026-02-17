-- Kubani Nexus Database Initialization
-- This script creates the schema for the Skill Registry and Nexus state.

-- =========================================================================
-- Skill Registry Tables
-- =========================================================================

CREATE TABLE IF NOT EXISTS skills (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    version VARCHAR(50) NOT NULL,
    category VARCHAR(100) DEFAULT 'general',
    oci_url VARCHAR(1024) NOT NULL,
    description TEXT,
    author VARCHAR(255) DEFAULT 'nexus-synthesizer',
    -- Security metadata
    risk_score FLOAT DEFAULT 0.0,
    requires_network BOOLEAN DEFAULT FALSE,
    requires_filesystem BOOLEAN DEFAULT FALSE,
    -- Lifecycle
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    -- status values: 'pending', 'validating', 'validated', 'pending_approval', 'approved', 'rejected'
    approved_by VARCHAR(255),
    approved_at TIMESTAMP WITH TIME ZONE,
    rejection_reason TEXT,
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    -- Constraints
    UNIQUE (name, version)
);

CREATE INDEX idx_skills_name ON skills(name);
CREATE INDEX idx_skills_status ON skills(status);
CREATE INDEX idx_skills_category ON skills(category);

-- =========================================================================
-- Skill Validation Records
-- =========================================================================

CREATE TABLE IF NOT EXISTS skill_validations (
    id SERIAL PRIMARY KEY,
    skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    -- Validation stages
    static_analysis_passed BOOLEAN,
    static_analysis_report JSONB,
    sandbox_execution_passed BOOLEAN,
    sandbox_execution_report JSONB,
    llm_review_passed BOOLEAN,
    llm_review_report JSONB,
    -- Aggregate
    overall_risk_score FLOAT,
    overall_passed BOOLEAN,
    -- Timestamps
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_validations_skill_id ON skill_validations(skill_id);

-- =========================================================================
-- Conversation State (for persistence across restarts)
-- =========================================================================

CREATE TABLE IF NOT EXISTS conversations (
    id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    source VARCHAR(50) NOT NULL DEFAULT 'kubani-ui',
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id SERIAL PRIMARY KEY,
    conversation_id VARCHAR(255) NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,  -- 'user' or 'assistant'
    content TEXT NOT NULL,
    source VARCHAR(50),
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_messages_conversation ON conversation_messages(conversation_id);
CREATE INDEX idx_messages_created ON conversation_messages(created_at);

-- =========================================================================
-- Agent Actions Log (for UI observability)
-- =========================================================================

CREATE TABLE IF NOT EXISTS agent_actions (
    id SERIAL PRIMARY KEY,
    conversation_id VARCHAR(255) REFERENCES conversations(id),
    action_type VARCHAR(100) NOT NULL,
    description TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'started',
    -- status values: 'started', 'completed', 'failed'
    input_summary TEXT,
    output_summary TEXT,
    error_message TEXT,
    duration_ms INTEGER,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_actions_conversation ON agent_actions(conversation_id);
CREATE INDEX idx_actions_started ON agent_actions(started_at DESC);
CREATE INDEX idx_actions_status ON agent_actions(status);

-- =========================================================================
-- Approval Queue (for HITL skill approvals)
-- =========================================================================

CREATE TABLE IF NOT EXISTS approval_requests (
    id SERIAL PRIMARY KEY,
    request_type VARCHAR(50) NOT NULL DEFAULT 'skill_approval',
    reference_id INTEGER,  -- e.g., skill_id
    title VARCHAR(500) NOT NULL,
    description TEXT,
    risk_score FLOAT,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    -- status values: 'pending', 'approved', 'rejected', 'expired'
    decided_by VARCHAR(255),
    decided_at TIMESTAMP WITH TIME ZONE,
    decision_reason TEXT,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_approvals_status ON approval_requests(status);
CREATE INDEX idx_approvals_created ON approval_requests(created_at DESC);
