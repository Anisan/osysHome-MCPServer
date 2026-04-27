"""MCP resources and prompts helpers for MCPServer plugin."""
# pylint: disable=protected-access

from __future__ import annotations

import json
from typing import List, Tuple
from urllib.parse import unquote, urlparse

from app.core.lib.object import getObject, getProperty
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
        "uri": "ngs://method-runtime/symbols",
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
]


def resources_list(plugin, params: dict) -> List[dict]:
    limit = plugin._safe_int(params.get("limit"), 50, 1, 5000)
    limit = min(limit, int(plugin.config.get("max_list_items", 200)))

    out = list(STATIC_RESOURCE_DEFINITIONS)
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
    if parsed.scheme != "ngs":
        raise ValueError(f"Unsupported URI scheme: {parsed.scheme}")

    host = parsed.netloc
    path = unquote(parsed.path.lstrip("/"))
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

    raise ValueError(f"Unsupported resource host: {host}")


def prompts_list() -> List[dict]:
    return list(PROMPT_DEFINITIONS)


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

    raise ValueError(f"Unknown prompt: {name}")
