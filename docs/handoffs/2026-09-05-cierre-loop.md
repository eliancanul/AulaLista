# HANDOFF cierre-loop — updated-tech 2h F1-F8
Fecha: 2026-09-05 | Rama: updated-tech (82d4a9d, up to date origin/main) | Agente: loop-2h
Base: 01-docs-arquitectura, 02-codigo-curriculum, 03-investigacion-evidencia, 04-techdebt-tests. Sin implementación de fixes.

## F1 inventario docs — vigencia confirmada
- Contratos inviolables vigentes: solo EditorialReviewer humano publica, solo maestra activa ClassroomSession, IA solo propone; sesiones leen PublishedPackageSnapshot SHA256 inmutable; DemoPackage sintético cero claims (CONTEXT.md, adr/0001,0002).
- Contradicciones abiertas (no tocadas): ADR 0007 duplicado (`0007-group-roadmap*` + `0007-pseudonymous*`); `implementation-current.md:12` "no usa LLM" vs DATABASE.md + `curriculum/prompts/` + Ollama; `DESIGN.md:72-78` visto/actual/disponible/bloqueado/completado vs `teacher-flow.md:108-116` ACTUAL/DISPONIBLE/COMPLETADA/BLOQUEADA; `teacher-flow.md:127` "No prescribe modelo DB" obsoleto; `StudentRoadmapProgress` CONTEXT:69 elimina vs DATABASE:16 persiste.
- `docs/DATABASE.md` es verdad operativa (máquinas CurriculumImportJob.status, formas JSON, trampa worker traga-excepción, deuda join por titulo §Deuda-1). Si discrepa con código, abrir issue.

## F2 auditoría código — núcleo vigente hoy
- `curriculum/views.py:3504` + `curriculum/models.py:1998` god-files. Total 6681 líneas en 6 py.
- Join frágil intacto: `views.py:2875-2876` (`topic_title==titulo and subtopic_title==titulo`) y `2959-2960` idem. `curriculum/schemas/` no existe → #54 pendiente.
- `_result_aggregate:1371-1585` ~214 líneas monolítica; cursor actual duplicado 7x (`3045,3121,3143,3180,3318,3357,3418`); N+1 `models.py:1125-1127` `objects.get(pk)` en dict-comprehension dentro de `close()`; índice posicional POST `views.py:2996` vs `_activity_id() 2826-2829` no usado.
- Seguridad: `settings.py:7-8` SECRET_KEY hardcodeada + DEBUG=True, ALLOWED_HOSTS=`*`, LocMemCache un proceso, SQLite WAL timeout 5. No tocar en prod sin ADR.

## F3 tests — matriz
- 41 ficheros test_*.py, `requirements.txt` solo Django/Wagtail/pypdf/segno → sin pytest declarado, `python3 -m pytest` falla aquí. `pytest.ini` solo settings + python_files.
- t24 solo-en-test (TOPIC/ACTIVITY/TRACE keys, worker failure) → lo que #54 quiere llevar a runtime. t15 staging/chunk/consolidate/#33, t16 propose ES→EN + is_valid + convert sin publicaciones. Migraciones 0001-0029 lineales, sin duplicados hoy.

## F5 evidencia — gaps intactos
- T12 `false` 2 teléfonos; T13 checklist vacío; `evidence/demo-viernes/` inexistente (promesa `demo-prototipo.md:106` rota); 3 prototipos `visual-a|b|c/` sin decisión (`docs/prototypes/` solo visual-c.md); doble raíz `health/templates/` vs `templates/`; prompts `propose_activities` vs `incremental` duplican 80% schema; `static/health/*` grep http/cdn=0 ok offline en esa capa.

## F4 fusión #53+#98+#54 — un solo ADR (cambio arquitectónico #1)
- #47 CLOSED (verificado `gh issue view 47`): desbloquea #53 del lado consolidación. Queda bloqueo demo-viernes como decisión humana, no técnica.
- #53 (Topic/Subtopic/ActivityProposal, plan doble-escritura→backfill→lectura) + #98 (único bug+ready-for-agent: idempotencia, dedup por clave documentada, conservar fuentes/estado/decisiones, ambiguos a humana, tests reintento/parcial/dos-títulos-iguales) + #54 (schemas `curriculum/schemas/*.json` + validación signal/full_clean) tocan el mismo código (`_import_action_*`, `_grouped_activities`, remove/topup, `job.topics/activities`). Hacer uno sin otro = retrabajo: #98 sobre JSON es parche sobre join que #53 elimina; #53 sin clave #98 migra duplicados; #54 sin #53 valida forma que va a cambiar.
- Decisión: un solo ADR `0009-staging-relacional-idempotente` (tras renumerar segundo 0007 → 0009 actual a 0010, o 0009+0010 según orden). Contenido ADR: modelo FK + `id_estable`/`content_hash` como clave idempotencia + reglas dedup + qué es ambiguo→humana + schemas versionados + estrategia migración datos + matriz tests t15/t16/t19/t20/t22/t24 verdes.
- Prerrequisito: #57 anti-colisión (`makemigrations --check` pre-PR, convención renumerar al rebasar; antecedente 0020 #37 vs #38) antes de cualquier migración #53+#98. #55/#56/#65 periféricos al final. #58 épica desactualizada: actualizar orden tras ADR único.

## F7 ranking recomendaciones (para otros agentes)
1. ADR único #53+#98+#54 + migración staging relacional idempotente — cuello real, hacerlo primero.
2. Extraer `services/results.py` (`_result_aggregate`) + `services/roadmap_cursor.py` (7x cursor) + fix N+1 `close()` con `in_bulk` — vistas <30 líneas, tests sin RequestFactory.
3. Renumerar ADR 0007 duplicado + unificar estados roadmap (DESIGN vs teacher-flow) + aclarar retención StudentRoadmapProgress + quién crea (maestra) vs aprueba (EditorialReviewer) + marcar `implementation-current.md` desactualizado (LLM sí).
4. Unificar templates a una raíz + decidir visual A/B/C (archivar perdedores) + crear/borrar `evidence/demo-viernes/` + dedup prompts con `_activity_schema.md` + cabecera SINTÉTICO.
5. Seguridad/ops: SECRET_KEY/DEBUG/ALLOWED_HOSTS + LocMemCache→multiproceso + documentar límite 30 escritores (locked); solo docs, no cambio prod sin humana.
6. Declarar pytest/pytest-django en requirements (o docs de env) + elevar t24 a runtime validation (dentro de #54).
7. #57 tooling pre-PR antes de migrar. No tocar #55 streaming (polling #36 cubre), #56 landing, #65 half-life (fuera MVP).

## F8 ticket siguiente ready-for-agent (draft, no creado)
Título: `ADR 0009: staging relacional idempotente (fusión #53+#98+#54) + spec migración`
Labels: `tech-debt, ready-for-agent`
Cuerpo:
- Contexto: join por `subtopic_title==titulo` (views.py:2875-2876,2959-2960), `curriculum/schemas/` inexistente, #47 closed, migraciones 0001-0029 lineales.
- Entregables solo-docs: `docs/adr/0009-staging-relacional-idempotente.md` (modelo Topic/Subtopic/ActivityProposal, clave idempotencia, reglas dedup, ambiguos→humana, schemas versionados, plan doble-escritura→backfill→lectura, matriz tests), renumerar segundo 0007→0010, actualizar #58 orden, spec `services/results.py` + `roadmap_cursor.py` (sin código).
- Aceptación: spec cita líneas exactas, no rompe contratos inviolables, tests t15/t16/t19/t20/t22/t24 mapeados, #57 como prerrequisito explícito, sin merge a main (rama updated-tech).
- Comando creación: `gh issue create --title "ADR 0009: staging relacional idempotente (fusión #53+#98+#54) + spec migración" --label tech-debt,ready-for-agent --body-file /tmp/adr0009.md`
- Alternativa si humana prefiere: reabrir #53 y editar para absorber #98+#54 en vez de issue nuevo.

## Estado git / pendientes
- `git status --short`: `?? .DS_Store, ?? docs/.DS_Store, ?? docs/handoffs/` (este archivo incluido). No commitear sin decisión humana; no merge a main.
- Opencode 200k (`~/.config/opencode/opencode.jsonc`) ya validado con `debug config`; requiere restart — pendiente humano.
- Siguiente agente: partir del ADR draft arriba, verificar `ls curriculum/schemas/`, `rg subtopic_title`, `cat docs/DATABASE.md`, `gh issue view 53/54/98/57`.
