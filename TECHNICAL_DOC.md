# Nex Timetrack — Documentación Técnica

## Visión General

CLI de time tracking para freelancers y agencias. Sin dependencias externas — Python 3.8+ stdlib + SQLite. Almacenamiento local, sin telemetría, sin cloud.

**Autor**: Nex AI (Kevin Blancaflor)
**Licencia**: MIT-0 (ClawHub) / AGPL-3.0 (GitHub)
**Versión**: 1.0.0

---

## Arquitectura

```
nex-timetrack/
├── nex-timetrack.py    ← CLI entry point (729 líneas)
├── lib/
│   ├── __init__.py     ← Package init
│   ├── config.py       ← Constantes y configuración
│   └── storage.py      ← Capa de datos SQLite (618 líneas)
├── setup.sh            ← Instalador
├── SKILL.md            ← Definición del skill para ClawHub
├── skill-card.md       ← Metadata del skill para marketplace
├── _meta.json          ← Metadata del proyecto
└── LICENSE.txt         ← Licencia AGPL-3.0
```

### Patrón arquitectónico

Arquitectura en 3 capas clásica para CLI:

```
┌──────────────────────────────┐
│  CLI Layer (argparse)        │  nex-timetrack.py
│  - Parsing de argumentos     │  cmd_*() functions
│  - Formateo de output        │  _fmt_*() helpers
│  - Resolución de entidades   │  _resolve_*() helpers
├──────────────────────────────┤
│  Config Layer                │  lib/config.py
│  - Constantes                │
│  - Paths                     │
│  - Categorías                │
├──────────────────────────────┤
│  Storage Layer (SQLite)      │  lib/storage.py
│  - CRUD entidades            │
│  - Timer state machine       │
│  - Rate cascade              │
│  - Reporting / export        │
│  - Full-text search (FTS5)   │
└──────────────────────────────┘
```

---

## Componentes

### 1. CLI Layer — [nex-timetrack.py](nex-timetrack.py)

**Propósito**: Parsing de argumentos, formateo de output, orquestación de comandos.

#### Helpers (`_fmt_*`, `_parse_*`, `_resolve_*`)

| Función | Propósito |
|---------|-----------|
| `_fmt_duration(minutes)` | Convierte minutos a formato `Xh Ym` |
| `_fmt_date(iso_str)` | ISO datetime → `YYYY-MM-DD` |
| `_fmt_time(iso_str)` | ISO datetime → `HH:MM` |
| `_fmt_money(amount)` | Formatea moneda con símbolo € |
| `_parse_duration(raw)` | Parsea `2h`, `90m`, `1h30m`, `1.5` → minutos |
| `_resolve_client(name)` | Busca client por nombre fuzzy → ID |
| `_resolve_project(name)` | Busca project por nombre fuzzy → ID |

#### Comandos (`cmd_*`)

18 subcomandos organizados en 5 dominios:

**Timer** (state machine con tabla singleton `active_timer`). **Deprecado en multi-user** — se mantiene para backward compat single-user:

| Comando | Handler | Descripción |
|---------|---------|-------------|
| `start` | `cmd_start` | Inicia timer. Si ya existe uno activo, muestra elapsed. **Deprecated multi-user.** |
| `stop` | `cmd_stop` | Detiene timer, guarda entry, calcula duración real. **Deprecated multi-user.** |
| `status` | `cmd_status` | Muestra timer activo con elapsed calculado en runtime. **Deprecated multi-user.** |
| `cancel` | `cmd_cancel` | Elimina timer sin guardar entry. **Deprecated multi-user.** |

**Entries CRUD**:

| Comando | Handler | Descripción |
|---------|---------|-------------|
| `log` | `cmd_log` | Crea entry manual con duración parseada. |
| `show` | `cmd_show` | Detalle completo de un entry (JOIN con clients/projects). |
| `list` | `cmd_list` | Lista tabular con filtros múltiples. Default limit: 50. |
| `edit` | `cmd_edit` | Actualización parcial — solo campos especificados. |
| `delete` | `cmd_delete` | Borrado con confirmación (`--confirm`). |
| `search` | `cmd_search` | Full-text search via FTS5. |

**Entidades**:

| Comando | Handler | Descripción |
|---------|---------|-------------|
| `client-add` | `cmd_client_add` | Crea cliente con rate opcional. |
| `clients` | `cmd_clients` | Lista todos los clientes. |
| `project-add` | `cmd_project_add` | Crea proyecto ligado a cliente. |
| `projects` | `cmd_projects` | Lista proyectos (solo activos por defecto). |

**Reporting**:

| Comando | Handler | Descripción |
|---------|---------|-------------|
| `summary` | `cmd_summary` | Resumen de horas facturables con desglose por client/project/category. |
| `stats` | `cmd_stats` | Estadísticas globales: ratio billable, top clients, barras por categoría. |

**Export**:

| Comando | Handler | Descripción |
|---------|---------|-------------|
| `export` | `cmd_export` | Exporta entries a JSON o CSV en `~/.nex-timetrack/exports/`. |

---

### 2. Config Layer — [lib/config.py](lib/config.py)

Constantes estáticas, sin lógica:

```python
DATA_DIR     = ~/.nex-timetrack/          # Override: NEX_TIMETRACK_DIR env var
DB_PATH      = ~/.nex-timetrack/timetrack.db
EXPORT_DIR   = ~/.nex-timetrack/exports/

DEFAULT_RATE = 85.00                      # EUR/h
CURRENCY     = EUR
ROUND_TO_MINUTES = 15                     # Redondeo para facturación

CATEGORIES = [development, design, meeting, research, admin,
              support, review, testing, deployment, planning,
              communication, other]       # 12 categorías
```

---

### 3. Storage Layer — [lib/storage.py](lib/storage.py)

**Propósito**: Toda interacción con SQLite. 618 líneas, ~35 funciones.

#### Conexión a DB

```python
@contextmanager
def _connect():
    # SQLite con WAL mode (lecturas concurrentes sin bloqueo)
    # Foreign keys ON
    # Auto-commit / rollback
```

#### Schema — Modelo de Datos

```
┌──────────────┐       ┌──────────────┐
│   clients    │       │  projects    │
│──────────────│       │──────────────│
│ id PK        │◄──┐   │ id PK        │
│ name UNIQUE  │   │   │ name         │
│ rate         │   └───│ client_id FK │
│ contact_email│       │ rate         │
│ notes        │       │ budget_hours │
│ created_at   │       │ notes        │
└──────────────┘       │ active       │
                       │ created_at   │
                       └──────┬───────┘
                              │
                              ▼
┌──────────────────────────────────────────────────┐
│                    entries                        │
│──────────────────────────────────────────────────│
│ id PK                                            │
│ project_id FK → projects.id (ON DELETE SET NULL) │
│ client_id FK → clients.id (ON DELETE SET NULL)   │
│ description                                      │
│ category                                         │
│ started_at          ─┐                           │
│ ended_at             │ solo si viene de timer    │
│ duration_minutes     │ log manual: started_at =  │
│ billable            ─┘ date T09:00, ended_at=NULL│
│ rate                                             │
│ tags                                             │
│ notes                                            │
│ created_at                                       │
│ updated_at                                       │
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│               entries_fts (FTS5)                  │
│──────────────────────────────────────────────────│
│ rowid → entries.id                               │
│ description                                      │
│ notes                                            │
│ tags                                             │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│               active_timer                        │
│──────────────────────────────────────────────────│
│ id CHECK(1) — singleton, máximo 1 row            │
│ description, project_id, client_id               │
│ category, billable, tags                         │
│ started_at — timestamp de inicio del timer       │
└──────────────────────────────────────────────────┘
```

**Tabla `clients`** — Catálogo de clientes. Se escribe cuando:
- `client-add` → INSERT (name UNIQUE, rate opcional)
- Nunca se modifica o elimina vía CLI (solo manualmente en DB)

**Tabla `projects`** — Catálogo de proyectos ligados a clientes. Se escribe cuando:
- `project-add` → INSERT con FK a client, rate y budget opcionales
- `active` flag permite "archivar" projects (no se exponen en list por defecto)

**Tabla `entries`** — Registro principal de tiempo. Se escribe cuando:
- `log` → INSERT manual. `started_at` = fecha + "T09:00:00", `ended_at` = NULL, `duration_minutes` = valor parseado
- `stop` → INSERT desde timer. `started_at` y `ended_at` calculados del timer, `duration_minutes` = diferencia real
- `edit` → UPDATE parcial (description, duration, category, tags, notes, rate, billable, client_id, project_id)
- `delete` → DELETE con `--confirm`

**Tabla `active_timer`** — Estado del timer en vivo (singleton). Se escribe cuando:
- `start` → INSERT/REPLACE row id=1 con timestamp actual
- `stop` → lee row, crea entry, luego DELETE row
- `cancel` → DELETE row sin crear entry

**Tabla `entries_fts`** — Índice de búsqueda full-text (FTS5 virtual table). Se escribe cuando:
- `stop_timer()` → sync después de crear entry
- `save_entry()` → sync después de INSERT manual
- `update_entry()` → re-sync con datos nuevos
- `delete_entry()` → DELETE row del índice

**Tablas internas de FTS5** — SQLite las crea automáticamente al hacer `CREATE VIRTUAL TABLE entries_fts USING fts5(...)`. No se crean explícitamente en el código:

| Tabla | Propósito |
|-------|-----------|
| `entries_fts_config` | Configuración del FTS5 (versión, opciones) |
| `entries_fts_content` | Contenido indexado (copia de description, notes, tags) |
| `entries_fts_data` | Estructura de datos interna del índice invertido |
| `entries_fts_docsize` | Tamaño de cada documento (para ranking BM25) |
| `entries_fts_idx` | Índice de términos → rowids (mapping invertido) |

Estas tablas se sincronizan automáticamente con `entries_fts` — nunca se manipulan directamente. Se borran todas juntas si se hace `DROP TABLE entries_fts`.

**Tabla `sqlite_sequence`** — Tabla interna de SQLite para rastrear el último valor `AUTOINCREMENT`. Contiene una row por cada tabla con AUTOINCREMENT (`entries`, `projects`). No se manipula directamente.

**Índice `sqlite_autoindex_clients_1`** — Índice automático de SQLite para garantizar `UNIQUE` en `clients.name`. Creado implícitamente por la constraint `UNIQUE`.

**Relaciones**:
- `entries.project_id` → `projects.id` (SET NULL on delete) — entry sobrevive si project se borra
- `entries.client_id` → `clients.id` (SET NULL on delete) — entry sobrevive si client se borra
- `projects.client_id` → `clients.id` (SET NULL on delete) — project sobrevive sin client

**Índices**: `idx_entries_project`, `idx_entries_client`, `idx_entries_date`, `idx_entries_billable`, `idx_entries_category`, `idx_projects_client`, `idx_projects_active`.

#### Ciclo de vida de un entry

```
                         ┌── timer flow (deprecado en multi-user) ──┐
                         │                                           │
                         ▼                                           │
  start ──→ active_timer ──→ stop ──→ entries + entries_fts         │
                     │                                               │
                     ▼                                               │
                   cancel ──→ void (no entry)                       │
                                                                     │
  ── log flow (flujo principal) ──────────────────────────────────  │
                                                                     │
  log ──→ entries + entries_fts ◄────────────────────────────────────┘
              │
              ├── show (lectura)
              ├── list (lectura + filtros)
              ├── search (lectura vía FTS5)
              ├── edit ──→ entries UPDATE + entries_fts re-sync
              ├── delete ──→ entries DELETE + entries_fts DELETE
              ├── summary (agregación en Python)
              ├── stats (agregación en SQL)
              └── export (JSON/CSV dump)
```

#### Funciones clave

| Función | Tipo | Detalle |
|---------|------|---------|
| `init_db()` | Setup | Crea directorios, permisos 700, schema + índices + FTS |
| `start_timer()` | Timer | INSERT en `active_timer` si vacío. Retorna `(started_at, None)` o `(None, existing)`. |
| `stop_timer()` | Timer | Lee `active_timer`, calcula duración, INSERT en `entries`, DELETE timer, sync FTS. |
| `get_active_timer()` | Timer | Lee timer + calcula `elapsed_minutes` en runtime. |
| `cancel_timer()` | Timer | DELETE timer sin crear entry. |
| `save_entry()` | CRUD | INSERT entry manual. Resuelve rate automático si no se especifica. |
| `get_entry()` | CRUD | SELECT con JOIN a projects/clients para nombres. |
| `list_entries()` | CRUD | Query builder dinámico con filtros opcionales. ORDER BY started_at DESC. |
| `update_entry()` | CRUD | UPDATE parcial. Whitelist de campos permitidos. Re-sincroniza FTS. |
| `delete_entry()` | CRUD | DELETE entry + FTS row. |
| `search_entries()` | Search | FTS5 MATCH. Fallback a LIKE si FTS falla. |
| `save_client()` | Entidad | INSERT client. Name UNIQUE. |
| `save_project()` | Entidad | INSERT project con FK a client. |
| `_resolve_rate()` | Rate cascade | entry > project > client > DEFAULT_RATE |
| `_round_up()` | Rounding | `ceil(minutes / 15) * 15` |
| `get_summary()` | Report | Agregaciones en Python sobre `list_entries()`. Desglose por client/project/category/date. |
| `get_stats()` | Report | Agregaciones en SQL (COUNT, SUM, GROUP BY). Top 10 clients, últimos 12 meses. |
| `export_entries()` | Export | JSON indentado o CSV con DictWriter. |
| `_sync_fts()` | FTS | Sincroniza row en `entries_fts` (DELETE + INSERT). |

---

## Mecanismos Clave

### Rate Cascade

Resolución automática de tarifa horaria en 4 niveles:

```
Entry.rate (override manual)
  → Project.rate
    → Client.rate
      → DEFAULT_RATE (85 EUR/h)
```

Implementación en `_resolve_rate()`:
1. Si `project_id` tiene rate → usar esa
2. Si el project tiene `client_id` → hereda y checkea client rate
3. Si `client_id` directo tiene rate → usar esa
4. Default a `DEFAULT_RATE`

### Timer State Machine

> **Deprecado en multi-user.** En el flujo Mattermost los usuarios loguean tiempo post-actividad con `log`. Los comandos `start`/`stop`/`status`/`cancel` se mantienen solo para backward compatibility en single-user.

```
[No timer] ──start──→ [active_timer row (id=1)]
     ↑                      │
     │ cancel          stop │
     │                      ↓
     │                [entries row creado]
     │                [active_timer eliminado]
     └──────────────────────┘
```

- Singleton: `CHECK (id = 1)` garantiza máximo un timer
- `start` con timer existente → no-op, muestra timer actual
- `stop` → calcula duración real (`now - started_at`), resuelve rate, crea entry, sincroniza FTS
- `cancel` → elimina timer sin entry

### Full-Text Search

Tabla virtual FTS5 sobre `(description, notes, tags)`:

- Sincronización manual: `_sync_fts()` se llama en `stop_timer()`, `save_entry()`, `update_entry()`
- `search_entries()`: usa `MATCH` con fallback a `LIKE` si FTS falla
- Ranking por relevancia FTS nativo (`fts.rank`)

### 15-Minute Rounding

Opcional vía flag `--round-up` en `summary`:

```python
def _round_up(minutes):
    return math.ceil(minutes / 15) * 15
```

Ejemplo: 23 min → 30 min, 47 min → 60 min. Solo afecta reportes, no entries originales.

---

## Setup — [setup.sh](setup.sh)

Script de instalación:

1. **Python check**: busca `python3` o `python` ≥ 3.8
2. **Directorios**: crea `~/.nex-timetrack/` y `exports/`
3. **Permisos**: `chmod 700` en data dir (no-Windows)
4. **DB init**: ejecuta `init_db()` via Python inline
5. **CLI wrapper**: crea `~/.local/bin/nex-timetrack` → wrapper bash que ejecuta el `.py`
6. **PATH check**: sugiere agregar `~/.local/bin` al PATH si no está

---

## Skill de ClawHub

### SKILL.md

Define el skill para el marketplace de ClawHub (Claude Code skills):

- **Metadata**: nombre, versión, autor, licencia, keywords, triggers
- **Keywords**: time tracking, billable hours, freelancer, urenregistratie (NL), etc.
- **Triggers**: "start timer", "log hours", "billable hours", etc.
- **Tone Guide**: mapea lenguaje natural → comandos CLI
- **Ejemplos**: 8 interacciones ejemplo con comandos concretos

### skill-card.md

Documentación oficial del skill para marketplace:
- Descripción, publisher, licencia
- Casos de uso
- Riesgos conocidos y mitigaciones (export con datos sensibles, paths custom, deletions)
- Output type/format
- Consideraciones éticas

### _meta.json

Metadata del proyecto en ClawHub:
- ownerId, slug, versión, timestamp de publicación

---

## Flujo de Datos Típico

### Timer flow

```
User → "nex-timetrack start 'Homepage redesign' --client 'Acme' --category design"
  → argparse parsea → cmd_start()
  → _resolve_client('Acme') → busca LIKE '%Acme%' → client_id=5
  → start_timer(description, client_id=5, category='design')
  → INSERT active_timer(id=1, ..., started_at=now)
  → Print confirmación

User → "nex-timetrack stop --notes 'Completed hero section'"
  → cmd_stop()
  → stop_timer(notes='Completed hero section')
  → SELECT active_timer → lee started_at
  → duration = now - started_at (en minutos)
  → _resolve_rate(conn, project_id, client_id) → €95/h (client rate)
  → INSERT entries(..., duration_minutes=127.3, rate=95)
  → _sync_fts(entry_id, description, notes, tags)
  → DELETE active_timer
  → Print resumen
```

### Manual log flow

```
User → "nex-timetrack log 'Design review' 1h30m --client 'Acme' --date 2026-05-28"
  → _parse_duration('1h30m') → 90 minutos
  → _resolve_client('Acme') → client_id=5
  → save_entry(description, duration_minutes=90, client_id=5, entry_date='2026-05-28')
  → started_at = '2026-05-28T09:00:00' (default 9am)
  → _resolve_rate() → €95/h
  → INSERT entries(...)
  → _sync_fts(...)
  → Print confirmación
```

---

## Limitaciones y Decisiones de Diseño

| Decisión | Razón |
|----------|-------|
| Zero dependencias | Portabilidad máxima, sin pip install |
| SQLite WAL | Lecturas no bloqueantes, writes secuenciales seguros |
| Singleton timer | Un solo timer activo — simple y sin conflictos |
| Rate en 4 niveles | Flexibilidad sin complejidad (override en cualquier nivel) |
| FTS5 sync manual | Control total, no trigger-dependent |
| Rounding solo en reports | Datos originales intactos, facturación flexible |
| Entries manuales a 09:00 | Simplificación — no se pide hora de inicio para logs manuales |
| LIKE fallback para search | Robustez si FTS5 no está disponible |
| Agregaciones en Python (summary) | Flexibilidad vs. SQL puro — permite rounding y lógica custom |
| Agregaciones en SQL (stats) | Performance — datos globales, no necesitan transformación |

---

## Extensibilidad

Puntos naturales para extensión:

- **Nuevos comandos**: agregar subparser + `cmd_*` + función en storage
- **Nuevas categorías**: agregar a `CATEGORIES` en config.py
- **Nuevos formatos de export**: agregar rama en `export_entries()`
- **Multi-moneda**: extender config con currency por client/project
- **Tags como entities**: mover de TEXT a tabla separada con M2M
- **API/HTTP wrapper**: storage.py es independiente del CLI — se puede exponer via Flask/FastAPI
