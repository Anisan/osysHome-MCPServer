"""Common dispatcher entry for MCPServer tool handlers."""
# pylint: disable=protected-access

from __future__ import annotations

from plugins.MCPServer.mcp.handlers.classes_templates import handle_class_tools, handle_template_tools
from plugins.MCPServer.mcp.handlers.docs import handle_docs_tools
from plugins.MCPServer.mcp.handlers.logs import handle_log_tools
from plugins.MCPServer.mcp.handlers.methods import handle_method_tools
from plugins.MCPServer.mcp.handlers.objects_bulk import handle_bulk_and_delete_tools, handle_object_tools
from plugins.MCPServer.mcp.handlers.property_runtime import (
    handle_history_and_runtime_tools,
    handle_property_tools,
    handle_read_tools,
)
from plugins.MCPServer.mcp.handlers.source import handle_source_tools


def tools_call(plugin, params: dict) -> dict:
    tool_name = params.get("name")
    args = params.get("arguments") or {}
    if not tool_name:
        raise ValueError("Missing tool name")
    if not isinstance(args, dict):
        raise ValueError("Tool arguments must be an object")

    for handler in (
        handle_read_tools,
        handle_log_tools,
        handle_source_tools,
        handle_docs_tools,
        handle_history_and_runtime_tools,
        handle_class_tools,
        handle_template_tools,
        handle_property_tools,
        handle_method_tools,
        handle_object_tools,
        handle_bulk_and_delete_tools,
    ):
        result = handler(plugin, tool_name, args)
        if result is not None:
            return result

    raise ValueError(f"Unknown tool: {tool_name}")
