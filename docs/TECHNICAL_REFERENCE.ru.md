# MCPServer: техническая документация

> [!IMPORTANT]
> Актуальный источник: `plugins/MCPServer/__init__.py` (RPC-транспорт) и `plugins/MCPServer/mcp/handlers/` (реализация инструментов).

## Точки входа

| Компонент | Путь | Назначение |
| :--- | :--- | :--- |
| Класс плагина | `plugins/MCPServer/__init__.py` | MCP-сервер, авторизация, RPC dispatch |
| Обработчики tools | `plugins/MCPServer/mcp/handlers/` | Логика инструментов по доменам |
| Схемы tools | `plugins/MCPServer/mcp/tools_schema.py` | Сборка схем для `tools/list` |
| Repository/utils | `plugins/MCPServer/core/` | Доступ к БД, общие утилиты |
| Resources/prompts | `plugins/MCPServer/mcp/resources.py` | MCP resources и prompts |
| HTTP endpoint | `/api/mcp` | MCP JSON-RPC транспорт |
| Admin UI | `plugins/MCPServer/templates/mcp_admin.html` | Настройки модуля |

## Модули обработчиков

| Модуль | Ответственность |
| :--- | :--- |
| `mcp/handlers/property_runtime.py` | Чтение объектов/свойств, история, `osys_set_property`, `osys_call_method`, UI-метаданные |
| `mcp/handlers/logs.py` | Список и чтение логов с маскированием секретов |
| `mcp/handlers/source.py` | Read-only доступ к исходникам `app/` и `plugins/` |
| `mcp/handlers/docs.py` | Поиск и чтение документации через плагин Docs |
| `mcp/handlers/classes_templates.py` | CRUD классов, шаблоны, интроспекция |
| `mcp/handlers/methods.py` | CRUD кода методов, валидация, dry-run |
| `mcp/handlers/objects_bulk.py` | Объекты, шаблоны объектов, bulk-операции, удаление |
| `mcp/handlers/common.py` | Маршрутизатор вызовов tools |

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
| Исходный код (read-only) | `osys_read_source`, `osys_search_source`, `osys_list_source` | `allow_source_access` |
| Документация | `osys_search_docs`, `osys_get_doc` | Плагин Docs активен; фильтр `docs_allowed_sources` |
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

## Инструменты документации

Доступны при установленном и активном плагине Docs. Иначе не попадают в `tools/list`.

| Инструмент | Назначение |
| :--- | :--- |
| `osys_search_docs` | Полнотекстовый поиск по индексу (`query`, опционально `source_id`, `locale`, `limit`) |
| `osys_get_doc` | Чтение одной страницы как plain text (`source_id`, `path`, опционально `max_chars`) |

`docs_allowed_sources` в конфиге ограничивает доступные `source_id`. По умолчанию: `core`, `Docs`, `MCPServer`.

## Инструменты доступа к исходникам

Read-only доступ к текстовым файлам в `app/` и `plugins/` (path traversal заблокирован).

| Инструмент | Назначение | Лимиты |
| :--- | :--- | :--- |
| `osys_read_source` | Чтение файла по диапазону строк | до 2000 строк за вызов |
| `osys_search_source` | Поиск текста или regex | до 200 совпадений, файлы до 2 МБ |
| `osys_list_source` | Список файлов/каталогов | до 2000 элементов |

Пропускаются каталоги: `__pycache__`, `.git`, `node_modules`, `.venv`, `venv`, `dist`, `build` и аналогичные.

## Resources

Схема URI: `osys://`.

Статические:
- `osys://method-runtime/context`
- `osys://method-runtime/spec`
- `osys://method-runtime/symbols`
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
- `osys_read_log` маскирует типичные секреты (токены, пароли, API keys, Bearer/Basic auth, JWT, cookies, private keys) перед возвратом содержимого.
- `allow_source_access` открывает исходный код приложения; включайте только для доверенных сценариев отладки.
- Инструменты документации учитывают whitelist `docs_allowed_sources`.

## Отказ от ответственности

> [!WARNING]
> MCPServer предоставляется «как есть». Перед использованием модуля и перед любыми write/manage-операциями обязательно создавать и проверять резервные копии.

## Ограничения

- `/api/mcp` `GET` используется как статус и не выполняет инструменты.
- Контракт шаблонов сейчас ориентирован на Jinja2 (`object.*`).
