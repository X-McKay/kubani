"""Database schema validation tests.

This module tests the database schema creation and validation:
- Schema creation from nexus-init.sql
- Table existence and structure
- Constraints (UNIQUE, FOREIGN KEY)
- Indexes

Requirements: 8.1-8.5
"""

import asyncio
import asyncpg
import pytest
from pathlib import Path


@pytest.fixture
async def db_connection():
    """Create a test database connection.
    
    This fixture connects to the test PostgreSQL instance and provides
    a connection for schema validation tests.
    """
    # Connect to test database
    conn = await asyncpg.connect(
        host="localhost",
        port=15432,
        user="nexus_test",
        password="nexus_test",
        database="nexus_test",
    )
    
    yield conn
    
    await conn.close()


@pytest.fixture
async def clean_database(db_connection):
    """Clean database before each test.
    
    This fixture drops all tables to ensure a clean state for testing
    schema creation.
    """
    # Drop all tables in reverse dependency order
    await db_connection.execute("DROP TABLE IF EXISTS approval_requests CASCADE")
    await db_connection.execute("DROP TABLE IF EXISTS agent_actions CASCADE")
    await db_connection.execute("DROP TABLE IF EXISTS conversation_messages CASCADE")
    await db_connection.execute("DROP TABLE IF EXISTS conversations CASCADE")
    await db_connection.execute("DROP TABLE IF EXISTS skill_validations CASCADE")
    await db_connection.execute("DROP TABLE IF EXISTS skills CASCADE")
    
    yield
    
    # Cleanup after test
    await db_connection.execute("DROP TABLE IF EXISTS approval_requests CASCADE")
    await db_connection.execute("DROP TABLE IF EXISTS agent_actions CASCADE")
    await db_connection.execute("DROP TABLE IF EXISTS conversation_messages CASCADE")
    await db_connection.execute("DROP TABLE IF EXISTS conversations CASCADE")
    await db_connection.execute("DROP TABLE IF EXISTS skill_validations CASCADE")
    await db_connection.execute("DROP TABLE IF EXISTS skills CASCADE")


async def execute_schema_file(conn: asyncpg.Connection, schema_path: Path) -> None:
    """Execute SQL schema file.
    
    Args:
        conn: Database connection
        schema_path: Path to SQL schema file
    """
    schema_sql = schema_path.read_text()
    await conn.execute(schema_sql)


@pytest.mark.integration
@pytest.mark.database
class TestSchemaCreation:
    """Test database schema creation.
    
    Validates: Requirements 8.1
    """
    
    async def test_schema_creation_from_sql_file(
        self,
        db_connection: asyncpg.Connection,
        clean_database,
    ):
        """Test that nexus-init.sql creates all required tables.
        
        This test verifies that executing the schema file creates all 5 tables:
        1. skills
        2. skill_validations
        3. conversations
        4. conversation_messages
        5. agent_actions
        6. approval_requests
        
        Requirements: 8.1
        """
        # Find the schema file
        schema_path = Path("infrastructure/docker/nexus-init.sql")
        
        if not schema_path.exists():
            pytest.skip(f"Schema file not found at {schema_path}")
        
        # Execute schema file
        await execute_schema_file(db_connection, schema_path)
        
        # Query for all tables
        tables = await db_connection.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        
        table_names = [row["table_name"] for row in tables]
        
        # Verify all 5 required tables exist
        expected_tables = [
            "agent_actions",
            "approval_requests",
            "conversation_messages",
            "conversations",
            "skill_validations",
            "skills",
        ]
        
        for expected_table in expected_tables:
            assert expected_table in table_names, (
                f"Table '{expected_table}' not found. "
                f"Found tables: {table_names}"
            )
        
        # Verify we have exactly the expected tables (no extras)
        assert len(table_names) == len(expected_tables), (
            f"Expected {len(expected_tables)} tables, found {len(table_names)}: "
            f"{table_names}"
        )
    
    async def test_skills_table_structure(
        self,
        db_connection: asyncpg.Connection,
        clean_database,
    ):
        """Test skills table has correct structure.
        
        Requirements: 8.1
        """
        schema_path = Path("infrastructure/docker/nexus-init.sql")
        if not schema_path.exists():
            pytest.skip(f"Schema file not found at {schema_path}")
        
        await execute_schema_file(db_connection, schema_path)
        
        # Query column information
        columns = await db_connection.fetch("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'skills'
            ORDER BY ordinal_position
        """)
        
        column_names = [row["column_name"] for row in columns]
        
        # Verify key columns exist
        required_columns = [
            "id", "name", "version", "category", "oci_url",
            "description", "author", "risk_score", "requires_network",
            "requires_filesystem", "status", "approved_by", "approved_at",
            "rejection_reason", "created_at", "updated_at"
        ]
        
        for col in required_columns:
            assert col in column_names, f"Column '{col}' not found in skills table"
    
    async def test_conversations_table_structure(
        self,
        db_connection: asyncpg.Connection,
        clean_database,
    ):
        """Test conversations table has correct structure.
        
        Requirements: 8.1
        """
        schema_path = Path("infrastructure/docker/nexus-init.sql")
        if not schema_path.exists():
            pytest.skip(f"Schema file not found at {schema_path}")
        
        await execute_schema_file(db_connection, schema_path)
        
        columns = await db_connection.fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'conversations'
            ORDER BY ordinal_position
        """)
        
        column_names = [row["column_name"] for row in columns]
        
        required_columns = ["id", "user_id", "source", "status", "created_at", "updated_at"]
        
        for col in required_columns:
            assert col in column_names, f"Column '{col}' not found in conversations table"


@pytest.mark.integration
@pytest.mark.database
class TestSkillsTableConstraints:
    """Test skills table constraints.
    
    Validates: Requirements 8.2
    """
    
    async def test_skills_unique_constraint_on_name_version(
        self,
        db_connection: asyncpg.Connection,
        clean_database,
    ):
        """Test UNIQUE constraint on (name, version) in skills table.
        
        This test verifies that the skills table has a UNIQUE constraint
        preventing duplicate (name, version) combinations.
        
        Requirements: 8.2
        """
        schema_path = Path("infrastructure/docker/nexus-init.sql")
        if not schema_path.exists():
            pytest.skip(f"Schema file not found at {schema_path}")
        
        await execute_schema_file(db_connection, schema_path)
        
        # Insert a skill
        await db_connection.execute("""
            INSERT INTO skills (name, version, oci_url, status)
            VALUES ($1, $2, $3, $4)
        """, "test-skill", "1.0.0", "oci://example.com/test-skill:1.0.0", "pending")
        
        # Attempt to insert duplicate (name, version) - should fail
        with pytest.raises(asyncpg.UniqueViolationError):
            await db_connection.execute("""
                INSERT INTO skills (name, version, oci_url, status)
                VALUES ($1, $2, $3, $4)
            """, "test-skill", "1.0.0", "oci://example.com/test-skill:1.0.0", "pending")
    
    async def test_skills_unique_constraint_allows_different_versions(
        self,
        db_connection: asyncpg.Connection,
        clean_database,
    ):
        """Test that different versions of same skill are allowed.
        
        Requirements: 8.2
        """
        schema_path = Path("infrastructure/docker/nexus-init.sql")
        if not schema_path.exists():
            pytest.skip(f"Schema file not found at {schema_path}")
        
        await execute_schema_file(db_connection, schema_path)
        
        # Insert skill version 1.0.0
        await db_connection.execute("""
            INSERT INTO skills (name, version, oci_url, status)
            VALUES ($1, $2, $3, $4)
        """, "test-skill", "1.0.0", "oci://example.com/test-skill:1.0.0", "pending")
        
        # Insert skill version 2.0.0 - should succeed
        await db_connection.execute("""
            INSERT INTO skills (name, version, oci_url, status)
            VALUES ($1, $2, $3, $4)
        """, "test-skill", "2.0.0", "oci://example.com/test-skill:2.0.0", "pending")
        
        # Verify both versions exist
        count = await db_connection.fetchval("""
            SELECT COUNT(*) FROM skills WHERE name = $1
        """, "test-skill")
        
        assert count == 2, f"Expected 2 versions, found {count}"


@pytest.mark.integration
@pytest.mark.database
class TestConversationMessagesForeignKey:
    """Test conversation_messages foreign key constraint.
    
    Validates: Requirements 8.3
    """
    
    async def test_conversation_messages_foreign_key_exists(
        self,
        db_connection: asyncpg.Connection,
        clean_database,
    ):
        """Test foreign key from conversation_messages to conversations.
        
        Requirements: 8.3
        """
        schema_path = Path("infrastructure/docker/nexus-init.sql")
        if not schema_path.exists():
            pytest.skip(f"Schema file not found at {schema_path}")
        
        await execute_schema_file(db_connection, schema_path)
        
        # Query foreign key constraints
        fk_constraints = await db_connection.fetch("""
            SELECT
                tc.constraint_name,
                tc.table_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name,
                rc.delete_rule
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            JOIN information_schema.referential_constraints AS rc
                ON rc.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_name = 'conversation_messages'
        """)
        
        # Verify foreign key exists
        assert len(fk_constraints) > 0, "No foreign keys found on conversation_messages"
        
        # Find the foreign key to conversations
        conversations_fk = None
        for fk in fk_constraints:
            if fk["foreign_table_name"] == "conversations":
                conversations_fk = fk
                break
        
        assert conversations_fk is not None, (
            "Foreign key to conversations table not found"
        )
        assert conversations_fk["column_name"] == "conversation_id", (
            f"Expected foreign key on conversation_id, found {conversations_fk['column_name']}"
        )
    
    async def test_conversation_messages_cascade_delete(
        self,
        db_connection: asyncpg.Connection,
        clean_database,
    ):
        """Test ON DELETE CASCADE behavior.
        
        This test verifies that deleting a conversation also deletes
        all associated messages.
        
        Requirements: 8.3
        """
        schema_path = Path("infrastructure/docker/nexus-init.sql")
        if not schema_path.exists():
            pytest.skip(f"Schema file not found at {schema_path}")
        
        await execute_schema_file(db_connection, schema_path)
        
        # Insert a conversation
        conversation_id = "test-conv-123"
        await db_connection.execute("""
            INSERT INTO conversations (id, user_id, source, status)
            VALUES ($1, $2, $3, $4)
        """, conversation_id, "test-user", "test", "active")
        
        # Insert messages for the conversation
        await db_connection.execute("""
            INSERT INTO conversation_messages (conversation_id, role, content)
            VALUES ($1, $2, $3)
        """, conversation_id, "user", "Hello")
        
        await db_connection.execute("""
            INSERT INTO conversation_messages (conversation_id, role, content)
            VALUES ($1, $2, $3)
        """, conversation_id, "assistant", "Hi there")
        
        # Verify messages exist
        message_count = await db_connection.fetchval("""
            SELECT COUNT(*) FROM conversation_messages
            WHERE conversation_id = $1
        """, conversation_id)
        
        assert message_count == 2, f"Expected 2 messages, found {message_count}"
        
        # Delete the conversation
        await db_connection.execute("""
            DELETE FROM conversations WHERE id = $1
        """, conversation_id)
        
        # Verify messages were cascade deleted
        message_count_after = await db_connection.fetchval("""
            SELECT COUNT(*) FROM conversation_messages
            WHERE conversation_id = $1
        """, conversation_id)
        
        assert message_count_after == 0, (
            f"Expected 0 messages after cascade delete, found {message_count_after}"
        )


@pytest.mark.integration
@pytest.mark.database
class TestAgentActionsIndexes:
    """Test agent_actions table indexes.
    
    Validates: Requirements 8.4
    """
    
    async def test_agent_actions_indexes_exist(
        self,
        db_connection: asyncpg.Connection,
        clean_database,
    ):
        """Test that required indexes exist on agent_actions table.
        
        This test verifies indexes on:
        - conversation_id
        - started_at
        - status
        
        Requirements: 8.4
        """
        schema_path = Path("infrastructure/docker/nexus-init.sql")
        if not schema_path.exists():
            pytest.skip(f"Schema file not found at {schema_path}")
        
        await execute_schema_file(db_connection, schema_path)
        
        # Query indexes on agent_actions table
        indexes = await db_connection.fetch("""
            SELECT
                indexname,
                indexdef
            FROM pg_indexes
            WHERE tablename = 'agent_actions'
            AND schemaname = 'public'
        """)
        
        index_names = [row["indexname"] for row in indexes]
        index_defs = {row["indexname"]: row["indexdef"] for row in indexes}
        
        # Check for conversation_id index
        conversation_idx = [idx for idx in index_names if "conversation" in idx.lower()]
        assert len(conversation_idx) > 0, (
            f"No index found for conversation_id. Found indexes: {index_names}"
        )
        
        # Check for started_at index
        started_idx = [idx for idx in index_names if "started" in idx.lower()]
        assert len(started_idx) > 0, (
            f"No index found for started_at. Found indexes: {index_names}"
        )
        
        # Check for status index
        status_idx = [idx for idx in index_names if "status" in idx.lower()]
        assert len(status_idx) > 0, (
            f"No index found for status. Found indexes: {index_names}"
        )
    
    async def test_agent_actions_conversation_index_performance(
        self,
        db_connection: asyncpg.Connection,
        clean_database,
    ):
        """Test that conversation_id index improves query performance.
        
        Requirements: 8.4
        """
        schema_path = Path("infrastructure/docker/nexus-init.sql")
        if not schema_path.exists():
            pytest.skip(f"Schema file not found at {schema_path}")
        
        await execute_schema_file(db_connection, schema_path)
        
        # Insert test conversation
        conversation_id = "test-conv-perf"
        await db_connection.execute("""
            INSERT INTO conversations (id, user_id, source, status)
            VALUES ($1, $2, $3, $4)
        """, conversation_id, "test-user", "test", "active")
        
        # Insert multiple actions
        for i in range(10):
            await db_connection.execute("""
                INSERT INTO agent_actions (
                    conversation_id, action_type, description, status
                )
                VALUES ($1, $2, $3, $4)
            """, conversation_id, "test_action", f"Action {i}", "completed")
        
        # Query with EXPLAIN to verify index usage
        explain_result = await db_connection.fetch("""
            EXPLAIN (FORMAT JSON)
            SELECT * FROM agent_actions
            WHERE conversation_id = $1
        """, conversation_id)
        
        # Parse EXPLAIN output
        explain_json = explain_result[0]["QUERY PLAN"]
        
        # Verify query plan uses index scan (not sequential scan)
        plan_str = str(explain_json)
        
        # The query should use an index scan, not a sequential scan
        # Note: This is a basic check - in production you'd want more sophisticated analysis
        assert "Index Scan" in plan_str or "Bitmap" in plan_str, (
            f"Query does not appear to use index. Plan: {plan_str}"
        )


@pytest.mark.integration
@pytest.mark.database
class TestApprovalRequestsIndexes:
    """Test approval_requests table indexes.
    
    Validates: Requirements 8.5
    """
    
    async def test_approval_requests_indexes_exist(
        self,
        db_connection: asyncpg.Connection,
        clean_database,
    ):
        """Test that required indexes exist on approval_requests table.
        
        This test verifies indexes on:
        - status
        - created_at
        
        Requirements: 8.5
        """
        schema_path = Path("infrastructure/docker/nexus-init.sql")
        if not schema_path.exists():
            pytest.skip(f"Schema file not found at {schema_path}")
        
        await execute_schema_file(db_connection, schema_path)
        
        # Query indexes on approval_requests table
        indexes = await db_connection.fetch("""
            SELECT
                indexname,
                indexdef
            FROM pg_indexes
            WHERE tablename = 'approval_requests'
            AND schemaname = 'public'
        """)
        
        index_names = [row["indexname"] for row in indexes]
        
        # Check for status index
        status_idx = [idx for idx in index_names if "status" in idx.lower()]
        assert len(status_idx) > 0, (
            f"No index found for status. Found indexes: {index_names}"
        )
        
        # Check for created_at index
        created_idx = [idx for idx in index_names if "created" in idx.lower()]
        assert len(created_idx) > 0, (
            f"No index found for created_at. Found indexes: {index_names}"
        )
    
    async def test_approval_requests_status_index_performance(
        self,
        db_connection: asyncpg.Connection,
        clean_database,
    ):
        """Test that status index improves query performance.
        
        Requirements: 8.5
        """
        schema_path = Path("infrastructure/docker/nexus-init.sql")
        if not schema_path.exists():
            pytest.skip(f"Schema file not found at {schema_path}")
        
        await execute_schema_file(db_connection, schema_path)
        
        # Insert multiple approval requests with different statuses
        for i in range(10):
            status = "pending" if i % 2 == 0 else "approved"
            await db_connection.execute("""
                INSERT INTO approval_requests (
                    request_type, title, description, status
                )
                VALUES ($1, $2, $3, $4)
            """, "skill_approval", f"Request {i}", f"Description {i}", status)
        
        # Query with EXPLAIN to verify index usage
        explain_result = await db_connection.fetch("""
            EXPLAIN (FORMAT JSON)
            SELECT * FROM approval_requests
            WHERE status = $1
        """, "pending")
        
        # Parse EXPLAIN output
        explain_json = explain_result[0]["QUERY PLAN"]
        plan_str = str(explain_json)
        
        # Verify query plan uses index scan
        assert "Index Scan" in plan_str or "Bitmap" in plan_str, (
            f"Query does not appear to use index. Plan: {plan_str}"
        )
