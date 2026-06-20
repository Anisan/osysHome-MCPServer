"""Assemble MCP tool schemas from handler modules."""

from __future__ import annotations

from typing import Dict, List

from plugins.MCPServer.mcp.handlers.classes_templates import get_tool_schemas as class_template_schemas
from plugins.MCPServer.mcp.handlers.docs import get_tool_schemas as docs_schemas
from plugins.MCPServer.mcp.handlers.logs import get_tool_schemas as logs_schemas
from plugins.MCPServer.mcp.handlers.methods import get_tool_schemas as method_schemas
from plugins.MCPServer.mcp.handlers.objects_bulk import get_tool_schemas as object_bulk_schemas
from plugins.MCPServer.mcp.handlers.property_runtime import get_tool_schemas as property_runtime_schemas
from plugins.MCPServer.mcp.handlers.source import get_tool_schemas as source_schemas


def build_tools_schema(property_params_schema: Dict, include_docs_tools: bool = True) -> List[dict]:
    schemas: List[dict] = []
    providers = [
        property_runtime_schemas,
        logs_schemas,
        source_schemas,
        class_template_schemas,
        method_schemas,
        object_bulk_schemas,
    ]
    if include_docs_tools:
        providers.insert(1, docs_schemas)
    for provider in providers:
        schemas.extend(provider(property_params_schema))
    return schemas
