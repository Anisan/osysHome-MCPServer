"""MCPServer meta tools: server capabilities introspection."""
# pylint: disable=protected-access

from __future__ import annotations

from typing import Any, Dict, List

from app.core.lib.common import getModule
from app.core.lib.mcp_contract import validate_plugin_mcp_capabilities
from plugins.MCPServer.mcp.handlers.plugins import list_mcp_capable_plugins
from plugins.MCPServer.mcp import resources as mcp_resources
from plugins.MCPServer.mcp.permissions import (
    WRITE_SAFETY_TOOLS,
    filter_tool_schemas,
    plugin_is_whitelisted,
    resource_access_payload,
    tool_groups_payload,
)
from plugins.MCPServer.mcp.telemetry import telemetry_summary

_CAPABILITY_NOTES = [
    "plugins_allowed empty list denies all plugin atomic MCP tools",
    "plugin write tools require allow_manage_plugins",
    "plugin read tools require allow_read_plugins",
    "Plugin config updates support optional if_match revision",
    "Secrets in osys_get_plugin_config are masked",
    "Dynamic resources include osys://object/{name} per loaded objects",
    "tools/list returns only tools allowed by current MCPServer permissions",
]


def _permissions_payload(plugin) -> dict:
    return {
        "auth_enabled": bool(str(plugin.config.get("auth_token") or "").strip()),
        "allow_write_tools": bool(plugin.config.get("allow_write_tools", False)),
        "allow_method_calls": bool(plugin.config.get("allow_method_calls", True)),
        "allow_logs_access": bool(plugin.config.get("allow_logs_access", False)),
        "allow_source_access": bool(plugin.config.get("allow_source_access", False)),
        "allow_class_introspection": bool(plugin.config.get("allow_class_introspection", False)),
        "allow_manage_classes": bool(plugin.config.get("allow_manage_classes", False)),
        "allow_manage_objects": bool(plugin.config.get("allow_manage_objects", False)),
        "allow_manage_properties": bool(plugin.config.get("allow_manage_properties", False)),
        "allow_manage_methods": bool(plugin.config.get("allow_manage_methods", False)),
        "allow_read_plugins": bool(plugin.config.get("allow_read_plugins", True)),
        "allow_manage_plugins": bool(plugin.config.get("allow_manage_plugins", False)),
        "plugins_allowed": list(plugin.config.get("plugins_allowed") or []),
        "max_list_items": int(plugin.config.get("max_list_items", 200)),
        "allow_docs_access": bool(plugin.config.get("allow_docs_access", False)),
        "docs_available": bool(plugin._docs_available()),
    }


def _mcp_plugins_payload(plugin) -> List[dict]:
    allowed = set(plugin.config.get("plugins_allowed") or [])
    items = []
    for entry in list_mcp_capable_plugins():
        name = entry.get("name")
        contract = {"ok": False, "errors": ["plugin not loaded"]}
        descriptors = {"tools": 0, "resources": 0, "prompts": 0}
        instance = getModule(name) if name else None
        if instance is not None:
            try:
                contract = validate_plugin_mcp_capabilities(instance.mcp_capabilities())
            except Exception as ex:
                contract = {"ok": False, "errors": [str(ex)]}
            try:
                descriptors = {
                    "tools": len(instance.mcp_tools() or []),
                    "resources": len(instance.mcp_resources() or []),
                    "prompts": len(instance.mcp_prompts() or []),
                }
            except Exception:
                pass
        items.append(
            {
                **entry,
                "allowed": plugin_is_whitelisted(plugin, name) if name else False,
                "contract": contract,
                "descriptors": descriptors,
            }
        )
    return items


def _plugin_tools_payload(plugin) -> Dict[str, Any]:
    payload = {}
    for plugin_name in plugin.config.get("plugins_allowed") or []:
        instance = getModule(plugin_name)
        if instance is None:
            continue
        try:
            payload[plugin_name] = {
                "tools": instance.mcp_tools() or [],
                "resources": instance.mcp_resources() or [],
                "prompts": instance.mcp_prompts() or [],
            }
        except Exception as ex:
            payload[plugin_name] = {"error": str(ex)}
    return payload


def build_server_capabilities(plugin) -> Dict[str, Any]:
    """Build server capabilities document for tool and resource consumers."""
    from plugins.MCPServer.mcp.tools_schema import build_tools_schema

    schema = build_tools_schema(
        plugin._property_params_schema(),
        include_docs_tools=plugin._docs_available(),
    )
    tool_names = {item["name"] for item in schema}
    available_schema = filter_tool_schemas(plugin, schema)
    available_names = {item["name"] for item in available_schema}
    groups = tool_groups_payload(plugin)
    for group in groups:
        group["tools_present"] = [name for name in group["tools"] if name in tool_names]
        group["tools_available"] = [name for name in group["tools"] if name in available_names]

    return {
        "protocol_version": plugin._PROTOCOL_VERSION,
        "server_name": "osysHome MCP Server",
        "server_version": str(plugin.version),
        "endpoint": "/api/mcp",
        "permissions": _permissions_payload(plugin),
        "tool_groups": groups,
        "tools_listed": sorted(tool_names),
        "tools_listed_count": len(tool_names),
        "tools_available": sorted(available_names),
        "tools_available_count": len(available_names),
        "write_safety": dict(WRITE_SAFETY_TOOLS),
        "resource_access": resource_access_payload(plugin),
        "plugin_tools": _plugin_tools_payload(plugin),
        "telemetry": telemetry_summary(limit=10),
        "mcp_capable_plugins": _mcp_plugins_payload(plugin),
        "resources": {
            "static": [item["uri"] for item in mcp_resources.STATIC_RESOURCE_DEFINITIONS],
            "dynamic": [
                "osys://object/{object_name}",
                "osys://property/{property_name}",
                "osys://plugin/{plugin_name}",
                "osys://plugin/{plugin_name}/schema/{collection}",
            ],
        },
        "prompts": [item["name"] for item in mcp_resources.prompts_list(plugin)],
        "osys_plugin_actions": {
            "read": sorted(
                [
                    "osys_plugin_capabilities",
                    "osys_plugin_config_schema",
                    "osys_plugin_entity_schema",
                    "osys_plugin_list_entities",
                    "osys_plugin_get_entity",
                    "osys_plugin_search",
                    "osys_plugin_validate_entity_code",
                    "osys_plugin_run_entity_dry",
                ]
            ),
            "write": sorted(
                [
                    "osys_plugin_upsert_entity",
                    "osys_plugin_delete_entity",
                    "osys_plugin_invoke",
                ]
            ),
        },
        "notes": list(_CAPABILITY_NOTES),
    }


def handle_meta_tools(plugin, tool_name: str, args: dict):
    _ = args
    if tool_name == "osys_server_capabilities":
        return plugin._tool_result(build_server_capabilities(plugin))
    if tool_name == "osys_health":
        try:
            from sqlalchemy import text

            with __import__("app.database", fromlist=["session_scope"]).session_scope() as session:
                session.execute(text("SELECT 1"))
            database_state = "ok"
        except Exception:
            database_state = "error"
        from app.core.main.ObjectsStorage import objects_storage

        return plugin._tool_result(
            {
                "ok": database_state == "ok",
                "database": database_state,
                "objects_loaded": len(objects_storage.objects),
                "plugins_active": len(__import__("app.core.main.PluginsHelper", fromlist=["plugins"]).plugins),
                "mcp_whitelist_count": len(plugin.config.get("plugins_allowed") or []),
                "docs_available": bool(plugin._docs_available()),
                "version": str(plugin.version),
                "telemetry": telemetry_summary(limit=5),
            }
        )
    if tool_name == "osys_self_test":
        plugin._require_permission("allow_manage_plugins", "Plugin management tools are disabled")
        steps = []
        all_ok = True
        checks = [
            ("list_objects", lambda: plugin._tool_list_objects({"limit": 1})),
            ("server_capabilities", lambda: build_server_capabilities(plugin)),
        ]
        for name, fn in checks:
            try:
                fn()
                steps.append({"name": name, "ok": True})
            except Exception as ex:
                all_ok = False
                steps.append({"name": name, "ok": False, "error": str(ex)})
        for plugin_name in plugin.config.get("plugins_allowed") or []:
            try:
                result = __import__(
                    "plugins.MCPServer.mcp.handlers.plugins",
                    fromlist=["_dispatch_plugin_action"],
                )._dispatch_plugin_action(
                    plugin,
                    {"plugin": plugin_name, "action": "capabilities", "args": {}},
                )
                steps.append({"name": f"plugin_capabilities:{plugin_name}", "ok": True, "result": bool(result)})
            except Exception as ex:
                all_ok = False
                steps.append({"name": f"plugin_capabilities:{plugin_name}", "ok": False, "error": str(ex)})
        return plugin._tool_result({"all_ok": all_ok, "steps": steps})
    if tool_name == "osys_system_stats":
        from app.core.lib.object import getObject

        stats_obj = getObject("SystemStats")
        if not stats_obj:
            return plugin._tool_result({"plugin": args.get("plugin"), "metrics": {}})
        plugin_name = str(args.get("plugin") or "").strip()
        prefix = str(args.get("prefix") or "").strip()
        metrics = {}
        for name, prop in stats_obj.properties.items():
            if plugin_name:
                expected_prefix = f"plugin_{plugin_name}_"
                if not name.startswith(expected_prefix):
                    continue
            if prefix and not name.startswith(prefix):
                continue
            metrics[name] = {
                "value": plugin._serialize_value(prop.getValue()),
                "type": getattr(prop, "type", ""),
            }
        return plugin._tool_result(
            {
                "plugin": plugin_name or None,
                "metrics": metrics,
                "telemetry": telemetry_summary(limit=10),
            }
        )
    if tool_name == "osys_audit_log":
        plugin._require_permission("allow_logs_access", "Log access tools are disabled in plugin config")
        import os

        from app.configuration import Config

        path = os.path.join(Config.APP_DIR, "logs", "security_audit.log")
        if not os.path.isfile(path):
            return plugin._tool_result({"items": [], "count": 0})
        query = str(args.get("query") or "").strip().lower()
        action = str(args.get("action") or "").strip()
        limit = plugin._safe_int(args.get("limit"), 50, 1, 500)
        with open(path, "r", encoding="utf-8", errors="ignore") as source:
            lines = source.readlines()
        items = []
        for line in reversed(lines):
            text = line.strip()
            if not text:
                continue
            if query and query not in text.lower():
                continue
            if action and action not in text:
                continue
            items.append({"raw": text})
            if len(items) >= limit:
                break
        return plugin._tool_result({"count": len(items), "items": items})
    return None


def get_tool_schemas(_property_params_schema) -> list[dict]:
    return [
        {
            "name": "osys_server_capabilities",
            "description": "Return MCPServer permissions, tool groups, and MCP plugin catalog for AI clients",
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
        },
        {
            "name": "osys_health",
            "description": "MCP server health check",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "osys_self_test",
            "description": "Run read-only MCP smoke tests",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "osys_system_stats",
            "description": "Read SystemStats metrics",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plugin": {"type": "string"},
                    "prefix": {"type": "string"},
                },
            },
        },
        {
            "name": "osys_audit_log",
            "description": "Read security audit records (masked)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "action": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                },
            },
        },
    ]
