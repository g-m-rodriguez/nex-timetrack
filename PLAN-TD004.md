# Audit Log Implementation Plan

## Context

Un agente de IA usó el `user_id` visible en outputs para impersonar un manager y crear usuarios. Esto demostró que necesitamos trazabilidad completa de quién hizo qué y cuándo. El audit log captura automaticamente toda mutación en el sistema (create/update/delete) con diff completo antes/después, sin intervención del usuario ni comando CLI adicional.

## Schema

```sql
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    action TEXT NOT NULL,              -- 'create','update','delete'
    actor_id TEXT,                     -- Mattermost sender_id (NULL en single-user/bootstrap)
    entity_type TEXT NOT NULL,         -- 'entry','client','project','user','role','assignment','setting','category','timer'
    entity_id TEXT NOT NULL,           -- PK del registro afectado
    before_json TEXT,                  -- JSON snapshot ANTES (NULL para creates)
    after_json TEXT,                   -- JSON snapshot DESPUÉS (NULL para deletes)
    metadata TEXT                      -- JSON extra context (reason, role, etc.)
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_id);
```

## Arquitectura

**Capa de implementación: `lib/storage.py`** (no CLI)

Razones:
1. **Atomicidad** — `_audit()` usa la misma conexión/transaction que la mutación. Si el INSERT del audit falla, la mutación hace rollback.
2. **Completitud** — todo path que muta datos pasa por storage. Ningún caller puede bypassar el audit.
3. **Simplicidad** — cada función storage ya sabe qué tabla muta y cuál es el PK.

**Helper central:**

```python
def _audit(conn, action, entity_type, entity_id, actor_id=None, before=None, after=None, metadata=None):
    conn.execute("""
        INSERT INTO audit_log (action, actor_id, entity_type, entity_id, before_json, after_json, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (action, actor_id, entity_type, str(entity_id),
          json.dumps(before) if before else None,
          json.dumps(after) if after else None,
          json.dumps(metadata) if metadata else None))
```

## Patrón por tipo de mutación

**CREATE** — `before=None`, `after` = snapshot del registro creado
**UPDATE** — `before` = SELECT antes de UPDATE, `after` = SELECT después
**DELETE** — `before` = SELECT antes de DELETE, `after=None`

## Cambios por archivo

### 1. `lib/storage.py`

- Agregar tabla + indexes en `init_db()` (migration block al final)
- Agregar `_audit()` helper privado (~10 líneas)
- Agregar `actor_id=None` a las 24 funciones mutantes
- Agregar captura de before/after y llamada a `_audit()` en cada una

**24 funciones a modificar:**

| Función | Action | Entity | Notes |
|---|---|---|---|
| `save_entry` | create | entry | `after` from inputs |
| `update_entry` | update | entry | before/after SELECT |
| `delete_entry` | delete | entry | before SELECT |
| `start_timer` | create | timer | after from inputs |
| `stop_timer` | create+delete | entry+timer | 2 audit records |
| `cancel_timer` | delete | timer | before SELECT |
| `save_client` | create | client | after from inputs |
| `rename_client` | update | client | before/after SELECT |
| `deactivate_client` | update | client | before/after SELECT |
| `reactivate_client` | update | client | before/after SELECT |
| `save_project` | create | project | after from inputs |
| `deactivate_project` | update | project | before/after SELECT |
| `reactivate_project` | update | project | before/after SELECT |
| `record_approval` | update | entry | before/after + metadata con reason |
| `save_user` | create/update | user | check existence para distinguir |
| `deactivate_user` | update | user | before/after SELECT |
| `add_role` | create | role | entity_id = `"user_id:role"` |
| `remove_role` | delete | role | entity_id = `"user_id:role"` |
| `add_assignment` | create | assignment | after from inputs |
| `remove_assignment` | delete | assignment | before SELECT |
| `set_setting` | create/update | setting | check existence |
| `add_category` | create | category | after from inputs |
| `deactivate_category` | update | category | before/after SELECT |

### 2. `nex-timetrack.py`

Cambio mecánico: agregar `actor_id=user_id` a cada llamada de storage function.

Ejemplo:
```python
# Antes:
entry_id = save_entry(description=..., user_id=user_id, ...)
# Después:
entry_id = save_entry(description=..., user_id=user_id, actor_id=user_id, ...)
```

Para bootstrap (user-add sin manager), `actor_id` queda `None` — correcto.

### 3. `test_nex_timetrack.py`

Agregar `TestAuditLog` class. Ver detalle de test cases abajo.

### 4. `TECHNICAL_DOC.md`

Documentar schema de `audit_log` y patrón de uso. Actualizar sección Deuda Técnica TD-004 estado a "Implementado".

### 5. `TEST-PLAN.md`

Agregar sección **26. Audit Log** con los test cases detallados abajo. Actualizar resumen con nuevos totales.

### 6. `TECH-DEBT.md`

Cambiar estado de TD-004 de "Planificado" a "✅ Implementado".

## No cambiar

- `entry_approvals` table — sigue siendo la fuente de historia de aprobaciones
- No agregar comando CLI — solo accesible via DB directa
- `lib/permissions.py` — sin cambios
- Todas las funciones read-only (get_*, list_*, search_*, etc.)

## Migration

`CREATE TABLE IF NOT EXISTS` — idempotente, no rompe DBs existentes. Audit log arranca vacío, captura hacia adelante.

## Verification

1. `python3 -m pytest test_nex_timetrack.py -x -q` — 185 tests existentes + nuevos audit tests pasan
2. Test manual: ejecutar flujo completo (user-add → client-add → log → approve) y verificar audit_log via `sqlite3 ~/.nex-timetrack/timetrack.db "SELECT * FROM audit_log"`
3. Verificar que `before_json` y `after_json` contienen diffs correctos

---

## Test Cases — Sección 26: Audit Log

### 26. Audit Log (TST-191 a TST-214) — 24 test cases

| ID | Descripción | Tipo | Qué verifica |
|---|---|---|---|
| TST-191 | Audit on user-add (create) | V | audit_log tiene action='create', entity_type='user', after_json con name, before_json NULL |
| TST-192 | Audit on role-add (create) | V | audit_log tiene action='create', entity_type='role', entity_id='user_id:role', metadata con role |
| TST-193 | Audit on role-remove (delete) | V | audit_log tiene action='delete', entity_type='role', before_json con datos del role |
| TST-194 | Audit on client-add (create) | V | audit_log tiene action='create', entity_type='client', after_json con name y rate |
| TST-195 | Audit on client-rename (update) | V | audit_log tiene action='update', entity_type='client', before_json.name≠after_json.name |
| TST-196 | Audit on client-deactivate (update) | V | audit_log tiene action='update', before_json.active=1, after_json.active=0 |
| TST-197 | Audit on project-add (create) | V | audit_log tiene action='create', entity_type='project', after_json con datos |
| TST-198 | Audit on assignment create/delete | V | assign genera 'create', unassign genera 'delete' con before_json |
| TST-199 | Audit on log entry (create) | V | audit_log tiene action='create', entity_type='entry', after_json con description, duration |
| TST-200 | Audit on edit entry (update) | V | audit_log tiene action='update', entity_type='entry', before_json con valor original, after_json con nuevo |
| TST-201 | Audit on delete entry (delete) | V | audit_log tiene action='delete', entity_type='entry', before_json con datos, after_json NULL |
| TST-202 | Audit on approve (update) | V | audit_log tiene action='update', entity_type='entry', metadata con approval_action='approved' |
| TST-203 | Audit on reject (update) | V | audit_log tiene action='update', entity_type='entry', metadata con approval_action='rejected' y reason |
| TST-204 | Audit on setting-set (create) | V | Setting nuevo: action='create', entity_type='setting', before_json NULL |
| TST-205 | Audit on setting-set (update) | V | Setting existente: action='update', before_json con valor viejo, after_json con nuevo |
| TST-206 | Audit on category-add (create) | V | audit_log tiene action='create', entity_type='category' |
| TST-207 | Audit on category-remove (update) | V | audit_log tiene action='update', entity_type='category', before_json.active=1, after_json.active=0 |
| TST-208 | Audit on user-deactivate (update) | V | audit_log tiene action='update', entity_type='user', before_json.active=1, after_json.active=0 |
| TST-209 | Audit actor_id correcto | V | Cada audit entry tiene actor_id = user_id del manager que ejecutó la acción |
| TST-210 | Audit actor_id NULL en bootstrap | V | Primer user-add (sin managers) genera audit con actor_id NULL |
| TST-211 | Read-only commands no generan audit | V | Ejecutar show, list, clients, projects, settings — verificar 0 audit entries |
| TST-212 | Audit timestamp populated | V | Todas las audit entries tienen timestamp no-NULL y formato ISO válido |
| TST-213 | Audit client-reactivate (update) | V | audit_log tiene action='update', entity_type='client', before_json.active=0, after_json.active=1 |
| TST-214 | Audit project-deactivate/reactivate | V | deactivate genera update active=0, reactivate genera update active=1 |

**Resumen audit:** 24 tests (24 válidos, 0 inválidos)

### TEST-PLAN.md — Resumen actualizado

| Dominio | Casos | Válidos | Inválidos |
|---------|-------|---------|-----------|
| ... (secciones 1-25 iguales) | | | |
| Audit Log | 24 | 24 | 0 |
| **Total** | **218** | **151** | **67** |
