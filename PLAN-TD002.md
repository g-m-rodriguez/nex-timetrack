# Plan: TD-002 — project_id y client_id NOT NULL en entries

## Context

Entries sin client/project no tienen sentido en un sistema de facturación. `project_id` y `client_id` actualmente son nullable en el schema. TD-002 los hace NOT NULL + agrega validación + SKILL.md recuerda al agente pasar siempre estos campos.

No hay entries huérfanas en producción → no necesita migración de datos.

---

## Cambios

### 1. Schema (`lib/storage.py` → `init_db()` executescript)

En `CREATE TABLE entries`, cambiar:
```sql
-- Antes:
project_id INTEGER,
client_id INTEGER,

-- Después:
project_id INTEGER NOT NULL,
client_id INTEGER NOT NULL,
```

### 2. Validación en `save_entry()` (`lib/storage.py` L498)

Agregar check al inicio de la función:
```python
if not client_id:
    raise ValueError("client_id is required")
if not project_id:
    raise ValueError("project_id is required")
```

### 3. Validación en `update_entry()` (`lib/storage.py` L596)

Si kwargs incluye `client_id=None` o `project_id=None`, rechazar:
```python
if 'client_id' in fields and fields['client_id'] is None:
    raise ValueError("client_id cannot be null")
if 'project_id' in fields and fields['project_id'] is None:
    raise ValueError("project_id cannot be null")
```

### 4. CLI handler `cmd_log()` (`nex-timetrack.py` L217)

Ya resuelve client/project antes de llamar save_entry. Agregar check explícito:
```python
if not client_id:
    print("Error: --client is required.")
    sys.exit(1)
if not project_id:
    print("Error: --project is required.")
    sys.exit(1)
```

### 5. CLI handler `cmd_edit()` (`nex-timetrack.py`)

Si el usuario intenta quitar client o project via edit, rechazar. (Ya existe validación de client active, agregar check de None).

### 6. SKILL.md — Security rule #6

Agregar regla:
```markdown
### 6. Always pass client and project when logging time
`--client` and `--project` are required fields for every time entry. If the user
does not specify them, ask before proceeding. Never log time without a client
and project.
```

### 7. SKILL.md — Required Fields

Actualizar sección "Required Fields in Multi-User" para indicar que son required **siempre**, no solo para collaborators:

```markdown
When logging time, these fields are always required:
- `--client` — client name (required, all roles)
- `--project` — project name (required, all roles)
- `--external-id` — external ticket reference
- `description` — what was done
- `duration` — time spent
```

### 8. TECH-DEBT.md

Marcar TD-002 como completado.

---

## Archivos

| Archivo | Cambio |
|---------|--------|
| `lib/storage.py` | Schema NOT NULL, validación en save_entry/update_entry |
| `nex-timetrack.py` | Validación explícita en cmd_log/cmd_edit |
| `SKILL.md` | Security rule #6 + Required Fields update |
| `TECH-DEBT.md` | Marcar TD-002 completado |

## Verificación

1. `nex-timetrack log "test" 1h` sin --client → error "client is required"
2. `nex-timetrack log "test" 1h --client Acme` sin --project → error "project is required"
3. `nex-timetrack log "test" 1h --client Acme --project Web` → funciona
4. Editar entry quitando client → error
5. Deploy a Hermes
