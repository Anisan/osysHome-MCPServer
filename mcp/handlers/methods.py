"""Method-related handler group for MCPServer tools."""
# pylint: disable=protected-access

from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.lib.object import addClassMethod, addObjectMethod, deleteClassMethod
from plugins.MCPServer.core import utils as mcp_utils


def _resolve_method_params(
    args: dict,
    existing: Optional[dict],
    *,
    update_mode: bool,
    merge_params: bool = True,
) -> Optional[Dict[str, Any]]:
    """Return params dict to pass to add*Method, or None to leave unchanged in DB."""
    params_patch = args.get("params")
    if params_patch is not None and not isinstance(params_patch, dict):
        raise ValueError("params must be an object")
    existing_params = (existing or {}).get("params") or {}
    if not isinstance(existing_params, dict):
        existing_params = {}

    if params_patch is None:
        if update_mode and existing is not None:
            return existing_params
        return None

    if update_mode and merge_params:
        params_arg = dict(existing_params)
        params_arg.update(params_patch)
    else:
        params_arg = params_patch
    mcp_utils.validate_method_params(params_arg)
    return params_arg


def _apply_method_params_kwarg(method_kwargs: Dict[str, Any], params: Optional[Dict[str, Any]]) -> None:
    if params is not None:
        method_kwargs["params"] = params


def handle_method_tools(plugin, tool_name: str, args: dict) -> Optional[dict]:
    if tool_name == "osys_get_class_method_code":
        plugin._require_permission("allow_manage_methods", "Method management tools are disabled")
        class_name = (args.get("class_name") or "").strip()
        name = (args.get("name") or "").strip()
        if not class_name or not name:
            raise ValueError("class_name and name are required")
        rec = plugin._get_class_method_record(class_name, name)
        if rec is None:
            raise ValueError(f"Class method not found: {class_name}.{name}")
        payload = {
            "scope": "class",
            "class_name": class_name,
            "name": name,
            "description": rec.get("description") or "",
            "call_parent": rec.get("call_parent"),
            "params": rec.get("params") or {},
            "has_code": bool(rec.get("code")),
            "code": rec.get("code") or "",
            "method_runtime_spec_uri": "osys://method-runtime/spec",
            "revision": plugin._revision_for_payload(rec),
        }
        return plugin._tool_result(payload)
    if tool_name == "osys_get_object_method_code":
        plugin._require_permission("allow_manage_methods", "Method management tools are disabled")
        object_name = (args.get("object_name") or "").strip()
        name = (args.get("name") or "").strip()
        if not object_name or not name:
            raise ValueError("object_name and name are required")
        rec = plugin._get_object_method_record(object_name, name)
        if rec is None:
            raise ValueError(f"Object method not found: {object_name}.{name}")
        payload = {
            "scope": "object",
            "object_name": object_name,
            "name": name,
            "description": rec.get("description") or "",
            "call_parent": rec.get("call_parent"),
            "params": rec.get("params") or {},
            "has_code": bool(rec.get("code")),
            "code": rec.get("code") or "",
            "method_runtime_spec_uri": "osys://method-runtime/spec",
            "revision": plugin._revision_for_payload(rec),
        }
        return plugin._tool_result(payload)
    if tool_name == "osys_add_class_method":
        plugin._require_permission("allow_manage_methods", "Method management tools are disabled")
        class_name = (args.get("class_name") or "").strip()
        name = (args.get("name") or "").strip()
        if not class_name or not name:
            raise ValueError("class_name and name are required")
        prepared_code, normalized = plugin._prepare_exec_method_code(
            args.get("code"),
            args.get("code_mode"),
        )
        update_mode = bool(args.get("update", False))
        existing = plugin._get_class_method_record(class_name, name) if update_mode else None
        method_kwargs: Dict[str, Any] = {
            "name": name,
            "class_name": class_name,
            "update": update_mode,
        }
        if "description" in args:
            method_kwargs["description"] = plugin._safe_text_arg(args, "description")
        if "code" in args or not update_mode:
            method_kwargs["code"] = prepared_code
        if "call_parent" in args or not update_mode:
            method_kwargs["call_parent"] = plugin._safe_int(args.get("call_parent"), 0, -1, 1)
        params = _resolve_method_params(args, existing, update_mode=update_mode, merge_params=False)
        _apply_method_params_kwarg(method_kwargs, params)
        method = addClassMethod(**method_kwargs)
        if method is not None:
            plugin._reload_objects_by_class_name(class_name)
        return plugin._tool_result(
            {
                "ok": method is not None,
                "method_id": plugin._safe_model_id(method),
                "normalized_from_function_wrapper": normalized,
            }
        )
    if tool_name == "osys_update_class_method":
        plugin._require_permission("allow_manage_methods", "Method management tools are disabled")
        class_name = (args.get("class_name") or "").strip()
        name = (args.get("name") or "").strip()
        if not class_name or not name:
            raise ValueError("class_name and name are required")
        existing = plugin._get_class_method_record(class_name, name)
        if existing is None:
            raise ValueError(f"Class method not found: {class_name}.{name}")
        plugin._enforce_if_match((args.get("if_match") or "").strip() or None, plugin._revision_for_payload(existing))
        normalized = False
        if "code" in args:
            prepared_code, normalized = plugin._prepare_exec_method_code(
                args.get("code"),
                args.get("code_mode"),
            )
        else:
            prepared_code = str(existing.get("code") or "")
        description = (
            plugin._safe_text_arg(args, "description")
            if "description" in args
            else str(existing.get("description") or "")
        )
        merge_params = bool(args.get("merge_params", True))
        params = _resolve_method_params(args, existing, update_mode=True, merge_params=merge_params)
        method_kwargs: Dict[str, Any] = {
            "name": name,
            "class_name": class_name,
            "description": description,
            "code": prepared_code,
            "call_parent": plugin._safe_int(args.get("call_parent"), int(existing.get("call_parent") or 0), -1, 1),
            "update": True,
        }
        _apply_method_params_kwarg(method_kwargs, params)
        method = addClassMethod(**method_kwargs)
        if method is not None:
            plugin._reload_objects_by_class_name(class_name)
        updated = plugin._get_class_method_record(class_name, name)
        return plugin._tool_result(
            {
                "ok": method is not None,
                "method_id": plugin._safe_model_id(method),
                "normalized_from_function_wrapper": normalized,
                "revision": plugin._revision_for_payload(updated or {}),
            }
        )
    if tool_name == "osys_delete_class_method":
        plugin._require_permission("allow_manage_methods", "Method management tools are disabled")
        class_name = (args.get("class_name") or "").strip()
        method_name = (args.get("method_name") or "").strip()
        if not class_name or not method_name:
            raise ValueError("class_name and method_name are required")
        existing = plugin._get_class_method_record(class_name, method_name)
        if existing is None:
            raise ValueError(f"Class method not found: {class_name}.{method_name}")
        plugin._enforce_if_match((args.get("if_match") or "").strip() or None, plugin._revision_for_payload(existing))
        success = deleteClassMethod(f"{class_name}.{method_name}")
        if not success:
            raise ValueError(f"Failed to delete class method: {class_name}.{method_name}")
        plugin._reload_objects_by_class_name(class_name)
        return plugin._tool_result({"ok": True, "deleted_method": f"{class_name}.{method_name}"})
    if tool_name == "osys_add_object_method":
        plugin._require_permission("allow_manage_methods", "Method management tools are disabled")
        object_name = (args.get("object_name") or "").strip()
        name = (args.get("name") or "").strip()
        if not object_name or not name:
            raise ValueError("object_name and name are required")
        prepared_code, normalized = plugin._prepare_exec_method_code(
            args.get("code"),
            args.get("code_mode"),
        )
        update_mode = bool(args.get("update", False))
        existing = plugin._get_object_method_record(object_name, name) if update_mode else None
        method_kwargs: Dict[str, Any] = {
            "name": name,
            "object_name": object_name,
            "update": update_mode,
        }
        if "description" in args:
            method_kwargs["description"] = plugin._safe_text_arg(args, "description")
        if "code" in args or not update_mode:
            method_kwargs["code"] = prepared_code
        if "call_parent" in args or not update_mode:
            method_kwargs["call_parent"] = plugin._safe_int(args.get("call_parent"), 0, -1, 1)
        params = _resolve_method_params(args, existing, update_mode=update_mode, merge_params=False)
        _apply_method_params_kwarg(method_kwargs, params)
        success = addObjectMethod(**method_kwargs)
        if success:
            plugin._reload_object_by_name(object_name)
        return plugin._tool_result(
            {
                "ok": bool(success),
                "method": f"{object_name}.{name}",
                "normalized_from_function_wrapper": normalized,
            }
        )
    if tool_name == "osys_update_object_method":
        plugin._require_permission("allow_manage_methods", "Method management tools are disabled")
        object_name = (args.get("object_name") or "").strip()
        name = (args.get("name") or "").strip()
        if not object_name or not name:
            raise ValueError("object_name and name are required")
        existing = plugin._get_object_method_record(object_name, name)
        if existing is None:
            inherited = plugin._get_inherited_class_method_for_object(object_name, name)
            if inherited is not None:
                raise ValueError(
                    f"Object method not found: {object_name}.{name}. "
                    f"Method exists in class '{inherited.get('class_name')}'. "
                    "Use osys_update_class_method or create object override via osys_add_object_method(update=true)."
                )
            raise ValueError(f"Object method not found: {object_name}.{name}")
        plugin._enforce_if_match((args.get("if_match") or "").strip() or None, plugin._revision_for_payload(existing))
        normalized = False
        if "code" in args:
            prepared_code, normalized = plugin._prepare_exec_method_code(
                args.get("code"),
                args.get("code_mode"),
            )
        else:
            prepared_code = str(existing.get("code") or "")
        description = (
            plugin._safe_text_arg(args, "description")
            if "description" in args
            else str(existing.get("description") or "")
        )
        merge_params = bool(args.get("merge_params", True))
        params = _resolve_method_params(args, existing, update_mode=True, merge_params=merge_params)
        method_kwargs: Dict[str, Any] = {
            "name": name,
            "object_name": object_name,
            "description": description,
            "code": prepared_code,
            "call_parent": plugin._safe_int(args.get("call_parent"), int(existing.get("call_parent") or 0), -1, 1),
            "update": True,
        }
        _apply_method_params_kwarg(method_kwargs, params)
        success = addObjectMethod(**method_kwargs)
        if success:
            plugin._reload_object_by_name(object_name)
        updated = plugin._get_object_method_record(object_name, name)
        return plugin._tool_result(
            {
                "ok": bool(success),
                "method": f"{object_name}.{name}",
                "normalized_from_function_wrapper": normalized,
                "revision": plugin._revision_for_payload(updated or {}),
            }
        )
    return None


def get_tool_schemas(_: Dict[str, Any]) -> list[dict]:
    method_params_schema = mcp_utils.method_params_schema()
    return [
        {
            "name": "osys_get_class_method_code",
            "description": "Get class method source code and metadata",
            "inputSchema": {
                "type": "object",
                "properties": {"class_name": {"type": "string"}, "name": {"type": "string"}},
                "required": ["class_name", "name"],
            },
        },
        {
            "name": "osys_get_object_method_code",
            "description": "Get object method source code and metadata",
            "inputSchema": {
                "type": "object",
                "properties": {"object_name": {"type": "string"}, "name": {"type": "string"}},
                "required": ["object_name", "name"],
            },
        },
        {
            "name": "osys_add_class_method",
            "description": "Create or update a class method (optional display params: icon, color, sort_order)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "code": {"type": "string"},
                    "code_mode": {"type": "string"},
                    "call_parent": {"type": "integer"},
                    "params": method_params_schema,
                    "update": {"type": "boolean"},
                },
                "required": ["class_name", "name"],
            },
        },
        {
            "name": "osys_update_class_method",
            "description": "Update class method (patch semantics: unspecified fields are left unchanged)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "code": {"type": "string"},
                    "code_mode": {"type": "string"},
                    "call_parent": {"type": "integer"},
                    "params": method_params_schema,
                    "merge_params": {"type": "boolean"},
                    "if_match": {"type": "string"},
                },
                "required": ["class_name", "name"],
            },
        },
        {
            "name": "osys_delete_class_method",
            "description": "Delete class method",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "class_name": {"type": "string"},
                    "method_name": {"type": "string"},
                    "if_match": {"type": "string"},
                },
                "required": ["class_name", "method_name"],
            },
        },
        {
            "name": "osys_add_object_method",
            "description": "Create or update an object method with code (optional display params: icon, color, sort_order)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "code": {"type": "string"},
                    "code_mode": {"type": "string"},
                    "call_parent": {"type": "integer"},
                    "params": method_params_schema,
                    "update": {"type": "boolean"},
                },
                "required": ["object_name", "name"],
            },
        },
        {
            "name": "osys_update_object_method",
            "description": "Update object method with code (patch semantics: unspecified fields are left unchanged)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "code": {"type": "string"},
                    "code_mode": {"type": "string"},
                    "call_parent": {"type": "integer"},
                    "params": method_params_schema,
                    "merge_params": {"type": "boolean"},
                    "if_match": {"type": "string"},
                },
                "required": ["object_name", "name"],
            },
        },
    ]
