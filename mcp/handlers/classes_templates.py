"""Class and template handler groups for MCPServer tools."""
# pylint: disable=protected-access

from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.lib.object import addClass
from app.core.models.Clasess import Class, Method, Object, Property
from app.database import session_scope


def _find_first_descendant_class(session, class_id: int):
    """Return first descendant class (any depth) for safety delete checks."""
    descendants_by_parent: Dict[int, list] = {}
    for row in session.query(Class.id, Class.name, Class.parent_id).all():
        if row.parent_id is None:
            continue
        descendants_by_parent.setdefault(row.parent_id, []).append({"id": row.id, "name": row.name})

    stack = list(descendants_by_parent.get(class_id, []))
    while stack:
        node = stack.pop(0)
        children = descendants_by_parent.get(node["id"], [])
        if children:
            stack = children + stack
        return node
    return None


def handle_class_tools(plugin, tool_name: str, args: dict) -> Optional[dict]:
    if tool_name == "osys_add_class":
        plugin._require_permission("allow_manage_classes", "Class management tools are disabled")
        class_name = (args.get("class_name") or "").strip()
        if not class_name:
            raise ValueError("class_name is required")
        class_exists = plugin._get_class_record(class_name) is not None
        update_mode = bool(args.get("update", False))
        add_kwargs: Dict[str, Any] = {"name": class_name, "update": update_mode}
        if "description" in args:
            add_kwargs["description"] = plugin._safe_text_arg(args, "description")
        if "parent_id" in args:
            add_kwargs["parentId"] = args.get("parent_id")
        rec = addClass(**add_kwargs)
        if "template" in args and (not class_exists or bool(args.get("update", False))):
            template = str(args.get("template") or "")
            rec = plugin._set_class_template(class_name, template)
            if rec is not None:
                plugin._reload_objects_by_class_name(class_name)
        return plugin._tool_result({"ok": rec is not None, "class": rec})
    if tool_name == "osys_update_class":
        plugin._require_permission("allow_manage_classes", "Class management tools are disabled")
        class_name = (args.get("class_name") or "").strip()
        if not class_name:
            raise ValueError("class_name is required")
        current = plugin._get_class_record(class_name)
        if current is None:
            raise ValueError(f"Class not found: {class_name}")
        plugin._enforce_if_match((args.get("if_match") or "").strip() or None, plugin._revision_for_payload(current))
        update_kwargs: Dict[str, Any] = {"name": class_name, "update": True}
        if "description" in args:
            update_kwargs["description"] = plugin._safe_text_arg(args, "description")
        if "parent_id" in args:
            update_kwargs["parentId"] = args.get("parent_id")
        rec = addClass(**update_kwargs)
        if "template" in args:
            template = str(args.get("template") or "")
            rec = plugin._set_class_template(class_name, template)
            if rec is not None:
                plugin._reload_objects_by_class_name(class_name)
        updated = plugin._get_class_record(class_name)
        return plugin._tool_result({"ok": rec is not None, "class": rec, "revision": plugin._revision_for_payload(updated or {})})
    if tool_name == "osys_delete_class":
        plugin._require_permission("allow_manage_classes", "Class management tools are disabled")
        class_name = (args.get("class_name") or "").strip()
        if not class_name:
            raise ValueError("class_name is required")
        with session_scope() as session:
            rec = session.query(Class).filter(Class.name == class_name).one_or_none()
            if rec is None:
                raise ValueError(f"Class not found: {class_name}")
            child_class = _find_first_descendant_class(session, rec.id)
            if child_class is not None:
                raise ValueError(
                    f"Cannot delete class '{class_name}': it has child class '{child_class['name']}'"
                )
            linked_object = session.query(Object).filter(Object.class_id == rec.id).first()
            if linked_object is not None:
                raise ValueError(
                    f"Cannot delete class '{class_name}': it has object '{linked_object.name}'"
                )
            session.query(Property).filter(Property.class_id == rec.id).delete(synchronize_session=False)
            session.query(Method).filter(Method.class_id == rec.id).delete(synchronize_session=False)
            session.delete(rec)
            session.commit()
        return plugin._tool_result({"ok": True, "deleted_class": class_name})
    if tool_name == "osys_get_class":
        plugin._require_permission("allow_class_introspection", "Class introspection tools are disabled")
        class_name = (args.get("class_name") or "").strip()
        if not class_name:
            raise ValueError("class_name is required")
        rec = plugin._get_class_record(class_name)
        if not rec:
            raise ValueError(f"Class not found: {class_name}")
        return plugin._tool_result({"class": rec, "revision": plugin._revision_for_payload(rec)})
    if tool_name == "osys_list_classes":
        plugin._require_permission("allow_class_introspection", "Class introspection tools are disabled")
        query = (args.get("query") or "").strip().lower()
        max_items = int(plugin.config.get("max_list_items", 200))
        limit = plugin._safe_int(args.get("limit"), max_items, 1, 5000)
        limit = min(limit, max_items)
        items = []
        with session_scope() as session:
            q = session.query(Class).order_by(Class.name)
            if query:
                q = q.filter(Class.name.ilike(f"%{query}%"))
            for row in q.limit(limit).all():
                items.append(
                    {
                        "id": row.id,
                        "name": row.name,
                        "parent_id": row.parent_id,
                        "description": row.description or "",
                    }
                )
        return plugin._tool_result({"count": len(items), "items": items})
    if tool_name == "osys_get_class_tree":
        plugin._require_permission("allow_class_introspection", "Class introspection tools are disabled")
        root_class_name = (args.get("root_class_name") or "").strip() or None
        include_templates = bool(args.get("include_templates", False))
        max_depth = plugin._safe_int(args.get("max_depth"), 100, 1, 1000)
        with session_scope() as session:
            rows = session.query(Class).order_by(Class.name).all()
            by_id = {}
            children = {}
            for row in rows:
                node = {
                    "id": row.id,
                    "name": row.name,
                    "description": row.description or "",
                    "parent_id": row.parent_id,
                }
                if include_templates:
                    node["template"] = row.template or ""
                by_id[row.id] = node
                children.setdefault(row.parent_id, []).append(row.id)

        if root_class_name:
            root = next((node for node in by_id.values() if node["name"] == root_class_name), None)
            if root is None:
                raise ValueError(f"Class not found: {root_class_name}")
            root_ids = [root["id"]]
        else:
            root_ids = sorted(children.get(None, []), key=lambda cid: by_id[cid]["name"].lower())

        def build_subtree(class_id: int, depth: int):
            node = dict(by_id[class_id])
            node["depth"] = depth
            if depth >= max_depth:
                node["children"] = []
                node["truncated"] = True
                return node
            child_ids = sorted(children.get(class_id, []), key=lambda cid: by_id[cid]["name"].lower())
            node["children"] = [build_subtree(cid, depth + 1) for cid in child_ids]
            node["truncated"] = False
            return node

        roots = [build_subtree(cid, 0) for cid in root_ids]
        return plugin._tool_result(
            {
                "count": len(by_id),
                "roots": roots,
            }
        )
    if tool_name == "osys_get_class_full":
        plugin._require_permission("allow_class_introspection", "Class introspection tools are disabled")
        class_name = (args.get("class_name") or "").strip()
        if not class_name:
            raise ValueError("class_name is required")
        rec = plugin._get_class_full_record(class_name)
        if rec is None:
            raise ValueError(f"Class not found: {class_name}")
        return plugin._tool_result({"class": rec, "revision": plugin._revision_for_payload(rec)})
    return None


def handle_template_tools(plugin, tool_name: str, args: dict) -> Optional[dict]:
    if tool_name == "osys_get_template_spec":
        engine = (args.get("engine") or "jinja2").strip().lower()
        data = plugin._get_template_spec(engine)
        return plugin._tool_result(data)
    if tool_name == "osys_validate_class_template":
        plugin._require_permission("allow_manage_classes", "Class management tools are disabled")
        class_name = (args.get("class_name") or "").strip()
        template = str(args.get("template") or "")
        object_name = (args.get("object_name") or "").strip() or None
        if not class_name:
            raise ValueError("class_name is required")
        if not template:
            raise ValueError("template is required")
        validate_only = bool(args.get("validate_only", False))
        data = plugin._validate_class_template(class_name, template, object_name, validate_only=validate_only)
        return plugin._tool_result(data)
    if tool_name == "osys_render_class_template":
        plugin._require_permission("allow_manage_classes", "Class management tools are disabled")
        class_name = (args.get("class_name") or "").strip()
        template = str(args.get("template") or "")
        object_name = (args.get("object_name") or "").strip() or None
        if not class_name:
            raise ValueError("class_name is required")
        if not template:
            raise ValueError("template is required")
        data = plugin._validate_class_template(class_name, template, object_name, validate_only=False)
        return plugin._tool_result(data)
    if tool_name == "osys_validate_object_template":
        object_name = (args.get("object_name") or "").strip()
        template = str(args.get("template") or "")
        validate_only = bool(args.get("validate_only", False))
        if not object_name:
            raise ValueError("object_name is required")
        if not template:
            raise ValueError("template is required")
        data = plugin._validate_object_template(object_name, template, validate_only=validate_only)
        return plugin._tool_result(data)
    if tool_name == "osys_render_object_template":
        object_name = (args.get("object_name") or "").strip()
        template_raw = args.get("template")
        if not object_name:
            raise ValueError("object_name is required")
        template = str(template_raw or "") if template_raw is not None else None
        data = plugin._render_object_template(object_name, template=template)
        return plugin._tool_result(data)
    return None


def get_tool_schemas(_: Dict[str, Any]) -> list[dict]:
    return [
        {
            "name": "osys_add_class",
            "description": "Create or update a class",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "description": {"type": "string"},
                    "parent_id": {"type": "integer"},
                    "template": {"type": "string"},
                    "update": {"type": "boolean"},
                },
                "required": ["class_name"],
            },
        },
        {
            "name": "osys_update_class",
            "description": "Update existing class metadata (patch semantics: only explicitly provided fields are changed)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "description": {"type": "string"},
                    "parent_id": {"type": "integer"},
                    "template": {"type": "string"},
                    "if_match": {"type": "string"},
                },
                "required": ["class_name"],
            },
        },
        {
            "name": "osys_delete_class",
            "description": "Delete class only when it has no child classes and no objects",
            "inputSchema": {"type": "object", "properties": {"class_name": {"type": "string"}}, "required": ["class_name"]},
        },
        {
            "name": "osys_get_class",
            "description": "Get class details by name (including template)",
            "inputSchema": {"type": "object", "properties": {"class_name": {"type": "string"}}, "required": ["class_name"]},
        },
        {
            "name": "osys_list_classes",
            "description": "List classes with id/name/parent_id",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 5000},
                },
            },
        },
        {
            "name": "osys_get_class_tree",
            "description": "Get class inheritance tree",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "root_class_name": {"type": "string"},
                    "max_depth": {"type": "integer", "minimum": 1, "maximum": 1000},
                    "include_templates": {"type": "boolean"},
                },
            },
        },
        {
            "name": "osys_get_class_full",
            "description": "Get class with inherited + own properties/methods including params",
            "inputSchema": {"type": "object", "properties": {"class_name": {"type": "string"}}, "required": ["class_name"]},
        },
        {
            "name": "osys_get_template_spec",
            "description": "Get explicit template engine/context specification",
            "inputSchema": {"type": "object", "properties": {"engine": {"type": "string"}}},
        },
        {
            "name": "osys_validate_class_template",
            "description": "Validate class template and optionally render preview",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "template": {"type": "string"},
                    "object_name": {"type": "string"},
                    "validate_only": {"type": "boolean"},
                },
                "required": ["class_name", "template"],
            },
        },
        {
            "name": "osys_render_class_template",
            "description": "Render class template preview for an object",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "template": {"type": "string"},
                    "object_name": {"type": "string"},
                },
                "required": ["class_name", "template"],
            },
        },
        {
            "name": "osys_validate_object_template",
            "description": "Validate object template and optionally render preview",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "template": {"type": "string"},
                    "validate_only": {"type": "boolean"},
                },
                "required": ["object_name", "template"],
            },
        },
        {
            "name": "osys_render_object_template",
            "description": "Render object template preview (argument template or effective saved template)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "template": {"type": "string"},
                },
                "required": ["object_name"],
            },
        },
    ]
