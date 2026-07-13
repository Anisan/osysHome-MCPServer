"""Common dispatcher entry for MCPServer tool handlers."""
# pylint: disable=protected-access

from __future__ import annotations

import time

from plugins.MCPServer.mcp.handlers.classes_templates import handle_class_tools, handle_template_tools
from plugins.MCPServer.mcp.handlers.logs import handle_log_tools
from plugins.MCPServer.mcp.handlers.methods import handle_method_tools
from plugins.MCPServer.mcp.handlers.objects_bulk import handle_bulk_and_delete_tools, handle_object_tools
from plugins.MCPServer.mcp.handlers.meta import handle_meta_tools
from plugins.MCPServer.mcp.handlers.plugins import handle_plugin_tools
from plugins.MCPServer.mcp.handlers.property_runtime import (
    handle_history_and_runtime_tools,
    handle_property_tools,
    handle_read_tools,
)
from plugins.MCPServer.mcp.handlers.source import handle_source_tools
from plugins.MCPServer.mcp.logging_support import log_tool_call
from plugins.MCPServer.mcp.telemetry import record_tool_call


def tools_call(plugin, params: dict) -> dict:
    tool_name = params.get("name")
    args = params.get("arguments") or {}
    if not tool_name:
        raise ValueError("Missing tool name")
    if not isinstance(args, dict):
        raise ValueError("Tool arguments must be an object")

    plugin_name = None
    if str(tool_name).startswith("osys_plugin_"):
        plugin_name = str(args.get("plugin") or "").strip() or None

    started = time.perf_counter()
    ok = True
    error = None
    error_type = None
    correlation_id = None
    try:
        for handler in (
            handle_meta_tools,
            handle_read_tools,
            handle_log_tools,
            handle_source_tools,
            handle_history_and_runtime_tools,
            handle_class_tools,
            handle_template_tools,
            handle_property_tools,
            handle_method_tools,
            handle_object_tools,
            handle_bulk_and_delete_tools,
            handle_plugin_tools,
        ):
            result = handler(plugin, tool_name, args)
            if result is not None:
                return result

        raise ValueError(f"Unknown tool: {tool_name}")
    except Exception as ex:
        ok = False
        error = str(ex)
        error_type = type(ex).__name__
        raise
    finally:
        duration_ms = (time.perf_counter() - started) * 1000.0
        correlation_id = record_tool_call(
            str(tool_name),
            duration_ms,
            ok,
            plugin=plugin_name,
            error=error,
            correlation_id=str(args.get("correlation_id") or "").strip() or None,
        )
        log_tool_call(
            plugin.logger,
            str(tool_name),
            duration_ms,
            ok,
            plugin=plugin_name,
            error=error,
            error_type=error_type,
            correlation_id=correlation_id,
        )
