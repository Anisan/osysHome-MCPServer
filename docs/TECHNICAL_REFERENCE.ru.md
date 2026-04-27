# MCPServer: техническая документация

> [!IMPORTANT]
> Актуальный источник: `plugins/MCPServer/__init__.py`.

## Точки входа

| Компонент | Путь | Назначение |
| :--- | :--- | :--- |
| Класс плагина | `plugins/MCPServer/__init__.py` | Реализация MCP-сервера |
| HTTP endpoint | `/api/mcp` | MCP JSON-RPC транспорт |
| Admin UI | `plugins/MCPServer/templates/mcp_admin.html` | Настройки модуля |

## MCP-методы

| Метод | Назначение |
| :--- | :--- |
| `initialize` | Инициализация и capabilities |
| `ping` | Проверка доступности |
| `notifications/initialized` | Обработка уведомления |
| `tools/list` | Схемы инструментов |
| `tools/call` | Вызов инструмента |
| `resources/list` | Список ресурсов |
| `resources/read` | Чтение ресурса |
| `prompts/list` | Список prompts |
| `prompts/get` | Получение prompt payload |

## Матрица инструментов

| Группа | Инструменты | Разрешение |
| :--- | :--- | :--- |
| Чтение | `osys_list_objects`, `osys_get_object`, `osys_get_property` | Не требуется |
| Логи | `osys_list_logs`, `osys_read_log` | `allow_logs_access` |
| Интроспекция классов | `osys_get_class`, `osys_list_classes`, `osys_get_class_full` | `allow_class_introspection` |
| UI-метаданные свойств | `osys_get_property_ui`, `osys_update_property_ui` | Чтение: не требуется, обновление: `allow_manage_properties` |
| История | `osys_get_property_history`, `osys_get_property_history_aggregate` | Не требуется |
| Запись значения | `osys_set_property` | `allow_write_tools` |
| Вызов метода | `osys_call_method` | `allow_method_calls` |
| Классы/шаблоны | `osys_add_class`, `osys_update_class`, `osys_delete_class`, `osys_get_template_spec`, `osys_validate_class_template`, `osys_render_class_template` | `allow_manage_classes` |
| Свойства класса | `osys_add_class_property`, `osys_update_class_property` | `allow_manage_properties` |
| Методы класса | `osys_add_class_method`, `osys_update_class_method`, `osys_get_class_method_code`, `osys_validate_method_code`, `osys_run_method_dry` | `allow_manage_methods` |
| Объекты | `osys_add_object`, `osys_update_object`, `osys_delete_object` | `allow_manage_objects` |
| Предпросмотр шаблонов объекта | `osys_validate_object_template`, `osys_render_object_template` | Не требуется |
| Свойства объекта | `osys_add_object_property`, `osys_update_object_property`, `osys_delete_object_property` | `allow_manage_properties` |
| Методы объекта | `osys_add_object_method`, `osys_update_object_method`, `osys_delete_object_method`, `osys_get_object_method_code` | `allow_manage_methods` |
| Массовые правки | `osys_bulk_update_class_properties`, `osys_bulk_update_methods` | По правам свойств/методов |

## Revision и конкурирующие правки

- Read API возвращает `revision`.
- Update-инструменты принимают опциональный `if_match`.
- При несовпадении `if_match` с текущей ревизией обновление отклоняется.

## Семантика обновлений

- `osys_update_class_property` и `osys_update_object_property` работают как partial update.
- `osys_update_object` работает как merge-patch: изменяются только переданные поля.
- `osys_delete_class` разрешен только если у класса нет потомков и связанных объектов.
- Контракт обновлений для AI/клиентов: нельзя перетирать любые данные, которые не были явно переданы в update payload.
- При обновлении не сбрасываются несвязанные поля.
- При обновлении свойства объекта сохраняется `linked`.
- Для успешного удаления delete-инструменты возвращают `ok: true`.

## Обновление кеша объектов

- Изменения на уровне класса вызывают `ObjectsStorage.reload_objects_by_class(class_id)`:
  - изменение шаблона класса (`osys_add_class`/`osys_update_class` при передаче `template`)
  - изменения свойств класса (`osys_add_class_property`, `osys_update_class_property`, class-ветка `osys_update_property_ui`)
  - изменения методов класса (`osys_add_class_method`, `osys_update_class_method`)
- Изменения на уровне объекта вызывают `ObjectsStorage.reload_object(object_id)`:
  - `osys_update_object`
  - `osys_add_object_property`, `osys_update_object_property`, object-ветка `osys_update_property_ui`
  - `osys_add_object_method`, `osys_update_object_method`
  - `osys_delete_object_property`, `osys_delete_object_method`

Приоритет выбора шаблона объекта:
`object.template` -> `class.template` -> встроенный шаблон по умолчанию.

## Метаданные `params`

- Инструменты свойств поддерживают `params` (JSON-объект).
- Типовые ключи из модуля Objects: `icon`, `unit`, `color`, `min`, `max`, `step`, `decimals`, `regexp`, `enum_values` (только для enum), `sort_order`, `read_only`.

## Resources

Статические:
- `osys://method-runtime/context`
- `osys://method-runtime/spec`
- `osys://method-runtime/examples`
- `osys://template/spec`

Динамические:
- `osys://object/<ObjectName>`

Поддерживается чтение напрямую:
- `osys://property/<ObjectName.propertyName>`

## Prompts

- `osys_object_overview`
- `osys_method_authoring`
- `osys_method_fix`

## Контракт runtime для кода методов

Код метода выполняется как `exec`-блок:

- без обертки `def`
- без `return`
- доступны `self`, `params`, `source`
- доступны helper-функции вроде `getProperty`, `setProperty`, `callMethod`

Перед сохранением рекомендуется `osys_validate_method_code`, затем `osys_run_method_dry`.

## Модель безопасности

- Опциональный токен через `Authorization: Bearer` или `X-MCP-Token`.
- Неудачные попытки авторизации пишутся в security audit как `MCP_UNAUTHORIZED`.
- Сравнение токенов: `hmac.compare_digest`.
- Запись/управление ограничены флагами `allow_*`.
- `osys_read_log` маскирует типичные секреты (token/password/api_key/Authorization/JWT) перед возвратом содержимого.

## Отказ от ответственности

> [!WARNING]
> MCPServer предоставляется «как есть». Перед использованием модуля и перед любыми write/manage-операциями обязательно создавать и проверять резервные копии.

## Ограничения

- `/api/mcp` `GET` используется как статус и не выполняет инструменты.
- Контракт шаблонов сейчас ориентирован на Jinja2 (`object.*`).
