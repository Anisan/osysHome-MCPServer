"""Structured logging helpers for MCPServer."""

from __future__ import annotations

import logging
from typing import Any, Optional

_CLIENT_ERROR_TYPES = frozenset(
    {
        "ValueError",
        "PermissionError",
        "NotImplementedError",
    }
)

_RPC_CLIENT_ERROR_CODES = frozenset({-32600, -32601, -32602})
_RPC_PERMISSION_ERROR_CODE = -32001


def _format_plugin(plugin: Optional[str]) -> str:
    return plugin or "-"


def log_tool_call(
    logger: logging.Logger,
    tool_name: str,
    duration_ms: float,
    ok: bool,
    *,
    plugin: Optional[str] = None,
    error: Optional[str] = None,
    error_type: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> None:
    """Log MCP tool execution to the plugin logger."""
    corr = correlation_id or "-"
    plugin_name = _format_plugin(plugin)
    if ok:
        logger.debug(
            "tool=%s ok duration_ms=%.1f plugin=%s corr=%s",
            tool_name,
            duration_ms,
            plugin_name,
            corr,
        )
        return

    message = error or "unknown error"
    if error_type in _CLIENT_ERROR_TYPES:
        logger.debug(
            "tool=%s failed duration_ms=%.1f plugin=%s corr=%s error=%s: %s",
            tool_name,
            duration_ms,
            plugin_name,
            corr,
            error_type or "Error",
            message,
        )
        return

    logger.error(
        "tool=%s failed duration_ms=%.1f plugin=%s corr=%s error=%s: %s",
        tool_name,
        duration_ms,
        plugin_name,
        corr,
        error_type or "Error",
        message,
    )


def log_rpc_request(logger: logging.Logger, method: str, req_id: Any = None) -> None:
    """Log incoming JSON-RPC method (skip noisy notifications)."""
    if method in {"notifications/initialized"}:
        return
    logger.debug("rpc method=%s id=%s", method, req_id if req_id is not None else "-")


def log_rpc_result(
    logger: logging.Logger,
    method: str,
    req_id: Any = None,
    *,
    summary: Optional[str] = None,
) -> None:
    """Log successful JSON-RPC response."""
    if method in {"notifications/initialized", "ping"}:
        return
    if summary:
        logger.debug("rpc method=%s id=%s %s", method, req_id if req_id is not None else "-", summary)
        return
    logger.debug("rpc method=%s id=%s ok", method, req_id if req_id is not None else "-")


def log_rpc_error(
    logger: logging.Logger,
    method: str,
    req_id: Any,
    code: int,
    message: str,
) -> None:
    """Log JSON-RPC error response."""
    if code == _RPC_PERMISSION_ERROR_CODE:
        logger.warning(
            "rpc method=%s id=%s code=%s error=%s",
            method,
            req_id if req_id is not None else "-",
            code,
            message,
        )
        return
    if code in _RPC_CLIENT_ERROR_CODES:
        logger.debug(
            "rpc method=%s id=%s code=%s error=%s",
            method,
            req_id if req_id is not None else "-",
            code,
            message,
        )
        return
    logger.error(
        "rpc method=%s id=%s code=%s error=%s",
        method,
        req_id if req_id is not None else "-",
        code,
        message,
    )


def log_rpc_exception(
    logger: logging.Logger,
    method: str,
    req_id: Any,
    exc: BaseException,
) -> None:
    """Log unexpected RPC handler exception with stack trace."""
    logger.exception(
        "rpc method=%s id=%s unexpected error: %s",
        method,
        req_id if req_id is not None else "-",
        exc,
    )
