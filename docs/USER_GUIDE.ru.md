# MCPServer: руководство пользователя

> [!NOTE]
> Практическое руководство по работе с MCPServer в osysHome.

## Содержание

- [Назначение](#назначение)
- [Быстрый старт](#быстрый-старт)
- [Настройки модуля](#настройки-модуля)
- [Авторизация](#авторизация)
- [Типовые сценарии](#типовые-сценарии)
  - [Документация](#документация-плагин-docs)
  - [Логи](#логи-нужно-разрешение)
  - [Исходный код](#исходный-код-нужно-разрешение)
- [Revision и if_match](#revision-и-if_match)
- [Ограничения кода методов](#ограничения-кода-методов)
- [Проверка через PowerShell](#проверка-через-powershell)
- [Чек-лист готовности](#чек-лист-готовности)

---

## Назначение

MCPServer открывает endpoint `/api/mcp` для MCP JSON-RPC:

- `GET /api/mcp` - health/info
- `POST /api/mcp` - MCP-запросы

## Быстрый старт

1. Откройте админку модуля `MCP Server`.
2. Задайте `Auth token`.
3. Включите только нужные `allow_*` флаги.
4. Подключите клиент к `http://127.0.0.1:5000/api/mcp`.
5. Выполните:
   - `initialize`
   - `tools/list`
   - `resources/list`

## Настройки модуля

| Параметр | Что делает |
| :--- | :--- |
| `Auth token` | Токен-авторизация MCP |
| `allow_write_tools` | Разрешает `osys_set_property` |
| `allow_method_calls` | Разрешает `osys_call_method` |
| `allow_logs_access` | Разрешает `osys_list_logs`, `osys_read_log` (чувствительные данные) |
| `allow_source_access` | Разрешает `osys_read_source`, `osys_search_source`, `osys_list_source` |
| `allow_class_introspection` | Read-only интроспекция классов |
| `allow_manage_classes` | Управление классами/шаблонами |
| `allow_manage_objects` | Объекты |
| `allow_manage_properties` | Свойства + UI-метаданные |
| `allow_manage_methods` | Методы + bulk-обновления |
| `max_list_items` | Ограничение объема выдачи |
| `docs_allowed_sources` | Whitelist `source_id` для `osys_search_docs` / `osys_get_doc` (нужен плагин Docs) |

## Авторизация

Передавайте один из заголовков:

- `Authorization: Bearer <token>`
- `X-MCP-Token: <token>`

Неуспешные попытки авторизации пишутся в security audit (`MCP_UNAUTHORIZED`).

## Отказ от ответственности и резервные копии

> [!WARNING]
> Модуль MCPServer предоставляется «как есть», без каких-либо гарантий. Пользователь самостоятельно несет ответственность за последствия write-операций и сценариев автоматизации.
>
> Перед началом работы с модулем обязательно создавайте и проверяйте резервные копии (база данных, конфигурация и критичные данные плагинов).

## Типовые сценарии

### Чтение и introspection

- `osys_list_objects`
- `osys_get_object`
- `osys_list_classes`
- `osys_get_class`
- `osys_get_class_full`

### Документация (плагин Docs)

- `osys_search_docs` — поиск по запросу, опционально `source_id` и `locale`
- `osys_get_doc` — чтение одной страницы как plain text (`source_id` + `path`)

Ограничивайте источники в админке через `docs_allowed_sources`, если не хотите отдавать MCP-клиенту всю документацию плагинов.

### Логи (нужно разрешение)

- `osys_list_logs`
- `osys_read_log` — чтение первых/последних N строк; секреты маскируются автоматически

### Исходный код (нужно разрешение)

- `osys_list_source` — обход каталогов `app/` или `plugins/`
- `osys_read_source` — чтение файла по диапазону строк
- `osys_search_source` — поиск текста или regex с опциональным `path_prefix`

Включайте только в доверенных сценариях: раскрывает внутренности приложения.

### Жизненный цикл класса

- `osys_add_class`
- `osys_update_class`
- `osys_delete_class`

Ограничение безопасного удаления для `osys_delete_class`:
- у класса не должно быть дочерних классов (всех уровней)
- у класса не должно быть связанных объектов

### Шаблоны объектов

- `osys_validate_object_template`
- `osys_render_object_template`
- `osys_update_object` поддерживает `template`, `template_engine`, `if_match`

Приоритет шаблона:
`object.template` -> `class.template` -> шаблон по умолчанию.

### История и аналитика

- `osys_get_property_history`
- `osys_get_property_history_aggregate`

### UI-метаданные

- `osys_get_property_ui`
- `osys_update_property_ui`

### Массовые правки

- `osys_bulk_update_class_properties`
- `osys_bulk_update_methods`

### Обновление кеша после изменений

- Изменения на уровне класса автоматически обновляют кеш объектов по дереву класса (`reload_objects_by_class`).
- Изменения на уровне объекта автоматически обновляют кеш целевого объекта (`reload_object`).

### Безопасный цикл работы с кодом методов

1. `osys_validate_method_code`
2. `osys_run_method_dry`
3. `osys_update_*_method`

## Revision и if_match

Read API возвращает `revision`.  
Update API принимает `if_match`, чтобы защитить от затирания изменений при параллельной работе.
Для AI-клиентов: отправляйте только явные изменения; любые неуказанные данные сущности должны оставаться без изменений.

Рекомендуемый паттерн:

1. Прочитать сущность и взять `revision`.
2. Отправить update с `if_match=<revision>`.
3. При mismatch повторно прочитать и смержить изменения.

## Ограничения кода методов

Код методов исполняется через `exec`:

- без `def` wrapper
- без `return`
- без markdown fences

## Проверка через PowerShell

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

## Чек-лист готовности

- [ ] Авторизация включена и проверена
- [ ] `tools/list` возвращает актуальный набор tools
- [ ] `osys_get_class_full` возвращает inherited + own
- [ ] `osys_delete_class` блокируется для классов с дочерними/связанными объектами
- [ ] `osys_get_property_ui`/`osys_update_property_ui` работают
- [ ] `revision` + `if_match` работают в update
- [ ] В security audit фиксируются неуспешные попытки входа
- [ ] `osys_search_docs` / `osys_get_doc` учитывают `docs_allowed_sources`
- [ ] Source tools выключены, если не нужны явно
