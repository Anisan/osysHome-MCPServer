"""Default MCP agent guidelines for osysHome MCPServer."""

from __future__ import annotations

from typing import Any

AGENT_GUIDELINES_URI = "osys://server/agent-guidelines"

DEFAULT_AGENT_GUIDELINES = """# osysHome MCP agent guidelines

Rules for AI clients working through MCPServer (`/api/mcp`).

## Start here

1. Call `osys_server_capabilities` or read `osys://server/capabilities` before writes.
2. Read `osys://security/policy` for permission and whitelist constraints.
3. Prefer schemas and dry-run over guessing APIs or inventing method code.

## Objects and properties

- Discover with `osys_global_search` / `osys_list_objects` / `osys_get_object`.
- Batch reads via `osys_get_properties_batch` when possible.
- On writes use `revision` + `if_match` when the tool returns them.
- Flow: validate → dry-run (when available) → write.

## Method and task code

- Before authoring: read `osys://method-runtime/spec` (and examples/symbols).
- Method code is a plain `exec` block: no `def`, no `return`.
- Validate with `osys_validate_method_code`, then `osys_run_method_dry`.
- Tasks/cron: `osys://task-runtime/*`, `osys://cron/spec`.

## Plugins

- Only plugins in `plugins_allowed` are reachable.
- Use `osys_plugin_capabilities` / `osys_plugin_entity_schema` — do not invent fields.
- Entity writes: validate / dry-run / `if_match`, then upsert.
- Binding: follow `osys://plugin/binding/spec`.

## Source and logs

- Use `osys_read_source` / `osys_search_source` only when needed (`allow_source_access`).
- Logs require `allow_logs_access`; do not dump secrets.
- Plugin config secrets are masked.

## Safety

- Empty `plugins_allowed` denies all plugin tools/resources.
- Prefer the smallest write surface that completes the task.
- Re-read capabilities if permissions or whitelist may have changed.
"""


def get_agent_guidelines(plugin: Any = None) -> str:
    """Return agent guidelines text; optional config override via agent_instructions."""
    if plugin is not None:
        config = getattr(plugin, "config", None) or {}
        override = config.get("agent_instructions")
        if isinstance(override, str) and override.strip():
            return override.strip()
    return DEFAULT_AGENT_GUIDELINES.strip() + "\n"
