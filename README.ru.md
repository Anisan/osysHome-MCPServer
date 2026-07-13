# MCPServer - endpoint Model Context Protocol

![MCPServer Icon](static/MCPServer.png)

Интеграция MCP для osysHome по HTTP JSON-RPC с безопасной моделью прав, поиском документации/исходников, инструментами валидации кода методов и поддержкой шаблонов классов.

## Документация

- [Руководство пользователя](docs/USER_GUIDE.ru.md)
- [Техническая документация](docs/TECHNICAL_REFERENCE.ru.md)
- [Индекс документации](docs/index.ru.md)

## Основные возможности

- Endpoint `/api/mcp` (`GET` статус + `POST` JSON-RPC)
- Токен-авторизация через `Authorization: Bearer` или `X-MCP-Token`
- Security audit логирование неудачных попыток (`MCP_UNAUTHORIZED`)
- Гибкие права через `allow_write_tools`, `allow_logs_access`, `allow_source_access`, `allow_manage_*`
- Документация через плагин Docs: `osys_plugin_list_entities` / `osys_plugin_get_entity` (коллекция `documents`; Docs в `plugins_allowed`)
- Read-only доступ к исходникам: `osys_read_source`, `osys_search_source`, `osys_list_source`
- Интроспекция классов: `osys_list_classes`, `osys_get_class_full`
- UI-метаданные свойств: `osys_get_property_ui`, `osys_update_property_ui`
- Версионирование правок: `revision` + `if_match`
- Массовые правки: `osys_bulk_update_class_properties`, `osys_bulk_update_methods`
- Шаблоны классов: `osys_get_template_spec`, `osys_validate_class_template`, `osys_render_class_template`
- Шаблоны объектов: `osys_validate_object_template`, `osys_render_object_template`
- История свойств и агрегаты: `osys_get_property_history`, `osys_get_property_history_aggregate`
- Валидация и dry-run кода методов: `osys_validate_method_code`, `osys_run_method_dry`
- Сохранение `linked` при редактировании свойств объекта

## Сведения о модуле

| Поле | Значение |
| --- | --- |
| Версия | `1` |
| Категория | `System` |
| Endpoint | `/api/mcp` |
| Протокол | `MCP over HTTP JSON-RPC` |

## Лицензия

См. лицензию основного проекта osysHome.
