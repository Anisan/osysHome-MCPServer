# MCPServer Technical Reference

> [!IMPORTANT]
> Source of truth: `plugins/MCPServer/__init__.py`.

## Entry Points

| Component | Path | Purpose |
| :--- | :--- | :--- |
| Plugin class | `plugins/MCPServer/__init__.py` | MCP server implementation |
| HTTP endpoint | `/api/mcp` | MCP JSON-RPC transport |
| Admin UI | `plugins/MCPServer/templates/mcp_admin.html` | Module settings |

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

## Resources

Static:
- `osys://method-runtime/context`
- `osys://method-runtime/spec`
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
- `osys_read_log` applies masking for common secrets (token/password/api_key/Authorization/JWT) before returning content.

## Disclaimer

> [!WARNING]
> MCPServer is provided "as is". Backup creation and verification are mandatory before module usage and before any write/manage operation.

## Known Constraints

- `/api/mcp` `GET` is status-only and does not execute tools.
- Template engine contract is currently Jinja2-oriented (`object.*` context root).
