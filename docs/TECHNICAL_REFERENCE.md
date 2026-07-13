# MCPServer Technical Reference

> [!IMPORTANT]
> Source of truth: `plugins/MCPServer/__init__.py` (RPC transport) and `plugins/MCPServer/mcp/handlers/` (tool implementations).

## Entry Points

| Component | Path | Purpose |
| :--- | :--- | :--- |
| Plugin class | `plugins/MCPServer/__init__.py` | MCP server, auth, RPC dispatch |
| Tool handlers | `plugins/MCPServer/mcp/handlers/` | Per-domain tool logic |
| Tool schemas | `plugins/MCPServer/mcp/tools_schema.py` | Schema assembly for `tools/list` |
| Repository/utils | `plugins/MCPServer/core/` | DB access helpers, shared utilities |
| Permissions | `plugins/MCPServer/mcp/permissions.py` | Permission-aware `tools/list` and resource filtering |
| Telemetry | `plugins/MCPServer/mcp/telemetry.py` | Tool call duration/outcome ring buffer |
| Resources/prompts | `plugins/MCPServer/mcp/resources.py` | MCP resources and prompts |
| HTTP endpoint | `/api/mcp` | MCP JSON-RPC transport |
| Admin UI | `plugins/MCPServer/templates/mcp_admin.html` | Module settings |

## Handler Modules

| Module | Responsibility |
| :--- | :--- |
| `mcp/handlers/property_runtime.py` | Read objects/properties, history, `osys_write_property`, `osys_invoke_method`, UI metadata |
| `mcp/handlers/logs.py` | Log listing and reading with secret masking |
| `mcp/handlers/source.py` | Read-only `app/` and `plugins/` source access |
| `mcp/handlers/plugins.py` | Plugin entity MCP tools (including Docs documentation) |
| `mcp/handlers/classes_templates.py` | Class CRUD, class templates, introspection |
| `mcp/handlers/methods.py` | Method code CRUD, validation, dry-run |
| `mcp/handlers/objects_bulk.py` | Objects, object templates, bulk updates, deletes |
| `mcp/handlers/meta.py` | Server capabilities, health, self-test, system stats |
| `mcp/handlers/plugins.py` | Atomic plugin tools, bindings, object context |
| `mcp/handlers/common.py` | Tool dispatch router + telemetry |

## MCP Methods

| Method | Purpose |
| :--- | :--- |
| `initialize` | Handshake and capabilities |
| `ping` | Health check |
| `notifications/initialized` | Notification handling |
| `tools/list` | Permission-filtered tool schemas |
| `tools/call` | Tool execution |
| `resources/list` | Resource discovery |
| `resources/read` | Resource payload |
| `prompts/list` | Prompt discovery |
| `prompts/get` | Prompt payload |

## Tool Matrix

| Group | Tools | Permission |
| :--- | :--- | :--- |
| Read | `osys_list_objects`, `osys_get_object`, `osys_get_property` | None |
| Logs | `osys_list_logs`, `osys_read_log` | `allow_logs_access` |
| Source code (read-only) | `osys_read_source`, `osys_search_source`, `osys_list_source` | `allow_source_access` |
| Class introspection | `osys_get_class`, `osys_list_classes`, `osys_get_class_tree`, `osys_get_class_full` | `allow_class_introspection` |
| Property UI metadata | `osys_get_property_ui`, `osys_update_property_ui` | Read: none, update: `allow_manage_properties` |
| History | `osys_get_property_history`, `osys_get_property_history_aggregate` | None |
| Write value | `osys_write_property` | `allow_write_tools` |
| Method call | `osys_invoke_method` | `allow_method_calls` |
| Class/template management | `osys_add_class`, `osys_update_class`, `osys_delete_class`, `osys_get_template_spec`, `osys_validate_class_template`, `osys_render_class_template` | `allow_manage_classes` |
| Class properties | `osys_add_class_property`, `osys_update_class_property`, `osys_delete_class_property` | `allow_manage_properties` |
| Class methods | `osys_add_class_method`, `osys_update_class_method`, `osys_delete_class_method`, `osys_get_class_method_code`, `osys_validate_method_code`, `osys_run_method_dry` | `allow_manage_methods` |
| Object management | `osys_add_object`, `osys_update_object`, `osys_delete_object` | `allow_manage_objects` |
| Object template preview | `osys_validate_object_template`, `osys_render_object_template` | None |
| Object properties | `osys_add_object_property`, `osys_update_object_property`, `osys_delete_object_property` | `allow_manage_properties` |
| Object methods | `osys_add_object_method`, `osys_update_object_method`, `osys_delete_object_method`, `osys_get_object_method_code` | `allow_manage_methods` |
| Bulk updates | `osys_bulk_update_class_properties`, `osys_bulk_update_methods` | Properties/methods permissions |
| Plugin read | `osys_plugin_capabilities`, `osys_plugin_list_entities`, … | `allow_read_plugins` + `plugins_allowed` |
| Plugin write | `osys_plugin_upsert_entity`, `osys_plugin_invoke`, … | `allow_manage_plugins` + `plugins_allowed` |
| Device binding | `osys_bind_device` | `allow_manage_plugins` + property-binding plugin |
| Meta / ops | `osys_server_capabilities`, `osys_health`, `osys_system_stats` | Mixed; see `osys_server_capabilities` |

## Server Capabilities (`osys_server_capabilities`)

Returns:

- `permissions` — effective `allow_*` flags and `plugins_allowed`
- `tool_groups` — groups with `enabled`, `tools_present`, `tools_available`
- `tools_listed` / `tools_available` — full schema vs permission-filtered surface
- `write_safety` — tools supporting `if_match`, dry-run, validate
- `resource_access` — static/dynamic/plugin URIs with `allowed`
- `plugin_tools` — declarative descriptors from whitelisted plugins
- `telemetry` — recent tool call summary
- `mcp_capable_plugins` — catalog with `contract` validation result

## Plugin MCP Contract

Plugins extend `BasePlugin` with:

- Entity CRUD: `mcp_capabilities`, `mcp_list_entities`, `mcp_upsert_entity`, …
- Descriptors: `mcp_tools()`, `mcp_resources()`, `mcp_prompts()` (via `app.core.lib.mcp_contract`)
- Safety: `mcp_entity_revision()`, `mcp_validate_entity()`

MCPServer exposes fixed atomic tools (`osys_plugin_*`), not per-plugin generated names.

## Telemetry

Each `tools/call` records: tool name, duration_ms, ok/error, optional plugin name, `correlation_id` from arguments.

Exposed in `osys_health`, `osys_system_stats`, and `osys_server_capabilities.telemetry`.

## Revisions and Concurrency

- Read responses include `revision` for optimistic concurrency.
- Update tools accept optional `if_match`.
- If `if_match` does not match current revision, update fails with a revision mismatch error.

## Update Semantics

- `osys_update_class_property` and `osys_update_object_property` use partial update semantics.
- `osys_update_object` uses merge-patch semantics; fields are changed only when explicitly provided.
- `osys_delete_class` is allowed only when the class has no descendants and no linked objects.
- Update contract for AI/clients: never overwrite any data that is not explicitly included in update payload.
- Editing property metadata does not reset unrelated fields.
- Object property updates preserve `linked`.
- Successful delete tools return `ok: true`.

## Cache Refresh Behavior

- Class-level changes trigger `ObjectsStorage.reload_objects_by_class(class_id)`:
  - class template changes (`osys_add_class`/`osys_update_class` when `template` is provided)
  - class property changes (`osys_add_class_property`, `osys_update_class_property`, class branch of `osys_update_property_ui`)
  - class method changes (`osys_add_class_method`, `osys_update_class_method`)
- Object-level changes trigger `ObjectsStorage.reload_object(object_id)`:
  - `osys_update_object`
  - `osys_add_object_property`, `osys_update_object_property`, object branch of `osys_update_property_ui`
  - `osys_add_object_method`, `osys_update_object_method`
  - `osys_delete_object_property`, `osys_delete_object_method`

Object template resolution priority is:
`object.template` -> `class.template` -> built-in default template.

## Params Metadata

- Property tools support `params` as JSON metadata.
- Typical property keys follow Objects module conventions, for example: `icon`, `unit`, `color`, `min`, `max`, `step`, `decimals`, `regexp`, `enum_values` (enum only), `sort_order`, `read_only`.
- Method tools support `params` for **display** metadata in object/class method lists: `icon`, `color`, `sort_order`.
- Use `merge_params` on method/property update tools to patch params partially (default: `true`).

## Documentation (Docs plugin)

Documentation search and read are exposed by the **Docs** plugin via standard plugin MCP tools (`osys_plugin_list_entities`, `osys_plugin_get_entity` on collection `documents`). Requires `allow_read_plugins` and `Docs` in `plugins_allowed`. See `plugins/Docs/docs/mcp.ru.md`.

## Source Access Tools

Read-only access to text files under `app/` and `plugins/` (path traversal blocked).

| Tool | Purpose | Limits |
| :--- | :--- | :--- |
| `osys_read_source` | Read file by line range | up to 2000 lines per call |
| `osys_search_source` | Text or regex search | up to 200 hits, files up to 2 MB |
| `osys_list_source` | List directory entries | up to 2000 items |

Skipped directories: `__pycache__`, `.git`, `node_modules`, `.venv`, `venv`, `dist`, `build`, and similar.

## Resources

URI scheme: `osys://`.

Static:
- `osys://method-runtime/context`
- `osys://method-runtime/spec`
- `osys://method-runtime/symbols`
- `osys://method-runtime/examples`
- `osys://template/spec`

Dynamic:
- `osys://object/<ObjectName>`

Supported for direct read:
- `osys://property/<ObjectName.propertyName>`

## Prompts

- `osys_object_overview`
- `osys_method_authoring`
- `osys_method_fix`

## Method Runtime Contract

Method code is executed as an `exec` block:

- no function wrapper (`def`)
- no `return`
- context variables include `self`, `params`, `source`
- helper functions like `getProperty`, `setProperty`, `callMethod` are available

Use `osys_validate_method_code` before save, and `osys_run_method_dry` for safe verification.

## Security Model

- Optional token auth via `Authorization: Bearer` or `X-MCP-Token`.
- Failed auth attempts are written to security audit as `MCP_UNAUTHORIZED`.
- Token compare uses `hmac.compare_digest`.
- Write/manage actions are guarded by `allow_*` flags.
- `osys_read_log` applies masking for common secrets (tokens, passwords, API keys, Bearer/Basic auth, JWT, cookies, private keys) before returning content.
- `allow_source_access` exposes application source code; enable only for trusted debugging scenarios.

## Disclaimer

> [!WARNING]
> MCPServer is provided "as is". Backup creation and verification are mandatory before module usage and before any write/manage operation.

## Known Constraints

- `/api/mcp` `GET` is status-only and does not execute tools.
- Template engine contract is currently Jinja2-oriented (`object.*` context root).
