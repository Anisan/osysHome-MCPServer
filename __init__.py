"""MCPServer plugin - exposes a small MCP endpoint over HTTP JSON-RPC."""

from __future__ import annotations

import hmac
import json
import re
import textwrap
import ast
import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from flask import jsonify, render_template, request
from jinja2 import Environment, TemplateSyntaxError, meta

from app.core.main.BasePlugin import BasePlugin
from app.core.lib.constants import PropertyType
from app.logging_config import security_audit_log
from app.core.lib.object import (
    addClass,
    addClassMethod,
    addClassProperty,
    addObject,
    addObjectMethod,
    addObjectProperty,
    callMethod,
    deleteObject,
    deleteObjectMethod,
    deleteObjectProperty,
    getObject,
    getHistory,
    getHistoryAggregate,
    getProperty,
    setLinkToObject,
    setProperty,
)
from app.core.models.Clasess import Class, Method, Object, Property
from app.core.main.ObjectsStorage import objects_storage
from app.database import session_scope
from plugins.MCPServer.mcp.handlers.common import tools_call as dispatch_tools_call
from plugins.MCPServer.mcp.logging_support import (
    log_rpc_error,
    log_rpc_exception,
    log_rpc_request,
    log_rpc_result,
)
from plugins.MCPServer.mcp.handlers.plugins import (
    get_plugin_mcp_tools_catalog_entry,
    list_mcp_capable_plugins,
)
from plugins.MCPServer.mcp.permissions import (
    DEFAULT_ACCESS_CONFIG_KEY,
    get_permission_category_catalog,
)
from plugins.MCPServer.mcp import resources as mcp_resources
from plugins.MCPServer.mcp.tools_schema import build_tools_schema
from plugins.MCPServer.core import repository as mcp_repository
from plugins.MCPServer.core import utils as mcp_utils


class MCPServer(BasePlugin):
    """Model Context Protocol server as a platform plugin."""

    _PROTOCOL_VERSION = "2024-11-05"

    def __init__(self, app):
        super().__init__(app, __name__)
        self.title = "MCP Server"
        self.description = "Model Context Protocol endpoint for osysHome"
        self.category = "System"
        self.version = 1

        changed = False
        defaults = {
            "auth_token": "",
            "allow_write_tools": False,
            "allow_method_calls": True,
            "allow_logs_access": False,
            "allow_source_access": False,
            "allow_class_introspection": False,
            "allow_manage_classes": False,
            "allow_manage_objects": False,
            "allow_manage_properties": False,
            "allow_manage_methods": False,
            "allow_read_plugins": True,
            "allow_manage_plugins": False,
            "plugins_allowed": [],
            "max_list_items": 200,
        }
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value
                changed = True
        # Migrate legacy documentation access flag to plugin whitelist.
        if bool(self.config.pop("allow_docs_access", False)):
            allowed = list(self.config.get("plugins_allowed") or [])
            if "Docs" not in allowed:
                allowed.append("Docs")
                self.config["plugins_allowed"] = allowed
            changed = True
        if "allow_docs_access" in self.config:
            self.config.pop("allow_docs_access", None)
            changed = True
        # Backward compatibility: old per-source docs whitelist (no longer used).
        if "docs_allowed_sources" in self.config:
            self.config.pop("docs_allowed_sources", None)
            changed = True
        # Backward compatibility: old configs with class management enabled
        # should keep read-only class introspection available after upgrade.
        if "allow_class_introspection" not in self.config and bool(self.config.get("allow_manage_classes", False)):
            self.config["allow_class_introspection"] = True
            changed = True
        if changed:
            self.saveConfig()

    def initialization(self):
        self.logger.info(
            "MCP Server started endpoint=/api/mcp version=%s auth=%s",
            self.version,
            "enabled" if bool(self.config.get("auth_token", "").strip()) else "disabled",
        )

    def route_admin_plugin_tools(self):
        from app.authentication.handlers import handle_admin_required

        @self.blueprint.route(
            "/admin/MCPServer/api/plugin-tools/<plugin_name>",
            methods=["GET"],
        )
        @handle_admin_required
        def admin_plugin_tools(plugin_name: str):
            entry = get_plugin_mcp_tools_catalog_entry(self, plugin_name)
            if entry is None:
                return jsonify(
                    {
                        "ok": False,
                        "error": f"Plugin not found or MCP is not supported: {plugin_name}",
                    }
                ), 404
            return jsonify(
                {
                    "ok": True,
                    "entry": entry,
                    "html": render_template(
                        "mcp_plugin_tools_body.html",
                        plugin_entry=entry,
                    ),
                }
            )

    def route_admin_permission_category(self):
        from app.authentication.handlers import handle_admin_required

        @self.blueprint.route(
            "/admin/MCPServer/api/permission-category/<config_key>",
            methods=["GET"],
        )
        @handle_admin_required
        def admin_permission_category(config_key: str):
            category = get_permission_category_catalog(self, config_key)
            if category is None:
                return jsonify(
                    {
                        "ok": False,
                        "error": f"Unknown permission category: {config_key}",
                    }
                ), 404
            return jsonify(
                {
                    "ok": True,
                    "category": category,
                    "html": render_template(
                        "mcp_permission_category_body.html",
                        category=category,
                    ),
                }
            )

    def admin(self, request):
        if request.method == "POST":
            clear_auth_token = request.form.get("clear_auth_token") == "on"
            entered_token = request.form.get("auth_token", "").strip()
            if clear_auth_token:
                self.config["auth_token"] = ""
            elif entered_token:
                self.config["auth_token"] = entered_token
            self.config["allow_write_tools"] = request.form.get("allow_write_tools") == "on"
            self.config["allow_method_calls"] = request.form.get("allow_method_calls") == "on"
            self.config["allow_logs_access"] = request.form.get("allow_logs_access") == "on"
            self.config["allow_source_access"] = request.form.get("allow_source_access") == "on"
            self.config["allow_class_introspection"] = request.form.get("allow_class_introspection") == "on"
            self.config["allow_manage_classes"] = request.form.get("allow_manage_classes") == "on"
            self.config["allow_manage_objects"] = request.form.get("allow_manage_objects") == "on"
            self.config["allow_manage_properties"] = request.form.get("allow_manage_properties") == "on"
            self.config["allow_manage_methods"] = request.form.get("allow_manage_methods") == "on"
            self.config["allow_read_plugins"] = request.form.get("allow_read_plugins") == "on"
            self.config["allow_manage_plugins"] = request.form.get("allow_manage_plugins") == "on"
            selected_plugins = [
                item.strip()
                for item in request.form.getlist("plugins_allowed_selected")
                if item.strip()
            ]
            self.config["plugins_allowed"] = selected_plugins
            self.config["max_list_items"] = self._safe_int(request.form.get("max_list_items"), 200, 1, 5000)
            self.saveConfig()

        endpoint = "/api/mcp"
        content = {
            "endpoint": endpoint,
            "auth_enabled": bool(self.config.get("auth_token", "").strip()),
            "allow_write_tools": bool(self.config.get("allow_write_tools", False)),
            "allow_method_calls": bool(self.config.get("allow_method_calls", True)),
            "allow_logs_access": bool(self.config.get("allow_logs_access", False)),
            "allow_source_access": bool(self.config.get("allow_source_access", False)),
            "allow_class_introspection": bool(self.config.get("allow_class_introspection", False)),
            "allow_manage_classes": bool(self.config.get("allow_manage_classes", False)),
            "allow_manage_objects": bool(self.config.get("allow_manage_objects", False)),
            "allow_manage_properties": bool(self.config.get("allow_manage_properties", False)),
            "allow_manage_methods": bool(self.config.get("allow_manage_methods", False)),
            "allow_read_plugins": bool(self.config.get("allow_read_plugins", True)),
            "allow_manage_plugins": bool(self.config.get("allow_manage_plugins", False)),
            "plugins_allowed": self.config.get("plugins_allowed") or [],
            "mcp_plugin_options": list_mcp_capable_plugins(),
            "max_list_items": int(self.config.get("max_list_items", 200)),
            "mcp_default_access": get_permission_category_catalog(self, DEFAULT_ACCESS_CONFIG_KEY),
        }
        return render_template("mcp_admin.html", **content)

    def route_mcp(self):
        from app.authentication.handlers import public_endpoint

        @self.blueprint.route("/api/mcp", methods=["GET", "POST"])
        @public_endpoint
        def mcp_endpoint():
            if request.method == "GET":
                return jsonify(
                    {
                        "name": "osysHome",
                        "protocolVersion": self._PROTOCOL_VERSION,
                        "endpoint": "/api/mcp",
                        "authRequired": True,
                        "authConfigured": bool(self.config.get("auth_token", "").strip()),
                    }
                )

            if not self._is_authorized(request):
                self.logger.warning(
                    "unauthorized request ip=%s reason=%s",
                    self._get_client_ip(request),
                    self._mcp_auth_failure_reason(request),
                )
                security_audit_log(
                    "MCP_UNAUTHORIZED",
                    ip=self._get_client_ip(request),
                    url=request.url,
                    endpoint="/api/mcp",
                    reason=self._mcp_auth_failure_reason(request),
                    user_agent=request.headers.get("User-Agent", ""),
                    method=request.method,
                )
                return jsonify({"error": "Unauthorized"}), 401

            payload = request.get_json(silent=True)
            if payload is None:
                self.logger.warning(
                    "invalid JSON payload ip=%s",
                    self._get_client_ip(request),
                )
                return jsonify({"error": "Invalid JSON payload"}), 400

            if isinstance(payload, list):
                responses = []
                for item in payload:
                    response = self._handle_rpc_request(item)
                    if response is not None:
                        responses.append(response)
                if not responses:
                    return ("", 204)
                return jsonify(responses)

            response = self._handle_rpc_request(payload)
            if response is None:
                return ("", 204)
            return jsonify(response)

    def _handle_rpc_request(self, req_data: dict) -> Optional[dict]:
        req_id = req_data.get("id")
        method = req_data.get("method")
        params = req_data.get("params", {})

        if not isinstance(req_data, dict) or not method:
            log_rpc_error(self.logger, str(method or "?"), req_id, -32600, "Invalid Request")
            return self._rpc_error(req_id, -32600, "Invalid Request")

        log_rpc_request(self.logger, str(method), req_id)

        try:
            result = self._dispatch_method(method, params)
            if req_id is None:
                return None
            summary = self._rpc_result_summary(str(method), result, params)
            log_rpc_result(self.logger, str(method), req_id, summary=summary)
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except ValueError as ex:
            log_rpc_error(self.logger, str(method), req_id, -32602, str(ex))
            return self._rpc_error(req_id, -32602, str(ex))
        except NotImplementedError as ex:
            log_rpc_error(self.logger, str(method), req_id, -32601, str(ex))
            return self._rpc_error(req_id, -32601, str(ex))
        except PermissionError as ex:
            log_rpc_error(self.logger, str(method), req_id, -32001, str(ex))
            return self._rpc_error(req_id, -32001, str(ex))
        except Exception as ex:
            log_rpc_exception(self.logger, str(method), req_id, ex)
            return self._rpc_error(req_id, -32000, str(ex))

    @staticmethod
    def _rpc_result_summary(method: str, result: dict, params: Optional[dict] = None) -> Optional[str]:
        if method == "tools/list" and isinstance(result, dict):
            tools = result.get("tools") or []
            return f"tools={len(tools)}"
        if method == "tools/call":
            tool_name = str((params or {}).get("name") or "?")
            return f"tool={tool_name}"
        if method == "resources/list" and isinstance(result, dict):
            resources = result.get("resources") or []
            return f"resources={len(resources)}"
        if method == "prompts/list" and isinstance(result, dict):
            prompts = result.get("prompts") or []
            return f"prompts={len(prompts)}"
        return None

    def _dispatch_method(self, method: str, params: dict) -> dict:
        if method == "initialize":
            from plugins.MCPServer.mcp.agent_guidelines import get_agent_guidelines

            return {
                "protocolVersion": self._PROTOCOL_VERSION,
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                "serverInfo": {"name": "osysHome MCP Server", "version": str(self.version)},
                "instructions": get_agent_guidelines(self),
            }
        if method == "ping":
            return {}
        if method == "notifications/initialized":
            return {}
        if method == "tools/list":
            return {"tools": self._tools_schema()}
        if method == "tools/call":
            return self._tools_call(params)
        if method == "resources/list":
            return {"resources": self._resources_list(params)}
        if method == "resources/read":
            return self._resources_read(params)
        if method == "prompts/list":
            return {"prompts": self._prompts_list()}
        if method == "prompts/get":
            return self._prompts_get(params)
        raise NotImplementedError(f"Method not found: {method}")

    def _tools_schema(self) -> List[dict]:
        from plugins.MCPServer.mcp.permissions import filter_tool_schemas

        schemas = build_tools_schema(self._property_params_schema())
        return filter_tool_schemas(self, schemas)

    def _tools_call(self, params: dict) -> dict:
        return dispatch_tools_call(self, params)

    def _tool_list_objects(self, args: dict) -> dict:
        query = (args.get("query") or "").strip().lower()
        max_items = int(self.config.get("max_list_items", 200))
        limit = self._safe_int(args.get("limit"), max_items, 1, 5000)
        limit = min(limit, max_items)

        rows = []
        with session_scope() as session:
            q = session.query(Object).order_by(Object.name)
            if query:
                q = q.filter(Object.name.ilike(f"%{query}%"))
            for row in q.limit(limit).all():
                rows.append(
                    {
                        "name": row.name,
                        "description": row.description or "",
                    }
                )
        return {"count": len(rows), "items": rows}

    def _resources_list(self, params: dict) -> List[dict]:
        return mcp_resources.resources_list(self, params)

    def _resources_read(self, params: dict) -> dict:
        return mcp_resources.resources_read(self, params)

    def _read_resource_uri(self, uri: str) -> Tuple[str, str]:
        return mcp_resources.read_resource_uri(self, uri)

    def _prompts_list(self) -> List[dict]:
        return mcp_resources.prompts_list(self)

    def _prompts_get(self, params: dict) -> dict:
        return mcp_resources.prompts_get(self, params)

    @staticmethod
    def _method_runtime_context_payload() -> dict:
        return mcp_utils.method_runtime_context_payload()

    @staticmethod
    def _method_runtime_symbols_payload() -> dict:
        return mcp_utils.method_runtime_symbols_payload()

    @staticmethod
    def _rpc_error(req_id: Any, code: int, message: str) -> dict:
        return mcp_utils.rpc_error(req_id, code, message)

    @staticmethod
    def _safe_model_id(value: Any) -> Any:
        return mcp_utils.safe_model_id(value)

    @staticmethod
    def _safe_int(value: Any, default: int, min_value: int, max_value: int) -> int:
        return mcp_utils.safe_int(value, default, min_value, max_value)

    @staticmethod
    def _parse_optional_datetime(value: Any, field_name: str) -> Optional[datetime]:
        return mcp_utils.parse_optional_datetime(value, field_name)

    @staticmethod
    def _looks_like_broken_cyrillic(text: str) -> bool:
        return mcp_utils.looks_like_broken_cyrillic(text)

    def _safe_text_arg(self, args: dict, key: str) -> str:
        return mcp_utils.safe_text_arg(args, key)

    @staticmethod
    def _parse_property_type(value: Any) -> PropertyType:
        return mcp_utils.parse_property_type(value)

    def _require_permission(self, config_key: str, error_message: str) -> None:
        if not self.config.get(config_key, False):
            raise PermissionError(error_message)

    def _require_any_permission(self, config_keys: List[str], error_message: str) -> None:
        for key in config_keys:
            if self.config.get(key, False):
                return
        raise PermissionError(error_message)

    @staticmethod
    def _set_class_template(class_name: str, template: str) -> Dict[str, Any]:
        return mcp_repository.set_class_template(class_name, template)

    @staticmethod
    def _get_class_record(class_name: str) -> Optional[Dict[str, Any]]:
        return mcp_repository.get_class_record(class_name)

    def _reload_objects_by_class_name(self, class_name: str) -> None:
        class_name = (class_name or "").strip()
        if not class_name:
            return
        rec = self._get_class_record(class_name)
        if rec is None:
            return
        class_id = rec.get("id")
        if class_id is None:
            return
        try:
            objects_storage.reload_objects_by_class(int(class_id))
        except Exception as ex:
            self.logger.exception("Failed to reload objects cache for class '%s': %s", class_name, ex)

    def _reload_object_by_name(self, object_name: str) -> None:
        object_name = (object_name or "").strip()
        if not object_name:
            return
        rec = self._get_object_record(object_name)
        if rec is None:
            return
        object_id = rec.get("id")
        if object_id is None:
            return
        try:
            objects_storage.reload_object(int(object_id))
        except Exception as ex:
            self.logger.exception("Failed to reload object cache for '%s': %s", object_name, ex)

    @staticmethod
    def _default_object_template() -> str:
        return mcp_repository.default_object_template()

    @staticmethod
    def _resolve_template_source(object_template: Any, class_template: Any) -> Tuple[str, str]:
        return mcp_repository.resolve_template_source(object_template, class_template)

    @staticmethod
    def _get_object_record(object_name: str) -> Optional[Dict[str, Any]]:
        return mcp_repository.get_object_record(object_name)

    @staticmethod
    def _get_class_method_record(class_name: str, method_name: str) -> Optional[Dict[str, Any]]:
        return mcp_repository.get_class_method_record(class_name, method_name)

    @staticmethod
    def _get_class_property_record(class_name: str, property_name: str) -> Optional[Dict[str, Any]]:
        return mcp_repository.get_class_property_record(class_name, property_name)

    @staticmethod
    def _get_object_property_record(object_name: str, property_name: str) -> Optional[Dict[str, Any]]:
        return mcp_repository.get_object_property_record(object_name, property_name)

    @staticmethod
    def _get_inherited_class_method_for_object(object_name: str, method_name: str) -> Optional[Dict[str, Any]]:
        return mcp_repository.get_inherited_class_method_for_object(object_name, method_name)

    @staticmethod
    def _parse_json_object(raw_value: Any) -> Dict[str, Any]:
        return mcp_utils.parse_json_object(raw_value)

    @staticmethod
    def _property_params_schema() -> Dict[str, Any]:
        return mcp_utils.property_params_schema()

    @staticmethod
    def _validate_property_params(params: Dict[str, Any]) -> None:
        mcp_utils.validate_property_params(params)

    @staticmethod
    def _method_params_schema() -> Dict[str, Any]:
        return mcp_utils.method_params_schema()

    @staticmethod
    def _validate_method_params(params: Dict[str, Any]) -> None:
        mcp_utils.validate_method_params(params)

    @staticmethod
    def _revision_for_payload(payload: Any) -> str:
        return mcp_utils.revision_for_payload(payload)

    @staticmethod
    def _enforce_if_match(if_match: Optional[str], current_revision: str) -> None:
        mcp_utils.enforce_if_match(if_match, current_revision)

    @staticmethod
    def _get_class_full_record(class_name: str) -> Optional[Dict[str, Any]]:
        return mcp_repository.get_class_full_record(class_name)

    @staticmethod
    def _get_object_method_record(object_name: str, method_name: str) -> Optional[Dict[str, Any]]:
        return mcp_repository.get_object_method_record(object_name, method_name)

    @staticmethod
    def _get_property_links(object_name: str, property_name: str) -> List[str]:
        return mcp_repository.get_property_links(object_name, property_name)

    @staticmethod
    def _restore_property_links(object_name: str, property_name: str, links_before: List[str]) -> None:
        mcp_repository.restore_property_links(object_name, property_name, links_before)

    @staticmethod
    def _get_template_spec(engine: str) -> Dict[str, Any]:
        engine_norm = (engine or "jinja2").strip().lower()
        if engine_norm != "jinja2":
            raise ValueError(f"Unsupported template engine: {engine_norm}")
        return {
            "engine": "jinja2",
            "variable_roots": ["object"],
            "required_prefix": "object.",
            "update_contract": {
                "rule": "Never overwrite any entity data that was not explicitly provided in update arguments.",
                "recommended_flow": [
                    "Read current entity and revision",
                    "Prepare minimal patch with only intended changes",
                    "Send update with if_match to avoid stale overwrite",
                ],
            },
            "notes": [
                "Templates are rendered with Jinja2",
                "Primary variable root is `object`",
                "Global helper `getProperty(name)` is also available",
                "For update tools, all unspecified data must be preserved (patch semantics)",
            ],
            "examples": [
                "{{ object.temp }}",
                "{{ object.pressure }}",
                "{{ object.status }}",
            ],
        }

    def _validate_class_template(
        self,
        class_name: str,
        template: str,
        object_name: Optional[str],
        validate_only: bool = False,
    ) -> Dict[str, Any]:
        class_rec = self._get_class_record(class_name)
        if class_rec is None:
            raise ValueError(f"Class not found: {class_name}")

        env = Environment()
        errors: List[str] = []
        undeclared: List[str] = []
        preview_html = ""
        selected_object = object_name

        try:
            ast_node = env.parse(template)
            undeclared = sorted(meta.find_undeclared_variables(ast_node))
        except Exception as ex:
            errors.append(f"Template parse error: {ex}")
            return {
                "ok": False,
                "class_name": class_name,
                "template_engine": "jinja2",
                "errors": errors,
                "resolved_vars": [],
                "preview_html": "",
            }

        if selected_object:
            obj = getObject(selected_object)
            if not obj:
                errors.append(f"Object not found: {selected_object}")
        else:
            with session_scope() as session:
                obj_row = (
                    session.query(Object)
                    .filter(Object.class_id == class_rec["id"])
                    .order_by(Object.name)
                    .first()
                )
                if obj_row:
                    selected_object = obj_row.name

        resolved_vars = [
            var
            for var in undeclared
            if var in {"object", "getProperty", "range", "len", "min", "max", "str", "int", "float", "bool"}
        ]
        unresolved_vars = [var for var in undeclared if var not in resolved_vars]
        if unresolved_vars:
            errors.append(
                "Undeclared variables outside allowed context: " + ", ".join(unresolved_vars)
            )

        if not validate_only and selected_object:
            obj = getObject(selected_object)
            if not obj:
                errors.append(f"Object not found: {selected_object}")
            else:
                try:
                    compiled = env.from_string(template)
                    preview_html = compiled.render(object=obj, getProperty=getProperty)
                except Exception as ex:
                    errors.append(f"Template render error: {ex}")

        return {
            "ok": len(errors) == 0,
            "class_name": class_name,
            "template_engine": "jinja2",
            "object_name": selected_object,
            "errors": errors,
            "resolved_vars": resolved_vars,
            "preview_html": preview_html,
        }

    @staticmethod
    def _format_template_error(ex: Exception, fallback_prefix: str) -> Dict[str, Any]:
        if isinstance(ex, TemplateSyntaxError):
            return {
                "message": f"{fallback_prefix}: {ex.message}",
                "line": int(getattr(ex, "lineno", 0) or 0) or None,
                "column": int(getattr(ex, "offset", 0) or 0) or None,
            }
        return {"message": f"{fallback_prefix}: {ex}", "line": None, "column": None}

    def _validate_object_template(
        self,
        object_name: str,
        template: str,
        validate_only: bool = False,
    ) -> Dict[str, Any]:
        rec = self._get_object_record(object_name)
        if rec is None:
            raise ValueError(f"Object not found: {object_name}")
        obj = getObject(object_name)
        if not obj:
            raise ValueError(f"Object not found: {object_name}")

        env = Environment()
        errors: List[Dict[str, Any]] = []
        undeclared: List[str] = []
        preview_html = ""

        try:
            ast_node = env.parse(template)
            undeclared = sorted(meta.find_undeclared_variables(ast_node))
        except Exception as ex:
            errors.append(self._format_template_error(ex, "Template parse error"))
            return {
                "ok": False,
                "object_name": object_name,
                "class_name": rec.get("class_name"),
                "template_engine": "jinja2",
                "template_source": "argument",
                "errors": errors,
                "resolved_vars": [],
                "preview_html": "",
            }

        allowed_roots = {"object", "getProperty", "range", "len", "min", "max", "str", "int", "float", "bool"}
        resolved_vars = [var for var in undeclared if var in allowed_roots]
        unresolved_vars = [var for var in undeclared if var not in allowed_roots]
        if unresolved_vars:
            errors.append(
                {
                    "message": "Undeclared variables outside allowed context: " + ", ".join(unresolved_vars),
                    "line": None,
                    "column": None,
                }
            )

        if not validate_only:
            try:
                compiled = env.from_string(template)
                preview_html = compiled.render(object=obj, getProperty=getProperty)
            except Exception as ex:
                errors.append(self._format_template_error(ex, "Template render error"))

        return {
            "ok": len(errors) == 0,
            "object_name": object_name,
            "class_name": rec.get("class_name"),
            "template_engine": "jinja2",
            "template_source": "argument",
            "errors": errors,
            "resolved_vars": resolved_vars,
            "preview_html": preview_html,
        }

    def _render_object_template(self, object_name: str, template: Optional[str] = None) -> Dict[str, Any]:
        rec = self._get_object_record(object_name)
        if rec is None:
            raise ValueError(f"Object not found: {object_name}")
        obj = getObject(object_name)
        if not obj:
            raise ValueError(f"Object not found: {object_name}")

        template_source = "argument"
        template_to_render = str(template or "") if template is not None else ""
        if template is None:
            template_to_render = str(rec.get("effective_template") or "")
            template_source = str(rec.get("effective_template_source") or "default")
        elif not template_to_render.strip():
            template_to_render = self._default_object_template()
            template_source = "default"

        env = Environment()
        errors: List[Dict[str, Any]] = []
        preview_html = ""
        try:
            compiled = env.from_string(template_to_render)
            preview_html = compiled.render(object=obj, getProperty=getProperty)
        except Exception as ex:
            errors.append(self._format_template_error(ex, "Template render error"))

        return {
            "ok": len(errors) == 0,
            "object_name": object_name,
            "class_name": rec.get("class_name"),
            "template_engine": "jinja2",
            "template_source": template_source,
            "errors": errors,
            "preview_html": preview_html,
        }

    @staticmethod
    def _validate_method_code_payload(code_value: Any, code_mode: Any = None) -> Dict[str, Any]:
        prepared_code, normalized = MCPServer._prepare_exec_method_code(code_value, code_mode)
        return {
            "ok": True,
            "normalized_from_function_wrapper": normalized,
            "normalized_code": prepared_code,
            "runtime_spec_uri": "osys://method-runtime/spec",
        }

    def _dry_run_method_code(
        self,
        code: Any,
        code_mode: Any = None,
        object_name: Optional[str] = None,
        params: Optional[dict] = None,
        source: str = "MCP:dry-run",
    ) -> Dict[str, Any]:
        prepared_code, normalized = self._prepare_exec_method_code(code, code_mode)
        params = params or {}

        obj = getObject(object_name) if object_name else None
        events: List[Dict[str, Any]] = []

        class DrySelfProxy:
            def __init__(self, target):
                self._target = target
                self.name = getattr(target, "name", object_name or "DryRunObject")

            def getProperty(self, prop_name):
                if self._target is not None:
                    prop = getattr(self._target, "properties", {}).get(prop_name)
                    if prop is not None:
                        try:
                            return prop.getValue()
                        except Exception:
                            pass
                full_name = f"{self.name}.{prop_name}"
                return getProperty(full_name)

        def get_property_stub(name):
            value = getProperty(name)
            events.append({"action": "getProperty", "name": name, "value": self._serialize_value(value)})
            return value

        def set_property_stub(name, value, source=""):
            events.append(
                {
                    "action": "setProperty",
                    "name": name,
                    "value": self._serialize_value(value),
                    "source": source,
                    "dry_run": True,
                }
            )
            return True

        def update_property_stub(name, value, source=""):
            events.append(
                {
                    "action": "updateProperty",
                    "name": name,
                    "value": self._serialize_value(value),
                    "source": source,
                    "dry_run": True,
                }
            )
            return True

        def call_method_stub(name, args=None, source=""):
            safe_args = args if isinstance(args, dict) else {}
            events.append(
                {
                    "action": "callMethod",
                    "name": name,
                    "args": self._serialize_value(safe_args),
                    "source": source,
                    "dry_run": True,
                }
            )
            return {"ok": True, "dry_run": True}

        safe_builtins = {
            "None": None,
            "True": True,
            "False": False,
            "bool": bool,
            "int": int,
            "float": float,
            "str": str,
            "len": len,
            "min": min,
            "max": max,
            "round": round,
            "abs": abs,
            "range": range,
            "isinstance": isinstance,
            "dict": dict,
            "list": list,
            "set": set,
            "tuple": tuple,
            "sum": sum,
            "sorted": sorted,
            "enumerate": enumerate,
            "Exception": Exception,
            "ValueError": ValueError,
            "TypeError": TypeError,
            "KeyError": KeyError,
            "RuntimeError": RuntimeError,
        }

        runtime = {
            "__builtins__": safe_builtins,
            "self": DrySelfProxy(obj),
            "params": params,
            "source": source,
            "logger": self.logger,
            "datetime": datetime,
            "timedelta": timedelta,
            "getProperty": get_property_stub,
            "setProperty": set_property_stub,
            "updateProperty": update_property_stub,
            "callMethod": call_method_stub,
        }

        try:
            exec(prepared_code, runtime, runtime)
            return {
                "ok": True,
                "object_name": object_name,
                "normalized_from_function_wrapper": normalized,
                "normalized_code": prepared_code,
                "captured_actions": events,
                "runtime_spec_uri": "osys://method-runtime/spec",
            }
        except Exception as ex:
            return {
                "ok": False,
                "object_name": object_name,
                "normalized_from_function_wrapper": normalized,
                "normalized_code": prepared_code,
                "captured_actions": events,
                "error": f"{type(ex).__name__}: {ex}",
                "runtime_spec_uri": "osys://method-runtime/spec",
            }

    @staticmethod
    def _prepare_exec_method_code(code_value: Any, code_mode: Any = None) -> Tuple[str, bool]:
        code = str(code_value or "")
        mode = (str(code_mode or "auto").strip().lower())
        if mode in ("raw", "as_is"):
            MCPServer._validate_exec_method_code(code)
            return code, False
        normalized = MCPServer._unwrap_single_function_wrapper(code)
        if normalized is None:
            MCPServer._validate_exec_method_code(code)
            return code, False
        MCPServer._validate_exec_method_code(normalized)
        return normalized, True

    @staticmethod
    def _unwrap_single_function_wrapper(code: str) -> Optional[str]:
        """
        If code looks like:
            [optional imports/comments]
            def some_method(self, ...):
                ...
        convert to exec-body format:
            [optional imports/comments]
            ...
        """
        lines = code.splitlines()
        if not lines:
            return None

        def_index = None
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("def "):
                def_index = idx
                break
            # first meaningful line is not def/import/comment -> no unwrap
            if not (stripped.startswith("import ") or stripped.startswith("from ") or stripped.startswith("#")):
                return None

        if def_index is None:
            return None

        def_line = lines[def_index]
        if not def_line.strip().endswith(":"):
            return None
        if not re.match(r"^\s*def\s+[A-Za-z_][A-Za-z0-9_]*\s*\(.*\)\s*:\s*$", def_line):
            return None

        prelude = lines[:def_index]
        body_lines = lines[def_index + 1 :]
        if not body_lines:
            return "\n".join(prelude).strip()

        # Remove one indentation level from function body.
        body = textwrap.dedent("\n".join(body_lines)).splitlines()

        # Keep body non-empty semantics.
        while body and not body[0].strip():
            body.pop(0)
        while body and not body[-1].strip():
            body.pop()

        out_lines = list(prelude)
        if out_lines and any(line.strip() for line in body):
            out_lines.append("")
        out_lines.extend(body)
        return "\n".join(out_lines).rstrip()

    @staticmethod
    def _validate_exec_method_code(code: str) -> None:
        """
        Methods in this platform are executed via exec as a plain code block.
        `return` is invalid at top level and leads to SyntaxError.
        """
        try:
            tree = ast.parse(code or "")
        except SyntaxError as ex:
            raise ValueError(f"Invalid Python code: {ex}") from ex

        class ReturnVisitor(ast.NodeVisitor):
            def __init__(self):
                self.has_return = False

            def visit_Return(self, node):
                self.has_return = True

        visitor = ReturnVisitor()
        visitor.visit(tree)
        if visitor.has_return:
            raise ValueError(
                "Method code must not contain 'return'. "
                "Code is executed via exec as a block."
            )

    def _is_authorized(self, req) -> bool:
        token = (self.config.get("auth_token") or "").strip()
        if not token:
            return False

        auth_header = req.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            incoming = auth_header[7:].strip()
        else:
            incoming = (req.headers.get("X-MCP-Token") or "").strip()
        if not incoming:
            return False
        return hmac.compare_digest(incoming, token)

    @staticmethod
    def _get_client_ip(req) -> str:
        xff = req.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip() or "?"
        return req.remote_addr or "?"

    def _mcp_auth_failure_reason(self, req) -> str:
        token = (self.config.get("auth_token") or "").strip()
        if not token:
            return "auth_not_configured"

        auth_header = req.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            incoming = auth_header[7:].strip()
            if not incoming:
                return "bearer_token_empty"
            return "token_mismatch"

        x_token = (req.headers.get("X-MCP-Token") or "").strip()
        if x_token:
            return "token_mismatch"
        if auth_header:
            return "authorization_not_bearer_and_x_token_missing"
        return "token_missing"

    @staticmethod
    def _tool_result(data: Any) -> dict:
        return mcp_utils.tool_result(data)

    def _serialize_object(self, obj) -> dict:
        properties = {}
        for name, prop in obj.properties.items():
            properties[name] = {
                "value": self._serialize_value(prop.getValue()),
                "type": prop.type,
                "description": prop.description,
                "source": prop.source,
                "changed": self._serialize_value(prop.changed),
                "params": self._serialize_value(getattr(prop, "params", {})),
            }
        methods = {}
        for name, method in obj.methods.items():
            methods[name] = {
                "description": method.description,
                "source": method.source,
                "executed": self._serialize_value(method.executed),
                "params": self._serialize_value(getattr(method, "params", {})),
            }
        rec = self._get_object_record(obj.name) or {}
        return {
            "name": obj.name,
            "description": obj.description,
            "class_name": rec.get("class_name"),
            "template": rec.get("template"),
            "template_engine": rec.get("template_engine", "jinja2"),
            "effective_template_source": rec.get("effective_template_source"),
            "parents": list(obj.parents),
            "properties": properties,
            "methods": methods,
        }

    def _serialize_value(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat(sep=" ", timespec="seconds")
        if isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._serialize_value(v) for v in value]
        return value

