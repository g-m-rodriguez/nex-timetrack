# Deuda Técnica — nex-timetrack

Registro de mejoras pendientes, ideas a implementar y bugs a corregir.

---

## Bugs

<!-- Fecha: YYYY-MM-DD | Contexto breve -->

## Mejoras pendientes

| ID | Fecha | Descripción | Prioridad | Estado |
|----|-------|-------------|-----------|--------|
| TD-001 | 2026-06-03 | Rol **approver** con workflow de aprobación de horas. Ver [PLAN-APPROVER.md](PLAN-APPROVER.md) | Alta | Planificado |
| TD-002 | 2026-06-03 | Hacer `project_id` y `client_id` NOT NULL en entries. Migrar entries existentes sin client/project (decision: eliminarlas o reasignar). Actualizar `save_entry()` para requerir ambos campos. Agregar regla en SKILL.md security rules recordando al agente que **siempre** pasar `--client` y `--project` al loguear tiempo. | Media | Pendiente |

## Ideas / Propuestas

| ID | Fecha | Descripción | Notas |
|----|-------|-------------|-------|
| TI-001 | 2026-06-03 | Skipped (reservado) | |
