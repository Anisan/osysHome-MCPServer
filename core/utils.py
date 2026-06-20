"""Utility helpers for MCPServer plugin."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.lib.constants import PropertyType
from app.core.lib.execute import MODULE_NAMES


def method_runtime_context_payload() -> dict:
    return {
        "execution_model": "Method code is executed with exec(code, environment) as a plain block",
        "auto_imports": {
            "description": (
                "Before method code execution, all public names from app.core.lib modules "
                "are auto-imported via 'from <module> import *'. You can use these functions/constants directly."
            ),
            "modules": list(MODULE_NAMES),
            "symbols_resource_uri": "osys://method-runtime/symbols",
        },
        "required_format": {
            "function_wrapper": "forbidden",
            "return_statement": "forbidden",
            "markdown_fences": "forbidden",
        },
        "available_variables": {
            "self": (
                "Current object manager instance. "
                "Type: app.core.main.ObjectManager.ObjectManager"
            ),
            "params": "Method call params dict; for property-trigger methods includes VALUE/NEW_VALUE/OLD_VALUE/PROPERTY/SOURCE",
            "source": "Execution source string",
            "logger": "System logger",
        },
        "self_contract": {
            "type": "ObjectManager",
            "python_path": "app.core.main.ObjectManager.ObjectManager",
            "description": (
                "In class/object method code, root `self` always points to ObjectManager instance "
                "for the current object."
            ),
        },
        "typical_helpers": [
            "getProperty(name)",
            "setProperty(name, value, source='')",
            "updateProperty(name, value, source='')",
            "callMethod(name, args={}, source='')",
        ],
        "safety_guidelines": [
            "Validate None/empty values before numeric conversions",
            "Wrap risky conversion/calculation blocks in try/except",
            "Use explicit object property names when calling setProperty",
        ],
    }


def method_runtime_symbols_payload() -> dict:
    """Build runtime payload with public symbols available via auto-import."""
    modules: List[dict] = []
    flat_names = set()

    for module_name in MODULE_NAMES:
        module_info: Dict[str, Any] = {
            "module": module_name,
            "status": "ok",
            "symbols": [],
            "counts": {"functions": 0, "classes": 0, "constants": 0, "other": 0},
        }
        try:
            module = importlib.import_module(module_name)
            exported = getattr(module, "__all__", None)
            if isinstance(exported, (list, tuple, set)):
                names = [name for name in exported if isinstance(name, str) and not name.startswith("_")]
            else:
                names = [name for name in dir(module) if not name.startswith("_")]

            for name in sorted(names):
                try:
                    value = getattr(module, name)
                except Exception:
                    symbol_type = "other"
                else:
                    if inspect.isfunction(value) or inspect.isbuiltin(value):
                        symbol_type = "function"
                    elif inspect.isclass(value):
                        symbol_type = "class"
                    elif name.isupper():
                        symbol_type = "constant"
                    else:
                        symbol_type = "other"

                module_info["symbols"].append({"name": name, "type": symbol_type})
                flat_names.add(name)
                if symbol_type == "function":
                    module_info["counts"]["functions"] += 1
                elif symbol_type == "class":
                    module_info["counts"]["classes"] += 1
                elif symbol_type == "constant":
                    module_info["counts"]["constants"] += 1
                else:
                    module_info["counts"]["other"] += 1
        except Exception as ex:
            module_info["status"] = "error"
            module_info["error"] = f"{type(ex).__name__}: {ex}"

        modules.append(module_info)

    return {
        "description": "Public symbols available in exec runtime through auto-imported app.core.lib modules",
        "modules": modules,
        "summary": {
            "module_count": len(modules),
            "unique_symbol_count": len(flat_names),
        },
    }


def rpc_error(req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def safe_model_id(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get("id")
    try:
        return value.__dict__.get("id")
    except Exception:
        return None


def safe_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
        if parsed < min_value:
            return min_value
        if parsed > max_value:
            return max_value
        return parsed
    except (TypeError, ValueError):
        return default


def parse_optional_datetime(value: Any, field_name: str) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
    except Exception as ex:
        raise ValueError(f"{field_name} must be ISO datetime string") from ex


def looks_like_broken_cyrillic(text: str) -> bool:
    if not text:
        return False
    q_count = text.count("?")
    if q_count < 4:
        return False
    has_cyr = any("\u0400" <= ch <= "\u04FF" for ch in text)
    if has_cyr:
        return False
    ratio = q_count / max(len(text), 1)
    return ratio >= 0.2


def safe_text_arg(args: dict, key: str) -> str:
    value = args.get(key)
    text = str(value or "").strip()
    if looks_like_broken_cyrillic(text):
        raise ValueError(
            f"'{key}' looks corrupted (contains many '?'). "
            "Likely encoding issue. Send UTF-8 text or use unicode escapes (\\uXXXX)."
        )
    return text


def parse_property_type(value: Any) -> PropertyType:
    if value is None or value == "":
        return PropertyType.Empty
    if isinstance(value, PropertyType):
        return value
    value_str = str(value).strip().lower()
    for item in PropertyType:
        if value_str == item.value or value_str == item.name.lower():
            return item
    raise ValueError(f"Unsupported property type: {value}")


def parse_json_object(raw_value: Any) -> Dict[str, Any]:
    if raw_value in (None, ""):
        return {}
    if isinstance(raw_value, dict):
        return raw_value
    try:
        loaded = json.loads(raw_value)
        if isinstance(loaded, dict):
            return loaded
    except Exception:
        pass
    return {}


def property_params_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "icon": {"type": "string"},
            "unit": {"type": "string"},
            "color": {"type": "string"},
            "group": {"type": "string"},
            "order": {"type": "integer"},
            "sort_order": {"type": "integer"},
            "hidden": {"type": "boolean"},
            "readonly": {"type": "boolean"},
            "read_only": {"type": "boolean"},
            "widget": {"type": "string"},
            "min": {"type": "number"},
            "max": {"type": "number"},
            "step": {"type": "number"},
            "decimals": {"type": "integer"},
            "regexp": {"type": "string"},
            "enum_values": {"type": "object"},
            "allowed_values": {"type": "array"},
            "rate_limit": {"type": "number"},
            "depends_on": {},
            "default_value": {},
        },
        "additionalProperties": True,
    }


def validate_property_params(params: Dict[str, Any]) -> None:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    if "enum_values" in params and params["enum_values"] is not None and not isinstance(params["enum_values"], dict):
        raise ValueError("params.enum_values must be an object")
    if "allowed_values" in params and params["allowed_values"] is not None and not isinstance(params["allowed_values"], list):
        raise ValueError("params.allowed_values must be an array")


def revision_for_payload(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def enforce_if_match(if_match: Optional[str], current_revision: str) -> None:
    if if_match and if_match != current_revision:
        raise ValueError(f"Revision mismatch: if_match={if_match}, current={current_revision}")


def tool_result(data: Any) -> dict:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": data,
        "isError": False,
    }
