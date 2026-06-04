# Plan: Rol Approver - Aprobación de horas

## Context

nex-timetrack necesita un rol `approver` que revise y apruebe/rechace horas reportadas por colaboradores. Granularidad: por entry individual, por día, o por semana (Lun-Dom). Approvers asignados por cliente/proyecto. Roles se acumulan (approver puede loguear horas propias). Rechazo con motivo. Propio flujo de aprobación deshabilitado por defecto.

---

## Fase 1: Schema y Storage (`lib/storage.py`)

### 1a. Setting `approval_required`
Agregar a `SETTING_TYPE_MAP` (L23) y `SETTING_DEFAULTS` (L28):
```python
'approval_required': bool,   # TYPE_MAP
'approval_required': False,  # DEFAULTS
```

### 1b. Nueva tabla `entry_approvals` en `init_db()` executescript (después de categories)
```sql
CREATE TABLE IF NOT EXISTS entry_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL,
    approver_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('approved','rejected')),
    reason TEXT,
    approved_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE,
    FOREIGN KEY (approver_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_approvals_entry ON entry_approvals(entry_id);
CREATE INDEX IF NOT EXISTS idx_approvals_approver ON entry_approvals(approver_id);
```

### 1c. Migración post-executescript en `init_db()`
1. Agregar columna `approval_status` a entries si no existe:
   ```sql
   ALTER TABLE entries ADD COLUMN approval_status TEXT DEFAULT 'pending'
       CHECK(approval_status IN ('pending','approved','rejected'));
   CREATE INDEX IF NOT EXISTS idx_entries_approval ON entries(approval_status);
   ```
2. Expandir CHECK de `user_roles` para incluir `'approver'`. SQLite no soporta ALTER COLUMN → rebuild table con savepoint test:
   - Intentar INSERT de 'approver' en savepoint
   - Si falla: crear `user_roles_new`, copiar datos, drop, rename

### 1d. Nuevas funciones storage
- `record_approval(entry_id, approver_id, action, reason=None)` → insert en `entry_approvals` + update `entries.approval_status`
- `get_pending_entries(approver_id, client_id=None, project_id=None, for_user=None, date_from=None, date_to=None)` → entries pending que el approver puede aprobar (join con assignments, excluyendo entries propias). Filtrable por user, proyecto, cliente, rango fechas
- `get_approval_history(entry_id)` → historial de aprobaciones/rechazos

### 1e. Modificar `save_entry()` (L498)
- Agregar `approval_status` al INSERT: `'pending'` si `get_setting('approval_required')`, sino `'approved'`

### 1f. Modificar `update_entry()` (L596)
- Si `approval_status` es `'approved'` o `'rejected'`, resetear a `'pending'` (entrada interna, no en `allowed` set)

---

## Fase 2: Permisos (`lib/permissions.py`)

### 2a. Nuevo import
```python
from lib.storage import ..., get_setting, get_entry
```

### 2b. Nueva función `check_approve_entry(approver_id, entry_id)`
Valida:
1. Multi-user activo
2. `approval_required` setting True
3. User tiene rol `approver` o `manager`
4. Entry existe y status es `pending`
5. Approver != entry.user_id **solo si no es manager** (manager puede auto-aprobarse)
6. Approver asignado al client/project del entry (vía `has_assignment`) — manager exempt, puede aprobar cualquier entry

### 2c. Nueva función `check_view_approvals(user_id)`
- manager/approver/timekeeper → `'all'`
- collaborator → `'own_rejections'`

### 2d. Modificar funciones existentes
- `check_log_entry()` (L54): Agregar `approver` — mismo flujo que collaborator (necesita assignment)
- `check_view_entries()` (L80): Agregar `approver` al scope `'all'`
- `check_modify_entry()` (L94): Agregar `approver` — solo puede modificar entries propias
- `check_view_users()` (L128): Agregar `approver` — puede ver users

---

## Fase 3: CLI (`nex-timetrack.py`)

### 3a. Actualizar choices de role
Líneas 1335 y 1342: agregar `'approver'` al choices list.

### 3b. Nuevos comandos (5 subparsers + handlers)

**Comando central: `pending`** — Approver consulta horas pendientes con filtros. Output incluye IDs para luego aprobar/rechazar.

| Comando | Args | Descripción |
|---------|------|-------------|
| `pending` | `--user`, `--project`, `--client`, `--date-from`, `--date-to` | Listar entries pendientes con IDs. Dos modos de uso: (a) por persona + rango fechas, (b) por proyecto (todas las personas) + rango fechas |
| `approve` | `ids+` (int) | Aprobar entries por ID |
| `reject` | `ids+` (int), `--reason` (required) | Rechazar entries con motivo |
| `rejections` | (sin args extra) | Ver entries propias rechazadas (collaborator) |
| `approval-history` | `id` (int) | Ver historial de aprobación de un entry |

**Output de `pending`** (ejemplo por persona):
```
$ nex-timetrack pending --user alice --date-from 2026-06-01 --date-to 2026-06-03
ID    Date        Duration   Description              Client       Project
---------------------------------------------------------------------------
42    2026-06-01  2h 30m     API integration          Acme Corp    Backend
43    2026-06-01  1h 15m     Code review              Acme Corp    Backend
44    2026-06-02  3h 00m     Bug fix                  Acme Corp    Backend
45    2026-06-03  4h 00m     Feature dev              Beta Inc     Frontend
Total: 4 entries pending approval for alice

$ nex-timetrack approve 42 43
$ nex-timetrack reject 44 --reason "Need more detail in description"
```

**Output de `pending`** (ejemplo por proyecto):
```
$ nex-timetrack pending --project Backend --date-from 2026-06-01 --date-to 2026-06-03
ID    Date        User        Duration   Description              Client
---------------------------------------------------------------------------
42    2026-06-01  alice       2h 30m     API integration          Acme Corp
43    2026-06-01  alice       1h 15m     Code review              Acme Corp
46    2026-06-02  bob         5h 00m     DB migration             Acme Corp
Total: 3 entries pending approval for project Backend
```

**Eliminados**: `approve-day`, `reject-day`, `approve-week`, `reject-week`. Flujo simplificado: approver consulta con `pending` + filtros, luego aprueba/rechaza por IDs individuales.

### 3c. Handlers pattern (ejemplo `cmd_approve`)
```python
def cmd_approve(args):
    init_db()
    approver_id = _resolve_user_id(args)
    for eid in args.ids:
        try:
            check_approve_entry(approver_id, eid)
            record_approval(eid, approver_id, 'approved')
            print(f"Entry #{eid} approved.")
        except PermissionDenied as e:
            print(f"Entry #{eid} skipped: {e}")
    print(FOOTER)
```

### 3d. Modificar comandos existentes
- `cmd_show`: mostrar approval_status y rejection reason si aplica
- `cmd_list`: agregar columna Status cuando `approval_required` True
- `cmd_edit`: advertir si entry approved → resetea a pending
- `cmd_log`: mostrar "Status: pending approval" cuando `approval_required` True

---

## Edge Cases

- **Auto-aprobación**: Bloqueada para approvers. Managers **pueden** auto-aprobarse.
- **Dual role**: Approver con rol collaborator puede loguear horas. Sus entries necesitan aprobación de otro.
- **Entries sin client/project**: Solo manager puede aprobarlas (sin scope check).
- **Workflow deshabilitado**: `approval_required=False` (default) → entries nuevas nacen `approved`. Comandos de approval avisan que workflow no está habilitado.
- **Edición de entry approved**: Resetea a `pending` automáticamente.
- **Rechazo → edición → re-aprobación**: Ciclo natural. Entry rechazada, colaborador edita, vuelve a pending.

---

## Archivos Críticos

| Archivo | Cambio |
|---------|--------|
| [lib/storage.py](lib/storage.py) | Schema migration, 3 funciones nuevas, modificar save_entry/update_entry, SETTING_DEFAULTS |
| [lib/permissions.py](lib/permissions.py) | 2 funciones nuevas (check_approve_entry, check_view_approvals), modificar 4 existentes |
| [nex-timetrack.py](nex-timetrack.py) | 5 comandos nuevos, 4 modificaciones existentes, 2 updates de choices |

---

## Orden de Implementación

1. Schema + storage (Fase 1) — base de todo
2. Permisos (Fase 2) — gate para CLI
3. CLI comandos nuevos (Fase 3a-3c)
4. CLI modificaciones existentes (Fase 3d)
5. Verificación end-to-end

## Verificación

1. Inicializar DB limpia, verificar migración sin errores
2. Crear user collaborator + approver, asignar roles
3. Asignar approver a client/project via `assign`
4. Loguear entries como collaborator → verificar status `pending`
5. `pending` como approver → ver entries del collaborator
6. `approve` entries → verificar status `approved`
7. `reject` con reason → verificar collaborador ve rechazo via `rejections`
8. Editar entry approved → verificar reset a `pending`
9. `pending --project Backend --date-from ... --date-to ...` → ver entries de múltiples usuarios
10. Intentar auto-aprobación como approver → verificar PermissionDenied
11. Auto-aprobación como manager → verificar permitido
12. Con `approval_required=false` → entries nuevas nacen `approved`
