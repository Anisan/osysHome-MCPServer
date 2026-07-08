"""MCP resources and prompts helpers for MCPServer plugin."""
# pylint: disable=protected-access

from __future__ import annotations

import json
from typing import List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

from app.core.lib.object import getObject, getProperty
from app.core.lib.common import getModule
from app.core.models.Clasess import Object
from app.database import session_scope

STATIC_RESOURCE_DEFINITIONS = [
    {
        "uri": "osys://method-runtime/context",
        "name": "method-runtime-context",
        "description": "Runtime context and constraints for method code executed via exec",
        "mimeType": "application/json",
    },
    {
        "uri": "osys://method-runtime/spec",
        "name": "method-runtime-spec",
        "description": "Stable runtime specification for authoring method code",
        "mimeType": "application/json",
    },
    {
        "uri": "osys://method-runtime/examples",
        "name": "method-runtime-examples",
        "description": "Examples for writing osysHome method code blocks",
        "mimeType": "application/json",
    },
    {
        "uri": "osys://method-runtime/symbols",
        "name": "method-runtime-symbols",
        "description": "Public symbols auto-imported into method exec runtime",
        "mimeType": "application/json",
    },
    {
        "uri": "osys://template/spec",
        "name": "template-spec",
        "description": "Template engine and context specification",
        "mimeType": "application/json",
    },
    {
        "uri": "osys://plugin/binding/spec",
        "name": "plugin-binding-spec",
        "description": "Property-plugin binding architecture summary",
        "mimeType": "text/markdown",
    },
    {
        "uri": "osys://server/capabilities",
        "name": "server-capabilities",
        "description": "MCPServer permissions, tool groups, and MCP plugin catalog",
        "mimeType": "application/json",
    },
    {
        "uri": "osys://plugin/catalog",
        "name": "plugin-catalog",
        "description": "Catalog of whitelisted MCP plugins",
        "mimeType": "application/json",
    },
    {
        "uri": "osys://binding/graph",
        "name": "binding-graph",
        "description": "Object-property-plugin binding graph",
        "mimeType": "application/json",
    },
    {
        "uri": "osys://task-runtime/spec",
        "name": "task-runtime-spec",
        "description": "Runtime specification for task code execution",
        "mimeType": "application/json",
    },
    {
        "uri": "osys://task-runtime/examples",
        "name": "task-runtime-examples",
        "description": "Examples for task runtime code",
        "mimeType": "application/json",
    },
    {
        "uri": "osys://task-runtime/symbols",
        "name": "task-runtime-symbols",
        "description": "Task runtime helper symbols",
        "mimeType": "application/json",
    },
    {
        "uri": "osys://cron/spec",
        "name": "cron-spec",
        "description": "Cron expression specification",
        "mimeType": "application/json",
    },
    {
        "uri": "osys://security/policy",
        "name": "security-policy",
        "description": "MCP security policy summary",
        "mimeType": "application/json",
    },
]

PROMPT_DEFINITIONS = [
    {
        "name": "osys_object_overview",
        "description": "Build a compact overview prompt for one object",
        "arguments": [{"name": "object_name", "required": True}],
    },
    {
        "name": "osys_method_authoring",
        "description": "Generate method code for osysHome exec runtime (no def/return)",
        "arguments": [
            {"name": "task", "required": True},
            {"name": "object_name", "required": False},
            {"name": "method_name", "required": False},
        ],
    },
    {
        "name": "osys_method_fix",
        "description": "Fix broken method code for osysHome exec runtime",
        "arguments": [
            {"name": "broken_code", "required": True},
            {"name": "error_text", "required": False},
            {"name": "object_name", "required": False},
            {"name": "method_name", "required": False},
        ],
    },
    {
        "name": "osys_plugin_binding",
        "description": "Guided workflow for plugin property binding (e.g. Mqtt topics)",
        "arguments": [
            {"name": "plugin", "required": True},
            {"name": "object_name", "required": False},
            {"name": "property_name", "required": False},
        ],
    },
    {
        "name": "osys_task_authoring",
        "description": "Guide for authoring Scheduler task entities",
        "arguments": [
            {"name": "task", "required": True},
            {"name": "schedule", "required": False},
            {"name": "object_name", "required": False},
        ],
    },
    {
        "name": "osys_plugin_entity_authoring",
        "description": "Guide for authoring plugin entities by schema",
        "arguments": [
            {"name": "plugin", "required": True},
            {"name": "collection", "required": True},
            {"name": "task", "required": True},
        ],
    },
    {
        "name": "osys_mqtt_topic_setup",
        "description": "Guide for configuring MQTT topic and binding",
        "arguments": [
            {"name": "object_name", "required": True},
            {"name": "property_name", "required": True},
            {"name": "topic_path", "required": True},
            {"name": "topic_path_write", "required": False},
            {"name": "task", "required": False},
        ],
    },
    {
        "name": "osys_automation_review",
        "description": "Review automation risks for one object",
        "arguments": [{"name": "object_name", "required": True}],
    },
]


def resources_list(plugin, params: dict) -> List[dict]:
    from plugins.MCPServer.mcp.permissions import filter_static_resources

    limit = plugin._safe_int(params.get("limit"), 50, 1, 5000)
    limit = min(limit, int(plugin.config.get("max_list_items", 200)))

    out = filter_static_resources(plugin, list(STATIC_RESOURCE_DEFINITIONS))
    with session_scope() as session:
        for row in session.query(Object).order_by(Object.name).limit(limit).all():
            out.append(
                {
                    "uri": f"osys://object/{row.name}",
                    "name": row.name,
                    "description": row.description or "",
                    "mimeType": "application/json",
                }
            )
    return out


def resources_read(plugin, params: dict) -> dict:
    uri = (params.get("uri") or "").strip()
    if not uri:
        raise ValueError("uri is required")
    content, mime = read_resource_uri(plugin, uri)
    return {
        "contents": [
            {
                "uri": uri,
                "mimeType": mime,
                "text": content,
            }
        ]
    }


def read_resource_uri(plugin, uri: str) -> Tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "osys":
        raise ValueError(f"Unsupported URI scheme: {parsed.scheme}")

    host = parsed.netloc
    path = unquote(parsed.path.lstrip("/"))
    query_params = parse_qs(parsed.query or "")
    if host == "object":
        name = path.strip()
        if not name:
            raise ValueError("Object name is empty")
        obj = getObject(name)
        if not obj:
            raise ValueError(f"Object not found: {name}")
        return json.dumps(plugin._serialize_object(obj), ensure_ascii=False, indent=2), "application/json"

    if host == "property":
        prop_name = path.strip()
        if not prop_name:
            raise ValueError("Property name is empty")
        value = getProperty(prop_name)
        payload = {"property": prop_name, "value": plugin._serialize_value(value)}
        return json.dumps(payload, ensure_ascii=False, indent=2), "application/json"

    if host == "method-runtime":
        key = path.strip()
        if key in ("context", "spec"):
            payload = plugin._method_runtime_context_payload()
            return json.dumps(payload, ensure_ascii=False, indent=2), "application/json"
        if key == "symbols":
            payload = plugin._method_runtime_symbols_payload()
            return json.dumps(payload, ensure_ascii=False, indent=2), "application/json"
        if key == "examples":
            payload = {
                "notes": [
                    "Method code is executed as a plain exec block",
                    "Do not use function wrapper (def ...)",
                    "Do not use return",
                    "Use self/params/source and imported helpers like setProperty/getProperty",
                ],
                "examples": [
                    {
                        "name": "simple_property_reaction",
                        "code": (
                            "new_value = None\n"
                            "if isinstance(params, dict):\n"
                            "    new_value = params.get('NEW_VALUE', params.get('VALUE'))\n"
                            "if new_value is not None:\n"
                            "    setProperty(f\"{self.name}.status\", str(new_value), source)\n"
                        ),
                    },
                    {
                        "name": "safe_numeric_calc",
                        "code": (
                            "temp = self.getProperty('temp')\n"
                            "hum = self.getProperty('hum')\n"
                            "if temp not in (None, '') and hum not in (None, ''):\n"
                            "    t = float(temp)\n"
                            "    h = float(hum)\n"
                            "    dew = t - ((100.0 - h) / 5.0)\n"
                            "    setProperty(f\"{self.name}.dew_point\", round(dew, 1), source)\n"
                        ),
                    },
                ],
            }
            return json.dumps(payload, ensure_ascii=False, indent=2), "application/json"
        raise ValueError(f"Unsupported method-runtime resource: {key}")
    if host == "template":
        key = path.strip()
        if key == "spec":
            payload = plugin._get_template_spec("jinja2")
            return json.dumps(payload, ensure_ascii=False, indent=2), "application/json"
        raise ValueError(f"Unsupported template resource: {key}")

    if host == "server":
        key = path.strip()
        if key == "capabilities":
            from plugins.MCPServer.mcp.handlers.meta import build_server_capabilities

            payload = build_server_capabilities(plugin)
            return json.dumps(payload, ensure_ascii=False, indent=2), "application/json"
        raise ValueError(f"Unsupported server resource: {key}")

    if host == "task-runtime":
        key = path.strip()
        if key == "spec":
            payload = {
                "engine": "exec",
                "context": ["params", "logger", "source"],
                "helpers": ["setProperty", "getProperty", "callMethod", "addCronJob", "removeCronJob"],
                "constraints": ["no async", "no return", "thread-pool execution"],
            }
            return json.dumps(payload, ensure_ascii=False, indent=2), "application/json"
        if key == "examples":
            payload = {
                "examples": [
                    "if params.get('enabled'): setProperty('Lamp01.status', 1, 'task')",
                    "value = getProperty('Sensor01.temp'); logger.info(value)",
                    "callMethod('Notifier.send', {'text': 'task done'}, 'task')",
                ]
            }
            return json.dumps(payload, ensure_ascii=False, indent=2), "application/json"
        if key == "symbols":
            payload = {"symbols": ["params", "logger", "setProperty", "getProperty", "callMethod"]}
            return json.dumps(payload, ensure_ascii=False, indent=2), "application/json"
        raise ValueError(f"Unsupported task-runtime resource: {key}")

    if host == "cron":
        key = path.strip()
        if key == "spec":
            payload = {
                "engine": "croniter",
                "fields": "minute hour day month day_of_week",
                "examples": ["0 8 * * *", "*/5 * * * *", "0 0 1 * *"],
                "validation_tool": "osys_plugin_invoke Scheduler validate_crontab",
            }
            return json.dumps(payload, ensure_ascii=False, indent=2), "application/json"
        raise ValueError(f"Unsupported cron resource: {key}")

    if host == "security":
        key = path.strip()
        if key == "policy":
            payload = {
                "always_denied_without_permission": [
                    "write_property",
                    "invoke_method",
                    "manage_classes",
                    "manage_objects",
                    "manage_properties",
                    "manage_methods",
                    "manage_plugins",
                ],
                "composite_tools": ["osys_bind_device"],
                "notes": [
                    "plugins_allowed empty denies all plugin tools/resources",
                    "osys_get_plugin_config masks secrets",
                    "prefer validate + dry-run + if_match on writes",
                ],
            }
            return json.dumps(payload, ensure_ascii=False, indent=2), "application/json"
        raise ValueError(f"Unsupported security resource: {key}")

    if host == "plugin":
        parts = [part for part in path.split("/") if part]
        if not parts:
            raise ValueError("Plugin resource path is empty")
        if parts[0] == "catalog":
            plugin._require_permission("allow_read_plugins", "Plugin read tools are disabled")
            allowed = plugin.config.get("plugins_allowed") or []
            items = []
            for plugin_name in allowed:
                instance = getModule(plugin_name)
                if instance is None:
                    continue
                capabilities = instance.mcp_capabilities() if hasattr(instance, "mcp_capabilities") else {}
                collections = capabilities.get("collections") or []
                collections_payload = []
                for collection in collections:
                    if not isinstance(collection, dict):
                        continue
                    cid = str(collection.get("id") or "").strip()
                    if not cid:
                        continue
                    schema = {}
                    if hasattr(instance, "mcp_entity_schema"):
                        try:
                            schema = instance.mcp_entity_schema(cid) or {}
                        except Exception:
                            schema = {}
                    collections_payload.append(
                        {
                            "id": cid,
                            "binding_mode": collection.get("binding_mode"),
                            "entity_schema": schema,
                        }
                    )
                items.append(
                    {
                        "name": plugin_name,
                        "capabilities": capabilities,
                        "collections": collections_payload,
                        "operations": capabilities.get("operations") or [],
                    }
                )
            return json.dumps({"plugins": items}, ensure_ascii=False, indent=2), "application/json"
        if parts[0] == "binding" and len(parts) > 1 and parts[1] == "spec":
            text = (
                "# Plugin binding\n\n"
                "1. Configure plugin entity (e.g. Mqtt topic) with linked_object and linked_property.\n"
                "2. Plugin must call setLinkToObject on save (use plugin_binding.sync_property_link).\n"
                "3. Verify Value.linked via osys_get_property.\n"
                "4. Test with osys_write_property on the linked property.\n"
            )
            return text, "text/markdown"
        plugin_name = parts[0]
        plugin._require_permission("allow_read_plugins", "Plugin read tools are disabled")
        allowed = plugin.config.get("plugins_allowed") or []
        if plugin_name not in allowed:
            raise PermissionError(f"Plugin '{plugin_name}' is not in plugins_allowed whitelist")
        instance = getModule(plugin_name)
        if instance is None:
            raise ValueError(f"Plugin not found: {plugin_name}")
        if len(parts) == 1:
            if not hasattr(instance, "mcp_capabilities"):
                raise ValueError(f"Plugin '{plugin_name}' does not support MCP")
            payload = instance.mcp_capabilities()
            return json.dumps(payload, ensure_ascii=False, indent=2), "application/json"
        if len(parts) >= 3 and parts[1] == "schema":
            collection = parts[2]
            if not hasattr(instance, "mcp_entity_schema"):
                raise ValueError(f"Plugin '{plugin_name}' does not support MCP schemas")
            payload = instance.mcp_entity_schema(collection)
            return json.dumps(payload, ensure_ascii=False, indent=2), "application/json"
        rel_path = "/".join(parts[1:])
        if rel_path and hasattr(instance, "mcp_read_resource"):
            try:
                return instance.mcp_read_resource(rel_path)
            except NotImplementedError:
                pass
        raise ValueError(f"Unsupported plugin resource path: {path}")

    if host == "binding":
        key = path.strip()
        if key == "graph":
            plugin._require_permission("allow_read_plugins", "Plugin read tools are disabled")
            plugin_filter = str((query_params.get("plugin") or [""])[0] or "").strip()
            limit = plugin._safe_int((query_params.get("limit") or [500])[0], 500, 1, 5000)
            nodes = []
            edges = []
            node_seen = set()
            edge_seen = set()
            allowed = plugin.config.get("plugins_allowed") or []
            with session_scope() as session:
                object_names = [
                    name
                    for (name,) in session.query(Object.name)
                    .order_by(Object.name)
                    .limit(limit)
                    .all()
                ]
            for object_name in object_names:
                obj = getObject(object_name)
                if not obj:
                    continue
                obj_node = f"object:{object_name}"
                if obj_node not in node_seen:
                    nodes.append({"id": obj_node, "type": "object"})
                    node_seen.add(obj_node)
                for prop_name, prop in obj.properties.items():
                    prop_node = f"property:{object_name}.{prop_name}"
                    if prop_node not in node_seen:
                        nodes.append({"id": prop_node, "type": "property"})
                        node_seen.add(prop_node)
                    edge_key = (obj_node, prop_node, "has")
                    if edge_key not in edge_seen:
                        edges.append({"from": obj_node, "to": prop_node, "kind": "has"})
                        edge_seen.add(edge_key)
                    for plugin_name in (prop.linked or []):
                        if plugin_filter and plugin_name != plugin_filter:
                            continue
                        if plugin_name not in allowed:
                            continue
                        plugin_node = f"plugin:{plugin_name}"
                        if plugin_node not in node_seen:
                            nodes.append({"id": plugin_node, "type": "plugin"})
                            node_seen.add(plugin_node)
                        edge_key = (prop_node, plugin_node, "linked")
                        if edge_key not in edge_seen:
                            edges.append({"from": prop_node, "to": plugin_node, "kind": "linked"})
                            edge_seen.add(edge_key)
            return json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False, indent=2), "application/json"
        raise ValueError(f"Unsupported binding resource: {key}")

    raise ValueError(f"Unsupported resource host: {host}")


def _collect_plugin_prompt_definitions(mcp_plugin) -> List[dict]:
    items: List[dict] = []
    seen = set()
    allowed = mcp_plugin.config.get("plugins_allowed") or []
    for plugin_name in allowed:
        instance = getModule(plugin_name)
        if instance is None:
            continue
        try:
            prompt_items = instance.mcp_prompts() or []
        except Exception:
            continue
        for item in prompt_items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            items.append(
                {
                    "name": name,
                    "description": item.get("description") or "",
                    "arguments": item.get("arguments") or [],
                }
            )
    return items


def _try_plugin_prompt(mcp_plugin, name: str, args: dict) -> Optional[dict]:
    allowed = mcp_plugin.config.get("plugins_allowed") or []
    for plugin_name in allowed:
        instance = getModule(plugin_name)
        if instance is None or not hasattr(instance, "mcp_get_prompt"):
            continue
        try:
            owned = {
                str(item.get("name") or "").strip()
                for item in (instance.mcp_prompts() or [])
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            }
        except Exception:
            continue
        if name not in owned:
            continue
        return instance.mcp_get_prompt(name, args)
    return None


def prompts_list(mcp_plugin=None) -> List[dict]:
    items = list(PROMPT_DEFINITIONS)
    if mcp_plugin is not None:
        items.extend(_collect_plugin_prompt_definitions(mcp_plugin))
    return items


def prompts_get(plugin, params: dict) -> dict:
    name = (params.get("name") or "").strip()
    args = params.get("arguments") or {}
    if name == "osys_object_overview":
        object_name = (args.get("object_name") or "").strip()
        if not object_name:
            raise ValueError("object_name is required")

        obj = getObject(object_name)
        if not obj:
            raise ValueError(f"Object not found: {object_name}")

        payload = plugin._serialize_object(obj)
        prompt_text = (
            "Analyze this osysHome object and propose safe automation steps.\n"
            f"Object JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )
        return {"messages": [{"role": "user", "content": {"type": "text", "text": prompt_text}}]}

    if name == "osys_method_authoring":
        task = (args.get("task") or "").strip()
        if not task:
            raise ValueError("task is required")
        object_name = (args.get("object_name") or "").strip()
        method_name = (args.get("method_name") or "").strip()
        ctx = plugin._method_runtime_context_payload()
        prompt_text = (
            "Write osysHome method code for exec runtime.\n"
            "Output only Python code block body, no markdown.\n"
            "You can directly use helpers/constants auto-imported from app.core.lib.* modules.\n"
            "In this runtime, `self` is app.core.main.ObjectManager.ObjectManager for current object.\n"
            f"Task: {task}\n"
            f"Object: {object_name or '-'}\n"
            f"Method: {method_name or '-'}\n"
            f"Runtime context:\n{json.dumps(ctx, ensure_ascii=False, indent=2)}"
        )
        return {"messages": [{"role": "user", "content": {"type": "text", "text": prompt_text}}]}

    if name == "osys_method_fix":
        broken_code = str(args.get("broken_code") or "").strip()
        if not broken_code:
            raise ValueError("broken_code is required")
        error_text = str(args.get("error_text") or "").strip()
        object_name = (args.get("object_name") or "").strip()
        method_name = (args.get("method_name") or "").strip()
        ctx = plugin._method_runtime_context_payload()
        prompt_text = (
            "Fix osysHome method code for exec runtime.\n"
            "Output only corrected Python code block body, no markdown.\n"
            "You can directly use helpers/constants auto-imported from app.core.lib.* modules.\n"
            "In this runtime, `self` is app.core.main.ObjectManager.ObjectManager for current object.\n"
            f"Object: {object_name or '-'}\n"
            f"Method: {method_name or '-'}\n"
            f"Error: {error_text or '-'}\n"
            f"Broken code:\n{broken_code}\n\n"
            f"Runtime context:\n{json.dumps(ctx, ensure_ascii=False, indent=2)}"
        )
        return {"messages": [{"role": "user", "content": {"type": "text", "text": prompt_text}}]}

    if name == "osys_plugin_binding":
        plugin_name = (args.get("plugin") or "").strip()
        if not plugin_name:
            raise ValueError("plugin is required")
        object_name = (args.get("object_name") or "").strip()
        property_name = (args.get("property_name") or "").strip()
        prompt_text = (
            "Configure plugin binding in osysHome using MCP tools.\n"
            f"Plugin: {plugin_name}\n"
            f"Target object: {object_name or '-'}\n"
            f"Target property: {property_name or '-'}\n\n"
            "Steps:\n"
            "1. osys_plugin_capabilities\n"
            "2. osys_plugin_entity_schema for the target collection\n"
            "3. osys_plugin_upsert_entity with linked_object/linked_property when binding_mode=property\n"
            "4. osys_get_property to verify linked list\n"
            "5. Optional osys_write_property dry test\n"
        )
        return {"messages": [{"role": "user", "content": {"type": "text", "text": prompt_text}}]}

    if name == "osys_task_authoring":
        task = str(args.get("task") or "").strip()
        schedule = str(args.get("schedule") or "").strip()
        object_name = str(args.get("object_name") or "").strip()
        if not task:
            raise ValueError("task is required")
        prompt_text = (
            "Author Scheduler task entity JSON.\n"
            f"Task: {task}\nSchedule: {schedule or '-'}\nObject: {object_name or '-'}\n"
            "Output fields: name, code, crontab(optional), runtime(optional).\n"
            "Use osys_plugin_validate_entity_code and Scheduler validate_crontab before upsert.\n"
        )
        return {"messages": [{"role": "user", "content": {"type": "text", "text": prompt_text}}]}

    if name == "osys_plugin_entity_authoring":
        plugin_name = str(args.get("plugin") or "").strip()
        collection = str(args.get("collection") or "").strip()
        task = str(args.get("task") or "").strip()
        if not plugin_name or not collection or not task:
            raise ValueError("plugin, collection and task are required")
        prompt_text = (
            "Create plugin entity payload by schema.\n"
            f"Plugin: {plugin_name}\nCollection: {collection}\nTask: {task}\n"
            "Use osys_plugin_entity_schema, then osys_plugin_validate_entity, then osys_plugin_upsert_entity.\n"
        )
        return {"messages": [{"role": "user", "content": {"type": "text", "text": prompt_text}}]}

    if name == "osys_mqtt_topic_setup":
        object_name = str(args.get("object_name") or "").strip()
        property_name = str(args.get("property_name") or "").strip()
        topic_path = str(args.get("topic_path") or "").strip()
        topic_path_write = str(args.get("topic_path_write") or "").strip()
        task = str(args.get("task") or "").strip()
        if not object_name or not property_name or not topic_path:
            raise ValueError("object_name, property_name and topic_path are required")
        prompt_text = (
            "Setup Mqtt topic binding.\n"
            f"Object: {object_name}\nProperty: {property_name}\nTopic read: {topic_path}\n"
            f"Topic write: {topic_path_write or '-'}\nTask: {task or '-'}\n"
            "Flow: validate -> osys_plugin_upsert_entity -> osys_manage_property_links(add) -> verify with osys_get_property.\n"
        )
        return {"messages": [{"role": "user", "content": {"type": "text", "text": prompt_text}}]}

    if name == "osys_automation_review":
        object_name = str(args.get("object_name") or "").strip()
        if not object_name:
            raise ValueError("object_name is required")
        prompt_text = (
            "Review automation risks for object.\n"
            f"Object: {object_name}\n"
            "Use osys_get_object_context, analyze methods, linked plugins, write permissions, and infinite-loop risks.\n"
            "Output: risks[], suggestions[], safe_read_only_actions[].\n"
        )
        return {"messages": [{"role": "user", "content": {"type": "text", "text": prompt_text}}]}

    delegated = _try_plugin_prompt(plugin, name, args)
    if delegated is not None:
        return delegated

    raise ValueError(f"Unknown prompt: {name}")
