"""Read/property/history/runtime handler groups for MCPServer tools."""
# pylint: disable=protected-access

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import or_

from app.core.lib.constants import PropertyType
from app.core.lib.common import getModulesByAction
from app.core.lib.object import (
    addClassProperty,
    addObjectProperty,
    callMethod,
    deleteClassProperty,
    getHistory,
    getHistoryAggregate,
    getObject,
    getProperty,
    setProperty,
)
from app.core.models.Clasess import Class, Method, Object, Property, Value
from app.database import session_scope


def handle_read_tools(plugin, tool_name: str, args: dict) -> Optional[dict]:
    if tool_name == "osys_global_search":
        query = str(args.get("query") or "").strip()
        if len(query) < 2:
            raise ValueError("query is required and must be at least 2 characters")
        query_like = f"%{query.lower()}%"
        include_plugin_search = bool(args.get("include_plugin_search", True))
        max_items = int(plugin.config.get("max_list_items", 200))
        limit = plugin._safe_int(args.get("limit"), 50, 1, 5000)
        limit = min(limit, max_items)

        items = []
        with session_scope() as session:
            rows = (
                session.query(
                    Object.id.label("object_id"),
                    Object.name.label("object_name"),
                    Object.description.label("object_description"),
                    Class.id.label("class_id"),
                    Class.name.label("class_name"),
                    Property.id.label("property_id"),
                    Property.name.label("property_name"),
                    Property.description.label("property_description"),
                    Property.method_id.label("property_method_id"),
                    Method.id.label("property_method_db_id"),
                    Method.name.label("property_method_name"),
                    Value.linked.label("linked"),
                    Value.value.label("property_value"),
                )
                .join(Class, Class.id == Object.class_id, isouter=True)
                .join(Property, Property.object_id == Object.id, isouter=True)
                .join(Method, Method.id == Property.method_id, isouter=True)
                .join(
                    Value,
                    (Value.object_id == Object.id) & (Value.name == Property.name),
                    isouter=True,
                )
                .filter(
                    or_(
                        Object.name.ilike(query_like),
                        Object.description.ilike(query_like),
                        Class.name.ilike(query_like),
                        Property.name.ilike(query_like),
                        Property.description.ilike(query_like),
                        Method.name.ilike(query_like),
                        Method.code.ilike(query_like),
                        Value.linked.ilike(query_like),
                        Value.value.ilike(query_like),
                    )
                )
                .order_by(Object.name, Property.name)
                .limit(limit)
                .all()
            )

            for row in rows:
                linked_plugins = []
                if row.linked:
                    linked_plugins = [item.strip() for item in str(row.linked).split(",") if item.strip()]
                items.append(
                    {
                        "source": "core",
                        "entity": {
                            "object": {
                                "id": row.object_id,
                                "name": row.object_name,
                                "description": row.object_description or "",
                            },
                            "class": (
                                {"id": row.class_id, "name": row.class_name}
                                if row.class_id is not None
                                else None
                            ),
                            "property": (
                                {
                                    "id": row.property_id,
                                    "name": row.property_name,
                                    "description": row.property_description or "",
                                    "value": row.property_value,
                                }
                                if row.property_id is not None
                                else None
                            ),
                            "method": (
                                {"id": row.property_method_db_id, "name": row.property_method_name}
                                if row.property_method_db_id is not None
                                else None
                            ),
                        },
                        "links": {
                            "linked_plugins": linked_plugins,
                        },
                        "relation_hints": [
                            hint
                            for hint in [
                                f"class:{row.class_name}" if row.class_name else None,
                                f"method:{row.property_method_name}" if row.property_method_name else None,
                                f"plugins:{','.join(linked_plugins)}" if linked_plugins else None,
                            ]
                            if hint
                        ],
                    }
                )

        if include_plugin_search and len(items) < limit:
            for search_plugin in getModulesByAction("search"):
                if len(items) >= limit:
                    break
                plugin_name = getattr(search_plugin, "name", search_plugin.__class__.__name__)
                try:
                    plugin_results = search_plugin.search(query)
                except Exception:
                    continue
                if not isinstance(plugin_results, list):
                    continue

                for rec in plugin_results:
                    if len(items) >= limit:
                        break
                    if not isinstance(rec, dict):
                        continue
                    tags = rec.get("tags") if isinstance(rec.get("tags"), list) else []
                    items.append(
                        {
                            "source": "plugin",
                            "source_plugin": plugin_name,
                            "entity": {
                                "title": rec.get("title"),
                                "url": rec.get("url"),
                            },
                            "links": {},
                            "tags": tags,
                            "relation_hints": [
                                hint
                                for hint in [
                                    f"plugin:{plugin_name}",
                                    f"tags:{','.join(str(tag.get('name')) for tag in tags if isinstance(tag, dict) and tag.get('name'))}"
                                    if tags
                                    else None,
                                ]
                                if hint
                            ],
                        }
                    )

        return plugin._tool_result({"query": query, "count": len(items), "items": items})
    if tool_name == "osys_list_objects":
        data = plugin._tool_list_objects(args)
        return plugin._tool_result(data)
    if tool_name == "osys_get_object":
        name = (args.get("object_name") or "").strip()
        if not name:
            raise ValueError("object_name is required")
        obj = getObject(name)
        if not obj:
            raise ValueError(f"Object not found: {name}")
        data = plugin._serialize_object(obj)
        rec = plugin._get_object_record(name)
        revision_payload = data
        if rec:
            data["class_name"] = rec.get("class_name")
            data["template"] = rec.get("template")
            data["template_engine"] = rec.get("template_engine", "jinja2")
            data["effective_template_source"] = rec.get("effective_template_source")
            revision_payload = rec
        return plugin._tool_result({"object": data, "revision": plugin._revision_for_payload(revision_payload)})
    if tool_name == "osys_get_property":
        prop_name = (args.get("property_name") or "").strip()
        if not prop_name:
            raise ValueError("property_name is required")
        value = getProperty(prop_name)
        if value is False:
            raise ValueError(f"Invalid property name: {prop_name}")
        return plugin._tool_result({"property": prop_name, "value": plugin._serialize_value(value)})
    if tool_name == "osys_get_properties_batch":
        names = args.get("property_names") or []
        include_source = bool(args.get("include_source", False))
        include_ui = bool(args.get("include_ui", False))
        if not isinstance(names, list):
            raise ValueError("property_names must be an array")
        items = []
        errors = []
        for idx, raw_name in enumerate(names):
            prop_name = str(raw_name or "").strip()
            if not prop_name:
                errors.append({"index": idx, "property": raw_name, "error": "property name is empty"})
                continue
            value = getProperty(prop_name)
            if value is False:
                errors.append({"index": idx, "property": prop_name, "error": "invalid property name"})
                continue
            item = {
                "property": prop_name,
                "value": plugin._serialize_value(value),
            }
            if include_source:
                source = getProperty(prop_name, "source")
                item["source"] = plugin._serialize_value(source)
            if include_ui:
                object_name, property_name = prop_name.split(".", 1)
                rec = plugin._get_object_property_record(object_name, property_name)
                if rec is None:
                    item["ui"] = None
                else:
                    item["ui"] = rec.get("params", {})
            items.append(item)
        return plugin._tool_result(
            {
                "count": len(items),
                "items": items,
                "errors": errors,
            }
        )
    if tool_name == "osys_get_property_ui":
        class_name = (args.get("class_name") or "").strip()
        object_name = (args.get("object_name") or "").strip()
        prop_name = (args.get("property_name") or "").strip()
        if not prop_name:
            raise ValueError("property_name is required")
        if bool(class_name) == bool(object_name):
            raise ValueError("Provide exactly one of class_name or object_name")
        if class_name:
            rec = plugin._get_class_property_record(class_name, prop_name)
            if rec is None:
                raise ValueError(f"Class property not found: {class_name}.{prop_name}")
            payload = {
                "scope": "class",
                "class_name": class_name,
                "property_name": prop_name,
                "ui": rec.get("params", {}),
                "revision": plugin._revision_for_payload(rec),
            }
            return plugin._tool_result(payload)
        rec = plugin._get_object_property_record(object_name, prop_name)
        if rec is None:
            raise ValueError(f"Object property not found: {object_name}.{prop_name}")
        payload = {
            "scope": "object",
            "object_name": object_name,
            "property_name": prop_name,
            "ui": rec.get("params", {}),
            "revision": plugin._revision_for_payload(rec),
        }
        return plugin._tool_result(payload)
    return None


def handle_property_tools(plugin, tool_name: str, args: dict) -> Optional[dict]:
    if tool_name == "osys_update_property_ui":
        plugin._require_permission("allow_manage_properties", "Property management tools are disabled")
        class_name = (args.get("class_name") or "").strip()
        object_name = (args.get("object_name") or "").strip()
        prop_name = (args.get("property_name") or "").strip()
        ui = args.get("ui")
        merge = bool(args.get("merge", True))
        if_match = (args.get("if_match") or "").strip() or None
        if not prop_name:
            raise ValueError("property_name is required")
        if not isinstance(ui, dict):
            raise ValueError("ui must be an object")
        if bool(class_name) == bool(object_name):
            raise ValueError("Provide exactly one of class_name or object_name")
        plugin._validate_property_params(ui)
        if class_name:
            existing = plugin._get_class_property_record(class_name, prop_name)
            if existing is None:
                raise ValueError(f"Class property not found: {class_name}.{prop_name}")
            rev = plugin._revision_for_payload(existing)
            plugin._enforce_if_match(if_match, rev)
            current_params = existing.get("params") or {}
            if not isinstance(current_params, dict):
                current_params = {}
            new_params = dict(current_params) if merge else {}
            new_params.update(ui)
            plugin._validate_property_params(new_params)
            prop = addClassProperty(
                name=prop_name,
                class_name=class_name,
                description=str(existing.get("description") or ""),
                history=plugin._safe_int(existing.get("history"), 0, 0, 36500),
                type=plugin._parse_property_type(existing.get("type")),
                method_name=(existing.get("method_name") or None),
                params=new_params,
                update=True,
            )
            if prop is not None:
                plugin._reload_objects_by_class_name(class_name)
            out = plugin._get_class_property_record(class_name, prop_name) if prop is not None else None
            return plugin._tool_result(
                {
                    "ok": prop is not None,
                    "scope": "class",
                    "class_name": class_name,
                    "property_name": prop_name,
                    "ui": (out or {}).get("params", new_params),
                    "revision": plugin._revision_for_payload(out or {}),
                }
            )
        existing = plugin._get_object_property_record(object_name, prop_name)
        if existing is None:
            raise ValueError(f"Object property not found: {object_name}.{prop_name}")
        rev = plugin._revision_for_payload(existing)
        plugin._enforce_if_match(if_match, rev)
        current_params = existing.get("params") or {}
        if not isinstance(current_params, dict):
            current_params = {}
        new_params = dict(current_params) if merge else {}
        new_params.update(ui)
        plugin._validate_property_params(new_params)
        links_before = plugin._get_property_links(object_name, prop_name)
        success = addObjectProperty(
            name=prop_name,
            object_name=object_name,
            description=str(existing.get("description") or ""),
            history=plugin._safe_int(existing.get("history"), 0, 0, 36500),
            type=plugin._parse_property_type(existing.get("type")),
            method_name=(existing.get("method_name") or None),
            params=new_params,
            update=True,
        )
        plugin._restore_property_links(object_name, prop_name, links_before)
        if success:
            plugin._reload_object_by_name(object_name)
        out = plugin._get_object_property_record(object_name, prop_name) if success else None
        return plugin._tool_result(
            {
                "ok": bool(success),
                "scope": "object",
                "object_name": object_name,
                "property_name": prop_name,
                "ui": (out or {}).get("params", new_params),
                "revision": plugin._revision_for_payload(out or {}),
            }
        )
    if tool_name == "osys_add_class_property":
        plugin._require_permission("allow_manage_properties", "Property management tools are disabled")
        class_name = (args.get("class_name") or "").strip()
        name = (args.get("name") or "").strip()
        if not class_name or not name:
            raise ValueError("class_name and name are required")
        existing = plugin._get_class_property_record(class_name, name)
        update_mode = bool(args.get("update", False))
        params_arg = args.get("params")
        if params_arg is not None and not isinstance(params_arg, dict):
            raise ValueError("params must be an object")
        if params_arg is None and update_mode and existing is not None:
            params_arg = existing.get("params")
        if params_arg is not None and not isinstance(params_arg, dict):
            params_arg = {}
        history_default = int((existing or {}).get("history") or 0) if update_mode else 0
        ptype_default = (
            plugin._parse_property_type((existing or {}).get("type"))
            if update_mode and existing is not None
            else PropertyType.Empty
        )
        method_default = (existing or {}).get("method_name") if update_mode else None
        add_kwargs: Dict[str, Any] = {
            "name": name,
            "class_name": class_name,
            "history": plugin._safe_int(args.get("history"), history_default, 0, 36500),
            "type": plugin._parse_property_type(args.get("type")) if "type" in args else ptype_default,
            "method_name": (args.get("method_name") or None) if "method_name" in args else method_default,
            "params": params_arg,
            "update": update_mode,
        }
        if "description" in args:
            add_kwargs["description"] = plugin._safe_text_arg(args, "description")
        prop = addClassProperty(**add_kwargs)
        if prop is not None:
            plugin._reload_objects_by_class_name(class_name)
        return plugin._tool_result({"ok": prop is not None, "property_id": plugin._safe_model_id(prop)})
    if tool_name == "osys_update_class_property":
        plugin._require_permission("allow_manage_properties", "Property management tools are disabled")
        class_name = (args.get("class_name") or "").strip()
        name = (args.get("name") or "").strip()
        if not class_name or not name:
            raise ValueError("class_name and name are required")
        existing = plugin._get_class_property_record(class_name, name)
        if existing is None:
            raise ValueError(f"Class property not found: {class_name}.{name}")
        plugin._enforce_if_match((args.get("if_match") or "").strip() or None, plugin._revision_for_payload(existing))
        params_patch = args.get("params")
        if params_patch is not None and not isinstance(params_patch, dict):
            raise ValueError("params must be an object")
        merge_params = bool(args.get("merge_params", True))
        existing_params = existing.get("params") or {}
        if not isinstance(existing_params, dict):
            existing_params = {}
        if params_patch is None:
            params_arg = existing_params
        elif merge_params:
            params_arg = dict(existing_params)
            params_arg.update(params_patch)
        else:
            params_arg = params_patch
        plugin._validate_property_params(params_arg or {})
        description = plugin._safe_text_arg(args, "description") if "description" in args else str(existing.get("description") or "")
        history = plugin._safe_int(args.get("history"), int(existing.get("history") or 0), 0, 36500)
        ptype = plugin._parse_property_type(args.get("type")) if "type" in args else plugin._parse_property_type(existing.get("type"))
        method_name = (args.get("method_name") or None) if "method_name" in args else (existing.get("method_name") or None)
        prop = addClassProperty(
            name=name,
            class_name=class_name,
            description=description,
            history=history,
            type=ptype,
            method_name=method_name,
            params=params_arg,
            update=True,
        )
        if prop is not None:
            plugin._reload_objects_by_class_name(class_name)
        updated = plugin._get_class_property_record(class_name, name)
        return plugin._tool_result(
            {
                "ok": prop is not None,
                "property_id": plugin._safe_model_id(prop),
                "revision": plugin._revision_for_payload(updated or {}),
            }
        )
    if tool_name == "osys_add_object_property":
        plugin._require_permission("allow_manage_properties", "Property management tools are disabled")
        object_name = (args.get("object_name") or "").strip()
        name = (args.get("name") or "").strip()
        if not object_name or not name:
            raise ValueError("object_name and name are required")
        existing = plugin._get_object_property_record(object_name, name)
        update_mode = bool(args.get("update", False))
        links_before = plugin._get_property_links(object_name, name)
        params_arg = args.get("params")
        if params_arg is not None and not isinstance(params_arg, dict):
            raise ValueError("params must be an object")
        if params_arg is None and update_mode and existing is not None:
            params_arg = existing.get("params")
        if params_arg is not None and not isinstance(params_arg, dict):
            params_arg = {}
        history_default = int((existing or {}).get("history") or 0) if update_mode else 0
        ptype_default = (
            plugin._parse_property_type((existing or {}).get("type"))
            if update_mode and existing is not None
            else PropertyType.Empty
        )
        method_default = (existing or {}).get("method_name") if update_mode else None
        add_kwargs: Dict[str, Any] = {
            "name": name,
            "object_name": object_name,
            "history": plugin._safe_int(args.get("history"), history_default, 0, 36500),
            "type": plugin._parse_property_type(args.get("type")) if "type" in args else ptype_default,
            "method_name": (args.get("method_name") or None) if "method_name" in args else method_default,
            "params": params_arg,
            "update": update_mode,
        }
        if "description" in args:
            add_kwargs["description"] = plugin._safe_text_arg(args, "description")
        success = addObjectProperty(**add_kwargs)
        plugin._restore_property_links(object_name, name, links_before)
        if success:
            plugin._reload_object_by_name(object_name)
        return plugin._tool_result({"ok": bool(success), "property": f"{object_name}.{name}"})
    if tool_name == "osys_update_object_property":
        plugin._require_permission("allow_manage_properties", "Property management tools are disabled")
        object_name = (args.get("object_name") or "").strip()
        name = (args.get("name") or "").strip()
        if not object_name or not name:
            raise ValueError("object_name and name are required")
        existing = plugin._get_object_property_record(object_name, name)
        if existing is None:
            raise ValueError(f"Object property not found: {object_name}.{name}")
        plugin._enforce_if_match((args.get("if_match") or "").strip() or None, plugin._revision_for_payload(existing))
        links_before = plugin._get_property_links(object_name, name)
        params_patch = args.get("params")
        if params_patch is not None and not isinstance(params_patch, dict):
            raise ValueError("params must be an object")
        merge_params = bool(args.get("merge_params", True))
        existing_params = existing.get("params") or {}
        if not isinstance(existing_params, dict):
            existing_params = {}
        if params_patch is None:
            params_arg = existing_params
        elif merge_params:
            params_arg = dict(existing_params)
            params_arg.update(params_patch)
        else:
            params_arg = params_patch
        plugin._validate_property_params(params_arg or {})
        success = addObjectProperty(
            name=name,
            object_name=object_name,
            description=plugin._safe_text_arg(args, "description") if "description" in args else str(existing.get("description") or ""),
            history=plugin._safe_int(args.get("history"), int(existing.get("history") or 0), 0, 36500),
            type=plugin._parse_property_type(args.get("type")) if "type" in args else plugin._parse_property_type(existing.get("type")),
            method_name=(args.get("method_name") or None) if "method_name" in args else (existing.get("method_name") or None),
            params=params_arg,
            update=True,
        )
        plugin._restore_property_links(object_name, name, links_before)
        if success:
            plugin._reload_object_by_name(object_name)
        updated = plugin._get_object_property_record(object_name, name)
        return plugin._tool_result(
            {
                "ok": bool(success),
                "property": f"{object_name}.{name}",
                "revision": plugin._revision_for_payload(updated or {}),
            }
        )
    if tool_name == "osys_delete_class_property":
        plugin._require_permission("allow_manage_properties", "Property management tools are disabled")
        class_name = (args.get("class_name") or "").strip()
        property_name = (args.get("property_name") or "").strip()
        if not class_name or not property_name:
            raise ValueError("class_name and property_name are required")
        existing = plugin._get_class_property_record(class_name, property_name)
        if existing is None:
            raise ValueError(f"Class property not found: {class_name}.{property_name}")
        plugin._enforce_if_match((args.get("if_match") or "").strip() or None, plugin._revision_for_payload(existing))
        success = deleteClassProperty(f"{class_name}.{property_name}")
        if not success:
            raise ValueError(f"Failed to delete class property: {class_name}.{property_name}")
        plugin._reload_objects_by_class_name(class_name)
        return plugin._tool_result({"ok": True, "deleted_property": f"{class_name}.{property_name}"})
    return None


def handle_history_and_runtime_tools(plugin, tool_name: str, args: dict) -> Optional[dict]:
    if tool_name == "osys_get_property_history":
        prop_name = (args.get("property_name") or "").strip()
        if not prop_name:
            raise ValueError("property_name is required")
        dt_begin = plugin._parse_optional_datetime(args.get("dt_begin"), "dt_begin")
        dt_end = plugin._parse_optional_datetime(args.get("dt_end"), "dt_end")
        limit = plugin._safe_int(args.get("limit"), 200, 1, 50000)
        order_desc = bool(args.get("order_desc", False))
        data = getHistory(prop_name, dt_begin=dt_begin, dt_end=dt_end, limit=limit, order_desc=order_desc)
        if data is None:
            raise ValueError(f"Failed to read history for property: {prop_name}")
        payload = {
            "property": prop_name,
            "dt_begin": dt_begin.isoformat(sep=" ", timespec="seconds") if dt_begin else None,
            "dt_end": dt_end.isoformat(sep=" ", timespec="seconds") if dt_end else None,
            "limit": limit,
            "order_desc": order_desc,
            "count": len(data) if isinstance(data, list) else None,
            "items": plugin._serialize_value(data),
        }
        return plugin._tool_result(payload)
    if tool_name == "osys_get_property_history_aggregate":
        prop_name = (args.get("property_name") or "").strip()
        if not prop_name:
            raise ValueError("property_name is required")
        dt_begin = plugin._parse_optional_datetime(args.get("dt_begin"), "dt_begin")
        dt_end = plugin._parse_optional_datetime(args.get("dt_end"), "dt_end")
        func = (args.get("func") or "").strip().lower() or None
        if func and func not in {"min", "max", "sum", "avg", "count"}:
            raise ValueError("func must be one of: min, max, sum, avg, count")
        agg = getHistoryAggregate(prop_name, dt_begin=dt_begin, dt_end=dt_end, func=func)
        payload = {
            "property": prop_name,
            "func": func or "all",
            "dt_begin": dt_begin.isoformat(sep=" ", timespec="seconds") if dt_begin else None,
            "dt_end": dt_end.isoformat(sep=" ", timespec="seconds") if dt_end else None,
            "value": plugin._serialize_value(agg),
        }
        return plugin._tool_result(payload)
    if tool_name == "osys_write_property":
        if not plugin.config.get("allow_write_tools", False):
            raise PermissionError("Write tools are disabled in plugin config")
        prop_name = (args.get("property_name") or "").strip()
        if not prop_name:
            raise ValueError("property_name is required")
        source = (args.get("source") or "MCP").strip()
        success = setProperty(prop_name, args.get("value"), source=source)
        if not success:
            raise ValueError(f"Failed to set property: {prop_name}")
        value = getProperty(prop_name)
        return plugin._tool_result({"ok": True, "property": prop_name, "value": plugin._serialize_value(value)})
    if tool_name == "osys_invoke_method":
        if not plugin.config.get("allow_method_calls", True):
            raise PermissionError("Method calls are disabled in plugin config")
        method_name = (args.get("method_name") or "").strip()
        if not method_name:
            raise ValueError("method_name is required")
        source = (args.get("source") or "MCP").strip()
        call_args = args.get("args") or {}
        if not isinstance(call_args, dict):
            raise ValueError("args must be an object")
        output = callMethod(method_name, args=call_args, source=source)
        return plugin._tool_result({"method": method_name, "output": plugin._serialize_value(output)})
    if tool_name == "osys_validate_method_code":
        code = args.get("code")
        if code is None:
            raise ValueError("code is required")
        payload = plugin._validate_method_code_payload(code, args.get("code_mode"))
        return plugin._tool_result(payload)
    if tool_name == "osys_run_method_dry":
        plugin._require_permission("allow_manage_methods", "Method management tools are disabled")
        code = args.get("code")
        if code is None:
            raise ValueError("code is required")
        params_arg = args.get("params") or {}
        if not isinstance(params_arg, dict):
            raise ValueError("params must be an object")
        payload = plugin._dry_run_method_code(
            code=code,
            code_mode=args.get("code_mode"),
            object_name=(args.get("object_name") or "").strip() or None,
            params=params_arg,
            source=(args.get("source") or "MCP:dry-run").strip() or "MCP:dry-run",
        )
        return plugin._tool_result(payload)
    return None


def get_tool_schemas(property_params_schema: Dict[str, Any]) -> list[dict]:
    return [
        {
            "name": "osys_global_search",
            "description": "Global search across objects/properties/methods with relation hints",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 5000},
                    "include_plugin_search": {"type": "boolean"},
                },
                "required": ["query"],
            },
        },
        {
            "name": "osys_list_objects",
            "description": "List objects available in osysHome",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 5000},
                },
            },
        },
        {
            "name": "osys_get_object",
            "description": "Get object details by name",
            "inputSchema": {"type": "object", "properties": {"object_name": {"type": "string"}}, "required": ["object_name"]},
        },
        {
            "name": "osys_get_property",
            "description": "Get property value by Object.Property name",
            "inputSchema": {"type": "object", "properties": {"property_name": {"type": "string"}}, "required": ["property_name"]},
        },
        {
            "name": "osys_get_properties_batch",
            "description": "Get multiple property values in one call",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "property_names": {"type": "array", "items": {"type": "string"}},
                    "include_source": {"type": "boolean"},
                    "include_ui": {"type": "boolean"},
                },
                "required": ["property_names"],
            },
        },
        {
            "name": "osys_get_property_ui",
            "description": "Get UI params for class/object property",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "object_name": {"type": "string"},
                    "property_name": {"type": "string"},
                },
                "required": ["property_name"],
            },
        },
        {
            "name": "osys_update_property_ui",
            "description": "Update UI params for class/object property (merge patch; any unspecified data must be preserved)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "object_name": {"type": "string"},
                    "property_name": {"type": "string"},
                    "ui": property_params_schema,
                    "merge": {"type": "boolean"},
                    "if_match": {"type": "string"},
                },
                "required": ["property_name", "ui"],
            },
        },
        {
            "name": "osys_get_property_history",
            "description": "Get property value history by Object.Property name",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "property_name": {"type": "string"},
                    "dt_begin": {"type": "string", "description": "ISO datetime, inclusive"},
                    "dt_end": {"type": "string", "description": "ISO datetime, inclusive"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50000},
                    "order_desc": {"type": "boolean"},
                },
                "required": ["property_name"],
            },
        },
        {
            "name": "osys_get_property_history_aggregate",
            "description": "Get property history aggregate by Object.Property name",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "property_name": {"type": "string"},
                    "dt_begin": {"type": "string", "description": "ISO datetime, inclusive"},
                    "dt_end": {"type": "string", "description": "ISO datetime, inclusive"},
                    "func": {"type": "string", "enum": ["min", "max", "sum", "avg", "count"]},
                },
                "required": ["property_name"],
            },
        },
        {
            "name": "osys_write_property",
            "description": "Write property value by Object.Property name",
            "inputSchema": {
                "type": "object",
                "properties": {"property_name": {"type": "string"}, "value": {}, "source": {"type": "string"}},
                "required": ["property_name", "value"],
            },
        },
        {
            "name": "osys_invoke_method",
            "description": "Invoke object method by Object.Method name",
            "inputSchema": {
                "type": "object",
                "properties": {"method_name": {"type": "string"}, "args": {"type": "object"}, "source": {"type": "string"}},
                "required": ["method_name"],
            },
        },
        {
            "name": "osys_validate_method_code",
            "description": "Validate method code for osysHome exec runtime",
            "inputSchema": {
                "type": "object",
                "properties": {"code": {"type": "string"}, "code_mode": {"type": "string"}},
                "required": ["code"],
            },
        },
        {
            "name": "osys_run_method_dry",
            "description": "Dry-run method code without side effects",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "code_mode": {"type": "string"},
                    "object_name": {"type": "string"},
                    "params": {"type": "object"},
                    "source": {"type": "string"},
                },
                "required": ["code"],
            },
        },
        {
            "name": "osys_add_class_property",
            "description": "Create or update a class property",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "history": {"type": "integer"},
                    "type": {"type": "string"},
                    "method_name": {"type": "string"},
                    "params": property_params_schema,
                    "update": {"type": "boolean"},
                },
                "required": ["class_name", "name"],
            },
        },
        {
            "name": "osys_update_class_property",
            "description": "Update class property (patch semantics; any unspecified data must be preserved)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "history": {"type": "integer"},
                    "type": {"type": "string"},
                    "method_name": {"type": "string"},
                    "params": property_params_schema,
                    "merge_params": {"type": "boolean"},
                    "if_match": {"type": "string"},
                },
                "required": ["class_name", "name"],
            },
        },
        {
            "name": "osys_delete_class_property",
            "description": "Delete class property",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "property_name": {"type": "string"},
                    "if_match": {"type": "string"},
                },
                "required": ["class_name", "property_name"],
            },
        },
        {
            "name": "osys_add_object_property",
            "description": "Create or update an object property with params",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "history": {"type": "integer"},
                    "type": {"type": "string"},
                    "method_name": {"type": "string"},
                    "params": property_params_schema,
                    "update": {"type": "boolean"},
                },
                "required": ["object_name", "name"],
            },
        },
        {
            "name": "osys_update_object_property",
            "description": "Update object property with params (patch semantics; any unspecified data must be preserved)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "history": {"type": "integer"},
                    "type": {"type": "string"},
                    "method_name": {"type": "string"},
                    "params": property_params_schema,
                    "merge_params": {"type": "boolean"},
                    "if_match": {"type": "string"},
                },
                "required": ["object_name", "name"],
            },
        },
    ]
