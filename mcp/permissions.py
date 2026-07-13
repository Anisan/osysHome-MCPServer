"""Permission-aware MCP tool and resource filtering for MCPServer."""
# pylint: disable=protected-access

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Tool groups mapped to MCPServer config permission flags.
TOOL_GROUPS: List[dict] = [
    {
        "id": "read",
        "title": "Object and property read",
        "permission": None,
        "tools": [
            "osys_global_search",
            "osys_list_objects",
            "osys_get_object",
            "osys_get_property",
            "osys_get_properties_batch",
            "osys_get_property_history",
            "osys_get_property_history_aggregate",
            "osys_get_property_ui",
            "osys_validate_object_template",
            "osys_render_object_template",
            "osys_get_object_context",
        ],
    },
    {
        "id": "write_property",
        "title": "Write property values",
        "permission": "allow_write_tools",
        "tools": ["osys_write_property"],
    },
    {
        "id": "method_calls",
        "title": "Call object methods",
        "permission": "allow_method_calls",
        "tools": ["osys_invoke_method"],
    },
    {
        "id": "logs",
        "title": "Log access",
        "permission": "allow_logs_access",
        "tools": ["osys_list_logs", "osys_read_log", "osys_audit_log"],
    },
    {
        "id": "source",
        "title": "Source code read",
        "permission": "allow_source_access",
        "tools": ["osys_read_source", "osys_search_source", "osys_list_source"],
    },
    {
        "id": "class_introspection",
        "title": "Class introspection",
        "permission": "allow_class_introspection",
        "tools": ["osys_get_class", "osys_list_classes", "osys_get_class_tree", "osys_get_class_full"],
    },
    {
        "id": "manage_classes",
        "title": "Class management",
        "permission": "allow_manage_classes",
        "tools": [
            "osys_add_class",
            "osys_update_class",
            "osys_delete_class",
            "osys_get_template_spec",
            "osys_validate_class_template",
            "osys_render_class_template",
        ],
    },
    {
        "id": "manage_properties",
        "title": "Property management",
        "permission": "allow_manage_properties",
        "tools": [
            "osys_add_class_property",
            "osys_update_class_property",
            "osys_add_object_property",
            "osys_update_object_property",
            "osys_delete_class_property",
            "osys_delete_object_property",
            "osys_update_property_ui",
        ],
    },
    {
        "id": "manage_methods",
        "title": "Method management",
        "permission": "allow_manage_methods",
        "tools": [
            "osys_add_class_method",
            "osys_update_class_method",
            "osys_delete_class_method",
            "osys_get_class_method_code",
            "osys_add_object_method",
            "osys_update_object_method",
            "osys_get_object_method_code",
            "osys_delete_object_method",
            "osys_validate_method_code",
            "osys_run_method_dry",
        ],
    },
    {
        "id": "manage_objects",
        "title": "Object management",
        "permission": "allow_manage_objects",
        "tools": [
            "osys_add_object",
            "osys_update_object",
            "osys_delete_object",
            "osys_bulk_update_class_properties",
            "osys_bulk_update_methods",
        ],
    },
    {
        "id": "plugins_read",
        "title": "Plugin read",
        "permission": "allow_read_plugins",
        "tools": [
            "osys_list_plugins",
            "osys_get_plugin_config",
            "osys_plugin_capabilities",
            "osys_plugin_config_schema",
            "osys_plugin_entity_schema",
            "osys_plugin_list_entities",
            "osys_plugin_get_entity",
            "osys_plugin_search",
            "osys_plugin_validate_entity_code",
            "osys_plugin_run_entity_dry",
            "osys_plugin_validate_entity",
            "osys_plugin_diff_entity",
            "osys_plugin_export_entities",
            "osys_find_bindings",
        ],
    },
    {
        "id": "plugins_write",
        "title": "Plugin write",
        "permission": "allow_manage_plugins",
        "tools": [
            "osys_update_plugin_config",
            "osys_manage_property_links",
            "osys_plugin_upsert_entity",
            "osys_plugin_delete_entity",
            "osys_plugin_invoke",
            "osys_plugin_import_entities",
            "osys_plugin_batch",
            "osys_bind_device",
        ],
    },
    {
        "id": "meta",
        "title": "Server meta",
        "permission": None,
        "tools": ["osys_server_capabilities"],
    },
    {
        "id": "ops",
        "title": "Operations and observability",
        "permission": None,
        "tools": ["osys_health", "osys_system_stats"],
    },
    {
        "id": "ops_plugins",
        "title": "Plugin diagnostics",
        "permission": "allow_manage_plugins",
        "tools": ["osys_self_test"],
    },
]

WRITE_SAFETY_TOOLS = {
    "if_match": [
        "osys_update_class",
        "osys_update_object",
        "osys_plugin_upsert_entity",
        "osys_update_plugin_config",
        "osys_bind_device",
    ],
    "dry_run": [
        "osys_run_method_dry",
        "osys_plugin_run_entity_dry",
        "osys_plugin_import_entities",
    ],
    "validate": [
        "osys_validate_method_code",
        "osys_validate_class_template",
        "osys_validate_object_template",
        "osys_plugin_validate_entity",
        "osys_plugin_validate_entity_code",
        "osys_plugin_diff_entity",
    ],
}

_STATIC_RESOURCE_RULES = {
    "osys://plugin/catalog": "allow_read_plugins",
    "osys://binding/graph": "allow_read_plugins",
}


def _build_tool_permission_map() -> Dict[str, Optional[str]]:
    mapping: Dict[str, Optional[str]] = {}
    for group in TOOL_GROUPS:
        permission = group.get("permission")
        for tool_name in group.get("tools") or []:
            mapping[str(tool_name)] = permission
    return mapping


_TOOL_PERMISSION_MAP = _build_tool_permission_map()


def permission_enabled(plugin, permission_key: str | None) -> bool:
    if permission_key is None:
        return True
    return bool(plugin.config.get(permission_key, False))


def tool_permission(tool_name: str) -> Optional[str]:
    return _TOOL_PERMISSION_MAP.get(tool_name)


def is_tool_allowed(plugin, tool_name: str) -> bool:
    permission_key = tool_permission(tool_name)
    if permission_key is None and tool_name not in _TOOL_PERMISSION_MAP:
        return True
    return permission_enabled(plugin, permission_key)


def filter_tool_schemas(plugin, schemas: List[dict]) -> List[dict]:
    return [item for item in schemas if is_tool_allowed(plugin, str(item.get("name") or ""))]


def tool_groups_payload(plugin) -> List[dict]:
    groups = []
    for group in TOOL_GROUPS:
        permission = group.get("permission")
        enabled = permission_enabled(plugin, permission)
        groups.append(
            {
                "id": group["id"],
                "title": group["title"],
                "permission": permission,
                "enabled": enabled,
                "tools": list(group["tools"]),
            }
        )
    return groups


def static_resource_allowed(plugin, uri: str) -> bool:
    rule = _STATIC_RESOURCE_RULES.get(uri)
    if rule is None:
        return True
    return permission_enabled(plugin, rule)


def filter_static_resources(plugin, resources: List[dict]) -> List[dict]:
    return [
        item
        for item in resources
        if static_resource_allowed(plugin, str(item.get("uri") or ""))
    ]


def resource_access_payload(plugin) -> Dict[str, Any]:
    from plugins.MCPServer.mcp import resources as mcp_resources

    static_items = []
    for item in mcp_resources.STATIC_RESOURCE_DEFINITIONS:
        uri = str(item.get("uri") or "")
        allowed = static_resource_allowed(plugin, uri)
        static_items.append(
            {
                "uri": uri,
                "allowed": allowed,
                "permission": _STATIC_RESOURCE_RULES.get(uri),
            }
        )
    allowed_plugins = list(plugin.config.get("plugins_allowed") or [])
    plugin_items = []
    for plugin_name in allowed_plugins:
        plugin_items.append(
            {
                "uri": f"osys://plugin/{plugin_name}",
                "allowed": permission_enabled(plugin, "allow_read_plugins"),
            }
        )
        plugin_items.append(
            {
                "uri": f"osys://plugin/{plugin_name}/schema/{{collection}}",
                "allowed": permission_enabled(plugin, "allow_read_plugins"),
            }
        )
    return {
        "static": static_items,
        "dynamic": [
            {"pattern": "osys://object/{object_name}", "allowed": True},
            {"pattern": "osys://property/{property_name}", "allowed": True},
        ],
        "plugin": plugin_items,
    }


def plugins_allowed_list(plugin) -> List[str]:
    allowed = plugin.config.get("plugins_allowed") or []
    if not isinstance(allowed, list):
        return []
    return [str(item).strip() for item in allowed if str(item).strip()]


def plugin_is_whitelisted(plugin, plugin_name: str) -> bool:
    allowed = plugins_allowed_list(plugin)
    if not allowed:
        return False
    return plugin_name in allowed


PERMISSION_ADMIN_CARDS: Dict[str, dict] = {
    "allow_write_tools": {
        "title": "Write properties",
        "risk": "medium",
        "risk_label": "Medium",
        "description": "Change object property values via MCP.",
    },
    "allow_method_calls": {
        "title": "Invoke methods",
        "risk": "medium",
        "risk_label": "Medium",
        "description": "Run object/class methods remotely.",
    },
    "allow_logs_access": {
        "title": "Logs access",
        "risk": "high",
        "risk_label": "High",
        "description": "May expose sensitive runtime data from application logs and audit trail.",
    },
    "allow_source_access": {
        "title": "Source code (read-only)",
        "risk": "high",
        "risk_label": "High",
        "description": "Browse and search application source files.",
    },
    "allow_class_introspection": {
        "title": "Class introspection",
        "risk": "low",
        "risk_label": "Low",
        "description": "Read class definitions, hierarchy, and metadata.",
    },
    "allow_manage_classes": {
        "title": "Class management",
        "risk": "critical",
        "risk_label": "Critical",
        "description": "Create, modify, or delete classes in the object model.",
    },
    "allow_manage_objects": {
        "title": "Object management",
        "risk": "critical",
        "risk_label": "Critical",
        "description": "Create, update, or remove objects and their runtime state.",
    },
    "allow_manage_properties": {
        "title": "Property management",
        "risk": "critical",
        "risk_label": "Critical",
        "description": "Manage class/object property schema and remove obsolete fields.",
    },
    "allow_manage_methods": {
        "title": "Method management",
        "risk": "critical",
        "risk_label": "Critical",
        "description": "Create, validate, and delete method implementations in objects/classes.",
    },
    "allow_read_plugins": {
        "title": "Plugin read tools",
        "risk": "low",
        "risk_label": "Low",
        "description": "List plugins, read config, list and inspect plugin entities.",
        "notes": [
            "Each call also requires the target plugin to be in plugins_allowed whitelist.",
        ],
    },
    "allow_manage_plugins": {
        "title": "Plugin write tools",
        "risk": "high",
        "risk_label": "High",
        "description": "Update plugin config, manage entities, invoke plugin actions.",
        "notes": [
            "Each call also requires the target plugin to be in plugins_allowed whitelist.",
        ],
    },
}


def _tool_names_for_config_key(config_key: str) -> List[str]:
    names: List[str] = []
    seen = set()
    for group in TOOL_GROUPS:
        if group.get("permission") == config_key:
            for tool_name in group.get("tools") or []:
                tool_name = str(tool_name).strip()
                if tool_name and tool_name not in seen:
                    seen.add(tool_name)
                    names.append(tool_name)
    return names


def _tool_schema_map(plugin) -> Dict[str, str]:
    from plugins.MCPServer.mcp.tools_schema import build_tools_schema

    schema = build_tools_schema(plugin._property_params_schema())
    mapping: Dict[str, str] = {}
    for item in schema:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        mapping[name] = str(item.get("description") or "").strip()
    return mapping


DEFAULT_ACCESS_CONFIG_KEY = "default_access"

DEFAULT_ACCESS_META = {
    "title": "Default access",
    "risk": "low",
    "risk_label": "Low",
    "description": "Core read and server tools available without enabling permission toggles.",
    "notes": [
        "Still requires a valid MCP auth token when authentication is configured.",
        "Plugin-specific tools require separate plugin read permission and whitelist.",
    ],
}


def _default_access_groups(schema_map: Dict[str, str]) -> List[dict]:
    groups: List[dict] = []
    for group in TOOL_GROUPS:
        if group.get("permission") is not None:
            continue
        tools = [
            {
                "name": str(tool_name).strip(),
                "description": schema_map.get(str(tool_name).strip(), ""),
            }
            for tool_name in (group.get("tools") or [])
            if str(tool_name).strip()
        ]
        if not tools:
            continue
        groups.append(
            {
                "id": group.get("id"),
                "title": group.get("title") or group.get("id"),
                "tools": tools,
                "tool_count": len(tools),
            }
        )
    return groups


def _build_default_access_catalog(plugin) -> dict:
    schema_map = _tool_schema_map(plugin)
    groups = _default_access_groups(schema_map)
    tools: List[dict] = []
    seen = set()
    for group in groups:
        for tool in group.get("tools") or []:
            name = str(tool.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            tools.append(tool)

    meta = DEFAULT_ACCESS_META
    return {
        "id": DEFAULT_ACCESS_CONFIG_KEY,
        "title": meta.get("title") or DEFAULT_ACCESS_CONFIG_KEY,
        "description": meta.get("description", ""),
        "risk": meta.get("risk"),
        "risk_label": meta.get("risk_label"),
        "permission_key": None,
        "enabled": True,
        "always_on": True,
        "tools": tools,
        "groups": groups,
        "tool_count": len(tools),
        "notes": list(meta.get("notes") or []),
    }


def get_permission_category_catalog(plugin, config_key: str) -> Optional[dict]:
    """Build MCP tools catalog for one admin permission category."""
    config_key = str(config_key or "").strip()
    if config_key == DEFAULT_ACCESS_CONFIG_KEY:
        return _build_default_access_catalog(plugin)

    meta = PERMISSION_ADMIN_CARDS.get(config_key)
    if not meta:
        return None

    tool_names = _tool_names_for_config_key(config_key)
    if not tool_names:
        return None

    schema_map = _tool_schema_map(plugin)
    tools = [
        {
            "name": name,
            "description": schema_map.get(name, ""),
        }
        for name in tool_names
    ]

    enabled = permission_enabled(plugin, config_key)
    notes = list(meta.get("notes") or [])

    return {
        "id": config_key,
        "title": meta.get("title") or config_key,
        "description": meta.get("description", ""),
        "risk": meta.get("risk"),
        "risk_label": meta.get("risk_label"),
        "permission_key": config_key,
        "enabled": enabled,
        "tools": tools,
        "tool_count": len(tools),
        "notes": notes,
    }
