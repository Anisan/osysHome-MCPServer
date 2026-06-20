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
| Resources/prompts | `plugins/MCPServer/mcp/resources.py` | MCP resources and prompts |
| HTTP endpoint | `/api/mcp` | MCP JSON-RPC transport |
| Admin UI | `plugins/MCPServer/templates/mcp_admin.html` | Module settings |

## Handler Modules

| Module | Responsibility |
| :--- | :--- |
| `mcp/handlers/property_runtime.py` | Read objects/properties, history, `osys_set_property`, `osys_call_method`, UI metadata |
| `mcp/handlers/logs.py` | Log listing and reading with secret masking |
| `mcp/handlers/source.py` | Read-only `app/` and `plugins/` source access |
| `mcp/handlers/docs.py` | Documentation search/read via Docs plugin |
| `mcp/handlers/classes_templates.py` | Class CRUD, class templates, introspection |
| `mcp/handlers/methods.py` | Method code CRUD, validation, dry-run |
| `mcp/handlers/objects_bulk.py` | Objects, object templates, bulk updates, deletes |
| `mcp/handlers/common.py` | Tool dispatch router |

## MCP Methods

| Method | Purpose |
| :--- | :--- |
| `initialize` | Handshake and capabilities |
| `ping` | Health check |
| `notifications/initialized` | Notification handling |
| `tools/list` | Tool schemas |
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
| Documentation | `osys_search_docs`, `osys_get_doc` | Docs plugin active; filtered by `docs_allowed_sources` |
| Class introspection | `osys_get_class`, `osys_list_classes`, `osys_get_class_full` | `allow_class_introspection` |
| Property UI metadata | `osys_get_property_ui`, `osys_update_property_ui` | Read: none, update: `allow_manage_properties` |
| History | `osys_get_property_history`, `osys_get_property_history_aggregate` | None |
| Write value | `osys_set_property` | `allow_write_tools` |
| Method call | `osys_call_method` | `allow_method_calls` |
| Class/template management | `osys_add_class`, `osys_update_class`, `osys_delete_class`, `osys_get_template_spec`, `osys_validate_class_template`, `osys_render_class_template` | `allow_manage_classes` |
| Class properties | `osys_add_class_property`, `osys_update_class_property` | `allow_manage_properties` |
| Class methods | `osys_add_class_method`, `osys_update_class_method`, `osys_get_class_method_code`, `osys_validate_method_code`, `osys_run_method_dry` | `allow_manage_methods` |
| Object management | `osys_add_object`, `osys_update_object`, `osys_delete_object` | `allow_manage_objects` |
| Object template preview | `osys_validate_object_template`, `osys_render_object_template` | None |
| Object properties | `osys_add_object_property`, `osys_update_object_property`, `osys_delete_object_property` | `allow_manage_properties` |
| Object methods | `osys_add_object_method`, `osys_update_object_method`, `osys_delete_object_method`, `osys_get_object_method_code` | `allow_manage_methods` |
| Bulk updates | `osys_bulk_update_class_properties`, `osys_bulk_update_methods` | Properties/methods permissions |

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
- Typical keys follow Objects module conventions, for example: `icon`, `unit`, `color`, `min`, `max`, `step`, `decimals`, `regexp`, `enum_values` (enum only), `sort_order`, `read_only`.

## Documentation Tools

Available when the Docs plugin is installed and active. Tools are omitted from `tools/list` otherwise.

| Tool | Purpose |
| :--- | :--- |
| `osys_search_docs` | Full-text search in the documentation index (`query`, optional `source_id`, `locale`, `limit`) |
| `osys_get_doc` | Read one page as plain text (`source_id`, `path`, optional `max_chars`) |

`docs_allowed_sources` in plugin config restricts which `source_id` values are searchable/readable. Default: `core`, `Docs`, `MCPServer`.

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
- Documentation tools respect `docs_allowed_sources` whitelist.

## Disclaimer

> [!WARNING]
> MCPServer is provided "as is". Backup creation and verification are mandatory before module usage and before any write/manage operation.

## Known Constraints

- `/api/mcp` `GET` is status-only and does not execute tools.
- Template engine contract is currently Jinja2-oriented (`object.*` context root).
