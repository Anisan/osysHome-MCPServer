"""Read-only source code access tools for debugging (app/ and plugins/)."""
# pylint: disable=protected-access

from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.configuration import Config

_ALLOWED_ROOTS = ("app", "plugins")
_SKIP_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
}
_TEXT_EXTENSIONS = {
    ".py",
    ".html",
    ".htm",
    ".js",
    ".ts",
    ".css",
    ".scss",
    ".json",
    ".md",
    ".txt",
    ".yml",
    ".yaml",
    ".sql",
    ".sh",
    ".bat",
    ".ini",
    ".cfg",
    ".toml",
    ".xml",
    ".jinja",
    ".j2",
    ".ru.md",
}
_MAX_READ_LINES = 2000
_MAX_SEARCH_RESULTS = 200
_MAX_SEARCH_FILE_SIZE = 2 * 1024 * 1024


def _normalize_rel_path(path: str) -> str:
    normalized = str(path or "").strip().replace("\\", "/").lstrip("/")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized


def _allowed_roots_abs() -> List[str]:
    return [os.path.abspath(os.path.join(Config.APP_DIR, root)) for root in _ALLOWED_ROOTS]


def _is_under_allowed_root(full_path: str) -> bool:
    full_path = os.path.abspath(full_path)
    for base in _allowed_roots_abs():
        try:
            if os.path.commonpath([base, full_path]) == base:
                return True
        except ValueError:
            continue
    return False


def _resolve_source_path(path: str, must_exist: bool = True) -> Tuple[str, str]:
    rel_path = _normalize_rel_path(path)
    if not rel_path:
        raise ValueError("path is required")
    if rel_path.startswith("../") or "/../" in f"/{rel_path}/":
        raise ValueError("path must not contain parent directory segments")
    root = rel_path.split("/", 1)[0]
    if root not in _ALLOWED_ROOTS:
        raise ValueError("path must start with app/ or plugins/")

    full_path = os.path.abspath(os.path.join(Config.APP_DIR, rel_path))
    if not _is_under_allowed_root(full_path):
        raise ValueError("path escapes allowed directories")
    if must_exist and not os.path.exists(full_path):
        raise ValueError(f"Path not found: {rel_path}")
    return rel_path, full_path


def _coerce_roots(raw_root: Any) -> List[str]:
    if raw_root is None or raw_root == "":
        return list(_ALLOWED_ROOTS)
    if isinstance(raw_root, str):
        tokens = [item.strip() for item in re.split(r"[,;]+", raw_root) if item.strip()]
    elif isinstance(raw_root, list):
        tokens = [str(item).strip() for item in raw_root if str(item).strip()]
    else:
        raise ValueError("root must be a string or list")
    roots = []
    for token in tokens:
        if token not in _ALLOWED_ROOTS:
            raise ValueError("root must contain only app and/or plugins")
        if token not in roots:
            roots.append(token)
    return roots or list(_ALLOWED_ROOTS)


def _is_text_source_file(filename: str) -> bool:
    lower = filename.lower()
    for ext in sorted(_TEXT_EXTENSIONS, key=len, reverse=True):
        if lower.endswith(ext):
            return True
    return False


def _read_line_range(file_path: str, offset: int, limit: int) -> Tuple[str, int, bool, int]:
    lines: List[str] = []
    start_line = max(1, offset)
    end_line = start_line + max(1, limit) - 1
    truncated = False
    total_lines = 0

    with open(file_path, "r", encoding="utf-8", errors="replace") as source:
        for line_no, line in enumerate(source, start=1):
            total_lines = line_no
            if line_no < start_line:
                continue
            if line_no <= end_line:
                lines.append(line)
            elif not truncated:
                truncated = True

    return "".join(lines), start_line, truncated, total_lines


def _iter_source_files(roots: Iterable[str], path_prefix: str = "") -> Iterable[Tuple[str, str]]:
    prefix = _normalize_rel_path(path_prefix) if path_prefix else ""
    if prefix and not prefix.endswith("/"):
        prefix = f"{prefix}/"

    for root in roots:
        base_rel = root
        base_abs = os.path.abspath(os.path.join(Config.APP_DIR, base_rel))
        if not os.path.isdir(base_abs):
            continue

        scan_root = base_abs
        if prefix:
            if not prefix.startswith(f"{root}/"):
                continue
            suffix = prefix[len(root) + 1 :]
            scan_root = os.path.abspath(os.path.join(base_abs, suffix))
            if not _is_under_allowed_root(scan_root):
                raise ValueError("path_prefix escapes allowed directories")
            if not os.path.isdir(scan_root):
                continue
            base_rel = prefix.rstrip("/")

        for current_root, dir_names, file_names in os.walk(scan_root):
            dir_names[:] = [name for name in dir_names if name not in _SKIP_DIR_NAMES]
            for filename in sorted(file_names):
                if not _is_text_source_file(filename):
                    continue
                full_path = os.path.join(current_root, filename)
                if not _is_under_allowed_root(full_path):
                    continue
                try:
                    if os.path.getsize(full_path) > _MAX_SEARCH_FILE_SIZE:
                        continue
                except OSError:
                    continue
                rel_path = os.path.relpath(full_path, Config.APP_DIR).replace("\\", "/")
                yield rel_path, full_path


def _search_in_file(
    rel_path: str,
    full_path: str,
    pattern: re.Pattern[str],
    context_lines: int,
) -> List[dict]:
    hits: List[dict] = []
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as source:
            lines = source.readlines()
    except OSError:
        return hits

    for index, line in enumerate(lines):
        if not pattern.search(line):
            continue
        start = max(0, index - context_lines)
        end = min(len(lines), index + context_lines + 1)
        snippet_lines = []
        for line_no in range(start, end):
            snippet_lines.append(f"{line_no + 1}: {lines[line_no].rstrip()}")
        hits.append(
            {
                "path": rel_path,
                "line": index + 1,
                "text": line.rstrip(),
                "snippet": "\n".join(snippet_lines),
            }
        )
    return hits


def handle_source_tools(plugin, tool_name: str, args: dict) -> Optional[dict]:
    if tool_name == "osys_read_source":
        plugin._require_permission(
            "allow_source_access",
            "Source access tools are disabled in plugin config",
        )
        rel_path, full_path = _resolve_source_path(args.get("path") or "")
        if not os.path.isfile(full_path):
            raise ValueError(f"Not a file: {rel_path}")

        offset = plugin._safe_int(args.get("offset"), 1, 1, 1_000_000)
        limit = plugin._safe_int(args.get("limit"), 200, 1, _MAX_READ_LINES)
        content, start_line, truncated, total_lines = _read_line_range(full_path, offset, limit)
        return plugin._tool_result(
            {
                "path": rel_path,
                "offset": start_line,
                "limit": limit,
                "total_lines": total_lines,
                "truncated": truncated,
                "content": content,
            }
        )

    if tool_name == "osys_search_source":
        plugin._require_permission(
            "allow_source_access",
            "Source access tools are disabled in plugin config",
        )
        query = str(args.get("query") or "").strip()
        if len(query) < 2:
            raise ValueError("query is required and must be at least 2 characters")

        use_regex = bool(args.get("regex", False))
        try:
            pattern = re.compile(query if use_regex else re.escape(query), re.IGNORECASE)
        except re.error as ex:
            raise ValueError(f"Invalid regex: {ex}") from ex

        roots = _coerce_roots(args.get("root"))
        path_prefix = str(args.get("path_prefix") or "").strip()
        if path_prefix:
            path_prefix = _normalize_rel_path(path_prefix)
            prefix_root = path_prefix.split("/", 1)[0]
            if prefix_root not in _ALLOWED_ROOTS:
                raise ValueError("path_prefix must start with app/ or plugins/")

        context_lines = plugin._safe_int(args.get("context_lines"), 1, 0, 5)
        limit = plugin._safe_int(args.get("limit"), 50, 1, _MAX_SEARCH_RESULTS)

        items: List[dict] = []
        files_scanned = 0
        for rel_path, full_path in _iter_source_files(roots, path_prefix):
            files_scanned += 1
            for hit in _search_in_file(rel_path, full_path, pattern, context_lines):
                items.append(hit)
                if len(items) >= limit:
                    return plugin._tool_result(
                        {
                            "query": query,
                            "regex": use_regex,
                            "root": roots,
                            "path_prefix": path_prefix or None,
                            "files_scanned": files_scanned,
                            "truncated": True,
                            "count": len(items),
                            "items": items,
                        }
                    )

        return plugin._tool_result(
            {
                "query": query,
                "regex": use_regex,
                "root": roots,
                "path_prefix": path_prefix or None,
                "files_scanned": files_scanned,
                "truncated": False,
                "count": len(items),
                "items": items,
            }
        )

    if tool_name == "osys_list_source":
        plugin._require_permission(
            "allow_source_access",
            "Source access tools are disabled in plugin config",
        )
        rel_path, full_path = _resolve_source_path(args.get("path") or "", must_exist=True)
        if not os.path.isdir(full_path):
            raise ValueError(f"Not a directory: {rel_path}")

        recursive = bool(args.get("recursive", False))
        limit = plugin._safe_int(args.get("limit"), 200, 1, 2000)
        items: List[dict] = []
        truncated = False

        if recursive:
            for current_rel, current_abs in _iter_source_files([rel_path.split("/", 1)[0]], rel_path):
                kind = "file"
                try:
                    size = int(os.path.getsize(current_abs))
                except OSError:
                    size = None
                items.append({"path": current_rel, "kind": kind, "size": size})
                if len(items) >= limit:
                    truncated = True
                    break
        else:
            try:
                entries = sorted(os.listdir(full_path))
            except OSError as ex:
                raise ValueError(f"Cannot list directory: {rel_path}") from ex
            for entry in entries:
                if entry in _SKIP_DIR_NAMES:
                    continue
                entry_abs = os.path.join(full_path, entry)
                if not _is_under_allowed_root(entry_abs):
                    continue
                entry_rel = f"{rel_path.rstrip('/')}/{entry}"
                if os.path.isdir(entry_abs):
                    items.append({"path": entry_rel, "kind": "directory", "size": None})
                elif _is_text_source_file(entry):
                    try:
                        size = int(os.path.getsize(entry_abs))
                    except OSError:
                        size = None
                    items.append({"path": entry_rel, "kind": "file", "size": size})
                if len(items) >= limit:
                    truncated = True
                    break

        return plugin._tool_result(
            {
                "path": rel_path,
                "recursive": recursive,
                "truncated": truncated,
                "count": len(items),
                "items": items,
            }
        )

    return None


def get_tool_schemas(_: Dict[str, Any]) -> list[dict]:
    return [
        {
            "name": "osys_read_source",
            "description": "Read source file from app/ or plugins/ (read-only, permission required)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path, e.g. app/core/main/BasePlugin.py or plugins/MCPServer/__init__.py",
                    },
                    "offset": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "1-based start line",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": _MAX_READ_LINES,
                        "description": "Number of lines to read",
                    },
                },
                "required": ["path"],
            },
        },
        {
            "name": "osys_search_source",
            "description": "Search text or regex in app/ and plugins/ sources (read-only, permission required)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "regex": {"type": "boolean", "description": "Treat query as regular expression"},
                    "root": {
                        "type": "string",
                        "description": "Search root: app, plugins, or app,plugins",
                    },
                    "path_prefix": {
                        "type": "string",
                        "description": "Optional subdirectory filter, e.g. plugins/MCPServer",
                    },
                    "context_lines": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 5,
                        "description": "Context lines around each match",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": _MAX_SEARCH_RESULTS,
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "osys_list_source",
            "description": "List files/directories under app/ or plugins/ path (read-only, permission required)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path, e.g. app or plugins/MCPServer/mcp/handlers",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Recursively list text source files",
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 2000},
                },
                "required": ["path"],
            },
        },
    ]
