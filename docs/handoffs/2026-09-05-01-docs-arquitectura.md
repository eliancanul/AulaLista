# HANDOFF 01 — Docs y Arquitectura
Fecha: 2026-09-05 | Rama: updated-tech | Agente: docs-arquitectura

## 1. Objetivo del sistema (3 líneas)
Nodo educativo local offline-first para ejecutar actividades en aula con sesiones temporales.
Contenido gobernado por personas: borrador → revisión humana → snapshot inmutable → sesión fijada a esa versión.
Demo inicial solo con `DemoPackage` sintético; prohibido afirmar validación pedagógica.

## 2. Contratos inviolables
- **Autoridad humana:** solo `EditorialReviewer` humano aprueba/publica (`CONTEXT.md:41-44`, `docs/adr/0002*`, `DESIGN.md:9`). Solo maestra activa `ClassroomSession` con confirmación explícita (`CONTEXT.md:93`, `docs/teacher-flow.md:47-60`). IA solo propone.
- **Snapshots inmutables:** sesión lee `PublishedPackageSnapshot` (SHA256), no objeto vivo (`CONTEXT.md:38,90-94`, `docs/adr/0001*`). Con roadmap: fija `PublishedRoadmapSnapshot` + `package_snapshot_id` por actividad (`CONTEXT.md:63-77`).
- **Determinismo:** misma respuesta + mismas reglas = mismo resultado. Ayuda no cambia score (`CONTEXT.md:112-119`, `docs/adr/0003*`).
- **Privacidad:** sin nombres/correo/matrícula/UUID en superficies aula. `StudentTurn.participant_key` = UUID aleatorio (`CONTEXT.md:104`). Control privado vs proyección pública (`docs/adr/0005*`). Al cerrar: borrar turnos/apodos, conservar solo `PseudonymousResult` + promedio encuesta (`CONTEXT.md:122-127`).
- **Institucional:** `School` conserva ámbito; `Director` decide adscripciones, `PlatformAdministrator` cuentas/roles (`CONTEXT.md:7-25`, `docs/adr/0008*`).

## 3. Mapa archivo → qué define
- `CONTEXT.md`: glosario canónico + Avoid por término, propiedad por cuenta creadora.
- `DESIGN.md`: contrato visual C-aula directa, tokens CSS, PrimaryAction única, estados empty/loading/ready/error.
- `AGENTS.md`: entrada mínima, issues vía `gh`, 5 labels triage.
- `docs/DATABASE.md`: verdad operativa modelo, máquinas `CurriculumImportJob.status`, formas JSON, retención #86.
- `docs/implementation-current.md`: foto MVP 2026-08-22 (main@d4fcb99), stack Django/Wagtail/SQLite.
- `docs/installation.md`: instalación reproducible, SQLite WAL, `AULALISTA_LAN_URL`.
- `docs/teacher-flow.md`: máquina Tema→Borrador→Revisión→Publicada→Preparada→Activa→Cerrada.
- `docs/agents/domain.md`, `issue-tracker.md`, `triage-labels.md`: cómo consumir contexto.
- `docs/adr/0001` a `0008`: snapshots, revisión humana, práctica determinista, baseline local, privacidad, progreso humano, roadmap grupal, scope institucional.

## 4. Contradicciones / desactualizados
1. Duplicado `0007-group-roadmap-progress-per-session.md` y `0007-pseudonymous-results-and-classroom-retention.md` — renumerar segundo a 0009.
2. `implementation-current.md:12` dice "no usa LLM" vs `DATABASE.md` + `curriculum/prompts/` + Ollama — desactualizado.
3. Vida `StudentRoadmapProgress`: `CONTEXT.md:69` dice se elimina al cerrar vs `DATABASE.md:16` que persiste desvinculado — aclarar.
4. Quién crea: `implementation-current.md:32` EditorialReviewer crea vs `CONTEXT.md:53-57` maestra crea — definir creador vs aprobador.
5. Estados roadmap: `DESIGN.md:72-78` visto/actual/disponible/bloqueado/completado vs `teacher-flow.md:108-116` ACTUAL/DISPONIBLE/COMPLETADA/BLOQUEADA — unificar.
6. `teacher-flow.md:127` "No prescribe modelo DB" obsoleto frente a DATABASE.md.
7. Conteo 238 pruebas / fecha 22-ago verificar vigencia.

## 5. Top 3 riesgos desde docs
1. Concurrencia SQLite single-process: WAL + LocMemCache + 1 WSGI; 30 escritores → `database table is locked`.
2. Joins por título + JSON jerárquico: frágil a renombres/duplicados, deuda explícita.
3. Fuga identidad/autoridad por omisión: superficie pública sin login, sesiones históricas sin propietaria, migraciones manuales con choque 0020.

## 6. Verificar por siguiente agente código
- Snapshots inmutables SHA256, sesión congela ambos.
- `CurriculumProgress` solo POST docente `/tutor/roadmaps/`.
- Cierre borra Turn/Assignment/apodos, conserva PseudonymousResult sin FK identidad.
- Control auth vs proyección sin login, no-cache, POST+CSRF.
- LAN solo desde `AULALISTA_LAN_URL`, sin autodetección IP, sin CDN/WAN.
- Tests `test_t24_database_contracts.py`, `AULALISTA_IMPORT_ASYNC=False` vs transaction=True.
