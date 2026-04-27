"""Object and bulk/delete handler groups for MCPServer tools."""
# pylint: disable=protected-access

from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.lib.object import addObject, deleteObject, deleteObjectMethod, deleteObjectProperty
from app.core.main.ObjectsStorage import objects_storage
from app.core.models.Clasess import Class, Method, Object, Property
from app.database import session_scope


def handle_object_tools(plugin, tool_name: str, args: dict) -> Optional[dict]:
    if tool_name == "osys_add_object":
        plugin._require_permission("allow_manage_objects", "Object management tools are disabled")
        object_name = (args.get("object_name") or "").strip()
        class_name = (args.get("class_name") or "").strip()
        if not object_name or not class_name:
            raise ValueError("object_name and class_name are required")
        add_kwargs: Dict[str, Any] = {
            "name": object_name,
            "class_name": class_name,
            "update": bool(args.get("update", False)),
        }
        if "description" in args:
            add_kwargs["description"] = plugin._safe_text_arg(args, "description")
        obj = addObject(**add_kwargs)
        return plugin._tool_result({"ok": obj is not None, "object_name": object_name})
    if tool_name == "osys_update_object":
        plugin._require_permission("allow_manage_objects", "Object management tools are disabled")
        object_name = (args.get("object_name") or "").strip()
        if not object_name:
            raise ValueError("object_name is required")
        rec_before = plugin._get_object_record(object_name)
        if rec_before is None:
            raise ValueError(f"Object not found: {object_name}")
        plugin._enforce_if_match((args.get("if_match") or "").strip() or None, plugin._revision_for_payload(rec_before))

        if "template_engine" in args:
            engine = (args.get("template_engine") or "").strip().lower()
            if engine and engine != "jinja2":
                raise ValueError(f"Unsupported template engine: {engine}")

        with session_scope() as session:
            rec = session.query(Object).filter(Object.name == object_name).one_or_none()
            if rec is None:
                raise ValueError(f"Object not found: {object_name}")

            if "class_name" in args:
                class_name_raw = args.get("class_name")
                class_name = str(class_name_raw).strip() if class_name_raw is not None else ""
                if class_name:
                    cls = session.query(Class).filter(Class.name == class_name).one_or_none()
                    if cls is None:
                        raise ValueError(f"Class not found: {class_name}")
                    rec.class_id = cls.id
                else:
                    rec.class_id = None
            if "description" in args:
                rec.description = plugin._safe_text_arg(args, "description")
            if "template" in args:
                rec.template = str(args.get("template") or "")
            session.commit()
            object_id = rec.id

        objects_storage.reload_object(object_id)
        rec_after = plugin._get_object_record(object_name) or {}
        return plugin._tool_result(
            {
                "ok": True,
                "object_name": object_name,
                "class_name": rec_after.get("class_name"),
                "template": rec_after.get("template"),
                "template_engine": rec_after.get("template_engine", "jinja2"),
                "effective_template_source": rec_after.get("effective_template_source"),
                "revision": plugin._revision_for_payload(rec_after),
            }
        )
    return None


def handle_bulk_and_delete_tools(plugin, tool_name: str, args: dict) -> Optional[dict]:
    if tool_name == "osys_bulk_update_class_properties":
        plugin._require_permission("allow_manage_properties", "Property management tools are disabled")
        class_name = (args.get("class_name") or "").strip()
        items = args.get("items") or []
        if not class_name:
            raise ValueError("class_name is required")
        if not isinstance(items, list):
            raise ValueError("items must be an array")
        updated_items = []
        errors = []
        for idx, item in enumerate(items):
            try:
                if not isinstance(item, dict):
                    raise ValueError("item must be object")
                payload = {"name": "osys_update_class_property", "arguments": {"class_name": class_name, **item}}
                res = plugin._tools_call(payload)
                updated_items.append({"index": idx, "result": res.get("structuredContent")})
            except Exception as ex:
                errors.append({"index": idx, "error": str(ex)})
        return plugin._tool_result({"ok": len(errors) == 0, "updated": updated_items, "errors": errors})
    if tool_name == "osys_bulk_update_methods":
        plugin._require_permission("allow_manage_methods", "Method management tools are disabled")
        class_name = (args.get("class_name") or "").strip()
        object_name = (args.get("object_name") or "").strip()
        items = args.get("items") or []
        if bool(class_name) == bool(object_name):
            raise ValueError("Provide exactly one of class_name or object_name")
        if not isinstance(items, list):
            raise ValueError("items must be an array")
        updated_items = []
        errors = []
        for idx, item in enumerate(items):
            try:
                if not isinstance(item, dict):
                    raise ValueError("item must be object")
                if class_name:
                    payload = {"name": "osys_update_class_method", "arguments": {"class_name": class_name, **item}}
                else:
                    payload = {"name": "osys_update_object_method", "arguments": {"object_name": object_name, **item}}
                res = plugin._tools_call(payload)
                updated_items.append({"index": idx, "result": res.get("structuredContent")})
            except Exception as ex:
                errors.append({"index": idx, "error": str(ex)})
        return plugin._tool_result(
            {
                "ok": len(errors) == 0,
                "scope": "class" if class_name else "object",
                "owner": class_name or object_name,
                "updated": updated_items,
                "errors": errors,
            }
        )
    if tool_name == "osys_delete_object":
        plugin._require_permission("allow_manage_objects", "Object management tools are disabled")
        object_name = (args.get("object_name") or "").strip()
        if not object_name:
            raise ValueError("object_name is required")
        deleteObject(object_name)
        return plugin._tool_result({"ok": True, "deleted_object": object_name})
    if tool_name == "osys_delete_object_property":
        plugin._require_permission("allow_manage_properties", "Property management tools are disabled")
        object_name = (args.get("object_name") or "").strip()
        property_name = (args.get("property_name") or "").strip()
        if not object_name or not property_name:
            raise ValueError("object_name and property_name are required")
        with session_scope() as session:
            obj = session.query(Object).filter(Object.name == object_name).one_or_none()
            if obj is None:
                raise ValueError(f"Object not found: {object_name}")
            prop = (
                session.query(Property)
                .filter(Property.object_id == obj.id, Property.name == property_name)
                .one_or_none()
            )
            if prop is None:
                raise ValueError(
                    f"Object property not found: {object_name}.{property_name}"
                )
        success = deleteObjectProperty(f"{object_name}.{property_name}")
        if not success:
            raise ValueError(
                f"Failed to delete object property: {object_name}.{property_name}"
            )
        plugin._reload_object_by_name(object_name)
        return plugin._tool_result({"ok": True, "deleted_property": f"{object_name}.{property_name}"})
    if tool_name == "osys_delete_object_method":
        plugin._require_permission("allow_manage_methods", "Method management tools are disabled")
        object_name = (args.get("object_name") or "").strip()
        method_name = (args.get("method_name") or "").strip()
        if not object_name or not method_name:
            raise ValueError("object_name and method_name are required")
        with session_scope() as session:
            obj = session.query(Object).filter(Object.name == object_name).one_or_none()
            if obj is None:
                raise ValueError(f"Object not found: {object_name}")
            method = (
                session.query(Method)
                .filter(Method.object_id == obj.id, Method.name == method_name)
                .one_or_none()
            )
            if method is None:
                raise ValueError(
                    f"Object method not found: {object_name}.{method_name}"
                )
        success = deleteObjectMethod(f"{object_name}.{method_name}")
        if not success:
            raise ValueError(
                f"Failed to delete object method: {object_name}.{method_name}"
            )
        plugin._reload_object_by_name(object_name)
        return plugin._tool_result({"ok": True, "deleted_method": f"{object_name}.{method_name}"})
    return None


def get_tool_schemas(property_params_schema: Dict[str, Any]) -> list[dict]:
    return [
        {
            "name": "osys_add_object",
            "description": "Create or update an object",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "class_name": {"type": "string"},
                    "description": {"type": "string"},
                    "update": {"type": "boolean"},
                },
                "required": ["object_name", "class_name"],
            },
        },
        {
            "name": "osys_update_object",
            "description": "Update existing object metadata/class (patch semantics: only explicitly provided fields are changed)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "class_name": {"type": "string"},
                    "description": {"type": "string"},
                    "template": {"type": "string"},
                    "template_engine": {"type": "string", "enum": ["jinja2"]},
                    "if_match": {"type": "string"},
                },
                "required": ["object_name"],
            },
        },
        {
            "name": "osys_bulk_update_class_properties",
            "description": "Bulk patch class properties",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                                "history": {"type": "integer"},
                                "type": {"type": "string"},
                                "method_name": {"type": "string"},
                                "params": property_params_schema,
                                "if_match": {"type": "string"},
                            },
                            "required": ["name"],
                        },
                    },
                },
                "required": ["class_name", "items"],
            },
        },
        {
            "name": "osys_bulk_update_methods",
            "description": "Bulk patch class/object methods",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "object_name": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                                "code": {"type": "string"},
                                "code_mode": {"type": "string"},
                                "call_parent": {"type": "integer"},
                                "if_match": {"type": "string"},
                            },
                            "required": ["name"],
                        },
                    },
                },
                "required": ["items"],
            },
        },
        {
            "name": "osys_delete_object",
            "description": "Delete object",
            "inputSchema": {"type": "object", "properties": {"object_name": {"type": "string"}}, "required": ["object_name"]},
        },
        {
            "name": "osys_delete_object_property",
            "description": "Delete object property",
            "inputSchema": {
                "type": "object",
                "properties": {"object_name": {"type": "string"}, "property_name": {"type": "string"}},
                "required": ["object_name", "property_name"],
            },
        },
        {
            "name": "osys_delete_object_method",
            "description": "Delete object method",
            "inputSchema": {
                "type": "object",
                "properties": {"object_name": {"type": "string"}, "method_name": {"type": "string"}},
                "required": ["object_name", "method_name"],
            },
        },
    ]
