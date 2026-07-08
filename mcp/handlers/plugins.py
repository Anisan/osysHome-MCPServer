"""Plugin configuration and entity MCP tools for MCPServer."""
# pylint: disable=protected-access

from __future__ import annotations

import inspect
import json
from typing import Any, List, Optional

from app.core.lib.common import callPluginFunction, getModule
from app.core.lib.object import getHistory, getObject, getProperty, removeLinkFromObject, setLinkToObject
from app.core.lib.plugin_binding import sync_object_link, sync_property_link
from app.core.main.PluginsHelper import plugins as active_plugins
from app.core.models.Plugins import Plugin
from app.database import row2dict, session_scope
from app.extensions import cache
from app.logging_config import security_audit_log

from plugins.MCPServer.mcp.permissions import plugins_allowed_list
from plugins.MCPServer.core import utils as mcp_utils

_SECRET_KEY_PARTS = (
    "password",
    "passwd",
    "pwd",
    "token",
    "secret",
    "api_key",
    "apikey",
    "authorization",
)

_READ_PLUGIN_ACTIONS = {
    "capabilities",
    "config_schema",
    "entity_schema",
    "list_entities",
    "get_entity",
    "search",
    "validate_entity_code",
    "validate_entity",
    "diff_entity",
    "export_entities",
    "run_entity_dry",
}

_WRITE_PLUGIN_ACTIONS = {
    "upsert_entity",
    "delete_entity",
    "invoke",
    "import_entities",
    "batch",
}

_ATOMIC_PLUGIN_TOOLS = {
    "osys_plugin_capabilities": "capabilities",
    "osys_plugin_config_schema": "config_schema",
    "osys_plugin_entity_schema": "entity_schema",
    "osys_plugin_list_entities": "list_entities",
    "osys_plugin_get_entity": "get_entity",
    "osys_plugin_search": "search",
    "osys_plugin_validate_entity_code": "validate_entity_code",
    "osys_plugin_validate_entity": "validate_entity",
    "osys_plugin_diff_entity": "diff_entity",
    "osys_plugin_export_entities": "export_entities",
    "osys_plugin_run_entity_dry": "run_entity_dry",
    "osys_plugin_upsert_entity": "upsert_entity",
    "osys_plugin_delete_entity": "delete_entity",
    "osys_plugin_import_entities": "import_entities",
    "osys_plugin_batch": "batch",
    "osys_plugin_invoke": "invoke",
}


def _is_secret_key(key: str) -> bool:
    lowered = str(key or "").lower()
    return any(part in lowered for part in _SECRET_KEY_PARTS)


def _mask_config_values(data: Any) -> Any:
    if isinstance(data, dict):
        masked = {}
        for key, value in data.items():
            if _is_secret_key(key) and value not in (None, ""):
                masked[key] = "***"
            else:
                masked[key] = _mask_config_values(value)
        return masked
    if isinstance(data, list):
        return [_mask_config_values(item) for item in data]
    return data


def _plugins_allowed(plugin) -> List[str]:
    return plugins_allowed_list(plugin)


def _is_plugin_allowed(plugin, plugin_name: str) -> bool:
    allowed = _plugins_allowed(plugin)
    return plugin_name in allowed


def _ensure_plugin_allowed(plugin, plugin_name: str) -> None:
    if not _is_plugin_allowed(plugin, plugin_name):
        raise PermissionError(f"Plugin '{plugin_name}' is not in plugins_allowed whitelist")


def _instance_mcp_capabilities(instance) -> dict:
    if not hasattr(instance, "mcp_capabilities"):
        return {}
    try:
        return instance.mcp_capabilities() or {}
    except Exception:
        return {}


def _instance_mcp_supported(instance) -> bool:
    if hasattr(instance, "mcp_supported"):
        try:
            return bool(instance.mcp_supported())
        except Exception:
            pass
    caps = _instance_mcp_capabilities(instance)
    return bool(caps.get("collections"))


def list_mcp_capable_plugins() -> List[dict]:
    """Return installed plugins that expose MCP collections."""
    items: List[dict] = []
    with session_scope() as session:
        rows = session.query(Plugin).order_by(Plugin.name).all()
        for rec in rows:
            name = rec.name
            runtime = active_plugins.get(name, {})
            instance = runtime.get("instance")
            if instance is None:
                continue
            try:
                if not _instance_mcp_supported(instance):
                    continue
                caps = _instance_mcp_capabilities(instance)
                collections = caps.get("collections") or []
            except Exception:
                continue
            collection_ids = [
                str(item.get("id")).strip()
                for item in collections
                if isinstance(item, dict) and str(item.get("id") or "").strip()
            ]
            items.append(
                {
                    "name": name,
                    "title": rec.title or getattr(instance, "title", None) or name,
                    "category": rec.category or getattr(instance, "category", None),
                    "active": bool(rec.active),
                    "collections": collection_ids,
                }
            )
    return items


def _get_plugin_row(plugin_name: str) -> Optional[dict]:
    with session_scope() as session:
        rec = session.query(Plugin).filter(Plugin.name == plugin_name).one_or_none()
        if rec is None:
            return None
        return row2dict(rec)


def _load_plugin_config(plugin_name: str, mask_secrets: bool = True) -> dict:
    row = _get_plugin_row(plugin_name)
    if row is None:
        raise ValueError(f"Plugin not found: {plugin_name}")
    config = {}
    if row.get("config"):
        try:
            config = json.loads(row["config"])
        except json.JSONDecodeError:
            config = {}
    payload = {
        "plugin": plugin_name,
        "title": row.get("title"),
        "category": row.get("category"),
        "hidden": row.get("hidden"),
        "active": row.get("active"),
        "url": row.get("url"),
        "branch": row.get("branch"),
        "config": config,
        "revision": mcp_utils.revision_for_payload({"config": config, "meta": {
            "title": row.get("title"),
            "category": row.get("category"),
            "hidden": row.get("hidden"),
            "active": row.get("active"),
            "url": row.get("url"),
            "branch": row.get("branch"),
        }}),
    }
    if mask_secrets:
        payload["config"] = _mask_config_values(payload["config"])
    return payload


def _update_plugin_config(plugin, plugin_name: str, args: dict) -> dict:
    _ensure_plugin_allowed(plugin, plugin_name)
    row = _get_plugin_row(plugin_name)
    if row is None:
        raise ValueError(f"Plugin not found: {plugin_name}")

    current = _load_plugin_config(plugin_name, mask_secrets=False)
    if_match = args.get("if_match")
    if if_match:
        mcp_utils.enforce_if_match(str(if_match), current["revision"])

    config_patch = args.get("config")
    if config_patch is not None and not isinstance(config_patch, dict):
        raise ValueError("config must be an object")

    meta_fields = ("title", "category", "hidden", "active", "url", "branch")
    with session_scope() as session:
        rec = session.query(Plugin).filter(Plugin.name == plugin_name).one_or_none()
        if rec is None:
            raise ValueError(f"Plugin not found: {plugin_name}")

        existing_config = {}
        if rec.config:
            try:
                existing_config = json.loads(rec.config)
            except json.JSONDecodeError:
                existing_config = {}

        if isinstance(config_patch, dict):
            for key, value in config_patch.items():
                if value is None and key in existing_config:
                    existing_config.pop(key, None)
                else:
                    existing_config[key] = value

        for field in meta_fields:
            if field in args:
                setattr(rec, field, args[field])

        rec.config = json.dumps(existing_config)
        session.commit()

    cache.delete("sidebar")
    if plugin_name in active_plugins:
        active_plugins[plugin_name]["instance"].loadConfig()

    security_audit_log(
        "MCP_PLUGIN_CONFIG_UPDATE",
        plugin=plugin_name,
        source="MCPServer",
    )
    return _load_plugin_config(plugin_name, mask_secrets=True)


def _list_plugins(plugin, args: dict) -> dict:
    plugin._require_permission("allow_read_plugins", "Plugin read tools are disabled")
    query = str(args.get("query") or "").strip().lower()
    active_only = bool(args.get("active_only", False))
    max_items = int(plugin.config.get("max_list_items", 200))
    limit = plugin._safe_int(args.get("limit"), max_items, 1, 5000)
    limit = min(limit, max_items)

    items: List[dict] = []
    with session_scope() as session:
        rows = session.query(Plugin).order_by(Plugin.name).all()
        for rec in rows:
            if active_only and not rec.active:
                continue
            name = rec.name
            if query and query not in name.lower():
                title = (rec.title or "").lower()
                if query not in title:
                    continue
            allowed = _plugins_allowed(plugin)
            if name not in allowed:
                continue
            runtime = active_plugins.get(name, {})
            instance = runtime.get("instance")
            installed = instance is not None
            mcp_supported = False
            collections: List[dict] = []
            if instance is not None:
                try:
                    if _instance_mcp_supported(instance):
                        mcp_supported = True
                        caps = _instance_mcp_capabilities(instance)
                        collections = caps.get("collections") or []
                except Exception:
                    mcp_supported = False
            item = {
                "name": name,
                "title": rec.title or (getattr(instance, "title", None) if instance else None) or name,
                "category": rec.category or (getattr(instance, "category", None) if instance else None),
                "active": bool(rec.active),
                "installed": installed,
                "alive": instance.is_alive() if installed and hasattr(instance, "is_alive") else False,
                "actions": list(getattr(instance, "actions", []) or []) if installed else [],
                "mcp_supported": mcp_supported,
                "collections": collections,
            }
            items.append(item)
            if len(items) >= limit:
                break
    return {"count": len(items), "items": items}


def _manage_property_links(plugin, args: dict) -> dict:
    plugin._require_permission("allow_manage_plugins", "Plugin management tools are disabled")
    action = str(args.get("action") or "list").strip().lower()
    object_name = str(args.get("object_name") or "").strip()
    property_name = str(args.get("property_name") or "").strip()
    link_plugin = str(args.get("plugin") or "").strip()

    if action == "list":
        if not object_name or not property_name:
            raise ValueError("object_name and property_name are required for list")
        obj = getObject(object_name)
        if obj is None:
            raise ValueError(f"Object not found: {object_name}")
        if property_name not in obj.properties:
            raise ValueError(f"Property not found: {object_name}.{property_name}")
        prop = obj.properties[property_name]
        linked = list(prop.linked or [])
        return {
            "object_name": object_name,
            "property_name": property_name,
            "linked": linked,
        }

    if not object_name or not property_name:
        raise ValueError("object_name and property_name are required")
    if action in ("add", "remove") and not link_plugin:
        raise ValueError("plugin is required for add/remove")

    if action == "add":
        ok = setLinkToObject(object_name, property_name, link_plugin)
        security_audit_log(
            "MCP_PROPERTY_LINK_CHANGE",
            action="add",
            object_name=object_name,
            property_name=property_name,
            plugin=link_plugin,
            source="MCPServer",
        )
        return {"ok": bool(ok), "action": action}

    if action == "remove":
        ok = removeLinkFromObject(object_name, property_name, link_plugin)
        security_audit_log(
            "MCP_PROPERTY_LINK_CHANGE",
            action="remove",
            object_name=object_name,
            property_name=property_name,
            plugin=link_plugin,
            source="MCPServer",
        )
        return {"ok": bool(ok), "action": action}

    if action == "replace":
        plugins_list = args.get("plugins")
        if plugins_list is None:
            plugins_list = []
        if not isinstance(plugins_list, list):
            raise ValueError("plugins must be an array")
        obj = getObject(object_name)
        if obj is None:
            raise ValueError(f"Object not found: {object_name}")
        if property_name not in obj.properties:
            raise ValueError(f"Property not found: {object_name}.{property_name}")
        current = list(obj.properties[property_name].linked or [])
        for name in current:
            removeLinkFromObject(object_name, property_name, name)
        for name in plugins_list:
            pname = str(name or "").strip()
            if pname:
                setLinkToObject(object_name, property_name, pname)
        security_audit_log(
            "MCP_PROPERTY_LINK_CHANGE",
            action="replace",
            object_name=object_name,
            property_name=property_name,
            plugins=plugins_list,
            source="MCPServer",
        )
        updated = list(getObject(object_name).properties[property_name].linked or [])
        return {"ok": True, "action": action, "linked": updated}

    raise ValueError(f"Unsupported action: {action}")


def _dispatch_plugin_action(plugin, args: dict) -> dict:
    plugin_name = str(args.get("plugin") or "").strip()
    action = str(args.get("action") or "").strip()
    action_args = args.get("args") or {}
    if not plugin_name:
        raise ValueError("plugin is required")
    if not action:
        raise ValueError("action is required")
    if not isinstance(action_args, dict):
        raise ValueError("args must be an object")

    _ensure_plugin_allowed(plugin, plugin_name)
    instance = getModule(plugin_name)
    if instance is None:
        raise ValueError(f"Plugin not installed or inactive: {plugin_name}")

    if action in _WRITE_PLUGIN_ACTIONS:
        plugin._require_permission("allow_manage_plugins", "Plugin management tools are disabled")
    elif action in _READ_PLUGIN_ACTIONS:
        plugin._require_permission("allow_read_plugins", "Plugin read tools are disabled")
    else:
        raise ValueError(f"Unsupported plugin action: {action}")

    if action == "search":
        if "search" not in getattr(instance, "actions", []):
            raise ValueError(f"Plugin '{plugin_name}' does not support search")
        query = str(action_args.get("query") or "").strip()
        if len(query) < 2:
            raise ValueError("query must be at least 2 characters")
        result = instance.search(query)
        return {"plugin": plugin_name, "action": action, "result": result}
    if action == "batch":
        steps = action_args.get("steps") or []
        stop_on_error = bool(action_args.get("stop_on_error", True))
        if not isinstance(steps, list):
            raise ValueError("steps must be an array")
        max_steps = plugin._safe_int(plugin.config.get("mcp_batch_max_steps"), 20, 1, 100)
        if len(steps) > max_steps:
            raise ValueError(f"steps exceeds max allowed ({max_steps})")
        results = []
        for idx, step in enumerate(steps):
            if not isinstance(step, dict):
                err = {"index": idx, "ok": False, "error": "step must be object"}
                results.append(err)
                if stop_on_error:
                    break
                continue
            try:
                step_plugin = str(step.get("plugin") or plugin_name).strip()
                step_action = str(step.get("action") or "").strip()
                step_args = step.get("args") or {}
                if not step_action:
                    raise ValueError("step.action is required")
                if not isinstance(step_args, dict):
                    raise ValueError("step.args must be object")
                step_result = _dispatch_plugin_action(
                    plugin,
                    {"plugin": step_plugin, "action": step_action, "args": step_args},
                )
                results.append({"index": idx, "ok": True, "result": step_result})
            except Exception as ex:
                results.append({"index": idx, "ok": False, "error": str(ex)})
                if stop_on_error:
                    break
        security_audit_log(
            "MCP_PLUGIN_BATCH",
            source="MCPServer",
            count=len(steps),
            stop_on_error=stop_on_error,
        )
        return {"plugin": plugin_name, "action": action, "result": {"results": results}}

    if action == "diff_entity":
        collection = str(action_args.get("collection") or "").strip()
        payload = action_args.get("payload")
        entity_id = action_args.get("entity_id")
        if not collection:
            raise ValueError("collection is required")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        current = {}
        if entity_id not in (None, ""):
            current = instance.mcp_get_entity(collection, entity_id) or {}
            if not isinstance(current, dict):
                current = {}
        keys = sorted(set(current.keys()) | set(payload.keys()))
        changes = []
        for key in keys:
            old_val = current.get(key)
            new_val = payload.get(key)
            if old_val != new_val:
                changes.append({"field": key, "old": old_val, "new": new_val})
        validation = None
        if hasattr(instance, "mcp_validate_entity"):
            try:
                validation = instance.mcp_validate_entity(collection, payload, entity_id=entity_id)
            except Exception as ex:
                validation = {"ok": False, "errors": [{"field": "_", "message": str(ex)}]}
        return {
            "plugin": plugin_name,
            "action": action,
            "result": {
                "creates": entity_id in (None, ""),
                "changes": changes,
                "validation": validation,
            },
        }

    if action == "export_entities":
        collection = str(action_args.get("collection") or "").strip()
        if not collection:
            raise ValueError("collection is required")
        if not hasattr(instance, "mcp_list_entities"):
            raise ValueError(f"Plugin '{plugin_name}' does not implement mcp_list_entities")
        query = action_args.get("query")
        limit = plugin._safe_int(action_args.get("limit"), 100, 1, 5000)
        entity_ids = action_args.get("entity_ids")
        all_items = instance.mcp_list_entities(collection, query=query, limit=limit)
        if not isinstance(all_items, list):
            all_items = []
        if isinstance(entity_ids, list) and entity_ids:
            allowed_ids = {str(item) for item in entity_ids}
            all_items = [item for item in all_items if isinstance(item, dict) and str(item.get("id")) in allowed_ids]
        return {
            "plugin": plugin_name,
            "action": action,
            "result": {
                "plugin": plugin_name,
                "collection": collection,
                "count": len(all_items),
                "items": all_items,
            },
        }

    if action == "import_entities":
        collection = str(action_args.get("collection") or "").strip()
        items = action_args.get("items") or []
        mode = str(action_args.get("mode") or "upsert").strip().lower()
        dry_run = bool(action_args.get("dry_run", False))
        if not collection:
            raise ValueError("collection is required")
        if mode not in {"upsert", "create_only"}:
            raise ValueError("mode must be 'upsert' or 'create_only'")
        if not isinstance(items, list):
            raise ValueError("items must be an array")
        imported = []
        errors = []
        for idx, item in enumerate(items):
            try:
                if not isinstance(item, dict):
                    raise ValueError("item must be object")
                entity_id = item.get("id")
                payload = dict(item)
                payload.pop("id", None)
                validation = instance.mcp_validate_entity(collection, payload, entity_id=entity_id)
                if isinstance(validation, dict) and validation.get("ok") is False:
                    raise ValueError(f"validation failed: {validation}")
                if "code" in payload and hasattr(instance, "mcp_validate_entity_code"):
                    code_validation = instance.mcp_validate_entity_code(collection, str(payload.get("code") or ""))
                    if isinstance(code_validation, dict) and code_validation.get("ok") is False:
                        raise ValueError(f"code validation failed: {code_validation}")
                if dry_run:
                    imported.append({"index": idx, "dry_run": True, "entity_id": entity_id})
                    continue
                if mode == "create_only":
                    entity_id = None
                upsert_result = instance.mcp_upsert_entity(collection, payload, entity_id=entity_id)
                imported.append({"index": idx, "result": upsert_result})
            except Exception as ex:
                errors.append({"index": idx, "error": str(ex)})
        security_audit_log(
            "MCP_PLUGIN_IMPORT",
            plugin=plugin_name,
            collection=collection,
            count=len(items),
            source="MCPServer",
        )
        return {
            "plugin": plugin_name,
            "action": action,
            "result": {"ok": len(errors) == 0, "imported": imported, "errors": errors, "dry_run": dry_run},
        }

    method_map = {
        "capabilities": "mcp_capabilities",
        "config_schema": "mcp_config_schema",
        "entity_schema": "mcp_entity_schema",
        "list_entities": "mcp_list_entities",
        "get_entity": "mcp_get_entity",
        "upsert_entity": "mcp_upsert_entity",
        "delete_entity": "mcp_delete_entity",
        "validate_entity_code": "mcp_validate_entity_code",
        "validate_entity": "mcp_validate_entity",
        "run_entity_dry": "mcp_run_entity_dry",
        "invoke": "mcp_invoke",
    }
    method_name = method_map.get(action)
    if not method_name:
        raise ValueError(f"Unsupported plugin action: {action}")

    if action in ("MCP_PLUGIN_ENTITY_UPSERT",):
        pass

    if not hasattr(instance, method_name):
        raise ValueError(f"Plugin '{plugin_name}' does not implement {method_name}")

    if action == "capabilities":
        result = instance.mcp_capabilities()
    elif action == "config_schema":
        result = instance.mcp_config_schema()
    elif action == "entity_schema":
        collection = str(action_args.get("collection") or "").strip()
        if not collection:
            raise ValueError("collection is required")
        result = instance.mcp_entity_schema(collection)
    elif action == "list_entities":
        collection = str(action_args.get("collection") or "").strip()
        if not collection:
            raise ValueError("collection is required")
        query = action_args.get("query")
        limit = plugin._safe_int(action_args.get("limit"), 100, 1, 5000)
        list_kwargs = {"query": query, "limit": limit}
        sig = inspect.signature(instance.mcp_list_entities)
        for key in sig.parameters:
            if key in ("self", "collection"):
                continue
            if key in action_args and action_args[key] is not None:
                list_kwargs[key] = action_args[key]
        list_kwargs = {
            key: value
            for key, value in list_kwargs.items()
            if key in sig.parameters
        }
        result = instance.mcp_list_entities(collection, **list_kwargs)
    elif action == "get_entity":
        collection = str(action_args.get("collection") or "").strip()
        entity_id = action_args.get("entity_id")
        if not collection or entity_id in (None, ""):
            raise ValueError("collection and entity_id are required")
        result = instance.mcp_get_entity(collection, entity_id)
    elif action == "upsert_entity":
        collection = str(action_args.get("collection") or "").strip()
        payload = action_args.get("payload")
        if not collection or not isinstance(payload, dict):
            raise ValueError("collection and payload object are required")
        entity_id = action_args.get("entity_id")
        if_match = str(action_args.get("if_match") or "").strip() or None
        if if_match:
            if not hasattr(instance, "mcp_entity_revision"):
                raise ValueError(f"Plugin '{plugin_name}' does not implement mcp_entity_revision")
            if entity_id in (None, ""):
                raise ValueError("entity_id is required when if_match is provided")
            current_revision = str(instance.mcp_entity_revision(collection, entity_id) or "").strip()
            mcp_utils.enforce_if_match(if_match, current_revision)
        result = instance.mcp_upsert_entity(collection, payload, entity_id=entity_id)
        security_audit_log(
            "MCP_PLUGIN_ENTITY_UPSERT",
            plugin=plugin_name,
            collection=collection,
            entity_id=entity_id,
            source="MCPServer",
        )
    elif action == "delete_entity":
        collection = str(action_args.get("collection") or "").strip()
        entity_id = action_args.get("entity_id")
        if not collection or entity_id in (None, ""):
            raise ValueError("collection and entity_id are required")
        result = instance.mcp_delete_entity(collection, entity_id)
        security_audit_log(
            "MCP_PLUGIN_ENTITY_DELETE",
            plugin=plugin_name,
            collection=collection,
            entity_id=entity_id,
            source="MCPServer",
        )
    elif action == "validate_entity_code":
        collection = str(action_args.get("collection") or "").strip()
        code = str(action_args.get("code") or "")
        if not collection:
            raise ValueError("collection is required")
        result = instance.mcp_validate_entity_code(collection, code)
    elif action == "validate_entity":
        collection = str(action_args.get("collection") or "").strip()
        payload = action_args.get("payload")
        entity_id = action_args.get("entity_id")
        if not collection:
            raise ValueError("collection is required")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        result = instance.mcp_validate_entity(collection, payload, entity_id=entity_id)
    elif action == "run_entity_dry":
        collection = str(action_args.get("collection") or "").strip()
        code = str(action_args.get("code") or "")
        context = action_args.get("context") or {}
        if not collection:
            raise ValueError("collection is required")
        if not isinstance(context, dict):
            raise ValueError("context must be an object")
        result = instance.mcp_run_entity_dry(collection, code, context=context)
    elif action == "invoke":
        operation = str(action_args.get("operation") or "").strip()
        params = action_args.get("params") or {}
        if not operation:
            raise ValueError("operation is required")
        if not isinstance(params, dict):
            raise ValueError("params must be an object")
        result = instance.mcp_invoke(operation, params)
    else:
        result = callPluginFunction(plugin_name, method_name, action_args)

    return {"plugin": plugin_name, "action": action, "result": result}


def _dispatch_atomic_plugin_tool(plugin, tool_name: str, args: dict) -> dict:
    action = _ATOMIC_PLUGIN_TOOLS[tool_name]
    plugin_name = str(args.get("plugin") or "").strip()
    if not plugin_name:
        raise ValueError("plugin is required")

    action_args = {}
    for key in (
        "collection",
        "entity_id",
        "query",
        "limit",
        "payload",
        "code",
        "context",
        "operation",
        "params",
        "if_match",
        "steps",
        "stop_on_error",
        "items",
        "mode",
        "dry_run",
        "entity_ids",
    ):
        if key in args:
            action_args[key] = args.get(key)

    dispatch_args = {
        "plugin": plugin_name,
        "action": action,
        "args": action_args,
    }
    return _dispatch_plugin_action(plugin, dispatch_args)


def _collect_plugin_entities_for_property(plugin, object_name: str, property_name: str, plugin_filter: str = "") -> list:
    allowed = _plugins_allowed(plugin)
    out = []
    for plugin_name in allowed:
        if plugin_filter and plugin_name != plugin_filter:
            continue
        instance = getModule(plugin_name)
        if instance is None:
            continue
        caps = _instance_mcp_capabilities(instance)
        collections = caps.get("collections") or []
        for collection in collections:
            if not isinstance(collection, dict):
                continue
            collection_id = str(collection.get("id") or "").strip()
            if not collection_id:
                continue
            binding_mode = str(collection.get("binding_mode") or "").strip().lower()
            if binding_mode and binding_mode != "property":
                continue
            try:
                entities = instance.mcp_list_entities(collection_id, query=None, limit=500)
            except Exception:
                continue
            if not isinstance(entities, list):
                continue
            for entity in entities:
                if not isinstance(entity, dict):
                    continue
                if (
                    str(entity.get("linked_object") or "").strip() == object_name
                    and str(entity.get("linked_property") or "").strip() == property_name
                ):
                    out.append(
                        {
                            "plugin": plugin_name,
                            "collection": collection_id,
                            "entity_id": entity.get("id"),
                            "entity": entity,
                        }
                    )
    return out


def _collection_binding_mode(instance, collection: str) -> str:
    caps = _instance_mcp_capabilities(instance)
    for item in caps.get("collections") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "").strip() == collection:
            return str(item.get("binding_mode") or "none").strip().lower()
    return "none"


def _bind_device(plugin, args: dict) -> dict:
    plugin._require_permission("allow_manage_plugins", "Plugin management tools are disabled")
    plugin_name = str(args.get("plugin") or "").strip()
    collection = str(args.get("collection") or "").strip()
    if not plugin_name or not collection:
        raise ValueError("plugin and collection are required")
    _ensure_plugin_allowed(plugin, plugin_name)
    instance = getModule(plugin_name)
    if instance is None:
        raise ValueError(f"Plugin not installed or inactive: {plugin_name}")
    if not _instance_mcp_supported(instance):
        raise ValueError(f"Plugin '{plugin_name}' does not support MCP entities")

    payload = args.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    payload = dict(payload)
    entity_id = args.get("entity_id")
    if_match = str(args.get("if_match") or "").strip() or None
    sync_links = bool(args.get("sync_links", True))
    verify_property = bool(args.get("verify_property", False))

    object_name = str(
        args.get("object_name") or args.get("linked_object") or payload.get("linked_object") or ""
    ).strip()
    property_name = str(
        args.get("property_name") or args.get("linked_property") or payload.get("linked_property") or ""
    ).strip()

    binding_mode = _collection_binding_mode(instance, collection)
    if binding_mode == "property":
        if not object_name or not property_name:
            raise ValueError("object_name and property_name are required for property-binding collections")
        payload["linked_object"] = object_name
        payload["linked_property"] = property_name
    elif binding_mode == "object":
        linked_object = str(payload.get("linked_object") or object_name or "").strip()
        if linked_object:
            payload["linked_object"] = linked_object
            ok, err = sync_object_link(linked_object)
            if not ok:
                raise ValueError(err or "object link validation failed")

    if if_match:
        if entity_id in (None, ""):
            raise ValueError("entity_id is required when if_match is provided")
        if not hasattr(instance, "mcp_entity_revision"):
            raise ValueError(f"Plugin '{plugin_name}' does not implement mcp_entity_revision")
        current_revision = str(instance.mcp_entity_revision(collection, entity_id) or "").strip()
        mcp_utils.enforce_if_match(if_match, current_revision)

    entity = instance.mcp_upsert_entity(collection, payload, entity_id=entity_id)

    linked: List[str] = []
    link_error = None
    if sync_links and binding_mode == "property" and object_name and property_name:
        ok, err = sync_property_link(plugin_name, object_name, property_name)
        if not ok:
            link_error = err
        else:
            obj = getObject(object_name)
            if obj and property_name in obj.properties:
                linked = list(obj.properties[property_name].linked or [])

    security_audit_log(
        "MCP_BIND_DEVICE",
        plugin=plugin_name,
        collection=collection,
        object_name=object_name or None,
        property_name=property_name or None,
        entity_id=entity.get("id") if isinstance(entity, dict) else entity_id,
        source="MCPServer",
    )

    result = {
        "ok": link_error is None,
        "plugin": plugin_name,
        "collection": collection,
        "entity": entity,
        "binding_mode": binding_mode,
        "linked": linked,
    }
    if link_error:
        result["link_error"] = link_error
    if verify_property and object_name and property_name:
        result["property_value"] = getProperty(f"{object_name}.{property_name}")
    if link_error:
        raise ValueError(link_error)
    return result


def _find_bindings(plugin, args: dict) -> dict:
    plugin._require_permission("allow_read_plugins", "Plugin read tools are disabled")
    object_name = str(args.get("object_name") or "").strip()
    property_name = str(args.get("property_name") or "").strip()
    include_plugin_entities = bool(args.get("include_plugin_entities", True))
    plugin_filter = str(args.get("plugin") or "").strip()
    if not object_name or not property_name:
        raise ValueError("object_name and property_name are required")
    obj = getObject(object_name)
    if obj is None:
        raise ValueError(f"Object not found: {object_name}")
    if property_name not in obj.properties:
        raise ValueError(f"Property not found: {object_name}.{property_name}")
    prop = obj.properties[property_name]
    linked_plugins = list(prop.linked or [])
    entities = []
    if include_plugin_entities:
        entities = _collect_plugin_entities_for_property(plugin, object_name, property_name, plugin_filter=plugin_filter)
    return {
        "object_name": object_name,
        "property_name": property_name,
        "linked_plugins": linked_plugins,
        "entities": entities,
        "current_value": getProperty(f"{object_name}.{property_name}"),
    }


def _get_object_context(plugin, args: dict) -> dict:
    object_name = str(args.get("object_name") or "").strip()
    include_history = bool(args.get("include_history", False))
    history_limit = plugin._safe_int(args.get("history_limit"), 5, 1, 500)
    include_plugin_entities = bool(args.get("include_plugin_entities", True))
    selected_properties = args.get("properties") or []
    if not object_name:
        raise ValueError("object_name is required")
    obj = getObject(object_name)
    if obj is None:
        raise ValueError(f"Object not found: {object_name}")
    if selected_properties and not isinstance(selected_properties, list):
        raise ValueError("properties must be an array")
    object_payload = plugin._serialize_object(obj)
    class_name = object_payload.get("class_name")
    class_payload = plugin._get_class_record(class_name) if class_name else None
    if selected_properties:
        property_names = [str(item).strip() for item in selected_properties if str(item).strip()]
    else:
        property_names = sorted(obj.properties.keys())
    properties = []
    history_samples = {}
    plugin_entities = []
    for prop_name in property_names:
        prop_full = f"{object_name}.{prop_name}"
        prop_obj = obj.properties.get(prop_name)
        if prop_obj is None:
            continue
        item = {
            "name": prop_name,
            "value": plugin._serialize_value(prop_obj.getValue()),
            "linked": list(prop_obj.linked or []),
            "ui": plugin._get_object_property_record(object_name, prop_name) or {},
        }
        properties.append(item)
        if include_history:
            history_samples[prop_name] = plugin._serialize_value(
                getHistory(prop_full, limit=history_limit, order_desc=True) or []
            )
        if include_plugin_entities:
            plugin_entities.extend(
                _collect_plugin_entities_for_property(plugin, object_name, prop_name)
            )
    methods = []
    for name, method in obj.methods.items():
        methods.append({"name": name, "description": getattr(method, "description", "") or ""})
    return {
        "object": object_payload,
        "class": class_payload,
        "properties": properties,
        "methods": methods,
        "plugin_entities": plugin_entities,
        "history_samples": history_samples,
    }


def handle_plugin_tools(plugin, tool_name: str, args: dict) -> Optional[dict]:
    if tool_name == "osys_list_plugins":
        return plugin._tool_result(_list_plugins(plugin, args))

    if tool_name == "osys_get_plugin_config":
        plugin._require_permission("allow_read_plugins", "Plugin read tools are disabled")
        plugin_name = str(args.get("plugin") or "").strip()
        if not plugin_name:
            raise ValueError("plugin is required")
        _ensure_plugin_allowed(plugin, plugin_name)
        return plugin._tool_result(_load_plugin_config(plugin_name, mask_secrets=True))

    if tool_name == "osys_update_plugin_config":
        plugin._require_permission("allow_manage_plugins", "Plugin management tools are disabled")
        plugin_name = str(args.get("plugin") or "").strip()
        if not plugin_name:
            raise ValueError("plugin is required")
        return plugin._tool_result(_update_plugin_config(plugin, plugin_name, args))

    if tool_name == "osys_manage_property_links":
        return plugin._tool_result(_manage_property_links(plugin, args))

    if tool_name == "osys_find_bindings":
        return plugin._tool_result(_find_bindings(plugin, args))

    if tool_name == "osys_get_object_context":
        return plugin._tool_result(_get_object_context(plugin, args))

    if tool_name == "osys_bind_device":
        return plugin._tool_result(_bind_device(plugin, args))

    if tool_name in _ATOMIC_PLUGIN_TOOLS:
        return plugin._tool_result(_dispatch_atomic_plugin_tool(plugin, tool_name, args))

    return None


def get_tool_schemas(_property_params_schema) -> list[dict]:
    return [
        {
            "name": "osys_list_plugins",
            "description": "List osysHome plugins with MCP capabilities",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "active_only": {"type": "boolean"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 5000},
                },
            },
        },
        {
            "name": "osys_get_plugin_config",
            "description": "Get plugin module config and metadata (secrets masked)",
            "inputSchema": {
                "type": "object",
                "properties": {"plugin": {"type": "string"}},
                "required": ["plugin"],
            },
        },
        {
            "name": "osys_update_plugin_config",
            "description": "Merge-patch plugin config and optional metadata fields",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plugin": {"type": "string"},
                    "config": {"type": "object", "additionalProperties": True},
                    "title": {"type": "string"},
                    "category": {"type": "string"},
                    "hidden": {"type": "boolean"},
                    "active": {"type": "boolean"},
                    "url": {"type": "string"},
                    "branch": {"type": "string"},
                    "if_match": {"type": "string"},
                },
                "required": ["plugin"],
            },
        },
        {
            "name": "osys_manage_property_links",
            "description": "List/add/remove/replace Value.linked plugin names for an object property",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "add", "remove", "replace"]},
                    "object_name": {"type": "string"},
                    "property_name": {"type": "string"},
                    "plugin": {"type": "string"},
                    "plugins": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        {
            "name": "osys_find_bindings",
            "description": "Find plugin bindings for object property",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "property_name": {"type": "string"},
                    "include_plugin_entities": {"type": "boolean"},
                    "plugin": {"type": "string"},
                },
                "required": ["object_name", "property_name"],
            },
        },
        {
            "name": "osys_get_object_context",
            "description": "Get aggregated object context for AI agents",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "include_history": {"type": "boolean"},
                    "history_limit": {"type": "integer", "minimum": 1, "maximum": 500},
                    "include_plugin_entities": {"type": "boolean"},
                    "properties": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["object_name"],
            },
        },
        {
            "name": "osys_bind_device",
            "description": "Upsert plugin entity and sync property/object binding in one step",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plugin": {"type": "string"},
                    "collection": {"type": "string"},
                    "entity_id": {},
                    "payload": {"type": "object", "additionalProperties": True},
                    "object_name": {"type": "string"},
                    "property_name": {"type": "string"},
                    "linked_object": {"type": "string"},
                    "linked_property": {"type": "string"},
                    "if_match": {"type": "string"},
                    "sync_links": {"type": "boolean"},
                    "verify_property": {"type": "boolean"},
                },
                "required": ["plugin", "collection", "payload"],
            },
        },
        {
            "name": "osys_plugin_capabilities",
            "description": "Get plugin MCP capabilities",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plugin": {"type": "string"},
                },
                "required": ["plugin"],
            },
        },
        {
            "name": "osys_plugin_config_schema",
            "description": "Get plugin config schema",
            "inputSchema": {
                "type": "object",
                "properties": {"plugin": {"type": "string"}},
                "required": ["plugin"],
            },
        },
        {
            "name": "osys_plugin_entity_schema",
            "description": "Get plugin entity schema by collection",
            "inputSchema": {
                "type": "object",
                "properties": {"plugin": {"type": "string"}, "collection": {"type": "string"}},
                "required": ["plugin", "collection"],
            },
        },
        {
            "name": "osys_plugin_list_entities",
            "description": "List plugin entities",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plugin": {"type": "string"},
                    "collection": {"type": "string"},
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 5000},
                    "list_id": {"type": "integer"},
                    "active_only": {"type": "boolean"},
                },
                "required": ["plugin", "collection"],
            },
        },
        {
            "name": "osys_plugin_get_entity",
            "description": "Get one plugin entity",
            "inputSchema": {
                "type": "object",
                "properties": {"plugin": {"type": "string"}, "collection": {"type": "string"}, "entity_id": {}},
                "required": ["plugin", "collection", "entity_id"],
            },
        },
        {
            "name": "osys_plugin_search",
            "description": "Search entities in plugin search API",
            "inputSchema": {
                "type": "object",
                "properties": {"plugin": {"type": "string"}, "query": {"type": "string"}},
                "required": ["plugin", "query"],
            },
        },
        {
            "name": "osys_plugin_validate_entity_code",
            "description": "Validate code for code-bearing plugin entity",
            "inputSchema": {
                "type": "object",
                "properties": {"plugin": {"type": "string"}, "collection": {"type": "string"}, "code": {"type": "string"}},
                "required": ["plugin", "collection", "code"],
            },
        },
        {
            "name": "osys_plugin_validate_entity",
            "description": "Validate plugin entity payload",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plugin": {"type": "string"},
                    "collection": {"type": "string"},
                    "payload": {"type": "object", "additionalProperties": True},
                    "entity_id": {},
                },
                "required": ["plugin", "collection", "payload"],
            },
        },
        {
            "name": "osys_plugin_diff_entity",
            "description": "Preview plugin entity changes before upsert",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plugin": {"type": "string"},
                    "collection": {"type": "string"},
                    "entity_id": {},
                    "payload": {"type": "object", "additionalProperties": True},
                },
                "required": ["plugin", "collection", "payload"],
            },
        },
        {
            "name": "osys_plugin_export_entities",
            "description": "Export plugin entities from collection",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plugin": {"type": "string"},
                    "collection": {"type": "string"},
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 5000},
                    "entity_ids": {"type": "array", "items": {}},
                },
                "required": ["plugin", "collection"],
            },
        },
        {
            "name": "osys_plugin_run_entity_dry",
            "description": "Dry-run plugin entity code",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plugin": {"type": "string"},
                    "collection": {"type": "string"},
                    "code": {"type": "string"},
                    "context": {"type": "object"},
                },
                "required": ["plugin", "collection", "code"],
            },
        },
        {
            "name": "osys_plugin_upsert_entity",
            "description": "Create or update plugin entity",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plugin": {"type": "string"},
                    "collection": {"type": "string"},
                    "entity_id": {},
                    "payload": {"type": "object", "additionalProperties": True},
                    "if_match": {"type": "string"},
                },
                "required": ["plugin", "collection", "payload"],
            },
        },
        {
            "name": "osys_plugin_delete_entity",
            "description": "Delete plugin entity",
            "inputSchema": {
                "type": "object",
                "properties": {"plugin": {"type": "string"}, "collection": {"type": "string"}, "entity_id": {}},
                "required": ["plugin", "collection", "entity_id"],
            },
        },
        {
            "name": "osys_plugin_import_entities",
            "description": "Import plugin entities into collection",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plugin": {"type": "string"},
                    "collection": {"type": "string"},
                    "items": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "mode": {"type": "string", "enum": ["upsert", "create_only"]},
                    "dry_run": {"type": "boolean"},
                },
                "required": ["plugin", "collection", "items"],
            },
        },
        {
            "name": "osys_plugin_batch",
            "description": "Run multiple plugin actions in one call",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plugin": {"type": "string"},
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "plugin": {"type": "string"},
                                "action": {
                                    "type": "string",
                                    "enum": sorted(list(_READ_PLUGIN_ACTIONS | _WRITE_PLUGIN_ACTIONS)),
                                },
                                "args": {"type": "object", "additionalProperties": True},
                            },
                            "required": ["action"],
                        },
                    },
                    "stop_on_error": {"type": "boolean"},
                },
                "required": ["plugin", "steps"],
            },
        },
        {
            "name": "osys_plugin_invoke",
            "description": "Invoke plugin-specific operation",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plugin": {"type": "string"},
                    "operation": {"type": "string"},
                    "params": {"type": "object", "additionalProperties": True},
                },
                "required": ["plugin", "operation"],
            },
        },
    ]
