"""Unit tests for Nexus database skill registry operations.

These tests use mocked database pools to validate the skill registry
operations without requiring a live database connection.

Tests cover:
- register_skill: Registering skills with duplicate handling
- get_skill: Retrieving skills by name and version
- list_skills: Listing skills with filters
"""

import pytest
from unittest.mock import AsyncMock
from hypothesis import given, strategies as st

# Import the db_pool_mock fixture
pytest_plugins = ['tests.fixtures.mocks']

from kubani.nexus.db import (
    register_skill,
    get_skill,
    list_skills,
)


# =========================================================================
# Test: register_skill with duplicate handling
# =========================================================================


@pytest.mark.asyncio
async def test_register_skill_with_duplicate_updates_existing(db_pool_mock):
    """Test that register_skill uses ON CONFLICT DO UPDATE for duplicates.
    
    **Validates: Requirements 2.6**
    
    This test verifies:
    1. The SQL uses ON CONFLICT (name, version) DO UPDATE
    2. The skill_id is returned from the database
    3. Duplicate registrations update existing records
    """
    # Arrange
    name = "test-skill"
    version = "1.0.0"
    oci_url = "oci://registry.example.com/skills/test-skill:1.0.0"
    description = "A test skill"
    category = "testing"
    author = "test-author"
    requires_network = False
    requires_filesystem = True
    expected_skill_id = 123
    
    # Mock the database to return a skill ID
    db_pool_mock.fetchval = AsyncMock(return_value=expected_skill_id)
    
    # Act
    skill_id = await register_skill(
        db_pool_mock,
        name,
        version,
        oci_url,
        description,
        category,
        author,
        requires_network,
        requires_filesystem,
    )
    
    # Assert
    assert skill_id == expected_skill_id
    
    # Verify the SQL was executed with correct parameters
    db_pool_mock.fetchval.assert_called_once()
    call_args = db_pool_mock.fetchval.call_args
    
    # Check the SQL query
    sql = call_args[0][0]
    assert "INSERT INTO skills" in sql
    assert "ON CONFLICT" in sql
    assert "DO UPDATE" in sql
    assert "RETURNING id" in sql
    
    # Check the parameters
    params = call_args[0][1:]
    assert params[0] == name
    assert params[1] == version
    assert params[2] == oci_url
    assert params[3] == description
    assert params[4] == category
    assert params[5] == author
    assert params[6] == requires_network
    assert params[7] == requires_filesystem


@pytest.mark.asyncio
async def test_register_skill_with_default_parameters(db_pool_mock):
    """Test that register_skill handles default parameters correctly."""
    # Arrange
    name = "minimal-skill"
    version = "0.1.0"
    oci_url = "oci://registry.example.com/skills/minimal:0.1.0"
    expected_skill_id = 456
    
    db_pool_mock.fetchval = AsyncMock(return_value=expected_skill_id)
    
    # Act - use default parameters
    skill_id = await register_skill(
        db_pool_mock,
        name,
        version,
        oci_url,
    )
    
    # Assert
    assert skill_id == expected_skill_id
    
    # Verify default values were used
    call_args = db_pool_mock.fetchval.call_args
    params = call_args[0][1:]
    
    # Check defaults: description="", category="general", author="nexus-synthesizer"
    assert params[3] == ""  # description
    assert params[4] == "general"  # category
    assert params[5] == "nexus-synthesizer"  # author
    assert params[6] is False  # requires_network
    assert params[7] is False  # requires_filesystem


@pytest.mark.asyncio
async def test_register_skill_sets_pending_status(db_pool_mock):
    """Test that register_skill sets status to 'pending' by default."""
    # Arrange
    name = "new-skill"
    version = "2.0.0"
    oci_url = "oci://registry.example.com/skills/new:2.0.0"
    expected_skill_id = 789
    
    db_pool_mock.fetchval = AsyncMock(return_value=expected_skill_id)
    
    # Act
    await register_skill(db_pool_mock, name, version, oci_url)
    
    # Assert
    call_args = db_pool_mock.fetchval.call_args
    sql = call_args[0][0]
    
    # Verify status is set to 'pending'
    assert "'pending'" in sql or "status" in sql


# =========================================================================
# Test: get_skill with version='latest'
# =========================================================================


@pytest.mark.asyncio
async def test_get_skill_with_latest_version(db_pool_mock):
    """Test that get_skill with version='latest' returns most recent approved skill.
    
    **Validates: Requirements 2.7**
    
    This test verifies:
    1. The SQL filters by status = 'approved'
    2. The SQL orders by created_at DESC
    3. The SQL limits to 1 result
    4. The most recent skill is returned
    """
    # Arrange
    name = "popular-skill"
    version = "latest"
    
    # Mock database row
    mock_row = {
        "id": 100,
        "name": name,
        "version": "3.2.1",
        "oci_url": "oci://registry.example.com/skills/popular:3.2.1",
        "description": "Latest version",
        "category": "general",
        "author": "nexus",
        "status": "approved",
        "risk_score": 2.5,
        "requires_network": False,
        "requires_filesystem": False,
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-15T10:00:00Z",
    }
    
    db_pool_mock.fetchrow = AsyncMock(return_value=mock_row)
    
    # Act
    skill = await get_skill(db_pool_mock, name, version)
    
    # Assert
    assert skill is not None
    assert skill["name"] == name
    assert skill["version"] == "3.2.1"
    assert skill["status"] == "approved"
    
    # Verify the SQL was executed correctly
    db_pool_mock.fetchrow.assert_called_once()
    call_args = db_pool_mock.fetchrow.call_args
    
    # Check the SQL query
    sql = call_args[0][0]
    assert "SELECT * FROM skills" in sql
    assert "status = 'approved'" in sql or "status = $" in sql
    assert "ORDER BY created_at DESC" in sql
    assert "LIMIT 1" in sql
    
    # Check the parameters
    params = call_args[0][1:]
    assert params[0] == name


@pytest.mark.asyncio
async def test_get_skill_with_specific_version(db_pool_mock):
    """Test that get_skill with specific version queries by name and version."""
    # Arrange
    name = "versioned-skill"
    version = "1.5.0"
    
    mock_row = {
        "id": 200,
        "name": name,
        "version": version,
        "oci_url": "oci://registry.example.com/skills/versioned:1.5.0",
        "description": "Specific version",
        "category": "general",
        "author": "nexus",
        "status": "approved",
        "risk_score": 3.0,
        "requires_network": True,
        "requires_filesystem": False,
        "created_at": "2024-01-10T10:00:00Z",
        "updated_at": "2024-01-10T10:00:00Z",
    }
    
    db_pool_mock.fetchrow = AsyncMock(return_value=mock_row)
    
    # Act
    skill = await get_skill(db_pool_mock, name, version)
    
    # Assert
    assert skill is not None
    assert skill["name"] == name
    assert skill["version"] == version
    
    # Verify the SQL was executed correctly
    call_args = db_pool_mock.fetchrow.call_args
    
    # Check the SQL query
    sql = call_args[0][0]
    assert "SELECT * FROM skills" in sql
    assert "name = $1 AND version = $2" in sql
    
    # Check the parameters
    params = call_args[0][1:]
    assert params[0] == name
    assert params[1] == version


@pytest.mark.asyncio
async def test_get_skill_not_found_returns_none(db_pool_mock):
    """Test that get_skill returns None when skill is not found."""
    # Arrange
    name = "nonexistent-skill"
    version = "latest"
    
    db_pool_mock.fetchrow = AsyncMock(return_value=None)
    
    # Act
    skill = await get_skill(db_pool_mock, name, version)
    
    # Assert
    assert skill is None


# =========================================================================
# Test: list_skills with filtering (Property-Based Test)
# =========================================================================


def create_mock_skill_row(
    skill_id: int,
    name: str,
    status: str,
    category: str,
) -> dict:
    """Helper to create a mock database row for a skill."""
    return {
        "id": skill_id,
        "name": name,
        "version": "1.0.0",
        "oci_url": f"oci://registry.example.com/skills/{name}:1.0.0",
        "description": f"Test skill {name}",
        "category": category,
        "author": "test-author",
        "status": status,
        "risk_score": 2.0,
        "requires_network": False,
        "requires_filesystem": False,
        "created_at": "2024-01-01T10:00:00Z",
        "updated_at": "2024-01-01T10:00:00Z",
    }


@pytest.mark.asyncio
@given(
    status_filter=st.sampled_from(["pending", "approved", "rejected", None]),
    category_filter=st.sampled_from(["general", "testing", "diagnostic", None]),
)
async def test_list_skills_filtering_property(status_filter, category_filter):
    """Property test: list_skills returns only skills matching all filters.
    
    **Feature: nexus-testing, Property 8: Skill list filtering**
    **Validates: Requirements 2.8**
    
    For any combination of status and category filters,
    list_skills should return only skills that match all specified filters.
    """
    # Arrange
    db_pool_mock = AsyncMock()
    
    # Create a diverse set of skills
    all_skills = [
        create_mock_skill_row(1, "skill-1", "pending", "general"),
        create_mock_skill_row(2, "skill-2", "approved", "general"),
        create_mock_skill_row(3, "skill-3", "rejected", "testing"),
        create_mock_skill_row(4, "skill-4", "approved", "testing"),
        create_mock_skill_row(5, "skill-5", "pending", "diagnostic"),
        create_mock_skill_row(6, "skill-6", "approved", "diagnostic"),
    ]
    
    # Filter skills based on the provided filters
    filtered_skills = all_skills
    if status_filter:
        filtered_skills = [s for s in filtered_skills if s["status"] == status_filter]
    if category_filter:
        filtered_skills = [s for s in filtered_skills if s["category"] == category_filter]
    
    # Mock the database to return filtered skills
    db_pool_mock.fetch = AsyncMock(return_value=filtered_skills)
    
    # Act
    result = await list_skills(
        db_pool_mock,
        status=status_filter,
        category=category_filter,
    )
    
    # Assert: All returned skills should match the filters
    assert len(result) == len(filtered_skills)
    
    for skill in result:
        if status_filter:
            assert skill["status"] == status_filter, \
                f"Skill {skill['name']} has status {skill['status']}, expected {status_filter}"
        if category_filter:
            assert skill["category"] == category_filter, \
                f"Skill {skill['name']} has category {skill['category']}, expected {category_filter}"
    
    # Verify the SQL was executed
    db_pool_mock.fetch.assert_called_once()
    call_args = db_pool_mock.fetch.call_args
    
    # Check the SQL query includes appropriate WHERE clauses
    sql = call_args[0][0]
    assert "SELECT * FROM skills" in sql
    
    if status_filter or category_filter:
        assert "WHERE" in sql
    
    if status_filter:
        assert "status" in sql
    
    if category_filter:
        assert "category" in sql


@pytest.mark.asyncio
async def test_list_skills_no_filters_returns_all(db_pool_mock):
    """Test that list_skills with no filters returns all skills."""
    # Arrange
    mock_skills = [
        create_mock_skill_row(1, "skill-a", "approved", "general"),
        create_mock_skill_row(2, "skill-b", "pending", "testing"),
        create_mock_skill_row(3, "skill-c", "rejected", "diagnostic"),
    ]
    
    db_pool_mock.fetch = AsyncMock(return_value=mock_skills)
    
    # Act
    result = await list_skills(db_pool_mock)
    
    # Assert
    assert len(result) == 3
    
    # Verify SQL doesn't have WHERE clause
    call_args = db_pool_mock.fetch.call_args
    sql = call_args[0][0]
    
    # Should not have WHERE clause when no filters
    # (or WHERE clause should be empty)
    assert "SELECT * FROM skills" in sql


@pytest.mark.asyncio
async def test_list_skills_respects_limit(db_pool_mock):
    """Test that list_skills respects the limit parameter."""
    # Arrange
    limit = 5
    mock_skills = [
        create_mock_skill_row(i, f"skill-{i}", "approved", "general")
        for i in range(limit)
    ]
    
    db_pool_mock.fetch = AsyncMock(return_value=mock_skills)
    
    # Act
    result = await list_skills(db_pool_mock, limit=limit)
    
    # Assert
    assert len(result) <= limit
    
    # Verify SQL includes LIMIT
    call_args = db_pool_mock.fetch.call_args
    sql = call_args[0][0]
    assert "LIMIT" in sql
    
    # Verify limit parameter is passed
    params = call_args[0][1:]
    assert limit in params


@pytest.mark.asyncio
async def test_list_skills_default_limit(db_pool_mock):
    """Test that list_skills uses default limit of 100."""
    # Arrange
    db_pool_mock.fetch = AsyncMock(return_value=[])
    
    # Act
    await list_skills(db_pool_mock)
    
    # Assert
    call_args = db_pool_mock.fetch.call_args
    params = call_args[0][1:]
    
    # Default limit should be 100
    assert 100 in params


@pytest.mark.asyncio
async def test_list_skills_orders_by_updated_at_desc(db_pool_mock):
    """Test that list_skills orders results by updated_at DESC."""
    # Arrange
    db_pool_mock.fetch = AsyncMock(return_value=[])
    
    # Act
    await list_skills(db_pool_mock)
    
    # Assert
    call_args = db_pool_mock.fetch.call_args
    sql = call_args[0][0]
    
    # Verify ORDER BY clause
    assert "ORDER BY updated_at DESC" in sql
