# Deuda Técnica — nex-timetrack

Registro de mejoras pendientes, ideas a implementar y bugs a corregir.

---

## Bugs

<!-- Fecha: YYYY-MM-DD | Contexto breve -->

## Mejoras pendientes

| ID | Fecha | Descripción | Prioridad | Estado |
|----|-------|-------------|-----------|--------|
| TD-001 | 2026-06-03 | Rol **approver** con workflow de aprobación de horas. Ver [PLAN-APPROVER.md](PLAN-APPROVER.md) | Alta | Planificado |
| TD-002 | 2026-06-03 | ~~Hacer `project_id` y `client_id` NOT NULL en entries~~ | Media | ✅ Completado |

## Ideas / Propuestas

| ID | Fecha | Descripción | Notas |
|----|-------|-------------|-------|
| TI-001 | 2026-06-03 | Skipped (reservado) | |
| TD-003 | 2026-06-04 | **Budget de horas por proyecto con control de exceso**. Al crear proyecto: indicar si tiene budget y si es mensual o total. Manager/timekeeper: ver consumo reportado y remanente. Approver: ver budget consumido y restante antes/después de aprobar horas. Si aprobación excede budget (total o mensual), approver debe justificar motivo. Requiere: schema (projects: budget_type 'monthly'|'total'|NULL, budget_hours ya existe), storage functions para cálculo de consumo, modificación de `pending`/`approve` para mostrar budget y exigir razón si excede. | Alta | Pendiente |
