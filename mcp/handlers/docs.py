"""Documentation search/read handlers for MCPServer tools."""
# pylint: disable=protected-access

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Optional

from app.core.lib.common import getModule
from plugins.Docs import indexer as docs_indexer

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_FORMAT_RE = re.compile(r"[#>*_`]")


def _strip_markdown(text: str) -> str:
    plain = _MD_LINK_RE.sub(r"\1", text)
    plain = _MD_FORMAT_RE.sub("", plain)
    return "\n".join(line.rstrip() for line in plain.splitlines()).strip()


def _docs_plugin_or_error():
    docs_plugin = getModule("Docs")
    if docs_plugin is None:
        raise ValueError("Docs plugin is not available or not active")
    return docs_plugin


def _allowed_sources(plugin) -> Optional[set[str]]:
    if not bool(plugin.config.get("allow_docs_access", False)):
        return set()
    return None


def _is_source_allowed(plugin, source_id: str) -> bool:
    allowed = _allowed_sources(plugin)
    return allowed is None or source_id in allowed


def _coerce_locale(args: dict) -> str:
    locale = str(args.get("locale") or "en").strip().lower()
    if not locale:
        return "en"
    return locale[:2]


def _built_at_iso(docs_plugin) -> Optional[str]:
    built_at = getattr(docs_plugin, "_index_built_at", None)
    if isinstance(built_at, datetime):
        return built_at.isoformat(sep=" ", timespec="seconds")
    return None


def handle_docs_tools(plugin, tool_name: str, args: dict) -> Optional[dict]:
    if tool_name == "osys_search_docs":
        docs_plugin = _docs_plugin_or_error()
        query = str(args.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        source_id = str(args.get("source_id") or "").strip()
        if source_id and not _is_source_allowed(plugin, source_id):
            raise ValueError(f"source_id is not allowed: {source_id}")

        limit = plugin._safe_int(args.get("limit"), 10, 1, 100)
        locale = _coerce_locale(args)
        index_ready = docs_plugin._ensure_index_started()
        if not index_ready:
            return plugin._tool_result(
                {
                    "query": query,
                    "index_ready": False,
                    "message": "Docs index is rebuilding, try again shortly.",
                    "count": 0,
                    "items": [],
                    "index_built_at": _built_at_iso(docs_plugin),
                }
            )

        results = docs_indexer.search_docs(docs_plugin, query, locale)
        filtered = []
        for item in results:
            sid = item.get("source_id") or ""
            if not _is_source_allowed(plugin, sid):
                continue
            if source_id and sid != source_id:
                continue
            filtered.append(
                {
                    "title": item.get("title", ""),
                    "source_id": sid,
                    "path": item.get("path", ""),
                    "url": item.get("url", ""),
                    "snippet": _strip_markdown(str(item.get("snippet") or ""))[:400],
                }
            )
            if len(filtered) >= limit:
                break

        return plugin._tool_result(
            {
                "query": query,
                "source_id": source_id or None,
                "locale": locale,
                "index_ready": True,
                "count": len(filtered),
                "items": filtered,
                "index_built_at": _built_at_iso(docs_plugin),
            }
        )

    if tool_name == "osys_get_doc":
        docs_plugin = _docs_plugin_or_error()
        source_id = str(args.get("source_id") or "").strip()
        path = str(args.get("path") or "").strip().replace("\\", "/")
        if not source_id:
            raise ValueError("source_id is required")
        if not path:
            raise ValueError("path is required")
        if not _is_source_allowed(plugin, source_id):
            raise ValueError(f"source_id is not allowed: {source_id}")

        max_chars = plugin._safe_int(args.get("max_chars"), 12000, 500, 50000)
        index_ready = docs_plugin._ensure_index_started()
        if not index_ready:
            return plugin._tool_result(
                {
                    "source_id": source_id,
                    "path": path,
                    "index_ready": False,
                    "message": "Docs index is rebuilding, try again shortly.",
                    "index_built_at": _built_at_iso(docs_plugin),
                }
            )

        entry = docs_plugin._get_doc_entry(source_id, path)
        if not entry:
            raise ValueError(f"Document not found: {source_id}/{path}")

        file_path = entry.get("file_path")
        if not file_path:
            raise ValueError(f"Document has no file path: {source_id}/{path}")

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        plain = _strip_markdown(text)
        truncated = len(plain) > max_chars
        content = plain[:max_chars]

        return plugin._tool_result(
            {
                "source_id": source_id,
                "path": entry.get("path", path),
                "title": entry.get("title") or "",
                "lang": entry.get("lang") or "default",
                "index_ready": True,
                "index_built_at": _built_at_iso(docs_plugin),
                "truncated": truncated,
                "content": content,
            }
        )

    return None


def get_tool_schemas(_: Dict[str, Any]) -> list[dict]:
    return [
        {
            "name": "osys_search_docs",
            "description": "Search osysHome documentation index (read-only)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "source_id": {"type": "string"},
                    "locale": {"type": "string", "description": "Language hint, e.g. en or ru"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
                "required": ["query"],
            },
        },
        {
            "name": "osys_get_doc",
            "description": "Get one documentation page by source/path as plain text (read-only)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                    "path": {"type": "string"},
                    "max_chars": {"type": "integer", "minimum": 500, "maximum": 50000},
                },
                "required": ["source_id", "path"],
            },
        },
    ]
