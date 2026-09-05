# HANDOFF loop-implementación — updated-tech
Fecha: 2026-09-05 | Rama: updated-tech | Base: 82d4a9d | Sin merge a main.

## Qué se implementó (todo verificado)
- **Fase A docs:** `0007-pseudonymous*` → `docs/adr/0009-*` (header + nota
  renumerado, sin cambio de decisión). `implementation-current.md`: aclara que
  el LLM local (Ollama) solo propone staging + creador=maestra/aprobador=
  EditorialReviewer + verificación con `requirements-dev` y `check_migrations`.
  `teacher-flow.md`: mapea estados runtime MAYÚSCULAS ↔ DESIGN minúsculas
  (+`visto` manual) y apunta el modelo a `docs/DATABASE.md`.
- **Fase B #57:** `scripts/check_migrations.py` (duplicados + orden lineal;
  antecedente 0020) OK. `docs/DATABASE.md`: pytest vive en
  `requirements-dev.txt`, convención pre-PR. (pytest ya estaba en dev;
  no se tocó el runtime.)
- **Fase C refactor:** `curriculum/services/roadmap_cursor.py`
  (`current_activity_id`, 7/7 call sites en views, `rg` confirma 0 dups).
  `curriculum/services/results.py` (545 líneas: validación, catálogo,
  agregado, registro, navegación; views 3504→2979, re-exporta 14 nombres —
  `test_t100` sigue importando de views). `ClassroomSession.close()`:
  N+1 `objects.get` → 1× `in_bulk` con fail-closed si falta snapshot.
- **Fase D #54/#98 (paso 1) + ADR-0010:** `curriculum/schemas/v1/`
  (topics/activities/llm_trace + README versionado),
  `curriculum/staging_validation.py` (validadores puros + `content_hash`
  SHA256 normalizado + `find_duplicate_groups` exact/ambiguo sin fusionar),
  `CurriculumImportJob.clean()` (solo payloads no vacíos; `save()` intacto),
  `tests/test_t54_staging_contracts.py` (5 tests), `docs/adr/0010-*`
  (diseño fusión #53+#98+#54; tablas relacionales = migración futura).
- **Fase E:** `health/templates/health/local_access.html` →
  `templates/health/` (raíz única; mismo nombre, sin cambio de conducta).
  `settings.py`: `SECRET_KEY`/`DEBUG` por env con mismos defaults locales +
  aviso deploy.

## Verificación
- `/tmp/al-venv` (3.13, requirements + pytest + zxing): **305 passed
  en 12.26s** (suite completa). `manage.py check` OK, `migrate --check`
  sin salida pendiente, `check_migrations` OK, `py_compile`/AST OK,
  validación pura de staging OK, schemas JSON parse OK.
- No se tocaron: #55/#56/#65, prototipos A/B/C, `evidence/demo-viernes/`,
  migración de datos #53 (solo diseño en ADR-0010).

## Pendiente / siguiente
- Revisar este diff en `updated-tech` (no commiteado, no merge): 7 modificados
  + nuevos `services/`, `schemas/`, `staging_validation.py`, `check_migrations.py`,
  `test_t54`, `adr/0010`, este handoff.
- Siguiente agente: migración relacional del ADR-0010 (doble escritura →
  backfill con reporte de ambiguos → lectura nueva), con #57 pre-PR y
  `docs/DATABASE.md` en el mismo PR. Opcional: mover `_activity_snapshot`
  a `services/roadmap_store.py::resolve_activity_snapshot()` con `in_bulk`.
