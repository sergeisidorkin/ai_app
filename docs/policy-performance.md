# Производительность раздела «Продукты»

## Базовая линия

Замеры необходимо выполнять на PostgreSQL с данными, близкими к production. Локальная
SQLite-база используется только как дополнительная точка сравнения.

Исходный замер до декомпозиции `policy_partial.html`:

- endpoint: `GET /policy/policy/partial/`;
- локальная PostgreSQL-база, staff-пользователь;
- данные: 48 продуктов, 68 разделов, 7 структур раздела, 7 структур
  отчета, 2 цели, 10 составов услуг, 3 срока, 7 грейдов и 5 тарифов;
- 33 SQL-запроса;
- 456 566 байт несжатого HTML;
- 556,4 мс полного Django render.
- `policy_app/tests.py`: 130 тестов и 12 subtests, 85,06 с, без ошибок;
- `manage.py check` и `makemigrations --check --dry-run`: без ошибок.

Повторяемый probe `manage.py policy_performance` после механического разделения
шаблонов (PostgreSQL, прогретый процесс) показал 33 запроса, 423 270 байт и
197,97 мс для legacy partial. Самые крупные fragments до пагинации:
`typical-sections` — 159 793 байта, `products` — 95 015 байт,
`consulting-directions` — 32 029 байт.

## Этапные проверки

- Этап 1: 12 независимых table templates/context builders/GET endpoints;
  135 тестов и 60 subtests прошли.
- Этап 2A: TypicalSection фильтруется и пагинируется сервером по 50 строк,
  compact filter catalog не зависит от текущей DOM-страницы; 146 тестов и
  62 subtests прошли.
- Этап 2B: тот же контракт применен к восьми product-dependent fragments;
  refresh ограничен двумя параллельными запросами, а exports не пагинируются;
  152 теста и 76 subtests прошли.
- Этап 3A: HTMX CRUD и CSV upload для SectionStructure возвращают малый
  command response и обновляют только `section-structures`; legacy fallback
  сохранен; 159 тестов и 76 subtests прошли.
- Этап 3B: единая dependency map перевела все policy CRUD/import/Gantt на
  fragment-scoped обновления; product catalog и оба sidebar больше не зависят
  от строк paginated DOM; 164 теста и 159 subtests прошли.
- Этап 4: policy-запросов нет до первого открытия вкладки; HTMX shell содержит
  12 lazy placeholders и занимает 15 597 байт (1 120 байт gzip) вместо
  423 270 байт legacy partial. Первые два fragments загружаются сразу,
  остальные — viewport-очередью по два; 168 тестов и 159 subtests прошли.
- Этап 5: 177 non-browser policy tests и 37 затронутых policy/admin/core/requests
  tests прошли; `check`, `makemigrations --check --dry-run` и `git diff --check`
  завершились без ошибок.
- Этап 6: общий filter catalog использует отдельный generation-based cache;
  cold/warm выполняют 1/0 catalog SQL queries, invalidation происходит только
  после commit, Redis failures работают fail-open.
- Этап 7: устранён duplicate WhiteNoise, добавлены PostgreSQL connection
  controls, согласованные nginx/Gunicorn examples и route-scoped observability;
  189 policy и 28 core tests прошли.

## Этап 5: SQL, N+1 и PostgreSQL plans

Замеры выполнены локально на PostgreSQL через `manage.py policy_performance`.
Абсолютное время зависит от прогрева процесса и page cache, поэтому regression
tests фиксируют число запросов, но не wall-clock thresholds.

### Table endpoints: before/after

До исправления N+1 и route-aware context processor fast path:

- `policy_products_table`: 6 запросов, 46,57 мс;
- `policy_expertise_directions_table`: 5 запросов, 9,24 мс;
- `policy_consulting_directions_table`: 12 запросов, 13,73 мс;
- `policy_specialty_tariffs_table`: 9 запросов, 46,05 мс.

После:

- `policy_products_table`: 3 запроса, 42,71 мс;
- `policy_expertise_directions_table`: 2 запроса, 7,55 мс;
- `policy_consulting_directions_table`: 4 запроса, 9,16 мс;
- `policy_specialty_tariffs_table`: 2 запроса, 31,97 мс.

Три запроса на каждом endpoint исключены безопасным fast path для
`templates_products`, `templates_sections_map` и `notifications_counters`.
Он действует только для `/policy/policy/tables/`, filter catalog и HTMX lazy
shell; legacy partial, index, Templates/Requests и form routes сохраняют полный
context.

В прогретом общем after-run остальные paginated fragments показали:

- product-dependent простые таблицы — 2 запроса (`COUNT` + page query);
- `report-structures` — 3 запроса (`COUNT`, numbering metadata, page query);
- `typical-sections` — 4 запроса (`COUNT`, page query и два specialty prefetch);
- HTMX lazy shell — 0 запросов.

Single-product и multi-product probes сохраняют постоянные budgets:

- products — 3 запроса;
- typical sections — 4 запроса.

Команда поддерживает повторяемые `--product`, `--consulting`, `--category`,
`--subtype`, а также `--page` и `--label`; JSON дополнительно содержит
суммарное reported SQL time.

### EXPLAIN (ANALYZE, BUFFERS)

Проверка выполнена без production-данных на временных PostgreSQL tables внутри
rollback transaction: 100 продуктов и 20 000 разделов. Сравнивался текущий
набор PK/FK/`position` индексов с временным кандидатом
`(product_id, position, id)`.

Текущий план:

- unfiltered order/limit: `Seq Scan` + `Hash Join` + top-N sort, 4,825 мс;
- single product: существующий FK index + top-N sort, 0,168 мс;
- пять продуктов: существующий FK index + hash join + top-N sort, 0,527 мс;
- filtered `COUNT(*)`: index-only scan существующего FK index, 0,057 мс.

После создания временного composite candidate форма всех четырёх plans не
изменилась: PostgreSQL продолжил использовать FK index или sequential scan, а
сортировка по `product.short_name` осталась. Более низкое время повторного
запуска (4,117/0,073/0,223/0,032 мс) обусловлено прогретыми buffers; candidate
не был выбран.

Принятые новые индексы: **нет**. Migration на этапе 5 не создаётся.

Отклонены без production `EXPLAIN`:

- `TypicalSection(product_id, position, id)` — не выбран representative plan;
- массовые `(position, id)` — текущая cardinality мала, уже есть index на
  `position`, а PostgreSQL корректно предпочитает seq scan;
- `(created_by_id, position, id)` для grade/tariff tables — потенциально
  полезен только при существенно большей user-scoped cardinality;
- catalog mega-indexes — не соответствуют OR между FK и legacy filters и
  увеличивают write cost.

Перед пересмотром решения нужны production-like планы отдельно для первой и
дальних страниц, одного/нескольких продуктов и department-head scope.

### Move/reorder

Rollback probe на 500 строках с разреженными позициями:

- Product normalize: 501 запрос и 86,82 мс до; 2 запроса и 43,93 мс после;
- TypicalSection normalize одного продукта: 501 запрос и 69,35 мс до;
  2 запроса и 41,07 мс после.
- полный Product move-up path: 507 запросов и 87,19 мс до;
  5 запросов и 74,42 мс после;
- полный TypicalSection move-up path: 508 запросов и 75,23 мс до;
  6 запросов и 40,40 мс после.

Нормализация теперь делает один ordered locked read и один `bulk_update`.
Move handlers повторно используют полученный список, меняют соседнюю пару
одним `bulk_update` и не запускают второй full scan. Семантика сохранена:
Product остаётся global-scoped, TypicalSection — product-scoped, системный DSC
остаётся верхней границей. Unique constraint на `position` не добавлялся.

## Этап 6: ограниченный policy cache

Кэш включён только для полного компактного JSON endpoint
`policy_filter_catalog`. Ключ не зависит от пользователя, порядка query
parameters или `page`: endpoint не применяет эти параметры, а payload содержит
только общий product/filter catalog. Personalized grades, tariffs,
specialty-tariffs, table HTML и full policy HTML не кэшируются. После SQL
оптимизаций этапа 5 их повторный рендер дешёв, а ошибочная cache scope могла бы
показать данные одного пользователя другому.

Пример разделения Redis по назначению:

```dotenv
REDIS_URL=redis://redis:6379/0
POLICY_CACHE_URL=redis://redis:6379/2
POLICY_CACHE_KEY_PREFIX=ai_app:policy
POLICY_CACHE_TIMEOUT=300
POLICY_CACHE_CONNECT_TIMEOUT=0.2
POLICY_CACHE_SOCKET_TIMEOUT=0.2
```

`REDIS_URL` остаётся адресом Channels. Policy cache использует только
`POLICY_CACHE_URL` и отдельный Django cache alias `policy`; существующий
`default` cache не переиспользуется. Без `POLICY_CACHE_URL` local/test
использует отдельный LocMem, production — DummyCache и всегда свежий payload.

Поведение ответа наблюдаемо без раскрытия физических ключей:

- `X-Policy-Cache: MISS` — catalog построен и успешно записан;
- `X-Policy-Cache: HIT` — payload прочитан из policy cache;
- `X-Policy-Cache: BYPASS` — production fallback DummyCache;
- `X-Policy-Cache: ERROR` — Redis `get`/`set` завершился RedisError/OSError,
  но endpoint вернул свежий payload;
- `Server-Timing: policy-cache;desc="hit|miss|bypass|error"` дублирует статус.

Локальный regression probe с одним продуктом: cold request выполняет ровно
один catalog SQL query, warm request — 0; JSON совпадает. Auth/session queries
в это число намеренно не включены. Cache timeout — 300 секунд по умолчанию.
Generation key не истекает, а data keys ограничены timeout.

Invalidation меняет generation token только через `transaction.on_commit`.
Старые data keys становятся недостижимыми и естественно удаляются по TTL.
Поэтому committed изменения сразу дают следующий `MISS` во всех workers с
общим Redis, а rollback сохраняет текущий generation и следующий `HIT`.
Сигналы покрывают save/delete всех policy models, четыре policy M2M и внешние
display dependencies (`GroupMember`, `OrgUnit`, `ExpertSpecialty`,
`OKVCurrency`). Mutation/import response helpers отдельно покрывают
`bulk_update`, `QuerySet.update`, reorder, defaults и import paths, которые не
посылают model signals.

Cache I/O fail-open ограничен RedisError/OSError. После первой cache-ошибки
request больше не обращается к backend. Ошибки построения catalog не
перехватываются и остаются видимыми. Consulting catalog и HTML fragments на
этом этапе сознательно отклонены: независимый hit-rate не доказан, а
инвалидационная поверхность и риск scope leakage выше выгоды.

Ранее на production после сохранения структуры наблюдались:

- POST около 2,95 с;
- около 9,1 МБ распакованного ответа;
- 13 621 DOM-мутация;
- около 105 тысяч DOM-узлов, большинство скрыто клиентскими фильтрами.

## Этап 7: infrastructure и observability

### Django и database connections

Production использует единственную запись
`whitenoise.middleware.WhiteNoiseMiddleware` из `base.py`. Nginx остаётся
основным static server, а `CompressedManifestStaticFilesStorage` продолжает
создавать content-hashed и precompressed artifacts; повторный `insert()` из
`prod.py` удалён.

Только для PostgreSQL production settings задают:

```dotenv
DB_CONN_MAX_AGE=60
DB_CONN_HEALTH_CHECKS=true
POLICY_OBSERVABILITY_LATENCY_WARNING_MS=750
POLICY_OBSERVABILITY_BYTES_WARNING=524288
POLICY_OBSERVABILITY_LOG_LEVEL=INFO
```

SQLite этих database options не получает. Django держит соединение отдельно
на worker thread. Верхняя оценка для одного WSGI instance:
`workers × threads`; пример 3 × 4 даёт до 12 активных request connections,
не считая migrations, management commands, ASGI workers и operational reserve.
Перед изменением worker/thread count оператор должен проверить PostgreSQL
`max_connections`, pooler и фактическую RAM/CPU.

### Nginx и Gunicorn examples

Оба examples используют `/run/ai_app/ai_app.sock`. Gunicorn настроен как
`gthread`, а workers/threads/timeouts/keepalive/max_requests+jitter вынесены в
environment. Access/error logs идут в stdout/stderr. Это стартовые значения,
а не формула sizing.

Nginx использует named unix-socket upstream, HTTP/1.1 и upstream keepalive,
явные forwarding headers и proxy timeouts. Включены standard-module
`gzip`, `gzip_static`, `Vary`, minimum length и текстовые/JSON/XML types.
Brotli не включён, потому что наличие module не подтверждено. Только static
имена с 12-hex manifest hash получают `immutable` на год; прочая static имеет
консервативный cache на час.

WSGI upstream не обслуживает Channels WebSockets. Если production реально
использует `/ws/`, необходим отдельный ASGI service/socket и отдельный nginx
location. TLS остаётся deployment concern: example сохраняет HTTP listener и
комментарии для двух допустимых схем — TLS в nginx либо trusted external load
balancer, который перезаписывает `X-Forwarded-Proto`.

### Policy response observability

Middleware ограничен shell, table и filter-catalog route names. Он:

- добавляет `app;dur=<ms>` к существующему `Server-Timing`, не затирая
  `policy-cache;desc=...`;
- добавляет точный `X-Policy-Response-Bytes` для non-streaming response;
- пишет compact JSON event с route name, status, duration, byte count и
  cache status;
- повышает event до warning по latency/bytes thresholds;
- не логирует query parameters, filter values или body и не выполняет SQL;
- не читает streaming body; без известного `Content-Length` byte header
  отсутствует;
- не меняет responses остальных endpoints.

### Локальный sequential probe

`policy_performance --repeat 5` выполнен на локальном PostgreSQL. Это пять
последовательных render probes в одном процессе, не concurrent load test и не
production p99. `gzip_bytes` — размер локального Python gzip, а не
подтверждение negotiation через nginx.

- HTMX shell: 0 SQL во всех runs, 15 597 bytes / 1 120 gzip bytes;
  p50 0,33 мс, p95 27,56 мс, первый cold template run 34,37 мс.
- Filter catalog: первый `MISS` — 1 SQL, 15,86 мс; четыре `HIT` —
  0 SQL, 0,12–0,15 мс; p50 0,14 мс, p95 12,72 мс; 30 783 bytes /
  2 054 gzip bytes.
- Products table: 3 SQL во всех runs, 95 430 bytes / 6 388 gzip bytes;
  p50 10,10 мс, p95 19,48 мс.

Probe теперь сохраняет каждый run и выдаёт per-endpoint min/p50/p95/max,
cache-status counts и query/size distributions. Малое число runs означает,
что p95 описывает только эту локальную последовательность.

### Итог этап 0 → 7

- legacy all-in-one partial: 33 SQL, 456 566 bytes и 556,4 мс исходного
  полного render; повторный baseline после mechanical split —
  423 270 bytes и 197,97 мс;
- текущий lazy shell: 0 SQL, 15 597 bytes, без policy data до открытия;
- table fragments загружаются отдельно, пагинируются максимум по 50 строк и
  сохраняют constant query budgets;
- подтверждённые N+1 endpoints снижены: products 6→3, expertise 5→2,
  consulting 12→4, specialty tariffs 9→2 SQL;
- filter catalog: cold/warm 1→0 SQL;
- успешный обычный HTMX CRUD возвращает пустой command body и scoped trigger,
  а не прежний многомегабайтный policy DOM; import responses остаются
  компактным JSON.

### Rollback и production-only проверки

Изменения следует включать и откатывать независимо:

1. Django observability: удалить middleware entry или поднять log level;
   rollback не требует schema/cache changes.
2. Persistent DB connections: установить `DB_CONN_MAX_AGE=0`; health checks
   можно отключить отдельно после анализа ошибки.
3. Gunicorn: вернуть предыдущий unit override, выполнить operator-controlled
   `daemon-reload`/restart и проверить socket.
4. Nginx proxy/static/gzip: вернуть предыдущий конфиг, выполнить `nginx -t`,
   затем operator-controlled reload. `gzip_static` можно отключить отдельно.

Фактический anonymous production audit подтверждает только HTTP/2,
`nginx/1.24.0 Ubuntu` и HSTS. `/` отвечает redirect 302 на login без body,
поэтому dynamic gzip этим audit не доказан.

После deployment оператору ещё нужно проверить:

- `Content-Encoding` и `Vary` на достаточно большом authenticated policy
  HTML/JSON response, отдельно dynamic gzip и precompressed hashed static;
- CPU/RAM, worker restarts и latency под реальной concurrency;
- суммарные PostgreSQL connections против connection budget;
- Redis memory policy, eviction/TTL, generation visibility между workers и
  fail-open alerts;
- отдельный ASGI `/ws/` path, если WebSockets используются.

## Бюджеты

- paginated-таблица содержит не более 50 строк;
- успешный HTMX CRUD не возвращает полный `#policy-pane`;
- фильтрованный CSV/DOCX/XLSX содержит весь набор, а не только текущую страницу;
- число SQL-запросов table endpoint не зависит линейно от числа строк;
- нижние таблицы не запрашиваются до приближения к viewport;
- изменение одной сущности обновляет только реально зависимые загруженные таблицы.

## Обязательный контроль

После каждого этапа выполняются `policy_app` tests, downstream tests и полный CI suite.
Автоматический browser smoke проверяет отсутствие policy-запросов до открытия
вкладки, lazy shell/table load и реальное сохранение Product через HTMX с
точечным обновлением таблицы. Фильтры, пагинация, import/export, системный DSC,
оба Gantt и sidebar раздела «Шаблоны» остаются в ручной приемочной матрице.

Локальный запуск opt-in browser smoke:

```bash
python -m playwright install chromium
RUN_BROWSER_SMOKE=1 pytest -q -m browser
```

Если Chromium Playwright недоступен, но установлен Google Chrome:

```bash
RUN_BROWSER_SMOKE=1 PLAYWRIGHT_CHANNEL=chrome pytest -q -m browser
```

Финальная локальная проверка после устранения двух race conditions:

- полный suite: 1 192 passed, 185 subtests passed, browser smoke пропущен
  в обычном режиме как opt-in;
- `policy_app/tests.py`: 192 passed, 166 subtests passed;
- Playwright smoke с реальным Product save: 1 passed;
- `node --check`, local/prod `manage.py check`, migration drift и
  `git diff --check`: без ошибок.
