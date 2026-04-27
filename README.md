# MCPServer - Model Context Protocol endpoint

![MCPServer Icon](static/MCPServer.png)

MCP integration for osysHome over HTTP JSON-RPC with fine-grained permissions, method-code validation/dry-run tools, and class-template tooling.

## Documentation

- [User Guide](docs/USER_GUIDE.md)
- [Technical Reference](docs/TECHNICAL_REFERENCE.md)
- [Documentation Index](docs/index.md)

## Highlights

- MCP endpoint at `/api/mcp` (`GET` health + `POST` JSON-RPC)
- Token auth via `Authorization: Bearer` or `X-MCP-Token`
- Security-audit logging for failed auth attempts (`MCP_UNAUTHORIZED`)
- Safe permission model (`allow_write_tools`, `allow_manage_*`)
- Class introspection: `osys_list_classes`, `osys_get_class_full`
- UI metadata tools: `osys_get_property_ui`, `osys_update_property_ui`
- Revision/optimistic concurrency: `revision` in read API + `if_match` in updates
- Bulk operations: `osys_bulk_update_class_properties`, `osys_bulk_update_methods`
- Class-template tools (`osys_get_class`, validate/render/template spec)
- Object-template tools (`osys_validate_object_template`, `osys_render_object_template`)
- History analytics: `osys_get_property_history`, `osys_get_property_history_aggregate`
- Method code validation and dry-run (`osys_validate_method_code`, `osys_run_method_dry`)
- Preserves property `linked` values when editing object properties

## Module Info

| Field | Value |
| --- | --- |
| Version | `1` |
| Category | `System` |
| Endpoint | `/api/mcp` |
| Protocol | `MCP over HTTP JSON-RPC` |

## License

See main osysHome project license.

