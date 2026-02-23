#!/bin/bash
# Permission gate hook - auto-approves safe MCP tools, requires approval for destructive ones
# This hook runs on PermissionRequest events for MCP tools

set -e

# Get permission request from stdin with timeout to prevent hanging
INPUT=$(timeout 1s cat 2>/dev/null || echo '{}')
TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys, json; data=json.loads(sys.stdin.read()); print(data.get('tool_name', ''))" 2>/dev/null || echo "")

# If no tool name, allow (not an MCP tool)
if [ -z "$TOOL_NAME" ]; then
    exit 0
fi

# ============================================================================
# SAFE MCP TOOLS - Auto-approve these without prompting
# ============================================================================
SAFE_TOOLS=(
    # Read-only Kubernetes operations
    "mcp__kubernetes__configuration_view"
    "mcp__kubernetes__events_list"
    "mcp__kubernetes__namespaces_list"
    "mcp__kubernetes__pods_list"
    "mcp__kubernetes__pods_list_in_namespace"
    "mcp__kubernetes__pods_get"
    "mcp__kubernetes__pods_log"
    "mcp__kubernetes__pods_top"
    "mcp__kubernetes__nodes_top"
    "mcp__kubernetes__nodes_log"
    "mcp__kubernetes__nodes_stats_summary"
    "mcp__kubernetes__resources_list"
    "mcp__kubernetes__resources_get"
    "mcp__kubernetes__helm_list"

    # Read-only Discord operations
    "mcp__discord-mcp__get_messages"
    "mcp__discord-mcp__get_messages_by_channel_name"
    "mcp__discord-mcp__get_message"
    "mcp__discord-mcp__list_channels"
    "mcp__discord-mcp__list_webhooks"
    "mcp__discord-mcp__get_reactions"

    # Read-only Cloudflare operations
    "mcp__cloudflare-docs__search_cloudflare_documentation"
    "mcp__cloudflare-docs__migrate_pages_to_workers_guide"

    # All Playwright operations (auto-approved)
    "mcp__playwright__browser_close"
    "mcp__playwright__browser_resize"
    "mcp__playwright__browser_console_messages"
    "mcp__playwright__browser_handle_dialog"
    "mcp__playwright__browser_evaluate"
    "mcp__playwright__browser_file_upload"
    "mcp__playwright__browser_fill_form"
    "mcp__playwright__browser_install"
    "mcp__playwright__browser_press_key"
    "mcp__playwright__browser_type"
    "mcp__playwright__browser_navigate"
    "mcp__playwright__browser_navigate_back"
    "mcp__playwright__browser_network_requests"
    "mcp__playwright__browser_run_code"
    "mcp__playwright__browser_take_screenshot"
    "mcp__playwright__browser_snapshot"
    "mcp__playwright__browser_click"
    "mcp__playwright__browser_drag"
    "mcp__playwright__browser_hover"
    "mcp__playwright__browser_select_option"
    "mcp__playwright__browser_tabs"
    "mcp__playwright__browser_wait_for"

    # Playwright plugin variant (auto-approved)
    "mcp__plugin_playwright_playwright__browser_close"
    "mcp__plugin_playwright_playwright__browser_resize"
    "mcp__plugin_playwright_playwright__browser_console_messages"
    "mcp__plugin_playwright_playwright__browser_handle_dialog"
    "mcp__plugin_playwright_playwright__browser_evaluate"
    "mcp__plugin_playwright_playwright__browser_file_upload"
    "mcp__plugin_playwright_playwright__browser_fill_form"
    "mcp__plugin_playwright_playwright__browser_install"
    "mcp__plugin_playwright_playwright__browser_press_key"
    "mcp__plugin_playwright_playwright__browser_type"
    "mcp__plugin_playwright_playwright__browser_navigate"
    "mcp__plugin_playwright_playwright__browser_navigate_back"
    "mcp__plugin_playwright_playwright__browser_network_requests"
    "mcp__plugin_playwright_playwright__browser_run_code"
    "mcp__plugin_playwright_playwright__browser_take_screenshot"
    "mcp__plugin_playwright_playwright__browser_snapshot"
    "mcp__plugin_playwright_playwright__browser_click"
    "mcp__plugin_playwright_playwright__browser_drag"
    "mcp__plugin_playwright_playwright__browser_hover"
    "mcp__plugin_playwright_playwright__browser_select_option"
    "mcp__plugin_playwright_playwright__browser_tabs"
    "mcp__plugin_playwright_playwright__browser_wait_for"
)

# ============================================================================
# DESTRUCTIVE MCP TOOLS - Always require explicit approval
# ============================================================================
DESTRUCTIVE_TOOLS=(
    # Kubernetes destructive operations
    "mcp__kubernetes__pods_delete"
    "mcp__kubernetes__resources_delete"
    "mcp__kubernetes__helm_uninstall"

    # Discord destructive operations
    "mcp__discord-mcp__delete_message"
    "mcp__discord-mcp__delete_channel"
    "mcp__discord-mcp__delete_webhook"
)

# Check if tool is in safe list - auto-approve
for safe_tool in "${SAFE_TOOLS[@]}"; do
    if [ "$TOOL_NAME" = "$safe_tool" ]; then
        echo '{"decision": "allow"}'
        exit 0
    fi
done

# Check if tool is in destructive list - require approval with warning
for destructive_tool in "${DESTRUCTIVE_TOOLS[@]}"; do
    if [ "$TOOL_NAME" = "$destructive_tool" ]; then
        # Output warning but don't block - let the normal permission flow handle it
        echo "Destructive MCP operation: $TOOL_NAME requires explicit approval" >&2
        exit 0
    fi
done

# For unknown tools, allow normal permission flow
exit 0
