"""Log access MCP tools for MCPServer."""
# pylint: disable=protected-access

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Optional

from app.configuration import Config


LOGS_DIR = os.path.join(Config.APP_DIR, "logs")
_MAX_READ_LINES = 5000
_MASK = "***MASKED***"

# Mask values only when they are clearly bound to sensitive key names.
_SENSITIVE_KEY_VALUE_RE = re.compile(
    r"(?i)\b("
    r"authorization|x-mcp-token|token|access_token|refresh_token|api[_-]?key|secret|password|passwd|pwd|session(?:id)?"
    r")\b(\s*[:=]\s*)([^\s\",;]+|\"[^\"]*\"|'[^']*')"
)
_SENSITIVE_JSON_RE = re.compile(
    r"(?i)(\"(?:authorization|x-mcp-token|token|access_token|refresh_token|api[_-]?key|secret|password|passwd|pwd|session(?:id)?)\"\s*:\s*)"
    r"(\"(?:\\.|[^\"])*\"|[^\s,}\]]+)"
)
_BEARER_RE = re.compile(r"(?i)\b(Bearer)\s+([A-Za-z0-9\-._~+/]+=*)")
_BASIC_RE = re.compile(r"(?i)\b(Basic)\s+([A-Za-z0-9\-._~+/]+=*)")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9._-]+\.[A-Za-z0-9._-]+\b")
_JWT_GENERIC_RE = re.compile(r"\b[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b")
_SENSITIVE_QUERY_RE = re.compile(
    r"(?i)([?&](?:token|access_token|refresh_token|api[_-]?key|secret|password|passwd|pwd|session(?:id)?|auth|authorization)=)([^&\s]+)"
)
_COOKIE_RE = re.compile(r"(?i)\b(Cookie|Set-Cookie)\s*:\s*([^\r\n]+)")
_AUTH_HEADER_RE = re.compile(r"(?i)\b(X-API-Key|X-Auth-Token|X-CSRF-Token|X-Access-Token)\s*:\s*([^\s,;]+)")
_AWS_ACCESS_KEY_RE = re.compile(r"\b(A3T[A-Z0-9]|AKIA|ASIA|AGPA|AIDA|AROA|ANPA|ANVA)[A-Z0-9]{16}\b")
_OPENAI_KEY_RE = re.compile(r"\b(sk-[A-Za-z0-9]{20,})\b")
_GITHUB_TOKEN_RE = re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,})\b")
_SLACK_TOKEN_RE = re.compile(r"\b(xox[baprs]-[A-Za-z0-9-]{10,})\b")
_TELEGRAM_BOT_URL_RE = re.compile(
    r"(?i)(https?://api\.telegram\.org/(?:file/)?bot)([0-9]{6,}:[A-Za-z0-9_-]{20,})(/?)"
)
_PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN(?:\s+[A-Z0-9]+)+\s+PRIVATE KEY-----[\s\S]*?-----END(?:\s+[A-Z0-9]+)+\s+PRIVATE KEY-----",
    re.IGNORECASE,
)


def _ensure_logs_dir_exists() -> None:
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
    except OSError:
        pass


def _safe_log_path(filename: str) -> Optional[str]:
    if not filename or os.path.basename(filename) != filename:
        return None
    _ensure_logs_dir_exists()
    full_path = os.path.abspath(os.path.join(LOGS_DIR, filename))
    logs_dir_abs = os.path.abspath(LOGS_DIR)
    if os.path.commonpath([logs_dir_abs, full_path]) != logs_dir_abs:
        return None
    return full_path


def _read_first_lines(file_path: str, lines_count: int):
    total_lines = 0
    lines: list[str] = []
    with open(file_path, "r", encoding="utf-8", errors="ignore") as source:
        for line in source:
            total_lines += 1
            if len(lines) < lines_count:
                lines.append(line)
    truncated = total_lines > lines_count
    return "".join(lines), truncated, total_lines


def _read_last_lines(file_path: str, lines_count: int):
    from collections import deque

    total_lines = 0
    with open(file_path, "r", encoding="utf-8", errors="ignore") as source:
        tail = deque(maxlen=lines_count + 1)
        for line in source:
            total_lines += 1
            tail.append(line)
    truncated = total_lines > lines_count
    if truncated:
        tail.popleft()
    return "".join(tail), truncated, total_lines


def _mask_log_content(content: str) -> tuple[str, int]:
    masked_hits = 0

    def _replace_key_value(match: re.Match) -> str:
        nonlocal masked_hits
        masked_hits += 1
        return f"{match.group(1)}{match.group(2)}{_MASK}"

    def _replace_json_value(match: re.Match) -> str:
        nonlocal masked_hits
        masked_hits += 1
        return f"{match.group(1)}\"{_MASK}\""

    def _replace_auth(match: re.Match) -> str:
        nonlocal masked_hits
        masked_hits += 1
        return f"{match.group(1)} {_MASK}"

    def _replace_header(match: re.Match) -> str:
        nonlocal masked_hits
        masked_hits += 1
        return f"{match.group(1)}: {_MASK}"

    def _replace_query(match: re.Match) -> str:
        nonlocal masked_hits
        masked_hits += 1
        return f"{match.group(1)}{_MASK}"

    def _replace_jwt(_: re.Match) -> str:
        nonlocal masked_hits
        masked_hits += 1
        return _MASK

    def _replace_telegram_url(match: re.Match) -> str:
        nonlocal masked_hits
        masked_hits += 1
        return f"{match.group(1)}{_MASK}{match.group(3)}"

    masked = content
    masked = _PRIVATE_KEY_BLOCK_RE.sub(_replace_jwt, masked)
    masked = _SENSITIVE_JSON_RE.sub(_replace_json_value, masked)
    masked = _SENSITIVE_KEY_VALUE_RE.sub(_replace_key_value, masked)
    masked = _BEARER_RE.sub(_replace_auth, masked)
    masked = _BASIC_RE.sub(_replace_auth, masked)
    masked = _AUTH_HEADER_RE.sub(_replace_header, masked)
    masked = _COOKIE_RE.sub(_replace_header, masked)
    masked = _SENSITIVE_QUERY_RE.sub(_replace_query, masked)
    masked = _AWS_ACCESS_KEY_RE.sub(_replace_jwt, masked)
    masked = _OPENAI_KEY_RE.sub(_replace_jwt, masked)
    masked = _GITHUB_TOKEN_RE.sub(_replace_jwt, masked)
    masked = _SLACK_TOKEN_RE.sub(_replace_jwt, masked)
    masked = _TELEGRAM_BOT_URL_RE.sub(_replace_telegram_url, masked)
    masked = _JWT_RE.sub(_replace_jwt, masked)
    masked = _JWT_GENERIC_RE.sub(_replace_jwt, masked)
    return masked, masked_hits


def handle_log_tools(plugin, tool_name: str, args: dict):
    if tool_name == "osys_list_logs":
        plugin._require_permission(
            "allow_logs_access",
            "Log access tools are disabled in plugin config",
        )
        _ensure_logs_dir_exists()
        files = []
        for filename in os.listdir(LOGS_DIR):
            file_path = _safe_log_path(filename)
            if not file_path or not os.path.isfile(file_path):
                continue
            files.append(
                {
                    "name": filename,
                    "size": int(os.path.getsize(file_path)),
                    "modified": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat(),
                }
            )
        files.sort(key=lambda item: item["modified"], reverse=True)
        return plugin._tool_result({"logs_dir": LOGS_DIR, "count": len(files), "items": files})

    if tool_name == "osys_read_log":
        plugin._require_permission(
            "allow_logs_access",
            "Log access tools are disabled in plugin config",
        )
        filename = (args.get("filename") or "").strip()
        if not filename:
            raise ValueError("filename is required")
        file_path = _safe_log_path(filename)
        if not file_path:
            raise ValueError("Invalid filename")
        if not os.path.isfile(file_path):
            raise ValueError(f"Log file not found: {filename}")

        lines = plugin._safe_int(args.get("lines"), 200, 1, _MAX_READ_LINES)
        position = (args.get("position") or "end").strip().lower()
        if position not in {"start", "end"}:
            raise ValueError("position must be 'start' or 'end'")
        if position == "start":
            content, truncated, total_lines = _read_first_lines(file_path, lines)
        else:
            content, truncated, total_lines = _read_last_lines(file_path, lines)
        content_masked, masked_hits = _mask_log_content(content)
        return plugin._tool_result(
            {
                "filename": filename,
                "position": position,
                "lines": lines,
                "total_lines": total_lines,
                "truncated": truncated,
                "masked": True,
                "masked_hits": masked_hits,
                "content": content_masked,
            }
        )
    return None


def get_tool_schemas(_property_params_schema) -> list[dict]:
    return [
        {
            "name": "osys_list_logs",
            "description": "List files in osysHome logs directory (permission required)",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "osys_read_log",
            "description": "Read first or last lines from a log file (permission required)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "lines": {"type": "integer", "minimum": 1, "maximum": _MAX_READ_LINES},
                    "position": {"type": "string", "enum": ["start", "end"]},
                },
                "required": ["filename"],
            },
        },
    ]
