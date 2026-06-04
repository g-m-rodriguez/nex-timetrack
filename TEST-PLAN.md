# Test Plan — nex-timetrack

Todos los casos de uso válidos e inválidos, codificados TST-XXX para automatización.

**Convenciones**:
- ✅ = caso válido (esperado: éxito)
- ❌ = caso inválido (esperado: error específico)
- Roles: `MGR` = manager, `TK` = timekeeper, `COL` = collaborator, `APR` = approver
- Setup base por sección: DB limpia + users con roles asignados

---

## 1. Bootstrap

| ID | Tipo | Descripción | Precondiciones | Resultado esperado |
|----|------|-------------|----------------|--------------------|
| TST-001 | ✅ | Primer user-add sin managers | DB vacía, sin users | User creado sin requerir permisos |
| TST-002 | ✅ | Primer role-add manager (bootstrap) | TST-001, sin managers | Rol manager auto-asignado sin permisos |
| TST-003 | ❌ | User-add con managers existentes como no-manager | Managers existen | PermissionDenied |
| TST-004 | ✅ | Segundo user-add por manager | Managers existen, caller=MGR | User creado |
| TST-005 | ❌ | Role-add por no-manager | Caller=COL | PermissionDenied |

---

## 2. Users CRUD

| ID | Tipo | Descripción | Caller | Resultado esperado |
|----|------|-------------|--------|--------------------|
| TST-006 | ✅ | user-add con name | MGR | User creado |
| TST-007 | ✅ | user-list | MGR | Lista con roles y estado |
| TST-008 | ✅ | user-list | TK | Lista con roles y estado |
| TST-009 | ✅ | user-list | APR | Lista con roles y estado |
| TST-010 | ❌ | user-list | COL | PermissionDenied |
| TST-011 | ✅ | user-deactivate con --confirm | MGR | User desactivado |
| TST-012 | ❌ | user-deactivate sin --confirm | MGR | Mensaje de confirmación requerida |
| TST-013 | ❌ | user-deactivate | COL | PermissionDenied |
| TST-014 | ❌ | Operación como user desactivado | User inactivo | PermissionDenied: "User X is deactivated" |
| TST-015 | ❌ | user-add user_id inexistente como caller | User no registrado | PermissionDenied: "Unknown user" |

---

## 3. Roles

| ID | Tipo | Descripción | Caller | Resultado esperado |
|----|------|-------------|--------|--------------------|
| TST-016 | ✅ | role-add collaborator | MGR | Rol asignado |
| TST-017 | ✅ | role-add timekeeper | MGR | Rol asignado |
| TST-018 | ✅ | role-add approver | MGR | Rol asignado |
| TST-019 | ✅ | role-add manager | MGR | Rol asignado |
| TST-020 | ✅ | role-remove | MGR | Rol removido |
| TST-021 | ❌ | role-add rol inválido | MGR | Error: invalid choice |
| TST-022 | ❌ | role-add | COL | PermissionDenied |
| TST-023 | ✅ | Dual role: approver + collaborator | MGR | Ambos roles asignados |

---

## 4. Clients CRUD

| ID | Tipo | Descripción | Caller | Resultado esperado |
|----|------|-------------|--------|--------------------|
| TST-024 | ✅ | client-add con rate | MGR | Client creado |
| TST-025 | ✅ | client-add sin rate | MGR | Client creado con rate NULL |
| TST-026 | ✅ | clients (listar) | Cualquiera | Lista con nombre, rate, Active |
| TST-027 | ✅ | client-rename | MGR | Client renombrado |
| TST-028 | ❌ | client-rename | COL | PermissionDenied |
| TST-029 | ❌ | client-rename client inexistente | MGR | "Client 'X' not found." |
| TST-030 | ✅ | client-deactivate con --confirm | MGR | Client desactivado |
| TST-031 | ❌ | client-deactivate sin --confirm | MGR | Mensaje de confirmación |
| TST-032 | ❌ | client-deactivate | COL | PermissionDenied |
| TST-033 | ✅ | client-reactivate | MGR | Client reactivado |
| TST-034 | ❌ | client-reactivate client inexistente | MGR | "Client 'X' not found." |

---

## 5. Projects CRUD

| ID | Tipo | Descripción | Caller | Precondiciones | Resultado esperado |
|----|------|-------------|--------|----------------|--------------------|
| TST-035 | ✅ | project-add con client activo | MGR | Client activo | Project creado |
| TST-036 | ✅ | project-add sin client | MGR | — | Project creado sin client |
| TST-037 | ❌ | project-add con client inactivo | MGR | Client desactivado | "Client is deactivated. Cannot add projects." |
| TST-038 | ✅ | projects (listar activos) | Cualquiera | — | Solo proyectos activos |
| TST-039 | ✅ | projects --all | Cualquiera | — | Todos los proyectos |
| TST-040 | ✅ | project-deactivate con --confirm | MGR | Client activo | Project desactivado |
| TST-041 | ❌ | project-deactivate sin --confirm | MGR | — | Mensaje de confirmación |
| TST-042 | ❌ | project-deactivate con client inactivo | MGR | Client desactivado | "Client is deactivated. Reactivate client first." |
| TST-043 | ❌ | project-deactivate | COL | — | PermissionDenied |
| TST-044 | ✅ | project-reactivate | MGR | Client activo | Project reactivado |
| TST-045 | ❌ | project-reactivate con client inactivo | MGR | Client desactivado | "Client is deactivated. Reactivate client first." |

---

## 6. Assignments

| ID | Tipo | Descripción | Caller | Resultado esperado |
|----|------|-------------|--------|--------------------|
| TST-046 | ✅ | assign user a client+project | MGR | Assignment creado |
| TST-047 | ✅ | assign user a client solo (wildcard) | MGR | Assignment creado (project_id=NULL) |
| TST-048 | ❌ | assign user | COL | PermissionDenied |
| TST-049 | ✅ | unassign | MGR | Assignment removido |
| TST-050 | ✅ | assignments (sin user_id) | MGR | Todas las asignaciones |
| TST-051 | ✅ | assignments user_id específico | MGR | Asignaciones del user |

---

## 7. Entries CRUD — Log

| ID | Tipo | Descripción | Caller | Precondiciones | Resultado esperado |
|----|------|-------------|--------|----------------|--------------------|
| TST-052 | ✅ | log entry completo | MGR | Client/project activos | Entry creado, status=approved (approval_required=false) |
| TST-053 | ✅ | log entry con approval_required=true | COL | Workflow activo | Entry creado, status=pending. Output: "Status: pending approval" |
| TST-054 | ❌ | log sin --client | COL | Multi-user | "Error: --client is required." |
| TST-055 | ❌ | log sin --project | COL | Multi-user | "Error: --project is required." |
| TST-056 | ❌ | log con client inactivo | COL | Client desactivado | "Error: Client is deactivated. Time logging not allowed." |
| TST-057 | ❌ | log con project inactivo | COL | Project desactivado | "Error: Project is deactivated. Time logging not allowed." |
| TST-058 | ❌ | log como timekeeper | TK | — | PermissionDenied: "Timekeepers cannot log time entries." |
| TST-059 | ❌ | log sin assignment | COL | No asignado al client/project | PermissionDenied: "Not assigned to client/project" |
| TST-060 | ✅ | log como collaborator asignado | COL | Asignado al client/project | Entry creado |
| TST-061 | ✅ | log como approver asignado | APR | Asignado al client/project | Entry creado |
| TST-062 | ✅ | log con --external-id | COL | — | Entry con external_id |
| TST-063 | ✅ | log con --date pasada | COL | — | Entry con fecha especificada |
| TST-064 | ✅ | log con --non-billable | COL | — | Entry billable=false |
| TST-065 | ✅ | log con duración 2h | COL | — | 120 minutos |
| TST-066 | ✅ | log con duración 90m | COL | — | 90 minutos |
| TST-067 | ✅ | log con duración 1h30m | COL | — | 90 minutos |

---

## 8. Entries CRUD — Show / List / Search

| ID | Tipo | Descripción | Caller | Resultado esperado |
|----|------|-------------|--------|--------------------|
| TST-068 | ✅ | show entry propia | COL | Detalle completo |
| TST-069 | ✅ | show entry de otro | MGR | Detalle completo |
| TST-070 | ❌ | show entry inexistente | Cualquiera | "Entry X not found." |
| TST-071 | ✅ | show entry con approval_status (workflow activo) | COL | Muestra Approval: pending |
| TST-072 | ✅ | show entry rechazada | COL | Muestra Approval: rejected + reason + approver |
| TST-073 | ✅ | list entries | COL | Solo entries propias |
| TST-074 | ✅ | list entries | MGR | Todas las entries |
| TST-075 | ✅ | list entries con --client filtro | MGR | Solo entries de ese client |
| TST-076 | ✅ | list entries con --date-from/--date-to | MGR | Entries en rango |
| TST-077 | ✅ | list entries (workflow activo) | MGR | Columna Status visible |
| TST-078 | ✅ | list entries (workflow inactivo) | MGR | Sin columna Status |
| TST-079 | ✅ | search por texto | COL | Results con FTS5, scope own |
| TST-080 | ✅ | search por texto | MGR | Results con FTS5, scope all |
| TST-081 | ✅ | search sin resultados | Cualquiera | "No entries matching 'X'" |
| TST-082 | ✅ | search por external-id | MGR | Match por external_id |

---

## 9. Entries CRUD — Edit

| ID | Tipo | Descripción | Caller | Precondiciones | Resultado esperado |
|----|------|-------------|--------|----------------|--------------------|
| TST-083 | ✅ | edit entry propia (pending) | COL | approval_required=true | Entry actualizada, sigue pending |
| TST-084 | ✅ | edit entry propia (rejected) | COL | approval_required=true, entry rejected | Warning: "Editing will reset approval status to pending." Entry → pending |
| TST-085 | ❌ | edit entry propia (approved) | COL | approval_required=true, entry approved | "Error: Cannot edit an approved entry." |
| TST-086 | ✅ | edit entry propia (approved, workflow off) | COL | approval_required=false | Edit exitoso (sin check de approval) |
| TST-087 | ❌ | edit entry de otro | COL | — | PermissionDenied: "Can only modify own entries." |
| TST-088 | ✅ | edit entry de otro | MGR | — | Edit exitoso |
| TST-089 | ❌ | edit entry con client inactivo | COL | Client del entry desactivado | "Error: Client is deactivated. Cannot edit entries." |
| TST-090 | ❌ | edit entry inexistente | Cualquiera | — | "Entry X not found." |
| TST-091 | ❌ | edit entry como timekeeper | TK | — | PermissionDenied: "Timekeepers cannot modify entries." |
| TST-092 | ✅ | edit entry de otro | APR | — | PermissionDenied: "Can only modify own entries." |
| TST-093 | ✅ | edit entry propia | APR | — | Edit exitoso |

---

## 10. Entries CRUD — Delete

| ID | Tipo | Descripción | Caller | Resultado esperado |
|----|------|-------------|--------|--------------------|
| TST-094 | ✅ | delete entry propia con --confirm | COL | Entry eliminada, entry_approvals CASCADE |
| TST-095 | ❌ | delete entry propia sin --confirm | COL | Mensaje de confirmación |
| TST-096 | ❌ | delete entry de otro | COL | PermissionDenied |
| TST-097 | ✅ | delete entry de otro | MGR | Entry eliminada |
| TST-098 | ❌ | delete entry | TK | PermissionDenied |
| TST-099 | ❌ | delete entry inexistente | Cualquiera | "Entry X not found." |

---

## 11. Approval — Pending

| ID | Tipo | Descripción | Caller | Precondiciones | Resultado esperado |
|----|------|-------------|--------|----------------|--------------------|
| TST-100 | ✅ | pending con entries pendientes | APR | approval_required=true, entries de otros | Lista de entries con IDs |
| TST-101 | ✅ | pending --for-user | APR | — | Entries pendientes de un user específico |
| TST-102 | ✅ | pending --project | APR | — | Entries pendientes de un proyecto |
| TST-103 | ✅ | pending --client | APR | — | Entries pendientes de un cliente |
| TST-104 | ✅ | pending --date-from/--date-to | APR | — | Entries pendientes en rango de fechas |
| TST-105 | ❌ | pending sin approval_required | APR | approval_required=false | "Approval workflow is not enabled..." |
| TST-106 | ❌ | pending | COL | approval_required=true | PermissionDenied |
| TST-107 | ✅ | pending | TK | approval_required=true | Lista (scope all) |
| TST-108 | ✅ | pending sin resultados | APR | approval_required=true, sin entries | "No pending entries found." |
| TST-109 | ✅ | pending excluye entries propias | APR | APR tiene entries propias y ajenas | Solo se muestran entries ajenas |

---

## 12. Approval — Approve

| ID | Tipo | Descripción | Caller | Precondiciones | Resultado esperado |
|----|------|-------------|--------|----------------|--------------------|
| TST-110 | ✅ | approve entry pending | APR | Entry pending, assigned scope | Entry → approved. "Entry #X approved." |
| TST-111 | ✅ | approve múltiples entries | APR | Entries pending | Todas approved |
| TST-112 | ✅ | approve por manager (cualquier scope) | MGR | Entry pending | Entry → approved |
| TST-113 | ✅ | manager auto-aprueba propia entry | MGR | Entry propia pending | Entry → approved |
| TST-114 | ❌ | approver auto-aprueba propia entry | APR | Entry propia pending | "Cannot approve your own entries." |
| TST-115 | ❌ | approve entry no asignada | APR | Entry de client/project no asignado | "Not assigned as approver for this client/project." |
| TST-116 | ❌ | approve entry ya approved | APR | Entry approved | "Entry X is already approved." |
| TST-117 | ❌ | approve entry rejected | APR | Entry rejected | "Entry X is rejected." |
| TST-118 | ❌ | approve sin approval_required | APR | approval_required=false | "Approval workflow is not enabled..." |
| TST-119 | ❌ | approve como collaborator | COL | — | PermissionDenied |
| TST-120 | ✅ | approve con partial failure (mix valid/invalid IDs) | APR | Algunas pendientes, algunas no | Pendientes approved, otras skipped con mensaje |

---

## 13. Approval — Reject

| ID | Tipo | Descripción | Caller | Precondiciones | Resultado esperado |
|----|------|-------------|--------|----------------|--------------------|
| TST-121 | ✅ | reject entry pending con reason | APR | Entry pending | Entry → rejected con reason |
| TST-122 | ✅ | reject entry approved con reason | APR | Entry approved | Entry → rejected con reason |
| TST-123 | ❌ | reject entry sin --reason | APR | Entry pending | Error: argument --reason required |
| TST-124 | ❌ | reject entry rejected | APR | Entry rejected | "Entry X is rejected." |
| TST-125 | ✅ | reject por manager | MGR | Entry pending | Entry → rejected |
| TST-126 | ❌ | reject sin approval_required | APR | approval_required=false | "Approval workflow is not enabled..." |
| TST-127 | ✅ | reject múltiples entries | APR | Entries pending | Todas rejected |

---

## 14. Approval — Rejections / History

| ID | Tipo | Descripción | Caller | Resultado esperado |
|----|------|-------------|--------|--------------------|
| TST-128 | ✅ | rejections con entries rechazadas | COL | Lista entries rechazadas con reason y approver |
| TST-129 | ✅ | rejections sin entries rechazadas | COL | "No rejected entries." |
| TST-130 | ✅ | approval-history entry con history | Cualquiera | Timeline de aprobaciones/rechazos |
| TST-131 | ✅ | approval-history entry sin history | Cualquiera | "No approval history." |
| TST-132 | ❌ | approval-history entry inexistente | Cualquiera | "Entry X not found." |

---

## 15. Approval — Ciclo completo

| ID | Tipo | Descripción | Resultado esperado |
|----|------|-------------|--------------------|
| TST-133 | ✅ | Ciclo: log → pending → approve → approved | Entry termina approved |
| TST-134 | ✅ | Ciclo: log → pending → reject → rejected → edit → pending → approve | Entry rechazada, editada, re-aprobada |
| TST-135 | ✅ | Ciclo: log → pending → approve → reject → rejected → edit → pending | Entry aprobada, rechazada después, editada, vuelve a pending |
| TST-136 | ❌ | Editar entry approved (sin reject previo) | "Cannot edit an approved entry." |
| TST-137 | ✅ | Rechazar entry approved → editar → pending | Flujo completo de corrección post-aprobación |

---

## 16. Client deactivation — cascada

| ID | Tipo | Descripción | Precondiciones | Resultado esperado |
|----|------|-------------|----------------|--------------------|
| TST-138 | ❌ | Log a client desactivado | Client inactivo | "Client is deactivated." |
| TST-139 | ❌ | Log a project de client desactivado | Client inactivo | "Client is deactivated." |
| TST-140 | ❌ | Edit entry de client desactivado | Client del entry inactivo | "Client is deactivated. Cannot edit entries." |
| TST-141 | ❌ | Crear project en client desactivado | Client inactivo | "Client is deactivated. Cannot add projects." |
| TST-142 | ✅ | Reactivar client → log funciona | Client reactivado | Entry creada |

---

## 17. Project deactivation — cascada

| ID | Tipo | Descripción | Precondiciones | Resultado esperado |
|----|------|-------------|----------------|--------------------|
| TST-143 | ❌ | Log a project desactivado | Project inactivo | "Project is deactivated." |
| TST-144 | ✅ | Reactivar project → log funciona | Project reactivado, client activo | Entry creada |
| TST-145 | ❌ | Desactivar project con client inactivo | Client inactivo | "Client is deactivated. Reactivate client first." |

---

## 18. Settings

| ID | Tipo | Descripción | Caller | Resultado esperado |
|----|------|-------------|--------|--------------------|
| TST-146 | ✅ | settings (listar) | Cualquiera | Todas las settings |
| TST-147 | ✅ | setting-get | Cualquiera | Valor de la setting |
| TST-148 | ✅ | setting-set default_rate | MGR | Rate actualizado |
| TST-149 | ✅ | setting-set approval_required true | MGR | Workflow activado |
| TST-150 | ✅ | setting-set approval_required false | MGR | Workflow desactivado |
| TST-151 | ❌ | setting-set | COL | PermissionDenied |

---

## 19. Categories

| ID | Tipo | Descripción | Caller | Resultado esperado |
|----|------|-------------|--------|--------------------|
| TST-152 | ✅ | categories (listar) | Cualquiera | 12 categorías pre-seeded |
| TST-153 | ✅ | category-add | MGR | Nueva categoría |
| TST-154 | ❌ | category-add duplicada | MGR | Error UNIQUE constraint |
| TST-155 | ✅ | category-remove | MGR | Categoría desactivada |
| TST-156 | ❌ | category-add | COL | PermissionDenied |
| TST-157 | ❌ | category-remove | COL | PermissionDenied |

---

## 20. Reporting

| ID | Tipo | Descripción | Caller | Resultado esperado |
|----|------|-------------|--------|--------------------|
| TST-158 | ✅ | summary own | COL | Resumen de entries propias |
| TST-159 | ✅ | summary --team | MGR | Resumen de todos |
| TST-160 | ❌ | summary --team | COL | Error: team no disponible |
| TST-161 | ✅ | summary --team | APR | Resumen de todos |
| TST-162 | ✅ | summary --round-up | MGR | Duraciones redondeadas |
| TST-163 | ✅ | stats | MGR | Stats de todos |
| TST-164 | ✅ | stats | COL | Stats propias |

---

## 21. Export

| ID | Tipo | Descripción | Caller | Resultado esperado |
|----|------|-------------|--------|--------------------|
| TST-165 | ✅ | export json | MGR | Archivo JSON con entries |
| TST-166 | ✅ | export csv | MGR | Archivo CSV con entries |
| TST-167 | ✅ | export json | COL | JSON con entries propias |
| TST-168 | ✅ | export con filtros | MGR | JSON filtrado por client/project/fechas |
| TST-169 | ✅ | export sin entries | Cualquiera | "No entries to export." |

---

## 22. Rate Cascade

| ID | Tipo | Descripción | Precondiciones | Resultado esperado |
|----|------|-------------|----------------|--------------------|
| TST-170 | ✅ | Rate desde project | Project tiene rate | Entry usa project rate |
| TST-171 | ✅ | Rate desde client (sin project rate) | Project sin rate, client con rate | Entry usa client rate |
| TST-172 | ✅ | Rate default (sin project ni client rate) | Ninguno tiene rate | Entry usa default_rate setting |
| TST-173 | ✅ | Rate override manual | --rate pasado | Entry usa rate manual |

---

## 23. Single-user mode

| ID | Tipo | Descripción | Resultado esperado |
|----|------|-------------|--------------------|
| TST-174 | ✅ | log sin --user, sin users en DB | Entry creada sin user_id |
| TST-175 | ✅ | list sin --user | Todas las entries |
| TST-176 | ✅ | show sin --user | Detalle completo |
| TST-177 | ✅ | Timer: start → status → stop | Entry creada desde timer |
| TST-178 | ✅ | Timer: start → cancel | No entry creada |
| TST-179 | ❌ | Timer: stop sin timer activo | "No active timer." |
| TST-180 | ❌ | Timer: cancel sin timer activo | "No active timer." |
| TST-181 | ✅ | Timer: start con timer activo | "Timer already running" |

---

## 24. Multi-user mode — Timer deprecation

| ID | Tipo | Descripción | Precondiciones | Resultado esperado |
|----|------|-------------|----------------|--------------------|
| TST-182 | ✅ | start en multi-user | Users existen | Warning + no-op |
| TST-183 | ✅ | stop en multi-user | Users existen | Warning + no-op |
| TST-184 | ✅ | status en multi-user | Users existen | Warning + no-op |
| TST-185 | ✅ | cancel en multi-user | Users existen | Warning + no-op |

---

## 25. Duration parsing

| ID | Tipo | Input | Resultado esperado |
|----|------|-------|--------------------|
| TST-186 | ✅ | `2h` | 120 minutos |
| TST-187 | ✅ | `90m` | 90 minutos |
| TST-188 | ✅ | `1h30m` | 90 minutos |
| TST-189 | ✅ | `1.5` | 90 minutos |
| TST-190 | ✅ | `30m` | 30 minutos |

---

## Resumen

| Dominio | Casos | Válidos | Inválidos |
|---------|-------|---------|-----------|
| Bootstrap | 5 | 3 | 2 |
| Users CRUD | 10 | 5 | 5 |
| Roles | 8 | 6 | 2 |
| Clients CRUD | 11 | 6 | 5 |
| Projects CRUD | 11 | 6 | 5 |
| Assignments | 6 | 5 | 1 |
| Log | 16 | 11 | 5 |
| Show/List/Search | 15 | 13 | 2 |
| Edit | 11 | 5 | 6 |
| Delete | 6 | 2 | 4 |
| Pending | 10 | 7 | 3 |
| Approve | 11 | 5 | 6 |
| Reject | 7 | 4 | 3 |
| Rejections/History | 5 | 4 | 1 |
| Ciclo approval | 5 | 4 | 1 |
| Client deactivation | 5 | 1 | 4 |
| Project deactivation | 3 | 1 | 2 |
| Settings | 6 | 5 | 1 |
| Categories | 6 | 3 | 3 |
| Reporting | 7 | 6 | 1 |
| Export | 5 | 5 | 0 |
| Rate cascade | 4 | 4 | 0 |
| Single-user | 8 | 7 | 1 |
| Timer deprecation | 4 | 4 | 0 |
| Duration parsing | 5 | 5 | 0 |
| **Total** | **190** | **123** | **67** |
