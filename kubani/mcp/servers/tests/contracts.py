"""
Contract definitions for all MCP servers.

These contracts define the expected tools for each server.
Used for contract validation testing.
"""

from kubani.framework.mcp.server.testing import MCPContract, ToolContract

# =========================================================================
# Discord MCP Contract
# =========================================================================

DISCORD_CONTRACT = MCPContract(
    server_name="Discord MCP Server",
    tools=[
        ToolContract(
            name="send_message",
            parameters={
                "channel_id": {"type": "string", "required": True},
                "content": {"type": "string", "required": False},
                "embed": {"type": "object", "required": False},
            },
        ),
        ToolContract(
            name="send_message_to_channel_name",
            parameters={
                "channel_name": {"type": "string", "required": True},
                "content": {"type": "string", "required": False},
            },
        ),
        ToolContract(
            name="get_messages",
            parameters={
                "channel_id": {"type": "string", "required": True},
                "limit": {"type": "integer", "required": False},
            },
        ),
        ToolContract(
            name="get_messages_by_channel_name",
            parameters={
                "channel_name": {"type": "string", "required": True},
                "limit": {"type": "integer", "required": False},
            },
        ),
        ToolContract(
            name="get_message",
            parameters={
                "channel_id": {"type": "string", "required": True},
                "message_id": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="delete_message",
            parameters={
                "channel_id": {"type": "string", "required": True},
                "message_id": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="await_reply",
            parameters={
                "channel_id": {"type": "string", "required": True},
                "timeout_seconds": {"type": "number", "required": False},
            },
        ),
        ToolContract(
            name="add_reaction",
            parameters={
                "channel_id": {"type": "string", "required": True},
                "message_id": {"type": "string", "required": True},
                "emoji": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="remove_reaction",
            parameters={
                "channel_id": {"type": "string", "required": True},
                "message_id": {"type": "string", "required": True},
                "emoji": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="get_reactions",
            parameters={
                "channel_id": {"type": "string", "required": True},
                "message_id": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="await_reaction",
            parameters={
                "channel_id": {"type": "string", "required": True},
                "message_id": {"type": "string", "required": True},
            },
        ),
        ToolContract(name="list_channels", parameters={}),
        ToolContract(
            name="create_channel",
            parameters={
                "name": {"type": "string", "required": True},
                "topic": {"type": "string", "required": False},
            },
        ),
        ToolContract(
            name="delete_channel",
            parameters={
                "channel_id": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="list_webhooks",
            parameters={
                "channel_id": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="create_webhook",
            parameters={
                "channel_id": {"type": "string", "required": True},
                "name": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="delete_webhook",
            parameters={
                "channel_id": {"type": "string", "required": True},
                "webhook_id": {"type": "string", "required": True},
            },
        ),
    ],
)

# =========================================================================
# Temporal MCP Contract
# =========================================================================

TEMPORAL_CONTRACT = MCPContract(
    server_name="Temporal MCP Server",
    tools=[
        ToolContract(
            name="list_workflows",
            parameters={
                "query": {"type": "string", "required": False},
                "limit": {"type": "integer", "required": False},
                "status": {"type": "string", "required": False},
            },
        ),
        ToolContract(
            name="get_workflow",
            parameters={
                "workflow_id": {"type": "string", "required": True},
                "run_id": {"type": "string", "required": False},
            },
        ),
        ToolContract(
            name="get_workflow_history",
            parameters={
                "workflow_id": {"type": "string", "required": True},
                "run_id": {"type": "string", "required": False},
                "limit": {"type": "integer", "required": False},
            },
        ),
        ToolContract(
            name="start_workflow",
            parameters={
                "workflow_type": {"type": "string", "required": True},
                "workflow_id": {"type": "string", "required": True},
                "task_queue": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="signal_workflow",
            parameters={
                "workflow_id": {"type": "string", "required": True},
                "signal_name": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="query_workflow",
            parameters={
                "workflow_id": {"type": "string", "required": True},
                "query_name": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="cancel_workflow",
            parameters={
                "workflow_id": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="terminate_workflow",
            parameters={
                "workflow_id": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="list_schedules",
            parameters={
                "limit": {"type": "integer", "required": False},
            },
        ),
        ToolContract(
            name="pause_schedule",
            parameters={
                "schedule_id": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="unpause_schedule",
            parameters={
                "schedule_id": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="trigger_schedule",
            parameters={
                "schedule_id": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="get_workflow_result",
            parameters={
                "workflow_id": {"type": "string", "required": True},
            },
        ),
        ToolContract(name="get_worker_task_queues", parameters={}),
    ],
)

# =========================================================================
# Qdrant MCP Contract
# =========================================================================

QDRANT_CONTRACT = MCPContract(
    server_name="Qdrant MCP Server",
    tools=[
        ToolContract(name="list_collections", parameters={}),
        ToolContract(
            name="create_collection",
            parameters={
                "name": {"type": "string", "required": True},
                "vector_size": {"type": "integer", "required": True},
            },
        ),
        ToolContract(
            name="delete_collection",
            parameters={
                "name": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="get_collection_info",
            parameters={
                "name": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="upsert_vectors",
            parameters={
                "collection": {"type": "string", "required": True},
                "vectors": {"type": "array", "required": True},
            },
        ),
        ToolContract(
            name="search_vectors",
            parameters={
                "collection": {"type": "string", "required": True},
                "query_vector": {"type": "array", "required": True},
            },
        ),
        ToolContract(
            name="get_point",
            parameters={
                "collection": {"type": "string", "required": True},
                "point_id": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="delete_points",
            parameters={
                "collection": {"type": "string", "required": True},
                "point_ids": {"type": "array", "required": True},
            },
        ),
        ToolContract(
            name="scroll_points",
            parameters={
                "collection": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="count_points",
            parameters={
                "collection": {"type": "string", "required": True},
            },
        ),
    ],
)

# =========================================================================
# Memory MCP Contract
# =========================================================================

MEMORY_CONTRACT = MCPContract(
    server_name="Memory MCP Server",
    tools=[
        ToolContract(
            name="store_learning",
            parameters={
                "agent_id": {"type": "string", "required": True},
                "learning_type": {"type": "string", "required": True},
                "content": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="query_learnings",
            parameters={
                "query": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="get_agent_learnings",
            parameters={
                "agent_id": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="store_knowledge",
            parameters={
                "subject": {"type": "string", "required": True},
                "predicate": {"type": "string", "required": True},
                "object": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="query_knowledge",
            parameters={
                "query": {"type": "string", "required": True},
            },
        ),
        ToolContract(name="get_knowledge_graph", parameters={}),
        ToolContract(
            name="find_related_topics",
            parameters={
                "topic": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="create_relationship",
            parameters={
                "from_entity": {"type": "string", "required": True},
                "to_entity": {"type": "string", "required": True},
                "relationship_type": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="get_entity_relationships",
            parameters={
                "entity": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="cache_set",
            parameters={
                "key": {"type": "string", "required": True},
                "value": {"type": "any", "required": True},
            },
        ),
        ToolContract(
            name="cache_get",
            parameters={
                "key": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="cache_delete",
            parameters={
                "key": {"type": "string", "required": True},
            },
        ),
        ToolContract(name="get_memory_stats", parameters={}),
        ToolContract(
            name="consolidate_learnings",
            parameters={
                "agent_id": {"type": "string", "required": True},
            },
        ),
        ToolContract(
            name="store_article",
            parameters={
                "url": {"type": "string", "required": True},
                "title": {"type": "string", "required": True},
                "content": {"type": "string", "required": True},
            },
        ),
        ToolContract(name="query_articles", parameters={}),
        ToolContract(name="check_article_exists", parameters={}),
        ToolContract(name="get_entity_counts", parameters={}),
        ToolContract(
            name="store_trend_snapshot",
            parameters={
                "snapshot_date": {"type": "string", "required": True},
                "trends": {"type": "array", "required": True},
            },
        ),
        ToolContract(name="get_trend_snapshot", parameters={}),
    ],
)

# =========================================================================
# Skills MCP Contract
# =========================================================================

SKILLS_CONTRACT = MCPContract(
    server_name="Skills MCP Server",
    tools=[
        ToolContract(name="list_skills", parameters={}),
        ToolContract(
            name="get_skill",
            parameters={
                "skill_path": {"type": "string", "required": True},
            },
        ),
        ToolContract(name="refresh_skills", parameters={}),
        ToolContract(
            name="execute_skill",
            parameters={
                "skill_path": {"type": "string", "required": True},
            },
        ),
        ToolContract(name="get_execution_outcomes", parameters={}),
        ToolContract(name="health", parameters={}),
    ],
)

# =========================================================================
# All Contracts
# =========================================================================

ALL_CONTRACTS = {
    "discord": DISCORD_CONTRACT,
    "temporal": TEMPORAL_CONTRACT,
    "qdrant": QDRANT_CONTRACT,
    "memory": MEMORY_CONTRACT,
    "skills": SKILLS_CONTRACT,
}
