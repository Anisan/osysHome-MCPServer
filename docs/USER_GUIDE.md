# MCPServer user guide

> [!NOTE]
> Practical usage guide for MCPServer in osysHome.

## Contents

- [Purpose](#purpose)
- [Quick start](#quick-start)
- [Admin settings](#admin-settings)
- [Authentication](#authentication)
- [Typical workflows](#typical-workflows)
- [Revision and if_match](#revision-and-if_match)
- [Method code constraints](#method-code-constraints)
- [PowerShell check](#powershell-check)
- [Readiness checklist](#readiness-checklist)

---

## Purpose

MCPServer exposes `/api/mcp` for MCP JSON-RPC calls:

- `GET /api/mcp` - health/info
- `POST /api/mcp` - MCP requests

## Quick start

1. Open `MCP Server` admin page.
2. Configure `Auth token`.
3. Enable only required `allow_*` flags.
4. Connect client to `http://127.0.0.1:5000/api/mcp`.
5. Run:
   - `initialize`
   - `tools/list`
   - `resources/list`

## Admin settings

| Setting | Effect |
| :--- | :--- |
| `Auth token` | Token auth for MCP requests |
| `allow_write_tools` | Enables `osys_set_property` |
| `allow_method_calls` | Enables `osys_call_method` |
| `allow_class_introspection` | Read-only class introspection tools |
| `allow_manage_classes` | Class/template management tools |
| `allow_manage_objects` | Object tools |
| `allow_manage_properties` | Property + UI metadata tools |
| `allow_manage_methods` | Method code + bulk method updates |
| `max_list_items` | Limits list/read volumes |

## Authentication

Use one of:

- `Authorization: Bearer <token>`
- `X-MCP-Token: <token>`

Failed auth attempts are recorded in security audit logs (`MCP_UNAUTHORIZED`).

## Disclaimer and Backups

> [!WARNING]
> MCPServer is provided "as is", without warranties. You are solely responsible for any consequences of write operations and automation scenarios.
>
> Before working with this module, creating and verifying backups is mandatory (database, configuration, and critical plugin data).

## Typical workflows

### Read and introspection

- `osys_list_objects`
- `osys_get_object`
- `osys_list_classes`
- `osys_get_class`
- `osys_get_class_full`

### Class lifecycle

- `osys_add_class`
- `osys_update_class`
- `osys_delete_class`

Delete safety rule for `osys_delete_class`:
- class must not have descendant classes
- class must not have linked objects

### Object templates

- `osys_validate_object_template`
- `osys_render_object_template`
- `osys_update_object` supports `template`, `template_engine`, `if_match`

Template resolution order:
`object.template` -> `class.template` -> default template.

### Property history and analytics

- `osys_get_property_history`
- `osys_get_property_history_aggregate`

### UI metadata

- `osys_get_property_ui`
- `osys_update_property_ui`

### Bulk updates

- `osys_bulk_update_class_properties`
- `osys_bulk_update_methods`

### Cache update after writes

- Class-level updates automatically refresh object cache for the class tree (`reload_objects_by_class`).
- Object-level updates automatically refresh object cache for the target object (`reload_object`).

### Method-code safe flow

1. `osys_validate_method_code`
2. `osys_run_method_dry`
3. `osys_update_*_method`

## Revision and if_match

Read APIs return `revision`.  
Update APIs accept `if_match` to prevent accidental overwrite in concurrent edits.
For AI clients, send only explicit changes: any unspecified entity data must remain untouched.

Pattern:

1. Read entity (`revision`).
2. Send update with `if_match=<revision>`.
3. If mismatch occurs, re-read and merge.

## Method code constraints

Method code runs via `exec`:

- no `def` wrapper
- no `return`
- no markdown fences

## PowerShell check

```powershell
$url = "http://127.0.0.1:5000/api/mcp"
$headers = @{ Authorization = "Bearer YOUR_TOKEN" }
$body = @{
  jsonrpc = "2.0"
  id = 1
  method = "tools/list"
  params = @{}
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Method Post -Uri $url -Headers $headers -ContentType "application/json" -Body $body
```

## Readiness checklist

- [ ] Auth is enabled with token
- [ ] `tools/list` returns expected tools
- [ ] `osys_get_class_full` returns inherited + own data
- [ ] `osys_delete_class` is blocked for classes with descendants/objects
- [ ] `osys_get_property_ui`/`osys_update_property_ui` work
- [ ] `revision` + `if_match` works on updates
- [ ] Security audit logs record failed auth attempts
