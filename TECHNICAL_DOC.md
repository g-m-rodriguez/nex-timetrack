# Nex Timetrack — Documentación Técnica

## Visión General

CLI de time tracking multi-usuario para equipos, freelancers y agencias. Sin dependencias externas — Python 3.8+ stdlib + SQLite. Almacenamiento local, sin telemetría, sin cloud. Integración con Mattermost vía `HERMES_SESSION_USER_ID`.


---

## Arquitectura

```
nex-timetrack/
├── nex-timetrack.py     ← CLI entry point (38 comandos)
├── lib/
│   ├── __init__.py      ← Package init
│   ├── storage.py       ← Capa de datos SQLite + settings + categories
│   └── permissions.py   ← Capa de permisos centralizada + ROLES
├── setup.sh             ← Instalador
├── SKILL.md             ← Definición del skill para ClawHub
└── skill-card.md        ← Metadata del skill para marketplace
```

### Patrón arquitectónico

Arquitectura en 3 capas clásica para CLI:

```
┌──────────────────────────────────────┐
│  CLI Layer (argparse)                │  nex-timetrack.py
│  - Parsing de argumentos             │  cmd_*() functions
│  - Formateo de output                │  _fmt_*() helpers
│  - Resolución de entidades           │  _resolve_*() helpers
│  - Resolución de usuario             │  _resolve_user_id()
├──────────────────────────────────────┤
│  Permission Layer                    │  lib/permissions.py
│  - Role-based access control         │  check_*() functions
│  - Assignment validation             │  PermissionDenied exception
│  - Single-user bypass                │  ROLES constant
├──────────────────────────────────────┤
│  Storage Layer (SQLite)              │  lib/storage.py
│  - CRUD entidades                    │
│  - Settings & categories (DB)        │
│  - Rate cascade                      │
│  - Reporting / export                │
│  - Full-text search (FTS5)           │
│  - Multi-user (users, roles, assign) │
└──────────────────────────────────────┘
```

> **Nota**: `lib/config.py` fue eliminado. Toda la configuración de negocio migra a tablas `settings` y `categories` en SQLite. Los paths del filesystem (`DATA_DIR`, `DB_PATH`, `EXPORT_DIR`) son constantes en `storage.py`.

---

## Componentes

### 1. CLI Layer — [nex-timetrack.py](nex-timetrack.py)

**Propósito**: Parsing de argumentos, formateo de output, orquestación de comandos, integración de permisos.

#### Helpers (`_fmt_*`, `_parse_*`, `_resolve_*`)

| Función | Propósito |
|---------|-----------|
| `_fmt_duration(minutes)` | Convierte minutos a formato `Xh Ym` |
| `_fmt_date(iso_str)` | ISO datetime → `YYYY-MM-DD` |
| `_fmt_time(iso_str)` | ISO datetime → `HH:MM` |
| `_fmt_money(amount)` | Formatea moneda con símbolo desde DB (`get_setting('currency_symbol')`) |
| `_parse_duration(raw)` | Parsea `2h`, `90m`, `1h30m`, `1.5` → minutos |
| `_resolve_client(name)` | Busca client por nombre fuzzy → ID |
| `_resolve_project(name)` | Busca project por nombre fuzzy → ID |
| `_resolve_user_id(args)` | Lee `--user` o `HERMES_SESSION_USER_ID`. Error si falta en multi-user. |

#### Comandos (`cmd_*`)

33 subcomandos organizados en 8 dominios:

**Timer** (deprecated en multi-user — se mantiene para backward compat single-user):

| Comando | Handler | Descripción |
|---------|---------|-------------|
| `start` | `cmd_start` | Inicia timer. **Warning + no-op en multi-user.** |
| `stop` | `cmd_stop` | Detiene timer. **Warning + no-op en multi-user.** |
| `status` | `cmd_status` | Muestra timer activo. **Warning + no-op en multi-user.** |
| `cancel` | `cmd_cancel` | Elimina timer. **Warning + no-op en multi-user.** |

**Entries CRUD**:

| Comando | Handler | Descripción |
|---------|---------|-------------|
| `log` | `cmd_log` | Crea entry manual. En multi-user: `--client`, `--project`, `--external-id` requeridos para collaborator. Valida client y project activos. |
| `show` | `cmd_show` | Detalle completo de un entry. Incluye `external_id`. |
| `list` | `cmd_list` | Lista tabular con filtros. Scope por rol (all/own). Filtro `--external-id`. |
| `edit` | `cmd_edit` | Actualización parcial. `check_modify_entry()` valida ownership. Bloqueado si client desactivado. |
| `delete` | `cmd_delete` | Borrado con `--confirm`. `check_modify_entry()` valida ownership. |
| `search` | `cmd_search` | FTS5 search (incluye `external_id`). Scope por rol. |

**Entidades** (manager only para creación):

| Comando | Handler | Descripción |
|---------|---------|-------------|
| `client-add` | `cmd_client_add` | Crea cliente. `check_manage_clients()`. |
| `clients` | `cmd_clients` | Lista todos los clientes con estado Active. |
| `client-rename` | `cmd_client_rename` | Renombra cliente. Manager only. |
| `client-deactivate` | `cmd_client_deactivate` | Desactiva cliente (soft delete). Manager only, `--confirm`. Bloquea proyectos y time logging. |
| `client-reactivate` | `cmd_client_reactivate` | Reactiva cliente desactivado. Manager only. |
| `project-add` | `cmd_project_add` | Crea proyecto. `check_manage_clients()`. Valida client activo. |
| `projects` | `cmd_projects` | Lista proyectos (solo activos por defecto). |
| `project-deactivate` | `cmd_project_deactivate` | Desactiva proyecto. Manager only, `--confirm`. Client debe estar activo. Bloquea time logging. |
| `project-reactivate` | `cmd_project_reactivate` | Reactiva proyecto desactivado. Manager only. Client debe estar activo. |

**User Management** (manager only):

| Comando | Handler | Descripción |
|---------|---------|-------------|
| `user-add` | `cmd_user_add` | Registra usuario. Bootstrap: sin managers → cualquiera puede agregar. |
| `user-list` | `cmd_user_list` | Lista usuarios con roles. Manager/timekeeper only. |
| `user-deactivate` | `cmd_user_deactivate` | Desactiva usuario (soft delete). Manager only, `--confirm`. |
| `role-add` | `cmd_role_add` | Asigna rol. Bootstrap: sin managers → auto-asignar manager. |
| `role-remove` | `cmd_role_remove` | Remueve rol. |
| `assign` | `cmd_assign` | Asigna user a client/project. |
| `unassign` | `cmd_unassign` | Remueve asignación. |
| `assignments` | `cmd_assignments` | Lista asignaciones (sin user_id → todos). |

**Settings** (manager only para cambios):

| Comando | Handler | Descripción |
|---------|---------|-------------|
| `settings` | `cmd_settings` | Lista todas las settings. |
| `setting-get` | `cmd_setting_get` | Muestra valor de una setting. |
| `setting-set` | `cmd_setting_set` | Actualiza setting. `check_manage_settings()`. |
| `categories` | `cmd_categories` | Lista categorías activas. |
| `category-add` | `cmd_category_add` | Agrega categoría. `check_manage_settings()`. |
| `category-remove` | `cmd_category_remove` | Desactiva categoría (soft delete). `check_manage_settings()`. |

**Approval**:

| Comando | Handler | Descripción |
|---------|---------|-------------|
| `pending` | `cmd_pending` | Lista entries pendientes de aprobación. Filtros: `--user`, `--project`, `--client`, `--date-from`, `--date-to`. Requiere rol approver o manager. |
| `approve` | `cmd_approve` | Aprueba entries por ID. `check_approve_entry()` valida permisos. |
| `reject` | `cmd_reject` | Rechaza entries con `--reason` requerido. |
| `rejections` | `cmd_rejections` | Muestra entries propias rechazadas (vista collaborator). |
| `approval-history` | `cmd_approval_history` | Historial de aprobación/rechazo de un entry. |

**Reporting**:

| Comando | Handler | Descripción |
|---------|---------|-------------|
| `summary` | `cmd_summary` | Resumen facturación. `--team` para vista equipo. Scope por rol. |
| `stats` | `cmd_stats` | Estadísticas. Scope por rol (all/own). |

**Export**:

| Comando | Handler | Descripción |
|---------|---------|-------------|
| `export` | `cmd_export` | Exporta entries a JSON/CSV. `user_id` según permisos. |

---

### 2. Permission Layer — [lib/permissions.py](lib/permissions.py)

**Propósito**: Validación centralizada de permisos. Todas las funciones son no-op en single-user mode.

```python
ROLES = ("manager", "timekeeper", "collaborator", "approver")

class PermissionDenied(Exception): ...  # Exit code 3
```

| Función | Comportamiento |
|---------|----------------|
| `resolve_user(user_id)` | Valida user existe y está activo. None en single-user. |
| `require_user(user_id)` | Requiere user válido en multi-user. Error si falta. |
| `require_role(user_id, role)` | Valida que user tenga rol específico. |
| `check_log_entry(user_id, client_id, project_id)` | Manager→siempre, Timekeeper→denegado, Collaborator→solo asignados + requiere client/project. |
| `check_view_entries(user_id)` | Retorna 'all' o 'own' según roles. |
| `check_modify_entry(user_id, entry_user_id)` | Manager→cualquiera, Collaborator→solo propias, Timekeeper→denegado. |
| `check_manage_clients(user_id)` | Manager only. |
| `check_manage_users(user_id)` | Manager only. |
| `check_view_users(user_id)` | Manager, timekeeper, or approver. Collaborator blocked. |
| `check_manage_settings(user_id)` | Manager only. |
| `check_approve_entry(approver_id, entry_id)` | Valida approver/manager puede aprobar entry. Managers pueden auto-aprobarse. Approvers no. Requiere assignment al client/project (manager exempt). Entry debe estar pending. |
| `check_view_approvals(user_id)` | Retorna 'all' (manager/approver/timekeeper) o 'own_rejections' (collaborator). |

**Bootstrap**: cuando no hay managers en la DB, `user-add` y `role-add` no requieren permisos. Permite al primer usuario auto-asignar rol manager.

---

### 3. Storage Layer — [lib/storage.py](lib/storage.py)

**Propósito**: Toda interacción con SQLite. Constantes de paths, settings/categories desde DB, CRUD multi-user, reporting, FTS5.

#### Paths (constantes en storage.py)

```python
DATA_DIR   = Path(os.environ.get("NEX_TIMETRACK_DIR", Path.home() / ".nex-timetrack"))
DB_PATH    = DATA_DIR / "timetrack.db"
EXPORT_DIR = DATA_DIR / "exports"
```

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
│ active       │       │ notes        │
│ created_at   │       │ active       │
└──────────────┘       │ created_at   │
                       └──────┬───────┘
                              │
                              ▼
┌──────────────────────────────────────────────────┐
│                    entries                        │
│──────────────────────────────────────────────────│
│ id PK                                            │
│ project_id FK → projects.id (NOT NULL)           │
│ client_id FK → clients.id (NOT NULL)             │
│ description                                      │
│ category                                         │
│ started_at          ─┐                           │
│ ended_at             │ log: started_at =         │
│ duration_minutes     │ date T09:00, ended_at=NULL│
│ billable            ─┘                           │
│ rate                                             │
│ tags                                             │
│ notes                                            │
│ user_id          ← usuario que registró          │
│ external_id      ← JIRA/AzureDevOps/GitHub ref   │
│ approval_status ← pending/approved/rejected      │
│ created_at                                       │
│ updated_at                                       │
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│            entries_fts (FTS5)                     │
│──────────────────────────────────────────────────│
│ rowid → entries.id                               │
│ description, notes, tags, external_id            │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│            entry_approvals                        │
│──────────────────────────────────────────────────│
│ id PK                                            │
│ entry_id FK → entries.id (ON DELETE CASCADE)     │
│ approver_id FK → users.user_id (ON DELETE CASCADE)│
│ action CHECK('approved','rejected')              │
│ reason TEXT                                      │
│ approved_at                                      │
│                                                  │
│ Audit log append-only. Último registro = estado  │
│ actual. Sincronizado con entries.approval_status │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│               active_timer                        │
│──────────────────────────────────────────────────│
│ id CHECK(1) — singleton, solo single-user        │
│ description, project_id, client_id               │
│ category, billable, tags, started_at             │
└──────────────────────────────────────────────────┘

┌──────────────┐       ┌──────────────┐
│    users     │       │  user_roles  │
│──────────────│       │──────────────│
│ user_id PK   │◄──────│ user_id FK   │
│ name         │       │ role         │
│ active       │       │ PK(user,role)│
│ created_at   │       └──────────────┘
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│              assignments                          │
│──────────────────────────────────────────────────│
│ id PK                                            │
│ user_id FK → users (ON DELETE CASCADE)           │
│ client_id FK → clients (ON DELETE CASCADE)       │
│ project_id FK → projects (ON DELETE SET NULL)    │
│ UNIQUE(user_id, client_id, project_id)           │
│                                                  │
│ Wildcard: project_id IS NULL = todos los         │
│ proyectos del cliente                            │
└──────────────────────────────────────────────────┘

┌──────────────┐       ┌──────────────┐
│   settings   │       │  categories  │
│──────────────│       │──────────────│
│ key PK       │       │ id PK        │
│ value TEXT   │       │ name UNIQUE  │
│ updated_at   │       │ active       │
└──────────────┘       └──────────────┘
```

#### Cuándo se escribe cada tabla

**Tabla `clients`**:
- `client-add` → INSERT (name UNIQUE, rate opcional)

**Tabla `projects`**:
- `project-add` → INSERT con FK a client, rate y budget opcionales

**Tabla `entries`** — Registro principal de tiempo:
- `log` → INSERT manual. `started_at` = fecha + "T09:00:00", `ended_at` = NULL, `duration_minutes` = valor parseado. `user_id` y `external_id` opcionales en single-user, requeridos en multi-user. `approval_status` = `'pending'` si `approval_required` true, sino `'approved'`.
- `stop` → INSERT desde timer (solo single-user). `started_at` y `ended_at` calculados del timer.
- `edit` → UPDATE parcial (description, duration, category, tags, notes, rate, billable, client_id, project_id, external_id)
- `delete` → DELETE con `--confirm`

**Tabla `active_timer`** — Solo single-user:
- `start` → INSERT/REPLACE row id=1
- `stop` → lee row, crea entry, DELETE row
- `cancel` → DELETE row sin entry

**Tabla `entries_fts`** — Índice FTS5 (description, notes, tags, external_id):
- `stop_timer()`, `save_entry()`, `update_entry()` → sync
- `delete_entry()` → DELETE del índice

**Tabla `users`**:
- `user-add` → INSERT/UPSERT (user_id PK, name)
- Los user_id provienen de Mattermost IDs

**Tabla `user_roles`**:
- `role-add` → INSERT (user_id, role)
- `role-remove` → DELETE

**Tabla `assignments`**:
- `assign` → INSERT (user_id, client_id, project_id). Wildcard: project_id=NULL = todos los proyectos del cliente.
- `unassign` → DELETE

**Tabla `settings`**:

**Tabla `entry_approvals`** — Audit log de aprobaciones:
- `approve` → INSERT (entry_id, approver_id, action='approved'). Update entries.approval_status.
- `reject` → INSERT (entry_id, approver_id, action='rejected', reason). Update entries.approval_status.
- `delete_entry` → CASCADE delete de registros asociados.
- Seed en `init_db()` con INSERT OR IGNORE
- `setting-set` → UPSERT

**Tabla `categories`**:
- Seed en `init_db()` con INSERT OR IGNORE (12 categorías)
- `category-add` → INSERT
- `category-remove` → UPDATE active=0 (soft delete)

#### Relaciones

- `entries.project_id` → `projects.id` (NOT NULL) — entry siempre tiene project
- `entries.client_id` → `clients.id` (NOT NULL) — entry siempre tiene client
- `projects.client_id` → `clients.id` (SET NULL) — project sobrevive sin client
- `user_roles.user_id` → `users.user_id` (CASCADE) — roles se borran con user
- `assignments.user_id` → `users.user_id` (CASCADE) — asignaciones se borran con user
- `assignments.client_id` → `clients.id` (CASCADE) — asignaciones se borran con client
- `assignments.project_id` → `projects.id` (SET NULL) — asignación sobrevive sin project

#### Índices

`idx_entries_project`, `idx_entries_client`, `idx_entries_date`, `idx_entries_billable`, `idx_entries_category`, `idx_entries_user`, `idx_entries_external_id`, `idx_projects_client`, `idx_projects_active`, `idx_user_roles_user`, `idx_user_roles_role`, `idx_assignments_user`, `idx_assignments_client`, `idx_categories_active`.

#### Funciones clave

| Función | Tipo | Detalle |
|---------|------|---------|
| `init_db()` | Setup | Crea schema completo, seed settings + categories |
| `is_multiuser()` | Helper | True si hay usuarios activos en DB |
| `has_managers()` | Bootstrap | True si hay algún user con rol manager |
| `get_setting(key)` | Config | Lee de DB con type casting. Fallback a defaults. |
| `set_setting(key, value)` | Config | UPSERT en tabla settings |
| `get_categories()` | Config | Lee categorías activas de DB |
| `save_user()`, `list_users()` | Users | CRUD usuarios |
| `add_role()`, `remove_role()`, `get_roles()` | Roles | Gestión de roles (retorna set) |
| `add_assignment()`, `has_assignment()` | Assign | Asignaciones con wildcard check |
| `save_entry(user_id, external_id)` | CRUD | INSERT entry con multi-user fields |
| `get_entry_by_external_id()` | Lookup | Busca entries por referencia externa |
| `list_entries(user_id, external_id)` | CRUD | Query builder con filtros multi-user |
| `search_entries(query, user_id)` | Search | FTS5 + LIKE fallback con scope filter |
| `record_approval(entry_id, approver_id, action, reason)` | Approval | Insert en entry_approvals + update entries.approval_status |
| `get_pending_entries(approver_id, ...)` | Approval | Entries pending que approver puede aprobar (scoped por assignments) |
| `get_approval_history(entry_id)` | Approval | Historial de aprobaciones/rechazos |
| `get_rejected_entries(user_id)` | Approval | Entries rechazadas de un usuario |
| `get_summary(user_id, team)` | Report | Agregaciones Python. team=True ignora user_id filter |
| `get_stats(user_id, scope)` | Report | Agregaciones SQL con scope own/all |
| `_resolve_rate()` | Rate cascade | entry > project > client > `get_setting('default_rate')` |
| `_round_up()` | Rounding | Usa `get_setting('round_to_minutes')` |

#### Ciclo de vida de un entry

```
                         ┌── timer flow (solo single-user, deprecated) ──┐
                         │                                                │
                         ▼                                                │
  start ──→ active_timer ──→ stop ──→ entries + entries_fts              │
                     │                                                    │
                     ▼                                                    │
                   cancel ──→ void (no entry)                            │
                                                                          │
  ── log flow (flujo principal, multi-user) ──────────────────────────── │
                                                                          │
  log ──→ entries + entries_fts ◄────────────────────────────────────────┘
              │
              ├── show (lectura, incluye external_id + approval_status)
              ├── list (filtros: client, project, user, external_id, dates + Status column)
              ├── search (FTS5: description, notes, tags, external_id)
              ├── edit ──→ entries UPDATE + entries_fts re-sync + reset approval_status to pending
              ├── delete ──→ entries DELETE + entries_fts DELETE + entry_approvals CASCADE
              ├── summary (agregación Python, scope all/own)
              ├── stats (agregación SQL, scope all/own)
              ├── export (JSON/CSV, filtrado por permisos)
              ├── approve ──→ entry_approvals INSERT + entries.approval_status = 'approved'
              ├── reject ──→ entry_approvals INSERT + entries.approval_status = 'rejected'
              ├── pending (lista entries con approval_status='pending', scoped por assignments)
              ├── rejections (lista entries propias con status='rejected')
              └── approval-history (lista registros de entry_approvals)
```

---

## Mecanismos Clave

### Rate Cascade

Resolución automática de tarifa horaria en 4 niveles:

```
Entry.rate (override manual)
  → Project.rate
    → Client.rate
      → get_setting('default_rate') (85 EUR/h default, configurable)
```

### Multi-User Permission Model

```
┌─────────────────┐
│ is_multiuser()?  │
│  False → bypass  │
│  True  ──┐       │
└──────────┼───────┘
           ▼
┌─────────────────────┐
│ check_*() function   │
│  resolve_user()      │
│  get_roles()         │
│  validate action     │
│  ↓ fail              │
│  PermissionDenied    │
└─────────────────────┘
```

**Roles**:

| Acción | Manager | Timekeeper | Collaborator | Approver | Notas |
|--------|---------|------------|--------------|----------|-------|
| `log` | ✅ any client/project | ❌ | ✅ assigned only | ✅ assigned only | ❌ si client o project inactivo |
| `list`/`search` | ✅ all | ✅ all | ✅ own | ✅ all | |
| `show` | ✅ | ✅ | ✅ own | ✅ | Muestra approval_status si workflow activo |
| `edit` | ✅ any entry | ❌ | ✅ own | ✅ own | ❌ si client inactivo. Resetea approval a pending. Warning al editar approved/rejected. |
| `delete` | ✅ any entry (`--confirm`) | ❌ | ✅ own (`--confirm`) | ✅ own (`--confirm`) | CASCADE delete en entry_approvals |
| `summary` | ✅ own | ✅ own | ✅ own | ✅ own | |
| `summary --team` | ✅ | ✅ | ❌ | ✅ | |
| `stats` | ✅ all | ✅ all | ✅ own | ✅ all | |
| `export` | ✅ all | ✅ all | ✅ own | ✅ all | |
| `client-add`/`client-rename` | ✅ | ❌ | ❌ | ❌ | |
| `client-deactivate`/`client-reactivate` | ✅ (`--confirm`) | ❌ | ❌ | ❌ | Deactivate bloquea proyectos y time logging |
| `project-add` | ✅ | ❌ | ❌ | ❌ | ❌ si client inactivo |
| `project-deactivate`/`project-reactivate` | ✅ (`--confirm`) | ❌ | ❌ | ❌ | Deactivate bloquea time logging. Client debe estar activo. |
| `clients`/`projects` | ✅ | ✅ | ✅ | ✅ | |
| `user-add` | ✅ | ❌ | ❌ | ❌ | Bootstrap: sin managers → cualquiera puede agregar |
| `user-list` | ✅ | ✅ | ❌ | ✅ | |
| `user-deactivate` | ✅ (`--confirm`) | ❌ | ❌ | ❌ | |
| `role-add`/`role-remove` | ✅ | ❌ | ❌ | ❌ | Bootstrap: sin managers → auto-asignar |
| `assign`/`unassign` | ✅ | ❌ | ❌ | ❌ | |
| `assignments` | ✅ | ❌ | ❌ | ❌ | |
| `settings`/`setting-get` | ✅ | ✅ | ✅ | ✅ | |
| `setting-set` | ✅ | ❌ | ❌ | ❌ | |
| `categories` | ✅ | ✅ | ✅ | ✅ | |
| `category-add`/`category-remove` | ✅ | ❌ | ❌ | ❌ | |
| `pending` (view queue) | ✅ all | ✅ all | ❌ | ✅ assigned scope | Solo si `approval_required=true` |
| `approve` | ✅ any (incl. own) | ❌ | ❌ | ✅ assigned scope (not own) | Solo si `approval_required=true`. Entry debe estar `pending`. |
| `reject` | ✅ any (incl. own) | ❌ | ❌ | ✅ assigned scope (not own) | Solo si `approval_required=true`. Requiere `--reason`. Entry debe estar `pending`. |
| `rejections` (own) | ✅ | ✅ | ✅ | ✅ | Muestra entries propias rechazadas con motivo |
| `approval-history` | ✅ | ✅ | ✅ | ✅ | |

**Bootstrap**: si `has_managers()` retorna False, `user-add` y `role-add` no requieren permisos. Primer usuario se auto-asigna manager.

**Guards adicionales por estado**:

| Condición | Efecto |
|-----------|--------|
| Client inactivo | ❌ No se puede loguear tiempo, crear proyectos, ni editar entries existentes |
| Project inactivo | ❌ No se puede loguear tiempo |
| User inactivo | ❌ `resolve_user()` lanza PermissionDenied |
| `approval_required=false` | Entries nuevas nacen `approved`. Comandos approve/reject/pending avisan que workflow no está habilitado. |
| `approval_required=true` | Entries nuevas nacen `pending`. Editar entry approved/rejected → resetea a pending. |
| Entry status `pending` | Solo se puede approve/reject. No bloquea edit/delete. |
| Entry status `approved` | Edit → resetea a `pending` + warning. Approve/reject → error "already approved". |
| Entry status `rejected` | Edit → resetea a `pending` + warning. Approve/reject → error "already rejected". |

### Approval Workflow

Controlado por setting `approval_required` (default: False). Cuando está habilitado:

```
                    ┌───────────┐
                    │  pending  │ ← new entry, o edit de approved/rejected
                    └───────────┘
                     /          \
              approve/          \reject
                    /            \
          ┌───────────┐    ┌───────────┐
          │  approved │    │  rejected  │
          └───────────┘    └───────────┘
                ^               │
                │               │ (colaborador edita)
                └───────────────┘
```

**Reglas**:
- `approval_required=False`: entries nuevas nacen `approved`. Comandos de approval avisan que workflow no está habilitado.
- `approval_required=True`: entries nuevas nacen `pending`. Approvers/managers las aprueban o rechazan.
- **Auto-aprobación**: Managers pueden aprobar sus propias entries. Approvers NO.
- **Scope**: Approvers solo ven/approve entries de client/project al que están asignados (vía `assignments`). Managers tienen scope global.
- **Edición**: Editar un entry `approved` o `rejected` resetea a `pending`.
- **Audit**: Tabla `entry_approvals` es append-only. Cada aprobación/rechazo es un registro con timestamp, approver, y reason.
- **Rechazo**: Collaborators ven sus entries rechazadas via `rejections` con el motivo.

### Assignment Wildcard

`project_id IS NULL` en tabla `assignments` = acceso a todos los proyectos del cliente. `has_assignment()` checkea wildcard primero, luego project específico.

### Timer State Machine (deprecated)

```
[No timer] ──start──→ [active_timer row (id=1)]
     ↑                      │
     │ cancel          stop │
     │                      ↓
     │                [entries row creado]
     │                [active_timer eliminado]
     └──────────────────────┘
```

Solo funciona en single-user. En multi-user: warning + no-op.

### Full-Text Search

Tabla virtual FTS5 sobre `(description, notes, tags, external_id)`:
- Sincronización manual en `stop_timer()`, `save_entry()`, `update_entry()`
- `search_entries()`: MATCH con fallback a LIKE
- `external_id` indexado → busca por ticket JIRA/AzureDevOps
- Scope filter: `user_id` para collaborator (own only)

### Settings desde DB

```python
get_setting('default_rate')     # → 85.0 (float, auto-cast)
get_setting('currency_symbol')  # → '€' (string)
get_setting('round_to_minutes') # → 15 (int, auto-cast)
get_setting('approval_required') # → False (bool, auto-cast)
```

Type casting automático vía `SETTING_TYPE_MAP`. Defaults en `SETTING_DEFAULTS` dict.

### 15-Minute Rounding

Opcional vía `--round-up` en `summary`. Usa `get_setting('round_to_minutes')`:

```python
math.ceil(minutes / round_to) * round_to
```

Solo afecta reportes, no entries originales.

---

## Setup — [setup.sh](setup.sh)

Script de instalación:

1. **Python check**: busca `python3` o `python` ≥ 3.8 (compatible con macOS, sin `grep -P`)
2. **Directorios**: crea `~/.nex-timetrack/` y `exports/`
3. **Permisos**: `chmod 700` en data dir (no-Windows)
4. **DB init**: ejecuta `init_db()` → crea schema + seed settings + seed categories
5. **CLI wrapper**: crea `~/.local/bin/nex-timetrack`
6. **PATH check**: sugiere agregar `~/.local/bin` al PATH

---

## Skill de ClawHub

### SKILL.md

Define el skill v2.0.0 para ClawHub:
- Multi-user commands con `--user $HERMES_SESSION_USER_ID`
- Required fields en multi-user (client, project, external-id)
- Tabla de permisos por rol
- Bootstrap flow para primer manager
- Timer commands marcados como deprecated
- Keywords: JIRA, AzureDevOps, multi-user, team time tracking

### skill-card.md

Documentación marketplace:
- Descripción actualizada con multi-user y external IDs
- Nuevos riesgos: collaborator self-delete, user IDs en DB
- Versión 2.0.0

### _meta.json

- Versión actualizada a 2.0.0

---

## Flujo de Datos Típico

### Multi-user log flow (flujo principal)

```
User → "nex-timetrack log 'API integration' 2h --client 'Acme' --project 'Web' --external-id 'JIRA-1234' --user mm-bob"
  → argparse parsea → cmd_log()
  → _resolve_user_id(args) → mm-bob (de --user o env var)
  → _resolve_client('Acme') → client_id=1
  → _resolve_project('Web') → project_id=1
  → check_log_entry('mm-bob', 1, 1)
    → get_roles('mm-bob') → {'collaborator'}
    → has_assignment('mm-bob', 1, 1) → True
    → ✅
  → save_entry(description, duration=120, client_id=1, project_id=1,
               user_id='mm-bob', external_id='JIRA-1234')
    → _resolve_rate(conn, 1, 1) → €100/h (project rate)
    → INSERT entries(...)
    → _sync_fts(entry_id, description, notes, tags, 'JIRA-1234')
  → Print confirmación
```

### Bootstrap flow

```
Admin → "nex-timetrack user-add mm-alice --name 'Alice'"
  → is_multiuser() → False (no users yet)
  → save_user('mm-alice', 'Alice')
  → Print confirmación

Admin → "nex-timetrack role-add mm-alice manager"
  → has_managers() → False (bootstrap)
  → add_role('mm-alice', 'manager')
  → Print confirmación
  → Ahora mm-alice puede gestionar todo
```

### Single-user log flow (sin cambios)

```
User → "nex-timetrack log 'Design review' 1h30m --client 'Acme' --date 2026-05-28"
  → is_multiuser() → False
  → _resolve_user_id() → None (no requerido)
  → check_log_entry(None) → True (bypass)
  → save_entry(...) sin user_id ni external_id
  → Print confirmación
```

---

## Decisiones de Diseño

| Decisión | Razón |
|----------|-------|
| Zero dependencias | Portabilidad máxima, sin pip install |
| SQLite WAL | Lecturas no bloqueantes, writes secuenciales seguros |
| Config en DB (no config.py) | Managers pueden ajustar sin editar código |
| Permisos explícitos (no decorators) | Cada comando llama check explícito — claro y debuggable |
| Single-user bypass | Si no hay usuarios, todo funciona como antes |
| Timer deprecated en multi-user | El flujo Mattermost es log post-actividad |
| External ID obligatorio en multi-user | Vinculación con tickets JIRA/AzureDevOps |
| Assignment wildcard (project_id=NULL) | Acceso a todos los proyectos de un cliente sin asignar cada uno |
| Bootstrap sin permisos | Permite al primer usuario auto-asignar manager |
| FTS5 sync manual | Control total, no trigger-dependent |
| Rounding solo en reports | Datos originales intactos, facturación flexible |
| Entries manuales a 09:00 | Simplificación — no se pide hora de inicio para logs |
| LIKE fallback para search | Robustez si FTS5 no está disponible |
| `has_managers()` para bootstrap | Escape hatch limpio para chicken-and-egg del primer manager |

---

## Extensibilidad

Puntos naturales para extensión:

- **Nuevos comandos**: agregar subparser + `cmd_*` + función en storage
- **Nuevos roles**: agregar a `ROLES` en permissions.py + CHECK constraint en schema
- **Nuevos formatos de export**: agregar rama en `export_entries()`
- **Multi-moneda**: agregar currency por client/project (settings por entidad)
- **Tags como entities**: mover de TEXT a tabla separada con M2M
- **API/HTTP wrapper**: storage.py es independiente del CLI — se puede exponer via Flask/FastAPI
- **Notificaciones**: hook post-entry para enviar a Mattermost/Slack
- **Budget tracking**: alertas cuando project se acerca al budget_hours
