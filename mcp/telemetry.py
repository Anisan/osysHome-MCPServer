"""In-memory MCP tool execution telemetry for MCPServer."""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Any, Deque, Dict, List, Optional

_MAX_EVENTS = 500
_events: Deque[dict] = deque(maxlen=_MAX_EVENTS)
_lock = threading.Lock()
_counters: Dict[str, int] = {"total": 0, "errors": 0}


def _new_correlation_id() -> str:
    return uuid.uuid4().hex[:12]


def record_tool_call(
    tool_name: str,
    duration_ms: float,
    ok: bool,
    *,
    plugin: Optional[str] = None,
    error: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> str:
    correlation_id = correlation_id or _new_correlation_id()
    event = {
        "correlation_id": correlation_id,
        "tool": tool_name,
        "plugin": plugin,
        "duration_ms": round(duration_ms, 2),
        "ok": bool(ok),
        "error": (str(error)[:300] if error else None),
        "ts": time.time(),
    }
    with _lock:
        _events.append(event)
        _counters["total"] += 1
        if not ok:
            _counters["errors"] += 1
    return correlation_id


def telemetry_summary(limit: int = 20) -> Dict[str, Any]:
    with _lock:
        recent = list(_events)[-max(1, min(limit, 100)) :]
        counters = dict(_counters)
    errors = [item for item in recent if not item.get("ok")]
    durations = [float(item.get("duration_ms") or 0) for item in recent]
    avg_ms = round(sum(durations) / len(durations), 2) if durations else 0.0
    return {
        "total_calls": counters.get("total", 0),
        "error_calls": counters.get("errors", 0),
        "recent_count": len(recent),
        "recent_avg_duration_ms": avg_ms,
        "recent_errors": errors[-5:],
        "recent": recent,
    }
