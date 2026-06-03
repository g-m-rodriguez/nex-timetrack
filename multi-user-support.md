# Plan: nex-timetrack Multi-Usuario con Mattermost

## Context

nex-timetrack es un skill CLI de Hermes para trackeo de tiempo. Actualmente es single-user (sin user_id en entries, timer singleton). Se necesita convertir a multi-usuario para que un equipo completo lo use via Mattermost, con roles (manager/timekeeper/collaborator) y asignaciones por cliente/proyecto.

### Flujo de trabajo

Los usuarios logean tiempo **después de completar la actividad** (no hay timer en vivo). El flujo es exclusivamente `log` — se registra descripción, duración, cliente, proyecto, external ID y fecha. Esto elimina la necesidad de timer state machine en multi-user.

**Campos obligatorios en multi-user** (todo `log` debe incluir):
- `--client` — cliente al que se factura el tiempo
- `--project` — proyecto dentro del cliente
- `--external-id` — referencia externa (ticket JIRA, AzureDevOps, GitHub issue, etc.)
- `description` — descripción de la actividad (ya obligatorio en single-user)
- `duration` — duración (ya obligatorio)

> En single-user, `--client`, `--project` y `--external-id` siguen siendo opcionales para backward compatibility.

### Comandos deprecados

Los comandos de timer (`start`, `stop`, `status`, `cancel`) se marcan como **deprecated** en multi-user. Se mantienen funcionando en single-user para backward compatibility, pero no se usan en el flujo Mattermost.

```
# Single-user: siguen funcionando (backward compat)
nex-timetrack start "Task"
nex-timetrack stop

# Multi-user: ignorados, se emite warning
nex-timetrack start "Task" --user abc123
> Warning: Timer commands are deprecated in multi-user mode. Use 'log' to record time.
```

## Archivos a modificar/crear

| Archivo | Acción |
|---------|--------|
| `lib/storage.py` | Modificar — schema migration + funciones CRUD con user_id + settings/categories + paths de config.py |
| `lib/permissions.py` | **Nuevo** — capa de permisos centralizada + constante ROLES |
| `lib/config.py` | **Eliminar** — toda configuración migra a tablas `settings` y `categories` |
| `nex-timetrack.py` | Modificar — flag `--user`, comandos nuevos, permisos en existentes, deprecate timer commands, eliminar imports de config.py |
| `SKILL.md` | Modificar — instrucciones multi-usuario para agente Hermes |

## Fases

### Fase 1: Schema migration (`lib/storage.py`)

**Tablas nuevas** en `init_db()`:

```sql
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('manager','timekeeper','collaborator')),
    PRIMARY KEY (user_id, role),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    client_id INTEGER NOT NULL,
    project_id INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, client_id, project_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);

-- Configuración editable por managers (reemplaza constantes en config.py)
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Categorías editables por managers (reemplaza lista hardcoded en config.py)
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    active INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role);
CREATE INDEX IF NOT EXISTS idx_assignments_user ON assignments(user_id);
CREATE INDEX IF NOT EXISTS idx_assignments_client ON assignments(client_id);
CREATE INDEX IF NOT EXISTS idx_entries_user ON entries(user_id);
CREATE INDEX IF NOT EXISTS idx_categories_active ON categories(active);
```

**Seed de `settings`** (valores por defecto, solo se insertan si no existen):

```sql
INSERT OR IGNORE INTO settings (key, value) VALUES
    ('default_rate', '85.00'),
    ('currency', 'EUR'),
    ('currency_symbol', '€'),
    ('round_to_minutes', '15');
```

**Seed de `categories`** (12 categorías originales):

```sql
INSERT OR IGNORE INTO categories (name) VALUES
    ('development'), ('design'), ('meeting'), ('research'), ('admin'),
    ('support'), ('review'), ('testing'), ('deployment'), ('planning'),
    ('communication'), ('other');
```

**Migración de tablas existentes**:

- `entries`:
  - `ALTER TABLE entries ADD COLUMN user_id TEXT`
  - `ALTER TABLE entries ADD COLUMN external_id TEXT`
- `active_timer`: sin cambios (solo se usa en single-user deprecado)

**Helper**: `is_multiuser()` — retorna True si hay usuarios activos en tabla `users`. Todas las permission checks se bypassan si single-user mode.

> **Nota**: No se migra `active_timer` a multi-user. Los comandos de timer se deprecan. En multi-user el único flujo es `log`.

### Fase 2: Funciones CRUD nuevas (`lib/storage.py`)

- `save_user()`, `get_user()`, `list_users()`, `deactivate_user()`
- `add_role()`, `remove_role()`, `get_roles()` → retorna set
- `add_assignment()`, `remove_assignment()`, `get_assignments()`, `has_assignment()` — checkea client-level wildcard (`project_id IS NULL`) y specific project
- `get_entry_by_external_id(external_id)` — lookup por referencia externa (evitar duplicados, vincular con ticket)

**Settings y Categories (reemplazan constantes de config.py)**:

- `get_setting(key)` → retorna value o default de config.py si no existe en DB
- `set_setting(key, value)` → UPSERT en tabla `settings`
- `list_settings()` → retorna todas las settings
- `add_category(name)` → INSERT en `categories`
- `deactivate_category(name)` → soft delete (active=0)
- `list_categories(active_only=True)` → reemplaza `CATEGORIES` de config.py

### Fase 3: Capa de permisos (`lib/permissions.py` — NUEVO)

Funciones:

| Función | Uso |
|---------|-----|
| `resolve_user(user_id, require_user)` | En single-user retorna None. En multi-user valida que user existe y está activo. |
| `require_role(user_id, role)` | Para manager-only: client-add, project-add, user management |
| `check_log_entry(user_id, client_id, project_id)` | Manager→siempre, Collaborator→solo asignados, Timekeeper→denegado. En multi-user: valida que client_id, project_id y external_id estén presentes. |
| `check_view_entries(user_id)` | Manager/Timekeeper→'all', Collaborator→'own' |
| `check_modify_entry(user_id, entry_id)` | Manager→cualquiera, Collaborator→solo propias |
| `check_manage_clients(user_id)` | Manager only |
| `check_manage_users(user_id)` | Manager only |
| `check_manage_settings(user_id)` | Manager only — settings y categories |

### Fase 4: Modificar funciones storage existentes (`lib/storage.py`)

Solo funciones de entries agregan parámetros `user_id=None` y `external_id=None`. Funciones de timer **no se modifican**:

- `save_entry(user_id=..., external_id=...)` — incluye user_id y external_id en INSERT. En multi-user: rechaza si falta client_id, project_id o external_id.
- `get_entry(entry_id)` — sin cambios (entry_id es único global)
- `get_entry_by_external_id(external_id)` — lookup por referencia externa (nueva)
- `list_entries(user_id=..., external_id=...)` — filtro WHERE user_id=? (si scope='own'), filtro por external_id
- `search_entries(user_id=...)` — filtro por user_id en JOIN, FTS5 incluye external_id
- `get_summary(user_id=..., team=False)` — user_id filtra own, team=True muestra todo (manager/timekeeper)
- `get_stats(user_id=..., scope='own')` — scope 'own' o 'all' según rol
- `export_entries(user_id=...)` — filtro por user_id según permisos, external_id incluido en export
- `update_entry(entry_id, user_id=...)` — valida ownership si collaborator
- `delete_entry(entry_id, user_id=...)` — valida ownership si collaborator

### Fase 5: Cambios CLI (`nex-timetrack.py`)

**Helper nuevo**:
```python
def _resolve_user_id(args):
    user = args.user if hasattr(args, 'user') and args.user else None
    if not user:
        user = os.environ.get('HERMES_SESSION_USER_ID')
    if is_multiuser() and not user:
        print("Error: --user or HERMES_SESSION_USER_ID required in multi-user mode.")
        sys.exit(1)
    return user
```

**Timer commands — deprecated en multi-user**:

```python
def cmd_start(args):
    init_db()
    if is_multiuser():
        print("Warning: 'start' is deprecated in multi-user mode. Use 'log' to record time.")
        print(FOOTER)
        return
    # ... existing single-user logic unchanged

# idem cmd_stop, cmd_status, cmd_cancel
```

**10 comandos nuevos** (todos requieren manager):

| Comando | Args |
|---------|------|
| `user-add <user_id> --name "Name"` | Registra usuario |
| `user-list` | Lista usuarios con roles |
| `role-add <user_id> <role>` | Asigna rol |
| `role-remove <user_id> <role>` | Remueve rol |
| `assign <user_id> --client X [--project Y]` | Asigna a cliente/proyecto |
| `unassign <user_id> --client X [--project Y]` | Remueve asignación |
| `assignments [user_id]` | Lista asignaciones (sin user_id → todos, manager only) |
| `migrate --owner <user_id>` | Reclama entries legacy (NULL user_id) |
| `setting-get <key>` | Muestra valor de una setting |
| `setting-set <key> <value>` | Actualiza una setting (manager only) |
| `settings` | Lista todas las settings |
| `category-add <name>` | Agrega categoría (manager only) |
| `category-remove <name>` | Desactiva categoría (soft delete, manager only) |
| `categories` | Lista categorías activas (todos pueden ver) |

**Comandos existentes — flag `--user` + permisos**:

| Comando | Cambio |
|---------|--------|
| `log` | `--user`, `--client`, `--project`, `--external-id` requeridos en multi-user. `check_log_entry()` valida assignment y presencia de campos obligatorios. |
| `list` | `--user` opcional. `--external-id` para filtrar por referencia externa. Scope según rol ('all' o 'own') |
| `edit`, `delete` | `check_modify_entry()` — solo propias si collaborator |
| `show` | Muestra `external_id` si existe |
| `search` | FTS5 incluye `external_id` en índice. Filtra resultados según scope ('all' o 'own') |
| `summary` | `--user` individual, `--team` para equipo (manager/timekeeper) |
| `export` | Collaborator exporta propio, timekeeper/manager todo. `external_id` incluido en export |
| `client-add`, `project-add` | `check_manage_clients()` — manager only |
| `clients`, `projects` | Sin cambios — todos ven entidades compartidas |

### Fase 6: Eliminar `lib/config.py` — toda configuración a DB

`lib/config.py` se **elimina**. Todas las constantes migran a tablas `settings` y `categories`. Solo se conservan `DATA_DIR`, `DB_PATH`, `EXPORT_DIR` como constantes en `storage.py` (paths del filesystem, no configuración de negocio).

**ROLES** se mueve como constante en `lib/permissions.py` (no es configurable por managers).

**Funciones de acceso en `storage.py`**:

```python
# Paths — constantes en storage.py
DATA_DIR = Path(os.environ.get("NEX_TIMETRACK_DIR", Path.home() / ".nex-timetrack"))
DB_PATH = DATA_DIR / "timetrack.db"
EXPORT_DIR = DATA_DIR / "exports"

def get_setting(key, default=None):
    """Lee setting de DB. Retorna default si no existe."""
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row:
            if key in ('default_rate',): return float(row['value'])
            if key in ('round_to_minutes',): return int(row['value'])
            return row['value']
    return default

def set_setting(key, value):
    """UPSERT setting."""
    with _connect() as conn:
        conn.execute("""
            INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')
        """, (key, str(value)))

def list_settings():
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value, updated_at FROM settings ORDER BY key")
        return [dict(r) for r in cursor.fetchall()]

def get_categories(active_only=True):
    """Reemplaza CATEGORIES de config.py."""
    with _connect() as conn:
        cursor = conn.cursor()
        query = "SELECT name FROM categories"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY name"
        cursor.execute(query)
        return [r['name'] for r in cursor.fetchall()]

def add_category(name):
    with _connect() as conn:
        conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))

def deactivate_category(name):
    with _connect() as conn:
        conn.execute("UPDATE categories SET active = 0 WHERE name = ?", (name,))
```

**Seed en `init_db()`** (valores iniciales, solo si tabla vacía):

```sql
INSERT OR IGNORE INTO settings (key, value) VALUES
    ('default_rate', '85.00'), ('currency', 'EUR'),
    ('currency_symbol', '€'), ('round_to_minutes', '15');

INSERT OR IGNORE INTO categories (name) VALUES
    ('development'), ('design'), ('meeting'), ('research'), ('admin'),
    ('support'), ('review'), ('testing'), ('deployment'), ('planning'),
    ('communication'), ('other');
```

**Migración de referencias** — todos los `from lib.config import ...` se eliminan:

| Antes (config.py) | Después (storage.py / DB) |
|---|---|
| `DEFAULT_RATE` | `get_setting('default_rate')` |
| `CURRENCY_SYMBOL` | `get_setting('currency_symbol')` |
| `CURRENCY` | `get_setting('currency')` |
| `ROUND_TO_MINUTES` | `get_setting('round_to_minutes')` |
| `CATEGORIES` | `get_categories()` |
| `DATA_DIR`, `DB_PATH`, `EXPORT_DIR` | Constantes en `storage.py` |
| `BILLABLE`, `NON_BILLABLE` | Constantes en `nex-timetrack.py` (strings) |
| `SEPARATOR`, `SUBSEPARATOR` | Constantes en `nex-timetrack.py` (display) |

### Fase 7: SKILL.md

Actualizar instrucciones con:
- Flujo multi-usuario: solo `log` (no timer)
- Comandos multi-usuario con `--user $HERMES_SESSION_USER_ID`
- Sección admin (manager-only)
- Tabla de permisos por rol
- Timer commands marcados como deprecated

### Fase 8: setup.sh

Agregar llamada a `init_db()` post-instalación para ejecutar migraciones.

## Orden de implementación

1. `lib/storage.py` — paths + schema migration + settings/categories functions + seed
2. `lib/permissions.py` — nueva capa + constante ROLES
3. `lib/storage.py` — funciones CRUD nuevas (users, roles, assignments) + modificar existentes (user_id, external_id)
4. `nex-timetrack.py` — eliminar imports de config.py, deprecate timer commands, comandos nuevos, modificar existentes
5. `lib/config.py` — **eliminar archivo**
6. `SKILL.md` — instrucciones actualizadas
7. `setup.sh` — migración

## Decisiones de diseño

- **DB única compartida** (no por usuario) — clients/projects son compartidos
- **user_id = mattermost_id** — viene de `HERMES_SESSION_USER_ID`, no hay auth extra
- **Backward compatible** — si no hay usuarios en tabla, funciona como antes
- **NULL user_id legacy** — entries antiguos quedan NULL, `migrate --owner` los reclama
- **Permisos explícitos** — cada comando llama check explícito, no decorator
- **Timer deprecado en multi-user** — no se migra `active_timer`. El flujo es exclusivamente `log` post-actividad. Timer commands siguen funcionando en single-user.
- **Storage filtra, permissions valida** — storage recibe `user_id` solo como filtro de datos. Validación de permisos es responsabilidad exclusiva de `permissions.py`.
- **External ID obligatorio en multi-user** — todo entry debe referenciar un ticket/issue externo (JIRA, AzureDevOps, GitHub). En single-user es opcional para backward compat.
- **Campos obligatorios en multi-user** — client, project, external_id y description son requeridos. Se valida en `check_log_entry()` antes de INSERT.

## Modelo de permisos por rol

| Acción | Manager | Timekeeper | Collaborator |
|--------|---------|------------|--------------|
| `log` tiempo | ✅ cualquier cliente | ❌ denegado | ✅ solo asignados |
| `list` entries | ✅ todos | ✅ todos | ✅ solo propios |
| `edit`/`delete` entries | ✅ cualquiera | ❌ | ✅ solo propios |
| `summary` equipo | ✅ | ✅ | ❌ solo propio |
| `search` | ✅ todos | ✅ todos | ✅ solo propios |
| `export` | ✅ todo | ✅ todo | ✅ solo propio |
| `client-add`/`project-add` | ✅ | ❌ | ❌ |
| `user-add`/`role-*`/`assign` | ✅ | ❌ | ❌ |
| `clients`/`projects` (lectura) | ✅ | ✅ | ✅ |

## Verificación

1. `setup.sh` limpia — crear DB desde cero con nuevo schema
2. Registrar usuario → asignar rol collaborator → asignar a cliente → loguear tiempo → verificar entry tiene user_id
3. Verificar collaborator no puede loguear en cliente no asignado → PermissionDenied
4. Verificar timekeeper puede ver entries de todos pero no loguear
5. Verificar manager puede todo
6. `migrate --owner` — reclamar entries legacy
7. Sin usuarios registrados → comportamiento single-user sin cambios
8. Timer commands en single-user → funcionan normalmente
9. Timer commands en multi-user → warning + no-op
10. `assignments` sin user_id → lista todos (manager), error si no-manager
11. `log` sin `--client`, `--project` o `--external-id` en multi-user → error claro con campos faltantes
12. `log` con `--external-id` duplicado → warning (no error, puede haber múltiples entries para mismo ticket)
13. `list --external-id JIRA-123` → filtra entries por referencia externa
